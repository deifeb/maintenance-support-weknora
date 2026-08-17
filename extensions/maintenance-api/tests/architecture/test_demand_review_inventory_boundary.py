from __future__ import annotations

import ast
from pathlib import Path

import pytest

FEATURE_MARKER = "PLAN05_4C_TASK2_FEATURE_MISSING"
SERVICE_ROOT = Path(__file__).resolve().parents[2]
TARGETS = (
    SERVICE_ROOT / "app/services/demand_review_snapshot.py",
    SERVICE_ROOT / "app/services/demand_review_rules.py",
    SERVICE_ROOT / "app/services/demand_review_service.py",
)
FORBIDDEN_SYMBOLS = {
    "InventoryReservationService",
    "InventoryLedgerRepository",
    "InventoryTransactionService",
    "InventoryOperationService",
    "InventoryTransferService",
    "InventoryStocktakeService",
}
FORBIDDEN_MODULES = {
    "app.models.inventory_ledger",
    "app.models.inventory_operations",
}


def _require_targets() -> tuple[Path, ...]:
    missing = [str(path.relative_to(SERVICE_ROOT)) for path in TARGETS if not path.exists()]
    if missing:
        pytest.fail(
            f"{FEATURE_MARKER}: missing {', '.join(missing)}",
            pytrace=False,
        )
    return TARGETS


def _imports(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
            names.update(alias.name for alias in node.names)
    return modules, names


def test_formal_review_has_no_forbidden_inventory_authority_imports() -> None:
    for path in _require_targets():
        modules, names = _imports(path)
        assert FORBIDDEN_MODULES.isdisjoint(modules)
        assert FORBIDDEN_SYMBOLS.isdisjoint(names)


def test_snapshot_is_the_only_inventory_read_boundary() -> None:
    snapshot, rules, service = _require_targets()
    snapshot_text = snapshot.read_text(encoding="utf-8")
    assert "InventoryQueryService" in snapshot_text
    assert "summaries_for_parts" in snapshot_text

    for path in (rules, service):
        text = path.read_text(encoding="utf-8")
        assert "InventoryQueryService" not in text
        assert "summaries_for_parts" not in text


def test_formal_review_service_is_separate_from_ai_review_runtime() -> None:
    _, rules, service = _require_targets()
    for path in (rules, service):
        text = path.read_text(encoding="utf-8")
        assert "ai_review_service" not in text
        assert "AIReviewRun" not in text
        assert "AIReviewFinding" not in text
