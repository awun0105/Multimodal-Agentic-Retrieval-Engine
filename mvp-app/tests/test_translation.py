from unittest.mock import MagicMock, patch

import pytest
import torch

from translation import (
    DEFAULT_TRANSLATION_MODEL,
    DEFAULT_TRANSLATION_REVISION,
    SOURCE_LANGUAGE,
    TARGET_LANGUAGE,
    QueryTranslator,
)


def test_english_query_passes_through_without_loading_model(monkeypatch):
    translator = QueryTranslator()
    monkeypatch.setattr(translator, "detect_language", lambda _query: "english")
    prepared = translator.prepare("  a   red car  ")
    assert prepared.clip_query == "a red car"
    assert not prepared.translated
    assert prepared.translation_enabled
    assert translator._model is None


def test_legacy_language_detector_is_also_lazy():
    with patch("translation.langid.set_languages") as set_languages, patch(
        "translation.langid.classify", return_value=("vi", 1.0)
    ) as classify:
        translator = QueryTranslator()
        set_languages.assert_not_called()
        assert translator.detect_language("một con chim") == "vietnamese"
        assert translator.detect_language("một con chó") == "vietnamese"

    set_languages.assert_called_once_with(["en", "vi"])
    assert classify.call_count == 2


def test_translation_can_be_disabled_without_detection_or_model_loading(monkeypatch):
    translator = QueryTranslator()
    detect_language = MagicMock(side_effect=AssertionError("language detection should be skipped"))
    translate = MagicMock(side_effect=AssertionError("translation should be skipped"))
    monkeypatch.setattr(translator, "detect_language", detect_language)
    monkeypatch.setattr(translator, "translate", translate)

    prepared = translator.prepare("  con   chó  ", translate_vietnamese=False)

    assert prepared.original_query == "con chó"
    assert prepared.clip_query == "con chó"
    assert prepared.detected_language == "not_checked"
    assert not prepared.translation_enabled
    assert not prepared.translated
    assert translator._model is None
    detect_language.assert_not_called()
    translate.assert_not_called()


def test_vietnamese_query_is_translated(monkeypatch):
    translator = QueryTranslator()
    monkeypatch.setattr(translator, "detect_language", lambda _query: "vietnamese")
    monkeypatch.setattr(translator, "translate", lambda _query: "a red car")
    prepared = translator.prepare("một chiếc xe màu đỏ")
    assert prepared.clip_query == "a red car"
    assert prepared.translated
    assert prepared.translation_enabled
    assert prepared.detected_language == "vietnamese"


def test_enabled_checkbox_forces_translation_for_short_vietnamese_query(monkeypatch):
    translator = QueryTranslator()
    detect_language = MagicMock(return_value="english")
    translate = MagicMock(return_value="bird")
    monkeypatch.setattr(translator, "detect_language", detect_language)
    monkeypatch.setattr(translator, "translate", translate)

    prepared = translator.prepare("con chim", translate_vietnamese=True)

    assert prepared.original_query == "con chim"
    assert prepared.clip_query == "bird"
    assert prepared.detected_language == "vietnamese"
    assert prepared.translated
    assert prepared.translation_enabled
    detect_language.assert_not_called()
    translate.assert_called_once_with("con chim")


def test_translation_failure_keeps_original_query(monkeypatch):
    translator = QueryTranslator()

    def fail(_query):
        raise RuntimeError("offline")

    monkeypatch.setattr(translator, "translate", fail)
    prepared = translator.prepare("xin chao", requested_language="vietnamese")
    assert prepared.clip_query == "xin chao"
    assert not prepared.translated
    assert prepared.translation_enabled
    assert "offline" in prepared.warning


def test_legacy_english_mode_disables_translation(monkeypatch):
    translator = QueryTranslator()
    detect_language = MagicMock(side_effect=AssertionError("language detection should be skipped"))
    monkeypatch.setattr(translator, "detect_language", detect_language)

    prepared = translator.prepare("con chó", requested_language="english")

    assert prepared.clip_query == "con chó"
    assert not prepared.translation_enabled
    detect_language.assert_not_called()


def test_translation_result_is_cached():
    translator = QueryTranslator(cache_size=2, device="cpu")
    tokenizer = MagicMock()
    tokenized = MagicMock()
    tokenized.to.return_value = {"input_ids": MagicMock()}
    tokenizer.return_value = tokenized
    tokenizer.convert_tokens_to_ids.return_value = 256047
    tokenizer.batch_decode.return_value = ["a person"]
    model = MagicMock()
    model.generate.return_value = MagicMock()
    translator._tokenizer = tokenizer
    translator._model = model
    assert translator.translate("một người") == "a person"
    assert translator.translate("một người") == "a person"
    tokenized.to.assert_called_once_with("cpu")
    tokenizer.convert_tokens_to_ids.assert_called_once_with(TARGET_LANGUAGE)
    model.generate.assert_called_once_with(
        input_ids=tokenized.to.return_value["input_ids"],
        forced_bos_token_id=256047,
        max_length=128,
        num_beams=4,
    )


@pytest.mark.parametrize(
    ("device", "dtype"),
    [("cpu", torch.float32), ("cuda", torch.float16)],
)
def test_nllb_load_is_lazy_and_uses_device_precision(device, dtype):
    translator = QueryTranslator(device=device)
    assert not translator.is_loaded

    with (
        patch("translation.AutoTokenizer") as tokenizer_class,
        patch("translation.AutoModelForSeq2SeqLM") as model_class,
    ):
        model = model_class.from_pretrained.return_value
        loaded_model = model.to.return_value
        translator._ensure_loaded()

    tokenizer_class.from_pretrained.assert_called_once_with(
        DEFAULT_TRANSLATION_MODEL,
        revision=DEFAULT_TRANSLATION_REVISION,
        src_lang=SOURCE_LANGUAGE,
    )
    model_class.from_pretrained.assert_called_once_with(
        DEFAULT_TRANSLATION_MODEL,
        revision=DEFAULT_TRANSLATION_REVISION,
        dtype=dtype,
    )
    model.to.assert_called_once_with(device)
    loaded_model.eval.assert_called_once_with()
    assert translator.is_loaded
