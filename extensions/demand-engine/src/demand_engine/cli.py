from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from demand_engine import DemandCalculationEngine
from demand_engine.enums import ExecutionMode, FailureProcessMode, ReliabilityModelType
from demand_engine.models import (
    CalculationInput,
    DemandItemInput,
    InventoryInput,
    ReliabilityInput,
    SimulationConfig,
    StageInput,
)


def _build(data):
    stages = tuple(StageInput(**stage) for stage in data["stages"])
    items = []
    for item in data["items"]:
        rel = dict(item["reliability"])
        rel["model_type"] = ReliabilityModelType(rel["model_type"])
        items.append(DemandItemInput(
            **{k: v for k, v in item.items() if k not in {"reliability", "inventory", "failure_process_mode"}},
            reliability=ReliabilityInput(**rel),
            inventory=InventoryInput(**item.get("inventory", {})),
            failure_process_mode=FailureProcessMode(item.get("failure_process_mode", "AUTO")),
        ))
    simulation = SimulationConfig(**data.get("simulation", {}))
    return CalculationInput(
        calculation_code=data["calculation_code"],
        stages=stages,
        items=tuple(items),
        requested_mode=ExecutionMode(data.get("requested_mode", "AUTO")),
        simulation=simulation,
        random_seed=int(data.get("random_seed", 20260723)),
    )


def _json_default(value):
    if hasattr(value, "value"):
        return value.value
    raise TypeError(type(value).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="demand-engine")
    sub = parser.add_subparsers(dest="command", required=True)
    calculate = sub.add_parser("calculate")
    calculate.add_argument("--input", required=True)
    calculate.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = DemandCalculationEngine().calculate(_build(data))
    Path(args.output).write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
