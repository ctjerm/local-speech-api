"""Validated local runtime settings, specific to the Parakeet TDT adapter."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, DirectoryPath, Field


class ParakeetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)

    model_path: DirectoryPath = Field(strict=False)
    device: int = Field(default=0, ge=0)
    dtype: Literal["bfloat16", "float16", "float32"] = "bfloat16"
    chunk_length_s: float = Field(default=30.0, gt=0, allow_inf_nan=False)
    # The pinned TDT pipeline cannot trim overlapping strides.
    stride_length_s: int = Field(default=0, ge=0, le=0)
