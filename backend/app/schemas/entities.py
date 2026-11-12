from pydantic import BaseModel, Field


class ApplyRequest(BaseModel):
    stream_id: int


class StreamPatch(BaseModel):
    enabled: bool | None = None


class SettingPut(BaseModel):
    value: str


class HarvestRequest(BaseModel):
    source_dir: str = Field(min_length=1, max_length=512)
    stream_id: int | None = None
    auto_apply: bool = True
