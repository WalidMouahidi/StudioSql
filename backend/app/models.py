from typing import Literal

from pydantic import BaseModel, Field

class JobRequest(BaseModel):
    source_id: str
    schema_name: str = Field(default="dbo", alias="schema")
    table: str
    format: Literal["parquet", "csv"] = "parquet"
    partition_by: list[str] = Field(default_factory=list, max_length=4)
    compression: Literal["none", "snappy", "gzip", "zstd"] | None = None
    batch_size: int = Field(default=50_000, ge=1, le=250_000)


class SourceConfig(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=1433, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    user: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1)
    login_timeout: int = Field(default=5, ge=1, le=60)
    encryption: Literal["require"] | None = None


class SqlQueryRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=20_000)
    limit: int = Field(default=200, ge=1, le=1000)
