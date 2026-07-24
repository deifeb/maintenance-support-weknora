import hashlib
import json
import time
import uuid
from typing import Any

from maintenance_ai.enums import ProviderKind
from maintenance_ai.providers.schemas import CompletionMetadata, CompletionUsage


def digest(value: Any) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def metadata(
    provider: ProviderKind, model: str, raw: Any, started: float, **kwargs: Any
) -> CompletionMetadata:
    return CompletionMetadata(
        provider=provider,
        model=model,
        request_id=str(kwargs.pop("request_id", uuid.uuid4().hex)),
        latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
        raw_response_digest=digest(raw),
        usage=kwargs.pop("usage", CompletionUsage()),
        **kwargs,
    )
