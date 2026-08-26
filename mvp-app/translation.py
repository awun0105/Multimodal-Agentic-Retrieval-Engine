"""Local Vietnamese-to-English query preparation."""

from __future__ import annotations

import gc
import logging
from collections import OrderedDict
from threading import Lock
from typing import Any

import langid
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from schemas import PreparedQuery

logger = logging.getLogger(__name__)

DEFAULT_TRANSLATION_MODEL = "facebook/nllb-200-distilled-600M"
DEFAULT_TRANSLATION_REVISION = "f8d333a098d19b4fd9a8b18f94170487ad3f821d"
SOURCE_LANGUAGE = "vie_Latn"
TARGET_LANGUAGE = "eng_Latn"
SUPPORTED_LANGUAGES = {"auto", "english", "vietnamese"}


class QueryTranslator:
    """Detect query language and translate Vietnamese locally when needed."""

    def __init__(
        self,
        model_id: str = DEFAULT_TRANSLATION_MODEL,
        revision: str = DEFAULT_TRANSLATION_REVISION,
        cache_size: int = 256,
        device: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.cache_size = max(1, int(cache_size))
        self._device = device
        self._allow_cpu_fallback = device is None
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._load_lock = Lock()
        self._language_load_lock = Lock()
        self._language_detector_ready = False
        self._cache_lock = Lock()
        self._cache: OrderedDict[str, str] = OrderedDict()

    @property
    def device(self) -> str:
        return self._device or ("cuda" if torch.cuda.is_available() else "cpu")

    @property
    def dtype(self) -> torch.dtype:
        return torch.float16 if self.device == "cuda" else torch.float32

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @staticmethod
    def normalize_query(query: str) -> str:
        normalized = " ".join(str(query).split())
        if not normalized:
            raise ValueError("Query text cannot be empty")
        return normalized

    def detect_language(self, query: str) -> str:
        if not self._language_detector_ready:
            with self._language_load_lock:
                if not self._language_detector_ready:
                    langid.set_languages(["en", "vi"])
                    self._language_detector_ready = True
        language, _score = langid.classify(query)
        return "vietnamese" if language == "vi" else "english"

    def prepare(
        self,
        query: str,
        requested_language: str = "auto",
        *,
        translate_vietnamese: bool | None = None,
    ) -> PreparedQuery:
        normalized = self.normalize_query(query)
        requested = str(requested_language or "auto").strip().lower()
        if requested not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported query language: {requested_language}")

        explicit_translation_choice = translate_vietnamese is not None
        translation_enabled = (
            requested != "english"
            if not explicit_translation_choice
            else bool(translate_vietnamese)
        )
        if not translation_enabled:
            return PreparedQuery(
                normalized,
                normalized,
                requested,
                "not_checked",
                translation_enabled=False,
            )

        # The current UI checkbox is an explicit instruction. When it is on,
        # always run the vi-en model instead of trusting language detection;
        # short Vietnamese queries such as "con chim" are often classified as
        # English by langid. Legacy language modes retain their existing auto,
        # English, and Vietnamese behavior.
        detected = (
            "vietnamese"
            if explicit_translation_choice
            else self.detect_language(normalized)
            if requested == "auto"
            else requested
        )
        if detected == "english":
            return PreparedQuery(
                normalized,
                normalized,
                requested,
                detected,
                translation_enabled=True,
            )

        try:
            translated = self.translate(normalized)
        except Exception as exc:
            logger.exception("Vietnamese query translation failed")
            return PreparedQuery(
                normalized,
                normalized,
                requested,
                detected,
                warning=f"Translation unavailable: {exc}",
                translation_enabled=True,
            )
        return PreparedQuery(
            normalized,
            translated,
            requested,
            detected,
            translated=True,
            translation_enabled=True,
        )

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                revision=self.revision,
                src_lang=SOURCE_LANGUAGE,
            )
            try:
                self._model = self._load_model()
            except torch.OutOfMemoryError:
                if not self._allow_cpu_fallback or self.device != "cuda":
                    raise
                logger.warning("Not enough CUDA memory for NLLB; retrying on CPU")
            else:
                return

            self._device = "cpu"
            gc.collect()
            torch.cuda.empty_cache()
            self._model = self._load_model()

    def _load_model(self) -> Any:
        logger.info(
            "Loading NLLB translation model %s on %s with %s",
            self.model_id,
            self.device,
            self.dtype,
        )
        model = AutoModelForSeq2SeqLM.from_pretrained(
            self.model_id,
            revision=self.revision,
            dtype=self.dtype,
        ).to(self.device)
        model.eval()
        return model

    def _move_model_to_cpu(self) -> None:
        with self._load_lock:
            if self._model is None or self.device != "cuda":
                return
            logger.warning("CUDA ran out of memory during translation; switching NLLB to CPU")
            self._model.to("cpu")
            self._model.float()
            self._model.eval()
            self._device = "cpu"
            gc.collect()
            torch.cuda.empty_cache()

    def _translate_uncached(self, query: str) -> str:
        assert self._tokenizer is not None and self._model is not None
        inputs = self._tokenizer(
            query,
            return_tensors="pt",
            truncation=True,
            max_length=128,
        ).to(self.device)
        target_language_token_id = self._tokenizer.convert_tokens_to_ids(TARGET_LANGUAGE)
        output = self._model.generate(
            **inputs,
            forced_bos_token_id=target_language_token_id,
            max_length=128,
            num_beams=4,
        )
        translated = self._tokenizer.batch_decode(output, skip_special_tokens=True)[0].strip()
        if not translated:
            raise ValueError("Translation model returned an empty query")
        return translated

    @torch.no_grad()
    def translate(self, query: str) -> str:
        with self._cache_lock:
            cached = self._cache.get(query)
            if cached is not None:
                self._cache.move_to_end(query)
                return cached

        self._ensure_loaded()
        assert self._tokenizer is not None and self._model is not None
        try:
            translated = self._translate_uncached(query)
        except torch.OutOfMemoryError:
            if not self._allow_cpu_fallback or self.device != "cuda":
                raise
        else:
            return self._cache_translation(query, translated)

        self._move_model_to_cpu()
        translated = self._translate_uncached(query)
        return self._cache_translation(query, translated)

    def _cache_translation(self, query: str, translated: str) -> str:
        with self._cache_lock:
            self._cache[query] = translated
            self._cache.move_to_end(query)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return translated
