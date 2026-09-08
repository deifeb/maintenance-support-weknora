from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class SnapshotService:
    def normalize(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            normalized = value.normalize()
            return format(normalized, "f")
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self.normalize(value[key]) for key in sorted(value, key=str)}
        if isinstance(value, (list, tuple)):
            return [self.normalize(item) for item in value]
        return value

    def canonical_json(self, value: Any) -> str:
        return json.dumps(
            self.normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    def canonical_hash(self, value: Any) -> str:
        return hashlib.sha256(self.canonical_json(value).encode("utf-8")).hexdigest()


snapshot_service = SnapshotService()
