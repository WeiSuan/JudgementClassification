from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class JudgmentItem(BaseModel):
    judgment_id: str = Field(default="")
    judgment_date: str = Field(default="")
    case_type: str = Field(default="")
    full_text: str = Field(default="")
    source_url: str = Field(default="")


class CustomerRecord(BaseModel):
    receive_dates: list[str] = Field(default_factory=list)
    customer_name: str
    customer_key: str
    query_status: Literal["FOUND", "NO_DATA", "ERROR"]
    query_note: str = Field(default="")
    judgments: list[JudgmentItem] = Field(default_factory=list)


class OutputMeta(BaseModel):
    source_file: str
    generated_at: str
    crawler: str = Field(default="playwright")
    site: str

    @classmethod
    def now(cls, source_file: str, site: str) -> "OutputMeta":
        return cls(
            source_file=source_file,
            generated_at=datetime.now(timezone.utc).isoformat(),
            site=site,
        )


class OutputPayload(BaseModel):
    meta: OutputMeta
    records: list[CustomerRecord] = Field(default_factory=list)
