from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator

SourceType = Literal["rtsp", "onvif", "usb"]
_PATH = r"^[A-Za-z0-9_\-/]{1,100}$"


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    source_type: SourceType
    zone_id: str | None = Field(default=None, max_length=64)
    endpoint: str | None = Field(default=None, max_length=512)
    device_label: str | None = Field(default=None, max_length=120)
    local_agent_id: str | None = Field(default=None, max_length=64)
    username: str | None = Field(default=None, max_length=128)
    password: SecretStr | None = Field(default=None, max_length=128)
    playback_path: str | None = Field(default=None, pattern=_PATH)

    @model_validator(mode="after")
    def _shape(self):
        if self.source_type in ("rtsp", "onvif") and not self.endpoint:
            raise ValueError("endpoint is required for rtsp/onvif cameras")
        if self.source_type == "usb":
            if self.endpoint:
                raise ValueError("usb cameras do not take an endpoint")
            if not self.device_label:
                raise ValueError("device_label is required for usb cameras")
        if bool(self.username) != bool(self.password):
            raise ValueError("provide both username and password, or neither")
        return self


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    zone_id: str | None = Field(default=None, max_length=64)
    playback_path: str | None = Field(default=None, pattern=_PATH)


class PtzCommand(BaseModel):
    action: Literal["move", "stop", "zoom", "home"]
    pan: float = Field(default=0, ge=-1, le=1)
    tilt: float = Field(default=0, ge=-1, le=1)
    zoom: float = Field(default=0, ge=-1, le=1)


class CameraOut(BaseModel):
    id: str
    name: str
    source_type: SourceType
    zone_id: str | None
    endpoint_host: str | None          # host:port only; paths/query may embed tokens
    status: str
    last_seen_at: datetime | None
    last_error_code: str | None
    capabilities: dict
    has_credentials: bool
    origin: Literal["registered"] = "registered"
    configured: bool
    access_policy: str = "operator-registered"
    analytics: str = "not-implemented"
    created_at: datetime
    updated_at: datetime
