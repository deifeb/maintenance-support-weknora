import json
from decimal import Decimal
from enum import Enum


def _default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def export_calculation_json(calculation, runs) -> bytes:
    payload = {
        "calculation": {
            "id": calculation.id,
            "calculation_code": calculation.calculation_code,
            "calculation_name": calculation.calculation_name,
            "status": calculation.status.value,
            "input_snapshot_hash": calculation.input_snapshot_hash,
            "result_summary": calculation.result_summary_json,
            "warnings": calculation.warnings_json,
        },
        "runs": [
            {
                "id": run.id,
                "mode": run.run_mode.value,
                "status": run.status.value,
                "items": [
                    {column.name: getattr(item, column.name) for column in item.__table__.columns}
                    for item in run.item_results
                ],
            }
            for run in runs
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=_default).encode("utf-8")
