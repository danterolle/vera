from datetime import UTC, datetime
from ipaddress import ip_address

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NetworkEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    src_ip: str
    dst_ip: str
    src_port: int | None = Field(default=None, ge=0, le=65535)
    dst_port: int | None = Field(default=None, ge=0, le=65535)
    protocol: str = Field(min_length=1, max_length=20)
    tcp_flags: str | None = Field(default=None, max_length=40)
    http_method: str | None = Field(default=None, max_length=20)
    http_host: str | None = Field(default=None, max_length=255)
    http_uri: str | None = Field(default=None, max_length=4096)
    http_status: int | None = Field(default=None, ge=100, le=599)
    bytes: int = Field(default=0, ge=0)
    simulated: bool = False

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        return str(ip_address(value))

    @field_validator("protocol")
    @classmethod
    def normalize_protocol(cls, value: str) -> str:
        return value.upper()


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    events: list[NetworkEvent] = Field(default_factory=list, max_length=100_000)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    simulated: bool = False

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("query must contain non-whitespace characters")
        return normalized
