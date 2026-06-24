from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Finding:
    file: str
    line: int  # 1-based
    rule: str
    action: str  # "delete" | "tighten"
    message: str

    def to_dict(self) -> dict:
        return asdict(self)
