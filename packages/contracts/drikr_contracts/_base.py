from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base for all contracts: unknown fields are rejected rather than silently dropped."""

    model_config = ConfigDict(extra="forbid")
