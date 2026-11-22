"""Validation for Breeze defaults and optional legacy request overrides."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

GuidanceScale = Annotated[float, Field(gt=0, allow_inf_nan=False)]
# The worker seeds NumPy's legacy RandomState, which accepts unsigned 32-bit seeds.
Seed = Annotated[int, Field(ge=0, le=2**32 - 1)]


class BreezeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)

    plain_cfg_scale: GuidanceScale = 1.0
    instructed_cfg_scale: GuidanceScale = 4.0
    seed: Seed = 42


class BreezeOptions(BaseModel):
    # HTTP form values are strings, so numeric parsing is intentional here.
    model_config = ConfigDict(extra="forbid", frozen=True)

    cfg_scale: GuidanceScale
    seed: Seed
