from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from clip import (
    DEFAULT_IMAGE_MODEL_ID,
    DEFAULT_IMAGE_MODEL_REVISION,
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    CLIPSearcher,
    _as_tensor,
)


def _loaded_text_searcher(output):
    searcher = CLIPSearcher(device="cpu")
    model = MagicMock()
    model.encode.return_value = output
    searcher._model = model
    return searcher


def test_as_tensor_supports_legacy_and_wrapped_outputs():
    tensor = torch.ones(1, 4)
    assert _as_tensor(tensor) is tensor
    assert _as_tensor(SimpleNamespace(pooler_output=tensor)) is tensor
    with pytest.raises(TypeError, match="Unexpected CLIP output type"):
        _as_tensor(object())


@pytest.mark.parametrize(
    ("device", "dtype"),
    [("cpu", torch.float32), ("cuda", torch.float16)],
)
def test_explicit_device_selects_expected_precision(device, dtype):
    searcher = CLIPSearcher(device=device)
    assert searcher.device == device
    assert searcher.dtype == dtype


def test_default_device_uses_cuda_availability():
    with patch("clip.torch.cuda.is_available", return_value=True):
        assert CLIPSearcher().device == "cuda"
    with patch("clip.torch.cuda.is_available", return_value=False):
        assert CLIPSearcher().device == "cpu"


@pytest.mark.parametrize(("device", "precision_method"), [("cpu", "float"), ("cuda", "half")])
def test_text_model_load_uses_device_precision_and_eval(device, precision_method):
    searcher = CLIPSearcher(device=device)
    with patch("clip.SentenceTransformer") as model_class:
        model = model_class.return_value
        searcher.load()

    model_class.assert_called_once_with(
        DEFAULT_MODEL_ID,
        revision=DEFAULT_MODEL_REVISION,
        device=device,
        model_kwargs={"dtype": searcher.dtype},
    )
    getattr(model, precision_method).assert_called_once_with()
    model.eval.assert_called_once_with()
    assert searcher.is_loaded
    assert not searcher.is_image_model_loaded


def test_text_features_use_sentence_transformer_and_return_float32():
    output = np.arange(4, dtype=np.float16).reshape(1, 4)
    searcher = _loaded_text_searcher(output)

    result = searcher.get_text_features("một con chim")

    searcher._model.encode.assert_called_once_with(
        ["một con chim"],
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=False,
    )
    assert result.dtype == np.float32
    assert result.shape == (1, 4)
    assert np.linalg.norm(result[0]) == pytest.approx(1.0)


def test_image_encoder_remains_separately_lazy_for_release_tooling():
    searcher = CLIPSearcher(device="cpu")
    with patch("clip.CLIPModel") as model_class, patch("clip.CLIPProcessor") as processor:
        image_model = model_class.from_pretrained.return_value
        searcher._ensure_image_loaded()

    model_class.from_pretrained.assert_called_once_with(
        DEFAULT_IMAGE_MODEL_ID,
        revision=DEFAULT_IMAGE_MODEL_REVISION,
        dtype=torch.float32,
    )
    image_model.to.assert_called_once_with("cpu")
    image_model.eval.assert_called_once_with()
    processor.from_pretrained.assert_called_once_with(
        DEFAULT_IMAGE_MODEL_ID,
        revision=DEFAULT_IMAGE_MODEL_REVISION,
    )
    assert searcher.is_image_model_loaded
    assert not searcher.is_loaded


def test_empty_image_batch_does_not_load_either_model():
    searcher = CLIPSearcher(device="cpu")
    result = searcher.get_image_batch_features([])
    assert result.shape == (0, 512)
    assert not searcher.is_loaded
    assert not searcher.is_image_model_loaded
