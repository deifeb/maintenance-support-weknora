from __future__ import annotations

import ast
from pathlib import Path

AFFECTED_TESTS = (
    Path("tests/api/test_async_calculation.py"),
    Path("tests/api/test_calculation_routes.py"),
    Path("tests/api/test_repair_profiles.py"),
)

TENANT_MODELS = {
    "SparePart",
    "Part",
    "EquipmentModel",
    "Warehouse",
    "Inventory",
    "RepairProfile",
}


def test_affected_direct_tenant_models_supply_tenant_id() -> None:
    failures: list[str] = []

    for path in AFFECTED_TESTS:
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        for call in (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in TENANT_MODELS
        ):
            keyword_names = {
                keyword.arg
                for keyword in call.keywords
                if keyword.arg is not None
            }
            if "tenant_id" not in keyword_names:
                failures.append(
                    f"{path}:{call.lineno}: "
                    f"{ast.unparse(call)}"
                )

    assert failures == []
