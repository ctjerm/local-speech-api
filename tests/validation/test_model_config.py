import pytest
from pydantic import ValidationError

from speech_api.speech.breeze_config import BreezeConfig
from speech_api.transcription.parakeet_config import ParakeetConfig


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "four"])
def test_breeze_rejects_invalid_guidance_defaults(value):
    with pytest.raises(ValidationError):
        BreezeConfig(instructed_cfg_scale=value)


@pytest.mark.parametrize("seed", [-1, 2**32, 1.5, True, "42"])
def test_breeze_rejects_seeds_the_worker_cannot_use_or_incorrect_config_types(seed):
    with pytest.raises(ValidationError):
        BreezeConfig(seed=seed)


def test_breeze_config_is_frozen_and_rejects_typos():
    config = BreezeConfig(seed=2**32 - 1)
    assert (config.plain_cfg_scale, config.instructed_cfg_scale) == (1, 4)
    with pytest.raises(ValidationError):
        config.seed = -1
    with pytest.raises(ValidationError):
        BreezeConfig(cfg_sacle=3)


@pytest.mark.parametrize("overrides", [
    {"chunk_length_s": 0}, {"chunk_length_s": -5}, {"chunk_length_s": float("nan")},
    {"chunk_length_s": float("inf")}, {"device": -1}, {"device": True},
    {"dtype": "float8"}, {"stride_length_s": 1}, {"stride_length_s": False},
    {"chunk_lenght_s": 10},
])
def test_parakeet_rejects_invalid_or_unsupported_settings(tmp_path, overrides):
    with pytest.raises(ValidationError):
        ParakeetConfig(model_path=tmp_path, **overrides)


def test_parakeet_requires_a_local_model_directory_and_freezes_valid_settings(tmp_path):
    with pytest.raises(ValidationError):
        ParakeetConfig(model_path=tmp_path / "missing")
    file = tmp_path / "not-a-directory"
    file.write_text("fixture", encoding="utf-8")
    with pytest.raises(ValidationError):
        ParakeetConfig(model_path=file)
    config = ParakeetConfig(model_path=str(tmp_path), dtype="float32", chunk_length_s=10)
    assert config.model_path == tmp_path
    assert config.dtype == "float32"
    with pytest.raises(ValidationError):
        config.chunk_length_s = 0
