# Plan 05-4B Task 10.5 Inventory Server-Side List Query Contract Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已关闭的 Plan 05-4B backend/read surface 上，以最小增量方式为 balances、transactions、reservations、transfers、stocktakes 五类列表补齐已批准的 server-side filter / sort / stable pagination / OpenAPI contract，并在 SQLite 与真实 PostgreSQL 上验证一致语义后冻结给 Inventory Gap 前端使用。

**Architecture:** 保持现有三层结构：`queries.py` 负责 HTTP 参数、枚举/范围验证、重复 scalar guard 与 tenant override guard；`InventoryQueryService` 负责 tenant-scoped filters、四类聚合 parent-page query、显式 sort allowlist 与 child hydration；`InventoryLedgerRepository.list_balances()` 继续负责 balance filter/count/pagination 并增加 approved sort。所有查询执行顺序固定为 `FILTER → COUNT → SORT → PAGE → child hydration`，非 `id` 排序追加同方向 `id` tie-break，nullable sort 使用 portable `CASE ... IS NULL` 规则保证 SQLite/PostgreSQL 均为 NULLS LAST。

**Tech Stack:** Python 3.11、FastAPI、Pydantic、SQLAlchemy 2、SQLite、PostgreSQL 17 + psycopg 3、pytest、Ruff、PowerShell、Git。

## Global Constraints

- 权威规格：`docs/superpowers/specs/2026-08-16-maintenance-plan05-04b-task105-inventory-list-query-contract-design.md`；批准版本 SHA256：`56235759d1773655afbf3149ad49aaa2af5b6f5b75c8a073f6f286e14da1a7e3`。
- 该规格扩展但不替换 `docs/superpowers/specs/2026-08-04-maintenance-plan05-04b-inventory-operations-design.md` 与 `docs/superpowers/plans/2026-08-03-maintenance-plan05-04b-inventory-operations-stocktake.md`。
- 已验证设计基线分支：`codex/maintenance-plan05-4b`；设计时远端 HEAD：`dfb7498737fb7610826c36c6827946798767c6a0`。实施时允许 HEAD 前进，但 `dfb7498737fb7610826c36c6827946798767c6a0` 必须仍是 HEAD 的 ancestor。
- Task 10.5 只做 additive read-query contract；不得修改 reservation/transfer/stocktake 状态机、FEFO、ledger、mutation kernel、worker、write API 或 frontend。
- RED 阶段只允许修改 `extensions/maintenance-api/tests/services/test_inventory_query_service.py` 与 `extensions/maintenance-api/tests/api/test_inventory_queries_api.py`。
- GREEN production 范围冻结为三个现有文件：`extensions/maintenance-api/app/api/v1/inventory/queries.py`、`extensions/maintenance-api/app/services/inventory_query_service.py`、`extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`。如实施必须触碰第四个 production 文件，立即 STOP 并回到用户审批。
- **NO migration / NO new table / NO new index / NO frontend implementation**；Alembic head 必须保持 `20260803_11`。如果 approved contract 无法在该约束下实现，立即 STOP，不得自行扩大范围。
- 不新增 keyword/full-text/master-data name search、multi-value filter、cursor pagination、snapshot token 或 child-line spare-part filter。
- `tenant_id` 继续只能来自 `ActorContext.tenant_id`；query/body override 仍为 `422`。
- 默认分页保持 `page=1`、`page_size=20`，`page >= 1`，`1 <= page_size <= 100`。
- 默认排序保持 `sort_by=id&sort_order=asc`；不得改变旧请求的 `id ASC` 默认行为。
- `sort_order` 仅允许小写 `asc|desc`；非法 ID/status/operation_type/sort 输入返回 `422`，不做静默 fallback。
- 所有 approved filters 为 single exact value；多个不同 filter 之间使用 `AND`。已知 single-value query parameter 重复出现必须 `422`。
- nullable sort 始终 NULLS LAST；不得依赖 SQLite/PostgreSQL 默认 NULL 排序。
- 计划批准不等于批准 RED；RED 完成后必须 STOP，等待用户明确批准 GREEN。
- GREEN 批准不等于批准 **commit / push / PR / merge**；这些动作仍需分别明确批准。
- Task 10.5 closure 后下一步是 Inventory Gap Frontend Design，不得自动开始 Task 11 frontend implementation。

---

## File Map

### RED-only test files

- Modify: `extensions/maintenance-api/tests/services/test_inventory_query_service.py`
  - 增加五类 service semantic query contract fixtures/tests；证明 filter-before-page、filtered total、stable tie-break、NULLS LAST、tenant isolation、service fail-closed 与默认 `id ASC`。
- Modify: `extensions/maintenance-api/tests/api/test_inventory_queries_api.py`
  - 增加五类 OpenAPI/HTTP query contract、validation、duplicate scalar、真实 HTTP filter/sort/meta 行为与 backwards compatibility tests。

### GREEN production files

- Modify: `extensions/maintenance-api/app/api/v1/inventory/queries.py`
  - 声明 `Literal` query contracts；为五个 list route 暴露 filters / `sort_by` / `sort_order`；增加 per-resource duplicate single-value guard；把 query 参数完整传给 service。
- Modify: `extensions/maintenance-api/app/services/inventory_query_service.py`
  - 为 transactions/reservations/transfers/stocktakes 增加 filters 与 sort；以显式 allowlist 构造 tenant-scoped parent query；复用 parent-page-then-child-hydration；service 对非法 sort fail closed。
- Modify: `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`
  - 扩展 `list_balances()` 的 `sort_by` / `sort_order`；显式 balance sort mapping；`available_quantity` 使用 SQL expression；`lot_id` portable NULLS LAST；保持现有 balance filters 与 count conditions。

### Explicitly untouched

- `frontend/**`
- `extensions/maintenance-api/alembic/**`
- `extensions/maintenance-api/app/models/**`
- reservation/transfer/stocktake write services
- FEFO service
- transaction mutation kernel
- expiry worker

---

## Approved Public Query Matrix

| Resource | Filters | Sorts |
|---|---|---|
| balances | `warehouse_id`, `spare_part_id`, `location_id`, `lot_id`, `serial_item_id` | `id`, `warehouse_id`, `spare_part_id`, `location_id`, `lot_id`, `on_hand_quantity`, `reserved_quantity`, `available_quantity` |
| transactions | `operation_type`, `status`, `reference_type`, `reference_id` | `id`, `operation_type`, `status`, `completed_at` |
| reservations | `status`, `owner_type`, `owner_id` | `id`, `status`, `expires_at` |
| transfers | `status`, `source_warehouse_id`, `source_location_id`, `target_warehouse_id`, `target_location_id`, `reference_type`, `reference_id` | `id`, `status`, `dispatched_at`, `completed_at` |
| stocktakes | `status`, `warehouse_id`, `location_id` | `id`, `status`, `snapshot_at`, `confirmed_at` |

All five also expose `page`, `page_size`, `sort_by`, `sort_order`.

---

### Task 0: Execution Preflight and Authority Check

**Files:**
- Read only: repository state, approved spec, current plan, Alembic metadata.
- Modify: none.

**Interfaces:**
- Consumes: approved design SHA and baseline commit.
- Produces: verified local execution context; no repository changes.

- [ ] **Step 1: Resolve repository, Git, and Python without modifying anything**

Run in PowerShell:

```powershell
$ErrorActionPreference = "Stop"

$repoRoot = "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-plan05-4b"
$git = "C:\Program Files\Git\cmd\git.exe"
$apiRoot = Join-Path $repoRoot "extensions\maintenance-api"
$requiredAncestor = "dfb7498737fb7610826c36c6827946798767c6a0"
$designRelative = "docs\superpowers\specs\2026-08-16-maintenance-plan05-04b-task105-inventory-list-query-contract-design.md"
$expectedDesignSha = "56235759d1773655afbf3149ad49aaa2af5b6f5b75c8a073f6f286e14da1a7e3"

if (-not (Test-Path -LiteralPath $repoRoot -PathType Container)) {
    throw "Task 10.5 worktree missing: $repoRoot"
}
if (-not (Test-Path -LiteralPath $git -PathType Leaf)) {
    throw "git.exe missing: $git"
}

$pythonCandidates = @(
    (Join-Path $apiRoot ".venv\Scripts\python.exe"),
    "E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\extensions\maintenance-api\.venv\Scripts\python.exe"
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $python) {
    throw "No approved Python 3.11 virtualenv interpreter found"
}

& $python --version
if ($LASTEXITCODE -ne 0) { throw "Python interpreter failed" }
$pythonVersion = (& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($pythonVersion -ne "3.11") {
    throw "Task 10.5 requires Python 3.11, found $pythonVersion"
}
```

- [ ] **Step 2: Verify branch, baseline ancestry, clean worktree, and no staged content**

```powershell
$branch = (& $git -C $repoRoot branch --show-current).Trim()
if ($branch -ne "codex/maintenance-plan05-4b") {
    throw "Wrong branch: $branch"
}

& $git -C $repoRoot merge-base --is-ancestor $requiredAncestor HEAD
if ($LASTEXITCODE -ne 0) {
    throw "Required Task 10.5 baseline is not an ancestor of HEAD"
}

$status = @(& $git -C $repoRoot status --porcelain=v1)
if ($LASTEXITCODE -ne 0) { throw "git status failed" }
if ($status.Count -ne 0) {
    $status | ForEach-Object { Write-Host $_ }
    throw "Implementation preflight requires a clean worktree"
}

$staged = @(& $git -C $repoRoot diff --cached --name-only)
if ($staged.Count -ne 0) {
    throw "Implementation preflight requires empty staged state"
}

& $git -C $repoRoot rev-parse HEAD
```

If the approved spec/plan documents have not yet been placed in the repository, do **not** bypass the clean-tree requirement by leaving them untracked. Their repository write/commit requires its own user approval before implementation begins.

- [ ] **Step 3: Verify the approved design document exactly if it is present in the implementation worktree**

```powershell
$designPath = Join-Path $repoRoot $designRelative
if (-not (Test-Path -LiteralPath $designPath -PathType Leaf)) {
    throw "Approved Task 10.5 design spec is not present in the worktree: $designPath"
}
$actualDesignSha = (Get-FileHash -LiteralPath $designPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualDesignSha -ne $expectedDesignSha) {
    throw "Task 10.5 design SHA mismatch: $actualDesignSha"
}
```

- [ ] **Step 4: Verify Alembic head remains unchanged before RED**

```powershell
Push-Location $apiRoot
try {
    $heads = @(& $python -m alembic heads)
    if ($LASTEXITCODE -ne 0) { throw "alembic heads failed" }
    if (($heads -join "`n") -notmatch "20260803_11 \(head\)") {
        throw "Unexpected Alembic head: $($heads -join '; ')"
    }
} finally {
    Pop-Location
}
```

- [ ] **Step 5: STOP if any preflight assertion fails**

No reset, stash, cleanup, pull, rebase, checkout, commit, push, PR or merge is authorized by this plan.

---

### Task 1: Write Task 10.5 RED Query Contract Tests

**Files:**
- Modify: `extensions/maintenance-api/tests/services/test_inventory_query_service.py`
- Modify: `extensions/maintenance-api/tests/api/test_inventory_queries_api.py`
- Production files: untouched.

**Interfaces:**
- Consumes: current five list services/routes and approved query matrix.
- Produces: RED tests that fail only because current production lacks the approved query contract.

- [ ] **Step 1: Extend service-test imports and add deterministic parent-row seed helpers**

At the top of `test_inventory_query_service.py`, extend imports so tests can create parent aggregates directly without invoking unrelated write workflows:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    InventoryBalance,
    InventoryLot,
    InventoryPolicy,
    InventoryReservation,
    InventoryStocktake,
    InventoryTransaction,
    InventoryTransfer,
    SerializedItem,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
```

Keep the existing `seed_balance()` helper. Add deterministic helpers with complete required parent fields:

```python
def seed_transaction(
    session,
    *,
    tenant_id: str,
    suffix: str,
    operation_type: str,
    status: str,
    reference_type: str | None,
    reference_id: str | None,
    completed_at: datetime | None,
) -> InventoryTransaction:
    row = InventoryTransaction(
        tenant_id=tenant_id,
        operation_type=operation_type,
        status=status,
        idempotency_key=f"query-contract-{suffix}",
        request_hash=(suffix.encode("utf-8").hex() + "0" * 64)[:64],
        reference_type=reference_type,
        reference_id=reference_id,
        reason=f"Task 10.5 query contract {suffix}",
        actor_user_id=f"actor-{tenant_id}",
        actor_roles_json=["ADMIN"],
        request_id=f"request-{suffix}",
        version=1,
        completed_at=completed_at,
    )
    session.add(row)
    session.flush()
    return row


def seed_reservation(
    session,
    *,
    tenant_id: str,
    suffix: str,
    status: str,
    owner_type: str,
    owner_id: str,
    expires_at: datetime | None,
) -> InventoryReservation:
    row = InventoryReservation(
        tenant_id=tenant_id,
        owner_type=owner_type,
        owner_id=owner_id,
        status=status,
        expires_at=expires_at,
        allow_partial=False,
        actor_user_id=f"actor-{tenant_id}",
        actor_roles_json=["ADMIN"],
        request_id=f"request-{suffix}",
        version=1,
    )
    session.add(row)
    session.flush()
    return row


def seed_transfer_parent(
    session,
    *,
    tenant_id: str,
    suffix: str,
    source: InventoryBalance,
    target: InventoryBalance,
    status: str,
    reference_type: str | None,
    reference_id: str | None,
    dispatched_at: datetime | None,
    completed_at: datetime | None,
) -> InventoryTransfer:
    row = InventoryTransfer(
        tenant_id=tenant_id,
        status=status,
        source_warehouse_id=source.warehouse_id,
        source_location_id=source.location_id,
        target_warehouse_id=target.warehouse_id,
        target_location_id=target.location_id,
        reference_type=reference_type,
        reference_id=reference_id,
        reason=f"Task 10.5 transfer {suffix}",
        actor_user_id=f"actor-{tenant_id}",
        actor_roles_json=["ADMIN"],
        request_id=f"request-{suffix}",
        version=1,
        dispatched_at=dispatched_at,
        completed_at=completed_at,
    )
    session.add(row)
    session.flush()
    return row


def seed_stocktake_parent(
    session,
    *,
    tenant_id: str,
    suffix: str,
    balance: InventoryBalance,
    status: str,
    snapshot_at: datetime,
    confirmed_at: datetime | None,
) -> InventoryStocktake:
    row = InventoryStocktake(
        tenant_id=tenant_id,
        warehouse_id=balance.warehouse_id,
        location_id=balance.location_id,
        status=status,
        snapshot_at=snapshot_at,
        actor_user_id=f"actor-{tenant_id}",
        actor_roles_json=["ADMIN"],
        request_id=f"request-{suffix}",
        version=1,
        confirmed_at=confirmed_at,
    )
    session.add(row)
    session.flush()
    return row
```

The helper values are deterministic and do not require child rows; current read builders already hydrate an empty child collection when the selected parent has no child rows.

- [ ] **Step 2: Add balance service contract test**

Add:

```python
def test_balance_query_contract_filters_and_sorts_before_pagination(
    session,
    actor_context,
) -> None:
    first, first_serial = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="Q-BAL-1",
        on_hand="9",
        reserved="4",
        with_serial=True,
    )
    second, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="Q-BAL-2",
        on_hand="8",
        reserved="1",
    )
    seed_balance(
        session,
        tenant_id="tenant-b",
        suffix="Q-BAL-FOREIGN",
        on_hand="100",
        reserved="0",
    )
    session.commit()

    assert first_serial is not None
    filtered = inventory_query_service.list_balances(
        session,
        actor_context(),
        page=1,
        page_size=1,
        warehouse_id=first.warehouse_id,
        spare_part_id=first.spare_part_id,
        location_id=first.location_id,
        lot_id=first.lot_id,
        serial_item_id=first_serial.id,
        sort_by="available_quantity",
        sort_order="desc",
    )

    assert second.id != first.id
    assert filtered.total == 1
    assert filtered.pages == 1
    assert [item.id for item in filtered.items] == [first.id]
```

Add this separate two-row same-filter test so `available_quantity` ordering is proven before pagination:

```python
def test_balance_query_contract_available_quantity_sort_precedes_page(
    session,
    actor_context,
) -> None:
    warehouse = Warehouse(
        tenant_id="tenant-a",
        code="WH-Q-BAL-SORT",
        name="Task 10.5 balance sort warehouse",
    )
    part = SparePart(
        tenant_id="tenant-a",
        code="SP-Q-BAL-SORT",
        name="Task 10.5 balance sort part",
    )
    lower, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="Q-BAL-LOW",
        warehouse=warehouse,
        part=part,
        on_hand="5",
        reserved="4",
    )
    higher, _ = seed_balance(
        session,
        tenant_id="tenant-a",
        suffix="Q-BAL-HIGH",
        warehouse=warehouse,
        part=part,
        on_hand="9",
        reserved="1",
    )
    session.commit()

    first_page = inventory_query_service.list_balances(
        session,
        actor_context(),
        page=1,
        page_size=1,
        warehouse_id=warehouse.id,
        spare_part_id=part.id,
        sort_by="available_quantity",
        sort_order="desc",
    )
    second_page = inventory_query_service.list_balances(
        session,
        actor_context(),
        page=2,
        page_size=1,
        warehouse_id=warehouse.id,
        spare_part_id=part.id,
        sort_by="available_quantity",
        sort_order="desc",
    )

    assert first_page.total == second_page.total == 2
    assert [item.id for item in first_page.items] == [higher.id]
    assert [item.id for item in second_page.items] == [lower.id]
```


- [ ] **Step 3: Add transaction filter-before-page and stable tie-break tests**

Add exactly two tests:

```python
def test_transaction_query_contract_filters_before_count_and_page(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    matching = [
        seed_transaction(
            session,
            tenant_id="tenant-a",
            suffix=f"FAILED-{index}",
            operation_type="ADJUST",
            status="FAILED",
            reference_type="WORK_ORDER",
            reference_id="WO-10.5",
            completed_at=base + timedelta(minutes=index),
        )
        for index in range(3)
    ]
    for index in range(7):
        seed_transaction(
            session,
            tenant_id="tenant-a",
            suffix=f"OTHER-{index}",
            operation_type="RESERVE",
            status="COMPLETED",
            reference_type="MANUAL",
            reference_id=f"OTHER-{index}",
            completed_at=base + timedelta(hours=1, minutes=index),
        )
    seed_transaction(
        session,
        tenant_id="tenant-b",
        suffix="FOREIGN-FAILED",
        operation_type="ADJUST",
        status="FAILED",
        reference_type="WORK_ORDER",
        reference_id="WO-10.5",
        completed_at=base,
    )
    session.commit()

    page = inventory_query_service.list_transactions(
        session,
        actor_context(),
        page=2,
        page_size=2,
        operation_type="ADJUST",
        status="FAILED",
        reference_type="WORK_ORDER",
        reference_id="WO-10.5",
        sort_by="id",
        sort_order="asc",
    )

    assert page.total == 3
    assert page.pages == 2
    assert [item.id for item in page.items] == [matching[2].id]


def test_transaction_query_contract_stable_tie_break_follows_sort_direction(
    session,
    actor_context,
) -> None:
    rows = [
        seed_transaction(
            session,
            tenant_id="tenant-a",
            suffix=f"TIE-{index}",
            operation_type="RESERVE",
            status="COMPLETED",
            reference_type="MANUAL",
            reference_id=f"TIE-{index}",
            completed_at=None,
        )
        for index in range(3)
    ]
    session.commit()

    ids = []
    for page_number in (1, 2, 3):
        page = inventory_query_service.list_transactions(
            session,
            actor_context(),
            page=page_number,
            page_size=1,
            status="COMPLETED",
            sort_by="status",
            sort_order="desc",
        )
        ids.extend(item.id for item in page.items)

    assert ids == sorted((row.id for row in rows), reverse=True)
```

Add transaction `completed_at` NULLS LAST in both directions:

```python
def test_transaction_query_contract_completed_at_nulls_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    early = seed_transaction(
        session, tenant_id="tenant-a", suffix="TX-EARLY",
        operation_type="ADJUST", status="COMPLETED",
        reference_type="MANUAL", reference_id="TX-NULL-SORT", completed_at=base,
    )
    late = seed_transaction(
        session, tenant_id="tenant-a", suffix="TX-LATE",
        operation_type="ADJUST", status="COMPLETED",
        reference_type="MANUAL", reference_id="TX-NULL-SORT",
        completed_at=base + timedelta(hours=1),
    )
    null_completed = seed_transaction(
        session, tenant_id="tenant-a", suffix="TX-NULL",
        operation_type="ADJUST", status="COMPLETED",
        reference_type="MANUAL", reference_id="TX-NULL-SORT", completed_at=None,
    )
    session.commit()

    asc_page = inventory_query_service.list_transactions(
        session, actor_context(), page=1, page_size=20,
        reference_id="TX-NULL-SORT", sort_by="completed_at", sort_order="asc",
    )
    desc_page = inventory_query_service.list_transactions(
        session, actor_context(), page=1, page_size=20,
        reference_id="TX-NULL-SORT", sort_by="completed_at", sort_order="desc",
    )

    assert [item.id for item in asc_page.items] == [early.id, late.id, null_completed.id]
    assert [item.id for item in desc_page.items] == [late.id, early.id, null_completed.id]
```

- [ ] **Step 4: Add reservation NULLS LAST, filters, and default-order tests**

```python
def test_reservation_query_contract_filters_and_keeps_null_expiry_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    early = seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="RES-EARLY",
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        expires_at=base,
    )
    late = seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="RES-LATE",
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        expires_at=base + timedelta(hours=1),
    )
    null_expiry = seed_reservation(
        session,
        tenant_id="tenant-a",
        suffix="RES-NULL",
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        expires_at=None,
    )
    seed_reservation(
        session,
        tenant_id="tenant-b",
        suffix="RES-FOREIGN",
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        expires_at=base - timedelta(hours=1),
    )
    session.commit()

    asc_page = inventory_query_service.list_reservations(
        session,
        actor_context(),
        page=1,
        page_size=20,
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        sort_by="expires_at",
        sort_order="asc",
    )
    desc_page = inventory_query_service.list_reservations(
        session,
        actor_context(),
        page=1,
        page_size=20,
        status="ACTIVE",
        owner_type="MANUAL",
        owner_id="OWNER-10.5",
        sort_by="expires_at",
        sort_order="desc",
    )

    assert [item.id for item in asc_page.items] == [early.id, late.id, null_expiry.id]
    assert [item.id for item in desc_page.items] == [late.id, early.id, null_expiry.id]
    assert asc_page.total == desc_page.total == 3


def test_inventory_list_default_order_remains_id_ascending(
    session,
    actor_context,
) -> None:
    rows = [
        seed_reservation(
            session,
            tenant_id="tenant-a",
            suffix=f"DEFAULT-{index}",
            status="ACTIVE",
            owner_type="MANUAL",
            owner_id=f"DEFAULT-{index}",
            expires_at=None,
        )
        for index in range(3)
    ]
    session.commit()

    page = inventory_query_service.list_reservations(
        session,
        actor_context(),
        page=1,
        page_size=20,
    )

    assert [item.id for item in page.items] == sorted(row.id for row in rows)
```

- [ ] **Step 5: Add transfer and stocktake service contract tests**

Build two locations per tenant with the existing `seed_balance()` helper and add:

```python
def test_transfer_query_contract_filters_and_nulls_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    source, _ = seed_balance(session, tenant_id="tenant-a", suffix="TR-SRC")
    target, _ = seed_balance(session, tenant_id="tenant-a", suffix="TR-DST")
    first = seed_transfer_parent(
        session,
        tenant_id="tenant-a",
        suffix="TR-FIRST",
        source=source,
        target=target,
        status="DISPATCHED",
        reference_type="WORK_ORDER",
        reference_id="WO-TR-10.5",
        dispatched_at=base,
        completed_at=base + timedelta(hours=1),
    )
    null_completed = seed_transfer_parent(
        session,
        tenant_id="tenant-a",
        suffix="TR-NULL",
        source=source,
        target=target,
        status="DISPATCHED",
        reference_type="WORK_ORDER",
        reference_id="WO-TR-10.5",
        dispatched_at=base + timedelta(minutes=1),
        completed_at=None,
    )
    foreign_source, _ = seed_balance(session, tenant_id="tenant-b", suffix="TR-FSRC")
    foreign_target, _ = seed_balance(session, tenant_id="tenant-b", suffix="TR-FDST")
    seed_transfer_parent(
        session,
        tenant_id="tenant-b",
        suffix="TR-FOREIGN",
        source=foreign_source,
        target=foreign_target,
        status="DISPATCHED",
        reference_type="WORK_ORDER",
        reference_id="WO-TR-10.5",
        dispatched_at=base - timedelta(hours=1),
        completed_at=base - timedelta(minutes=30),
    )
    session.commit()

    page = inventory_query_service.list_transfers(
        session,
        actor_context(),
        page=1,
        page_size=20,
        status="DISPATCHED",
        source_warehouse_id=source.warehouse_id,
        source_location_id=source.location_id,
        target_warehouse_id=target.warehouse_id,
        target_location_id=target.location_id,
        reference_type="WORK_ORDER",
        reference_id="WO-TR-10.5",
        sort_by="completed_at",
        sort_order="asc",
    )

    assert page.total == 2
    assert [item.id for item in page.items] == [first.id, null_completed.id]


def test_stocktake_query_contract_filters_and_nulls_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    balance, _ = seed_balance(session, tenant_id="tenant-a", suffix="STK")
    confirmed = seed_stocktake_parent(
        session,
        tenant_id="tenant-a",
        suffix="STK-CONFIRMED",
        balance=balance,
        status="CONFIRMED",
        snapshot_at=base,
        confirmed_at=base + timedelta(hours=1),
    )
    null_confirmed = seed_stocktake_parent(
        session,
        tenant_id="tenant-a",
        suffix="STK-NULL",
        balance=balance,
        status="CONFIRMED",
        snapshot_at=base + timedelta(minutes=1),
        confirmed_at=None,
    )
    foreign_balance, _ = seed_balance(session, tenant_id="tenant-b", suffix="STK-FOREIGN")
    seed_stocktake_parent(
        session,
        tenant_id="tenant-b",
        suffix="STK-FOREIGN",
        balance=foreign_balance,
        status="CONFIRMED",
        snapshot_at=base,
        confirmed_at=base,
    )
    session.commit()

    asc_page = inventory_query_service.list_stocktakes(
        session, actor_context(), page=1, page_size=20,
        status="CONFIRMED", warehouse_id=balance.warehouse_id,
        location_id=balance.location_id, sort_by="confirmed_at", sort_order="asc",
    )
    desc_page = inventory_query_service.list_stocktakes(
        session, actor_context(), page=1, page_size=20,
        status="CONFIRMED", warehouse_id=balance.warehouse_id,
        location_id=balance.location_id, sort_by="confirmed_at", sort_order="desc",
    )

    assert asc_page.total == desc_page.total == 2
    assert [item.id for item in asc_page.items] == [confirmed.id, null_confirmed.id]
    assert [item.id for item in desc_page.items] == [confirmed.id, null_confirmed.id]
```

Add explicit transfer `dispatched_at` NULLS LAST coverage:

```python
def test_transfer_query_contract_dispatched_at_nulls_last(
    session,
    actor_context,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    source, _ = seed_balance(session, tenant_id="tenant-a", suffix="TRD-SRC")
    target, _ = seed_balance(session, tenant_id="tenant-a", suffix="TRD-DST")
    dispatched = seed_transfer_parent(
        session, tenant_id="tenant-a", suffix="TRD-DISPATCHED",
        source=source, target=target, status="DRAFT",
        reference_type="MANUAL", reference_id="TRD-NULL-SORT",
        dispatched_at=base, completed_at=None,
    )
    null_dispatched = seed_transfer_parent(
        session, tenant_id="tenant-a", suffix="TRD-NULL",
        source=source, target=target, status="DRAFT",
        reference_type="MANUAL", reference_id="TRD-NULL-SORT",
        dispatched_at=None, completed_at=None,
    )
    session.commit()

    for sort_order in ("asc", "desc"):
        page = inventory_query_service.list_transfers(
            session, actor_context(), page=1, page_size=20,
            reference_id="TRD-NULL-SORT",
            sort_by="dispatched_at", sort_order=sort_order,
        )
        assert page.total == 2
        assert [item.id for item in page.items][-1] == null_dispatched.id
        assert dispatched.id in {item.id for item in page.items[:-1]}
```

- [ ] **Step 6: Add service fail-closed tests without importing future production constants**

```python
@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        ("list_transactions", {}),
        ("list_reservations", {}),
        ("list_transfers", {}),
        ("list_stocktakes", {}),
    ],
)
def test_inventory_query_service_rejects_unknown_sort_field(
    session,
    actor_context,
    method_name,
    kwargs,
) -> None:
    method = getattr(inventory_query_service, method_name)
    with pytest.raises(ValueError, match="unsupported sort_by"):
        method(
            session,
            actor_context(),
            page=1,
            page_size=20,
            sort_by="tenant_id",
            sort_order="asc",
            **kwargs,
        )


@pytest.mark.parametrize(
    "method_name",
    ["list_transactions", "list_reservations", "list_transfers", "list_stocktakes"],
)
def test_inventory_query_service_rejects_unknown_sort_order(
    session,
    actor_context,
    method_name,
) -> None:
    method = getattr(inventory_query_service, method_name)
    with pytest.raises(ValueError, match="unsupported sort_order"):
        method(
            session,
            actor_context(),
            page=1,
            page_size=20,
            sort_by="id",
            sort_order="sideways",
        )
```

Add explicit balance-path fail-closed coverage:

```python
def test_balance_query_service_rejects_unknown_sort_field(
    session,
    actor_context,
) -> None:
    with pytest.raises(ValueError, match="unsupported sort_by"):
        inventory_query_service.list_balances(
            session,
            actor_context(),
            page=1,
            page_size=20,
            sort_by="tenant_id",
            sort_order="asc",
        )


def test_balance_query_service_rejects_unknown_sort_order(
    session,
    actor_context,
) -> None:
    with pytest.raises(ValueError, match="unsupported sort_order"):
        inventory_query_service.list_balances(
            session,
            actor_context(),
            page=1,
            page_size=20,
            sort_by="id",
            sort_order="sideways",
        )
```


- [ ] **Step 7: Add API/OpenAPI exact-parameter contract tests**

In `test_inventory_queries_api.py`, first change the datetime import to:

```python
from datetime import date, datetime, timedelta, timezone
```

The file already imports `Any`; keep it because the OpenAPI enum resolver uses it. Then define the approved query name map in the test file:

```python
EXPECTED_LIST_QUERY_PARAMS = {
    "balances": {
        "page", "page_size", "warehouse_id", "spare_part_id", "location_id",
        "lot_id", "serial_item_id", "sort_by", "sort_order",
    },
    "transactions": {
        "page", "page_size", "operation_type", "status", "reference_type",
        "reference_id", "sort_by", "sort_order",
    },
    "reservations": {
        "page", "page_size", "status", "owner_type", "owner_id",
        "sort_by", "sort_order",
    },
    "transfers": {
        "page", "page_size", "status", "source_warehouse_id",
        "source_location_id", "target_warehouse_id", "target_location_id",
        "reference_type", "reference_id", "sort_by", "sort_order",
    },
    "stocktakes": {
        "page", "page_size", "status", "warehouse_id", "location_id",
        "sort_by", "sort_order",
    },
}
```

Add:

```python
def test_inventory_list_openapi_exposes_exact_task105_query_contract(
    client: TestClient,
) -> None:
    openapi = client.app.openapi()
    for resource, path in READ_LIST_PATHS.items():
        parameters = openapi["paths"][path]["get"]["parameters"]
        query_parameters = {
            parameter["name"]: parameter
            for parameter in parameters
            if parameter.get("in") == "query"
        }
        assert set(query_parameters) == EXPECTED_LIST_QUERY_PARAMS[resource]
```

Add exact expected enum maps and one resolver that handles inline enums, `anyOf`, and `$ref` without depending on FastAPI's chosen OpenAPI encoding:

```python
EXPECTED_QUERY_ENUMS = {
    "balances": {
        "sort_order": {"asc", "desc"},
        "sort_by": {
            "id", "warehouse_id", "spare_part_id", "location_id", "lot_id",
            "on_hand_quantity", "reserved_quantity", "available_quantity",
        },
    },
    "transactions": {
        "sort_order": {"asc", "desc"},
        "sort_by": {"id", "operation_type", "status", "completed_at"},
        "operation_type": {
            "OPENING", "ADJUST", "RESERVE", "UNRESERVE", "ISSUE", "RETURN",
            "TRANSFER_DISPATCH", "TRANSFER_RECEIVE", "FREEZE", "UNFREEZE",
            "REVERSE", "STOCKTAKE_CONFIRM",
        },
        "status": {
            "PREVIEWED", "COMPLETED", "PARTIALLY_COMPLETED",
            "FAILED", "EXPIRED", "REVERSED",
        },
    },
    "reservations": {
        "sort_order": {"asc", "desc"},
        "sort_by": {"id", "status", "expires_at"},
        "status": {
            "ACTIVE", "PARTIALLY_ISSUED", "FULFILLED",
            "RELEASED", "CANCELLED", "EXPIRED",
        },
    },
    "transfers": {
        "sort_order": {"asc", "desc"},
        "sort_by": {"id", "status", "dispatched_at", "completed_at"},
        "status": {
            "DRAFT", "DISPATCHED", "PARTIALLY_RECEIVED", "COMPLETED", "CANCELLED",
        },
    },
    "stocktakes": {
        "sort_order": {"asc", "desc"},
        "sort_by": {"id", "status", "snapshot_at", "confirmed_at"},
        "status": {
            "DRAFT", "COUNTING", "REVIEWING", "CONFIRMED", "CONFLICTED", "CANCELLED",
        },
    },
}


def _openapi_enum_values(openapi: dict[str, Any], schema: dict[str, Any]) -> set[str]:
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return _openapi_enum_values(openapi, openapi["components"]["schemas"][name])
    values = {str(value) for value in schema.get("enum", []) if value is not None}
    for branch in schema.get("anyOf", []):
        values.update(_openapi_enum_values(openapi, branch))
    return values


def test_inventory_list_openapi_exposes_exact_task105_query_enums(
    client: TestClient,
) -> None:
    openapi = client.app.openapi()
    for resource, expected in EXPECTED_QUERY_ENUMS.items():
        path = READ_LIST_PATHS[resource]
        parameters = {
            parameter["name"]: parameter
            for parameter in openapi["paths"][path]["get"]["parameters"]
            if parameter.get("in") == "query"
        }
        for parameter_name, expected_values in expected.items():
            actual_values = _openapi_enum_values(
                openapi,
                parameters[parameter_name]["schema"],
            )
            assert actual_values == expected_values
```

Also import the model status constants directly from `app.models.inventory_ledger` and add a drift guard:

```python
from app.models.inventory_ledger import (
    RESERVATION_STATUSES,
    STOCKTAKE_STATUSES,
    TRANSACTION_STATUSES,
    TRANSFER_STATUSES,
)


def test_inventory_query_status_contract_matches_model_status_sets() -> None:
    assert EXPECTED_QUERY_ENUMS["transactions"]["status"] == set(TRANSACTION_STATUSES)
    assert EXPECTED_QUERY_ENUMS["reservations"]["status"] == set(RESERVATION_STATUSES)
    assert EXPECTED_QUERY_ENUMS["transfers"]["status"] == set(TRANSFER_STATUSES)
    assert EXPECTED_QUERY_ENUMS["stocktakes"]["status"] == set(STOCKTAKE_STATUSES)
```


- [ ] **Step 8: Add API validation matrix and duplicate scalar tests**

Add a parameterized 422 matrix using a viewer token:

```python
@pytest.mark.parametrize(
    ("resource", "params"),
    [
        ("balances", [("page", "0")]),
        ("balances", [("page_size", "101")]),
        ("balances", [("warehouse_id", "0")]),
        ("balances", [("warehouse_id", "-1")]),
        ("balances", [("warehouse_id", "abc")]),
        ("transactions", [("status", "UNKNOWN")]),
        ("transactions", [("operation_type", "UNKNOWN")]),
        ("transactions", [("sort_by", "response_snapshot_json")]),
        ("transactions", [("sort_order", "ASC")]),
        ("reservations", [("owner_id", "   ")]),
        ("transfers", [("reference_type", "")]),
        ("stocktakes", [("sort_order", "sideways")]),
    ],
)
def test_inventory_list_query_validation_returns_422(
    client,
    internal_auth_headers,
    resource,
    params,
) -> None:
    response = client.get(
        READ_LIST_PATHS[resource],
        params=params,
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.VIEWER,
            request_id=f"task105-validation-{resource}",
        ),
    )
    assert response.status_code == 422, response.text
```

Add duplicate single-value cases as a list of tuples so the HTTP client preserves duplicate keys:

```python
@pytest.mark.parametrize(
    ("resource", "params"),
    [
        ("reservations", [("status", "ACTIVE"), ("status", "EXPIRED")]),
        ("transactions", [("page", "1"), ("page", "2")]),
        ("balances", [("sort_by", "id"), ("sort_by", "warehouse_id")]),
        ("stocktakes", [("sort_order", "asc"), ("sort_order", "desc")]),
    ],
)
def test_inventory_list_rejects_duplicate_single_value_query_parameters(
    client,
    internal_auth_headers,
    resource,
    params,
) -> None:
    response = client.get(
        READ_LIST_PATHS[resource],
        params=params,
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.VIEWER,
            request_id=f"task105-duplicate-{resource}",
        ),
    )
    assert response.status_code == 422, response.text
```

- [ ] **Step 9: Add real HTTP behavior tests proving route binding and filtered metadata**

Use direct ORM inserts so the test controls exact sort/filter values. Add the following transaction HTTP test:

```python
def test_transaction_list_http_applies_filters_sort_and_filtered_meta(
    client,
    session,
    actor_context,
    internal_auth_headers,
) -> None:
    _seed_read_surface(session, actor_context)
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    first = InventoryTransaction(
        tenant_id="tenant-a",
        operation_type="ADJUST",
        status="FAILED",
        idempotency_key="task105-http-first",
        request_hash="1" * 64,
        reference_type="WORK_ORDER",
        reference_id="WO-HTTP-10.5",
        reason="Task 10.5 HTTP contract",
        actor_user_id="admin-tenant-a",
        actor_roles_json=["ADMIN"],
        request_id="task105-http-first",
        version=1,
        completed_at=base,
    )
    second = InventoryTransaction(
        tenant_id="tenant-a",
        operation_type="ADJUST",
        status="FAILED",
        idempotency_key="task105-http-second",
        request_hash="2" * 64,
        reference_type="WORK_ORDER",
        reference_id="WO-HTTP-10.5",
        reason="Task 10.5 HTTP contract",
        actor_user_id="admin-tenant-a",
        actor_roles_json=["ADMIN"],
        request_id="task105-http-second",
        version=1,
        completed_at=base + timedelta(minutes=1),
    )
    session.add_all([first, second])
    session.commit()

    response = client.get(
        READ_LIST_PATHS["transactions"],
        params={
            "operation_type": "ADJUST",
            "status": "FAILED",
            "reference_type": "WORK_ORDER",
            "reference_id": "WO-HTTP-10.5",
            "sort_by": "completed_at",
            "sort_order": "desc",
            "page": 1,
            "page_size": 1,
        },
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.VIEWER,
            request_id="task105-http-query",
        ),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["pages"] == 2
    assert [item["id"] for item in data["items"]] == [second.id]
```

Add these two HTTP tests so both the balance repository path and nullable service path are bound by the routes:

```python
def test_balance_list_http_exposes_existing_service_filters(
    client,
    session,
    internal_auth_headers,
) -> None:
    facts = _seed_balance_facts(
        session,
        tenant_id="tenant-a",
        suffix="TASK105-BAL-HTTP",
    )
    _seed_balance_facts(
        session,
        tenant_id="tenant-a",
        suffix="TASK105-BAL-OTHER",
    )
    session.commit()

    response = client.get(
        READ_LIST_PATHS["balances"],
        params={
            "warehouse_id": facts["warehouse"].id,
            "spare_part_id": facts["spare_part"].id,
            "location_id": facts["source_location"].id,
            "lot_id": facts["lot"].id,
            "sort_by": "available_quantity",
            "sort_order": "desc",
            "page": 1,
            "page_size": 20,
        },
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.VIEWER,
            request_id="task105-balance-http",
        ),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == [facts["balance"].id]


def test_reservation_list_http_keeps_null_expiry_last(
    client,
    session,
    internal_auth_headers,
) -> None:
    base = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    early = InventoryReservation(
        tenant_id="tenant-a",
        owner_type="MANUAL",
        owner_id="TASK105-HTTP-OWNER",
        status="ACTIVE",
        expires_at=base,
        allow_partial=False,
        actor_user_id="admin-tenant-a",
        actor_roles_json=["ADMIN"],
        request_id="task105-res-http-early",
        version=1,
    )
    late = InventoryReservation(
        tenant_id="tenant-a",
        owner_type="MANUAL",
        owner_id="TASK105-HTTP-OWNER",
        status="ACTIVE",
        expires_at=base + timedelta(hours=1),
        allow_partial=False,
        actor_user_id="admin-tenant-a",
        actor_roles_json=["ADMIN"],
        request_id="task105-res-http-late",
        version=1,
    )
    null_expiry = InventoryReservation(
        tenant_id="tenant-a",
        owner_type="MANUAL",
        owner_id="TASK105-HTTP-OWNER",
        status="ACTIVE",
        expires_at=None,
        allow_partial=False,
        actor_user_id="admin-tenant-a",
        actor_roles_json=["ADMIN"],
        request_id="task105-res-http-null",
        version=1,
    )
    session.add_all([early, late, null_expiry])
    session.commit()

    response = client.get(
        READ_LIST_PATHS["reservations"],
        params={
            "status": "ACTIVE",
            "owner_type": "MANUAL",
            "owner_id": "TASK105-HTTP-OWNER",
            "sort_by": "expires_at",
            "sort_order": "asc",
            "page": 1,
            "page_size": 20,
        },
        headers=_headers(
            internal_auth_headers,
            role=MaintenanceRole.VIEWER,
            request_id="task105-reservation-http",
        ),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 3
    assert [item["id"] for item in data["items"]] == [
        early.id,
        late.id,
        null_expiry.id,
    ]
```


- [ ] **Step 10: Verify test-file syntax and Ruff before running RED**

```powershell
Push-Location $apiRoot
try {
    & $python -m py_compile `
        tests/services/test_inventory_query_service.py `
        tests/api/test_inventory_queries_api.py
    if ($LASTEXITCODE -ne 0) { throw "Task 10.5 RED test syntax failed" }

    & $python -m ruff check `
        tests/services/test_inventory_query_service.py `
        tests/api/test_inventory_queries_api.py
    if ($LASTEXITCODE -ne 0) { throw "Task 10.5 RED test Ruff failed" }
} finally {
    Pop-Location
}
```

Expected: both commands PASS. Syntax/import/fixture failure is not a valid RED.

- [ ] **Step 11: Run the focused RED selection and prove failures are missing-contract failures**

Run the two complete query modules; current production lacks the approved parameters, so this is intentionally RED:

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
        tests/services/test_inventory_query_service.py `
        tests/api/test_inventory_queries_api.py `
        -v
    $redExit = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($redExit -eq 0) {
    throw "Task 10.5 RED unexpectedly passed; inspect whether production already implements the approved contract"
}
```

Valid RED signatures include:

```text
TypeError: ... got an unexpected keyword argument 'sort_by'
TypeError: ... got an unexpected keyword argument 'status'
OpenAPI assertion showing approved query parameters are missing
HTTP behavior showing route ignored/not accepted approved filter/sort parameters
```

Invalid RED signatures include syntax/collection/import/fixture/database-seed/auth/TestClient failures. If any invalid signature appears, fix only the two RED test files and rerun Step 10 + Step 11; do not touch production.

- [ ] **Step 12: RED scope/evidence review and mandatory STOP**

```powershell
& $git -C $repoRoot diff --check
if ($LASTEXITCODE -ne 0) { throw "git diff --check failed" }

$changed = @(& $git -C $repoRoot diff --name-only)
$allowedRed = @(
    "extensions/maintenance-api/tests/api/test_inventory_queries_api.py",
    "extensions/maintenance-api/tests/services/test_inventory_query_service.py"
)
$unexpected = @($changed | Where-Object { $_ -notin $allowedRed })
if ($unexpected.Count -ne 0) {
    throw "Unexpected RED files: $($unexpected -join ', ')"
}

& $git -C $repoRoot status --short
& $git -C $repoRoot diff -- `
    extensions/maintenance-api/tests/services/test_inventory_query_service.py `
    extensions/maintenance-api/tests/api/test_inventory_queries_api.py
& $git -C $repoRoot rev-parse HEAD
& $git -C $repoRoot diff --cached --name-only
```

**STOP.** Present RED test nodes, command, failure count/signatures, harness-health proof, diff, status, staged state and HEAD. Wait for explicit user approval: **“批准 Task 10.5 GREEN”**. Do not commit RED tests and do not modify production before that approval.

---

### Task 2: GREEN — Implement Service and Balance Repository Query Semantics

**Files:**
- Modify: `extensions/maintenance-api/app/services/inventory_query_service.py`
- Modify: `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`
- Test: `extensions/maintenance-api/tests/services/test_inventory_query_service.py`

**Interfaces:**
- Consumes: RED service tests and approved query matrix.
- Produces:
  - `InventoryQueryService.list_balances(..., sort_by: str = "id", sort_order: str = "asc")`
  - `InventoryQueryService.list_transactions(..., operation_type=None, status=None, reference_type=None, reference_id=None, sort_by="id", sort_order="asc")`
  - `InventoryQueryService.list_reservations(..., status=None, owner_type=None, owner_id=None, sort_by="id", sort_order="asc")`
  - `InventoryQueryService.list_transfers(..., status=None, source_warehouse_id=None, source_location_id=None, target_warehouse_id=None, target_location_id=None, reference_type=None, reference_id=None, sort_by="id", sort_order="asc")`
  - `InventoryQueryService.list_stocktakes(..., status=None, warehouse_id=None, location_id=None, sort_by="id", sort_order="asc")`
  - `InventoryLedgerRepository.list_balances(..., sort_by="id", sort_order="asc")`

- [ ] **Step 1: Add SQLAlchemy ordering support and explicit sort maps in `inventory_query_service.py`**

The file already imports `Sequence` from `collections.abc`; only extend the SQLAlchemy import to include `case`. Add resource-local maps near existing constants:

```python
from sqlalchemy import case, func, select

_TRANSACTION_SORT_FIELDS = {
    "id": InventoryTransaction.id,
    "operation_type": InventoryTransaction.operation_type,
    "status": InventoryTransaction.status,
    "completed_at": InventoryTransaction.completed_at,
}
_RESERVATION_SORT_FIELDS = {
    "id": InventoryReservation.id,
    "status": InventoryReservation.status,
    "expires_at": InventoryReservation.expires_at,
}
_TRANSFER_SORT_FIELDS = {
    "id": InventoryTransfer.id,
    "status": InventoryTransfer.status,
    "dispatched_at": InventoryTransfer.dispatched_at,
    "completed_at": InventoryTransfer.completed_at,
}
_STOCKTAKE_SORT_FIELDS = {
    "id": InventoryStocktake.id,
    "status": InventoryStocktake.status,
    "snapshot_at": InventoryStocktake.snapshot_at,
    "confirmed_at": InventoryStocktake.confirmed_at,
}

_NULLABLE_TRANSACTION_SORTS = frozenset({"completed_at"})
_NULLABLE_RESERVATION_SORTS = frozenset({"expires_at"})
_NULLABLE_TRANSFER_SORTS = frozenset({"dispatched_at", "completed_at"})
_NULLABLE_STOCKTAKE_SORTS = frozenset({"confirmed_at"})
_SORT_ORDERS = frozenset({"asc", "desc"})
```

Do not include `tenant_id`, audit fields, private preview fields, or child-row fields in any map.

- [ ] **Step 2: Replace `_list_tenant_rows()` with a filtered, validated, stable parent-page helper**

Keep it private to `InventoryQueryService`; this is not a new generic framework. The helper must receive a concrete per-resource map from the caller:

```python
@staticmethod
def _list_tenant_rows(
    session: Session,
    model: Any,
    tenant_id: str,
    *,
    page: int,
    page_size: int,
    conditions: Sequence[Any] = (),
    sort_by: str = "id",
    sort_order: str = "asc",
    sort_fields: dict[str, Any],
    nullable_sort_fields: frozenset[str] = frozenset(),
) -> tuple[list[Any], int]:
    sort_expression = sort_fields.get(sort_by)
    if sort_expression is None:
        raise ValueError(f"unsupported sort_by: {sort_by}")
    if sort_order not in _SORT_ORDERS:
        raise ValueError(f"unsupported sort_order: {sort_order}")

    all_conditions = [model.tenant_id == tenant_id, *conditions]
    ordering: list[Any] = []
    if sort_by in nullable_sort_fields:
        ordering.append(
            case((sort_expression.is_(None), 1), else_=0).asc()
        )

    primary = (
        sort_expression.desc()
        if sort_order == "desc"
        else sort_expression.asc()
    )
    ordering.append(primary)
    if sort_by != "id":
        ordering.append(
            model.id.desc() if sort_order == "desc" else model.id.asc()
        )

    statement = (
        select(model)
        .where(*all_conditions)
        .order_by(*ordering)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total = int(
        session.scalar(
            select(func.count())
            .select_from(model)
            .where(*all_conditions)
        )
        or 0
    )
    return list(session.scalars(statement).all()), total
```

This exact order guarantees filters and count share the same condition list and pagination occurs after ordering.

- [ ] **Step 3: Extend `list_transactions()` with approved exact filters and sort**

Use only parent columns:

```python
def list_transactions(
    self,
    session: Session,
    actor: ActorContext,
    *,
    page: int,
    page_size: int,
    operation_type: str | None = None,
    status: str | None = None,
    reference_type: str | None = None,
    reference_id: str | None = None,
    sort_by: str = "id",
    sort_order: str = "asc",
) -> PageData[InventoryTransactionRead]:
    conditions = []
    if operation_type is not None:
        conditions.append(InventoryTransaction.operation_type == operation_type)
    if status is not None:
        conditions.append(InventoryTransaction.status == status)
    if reference_type is not None:
        conditions.append(InventoryTransaction.reference_type == reference_type)
    if reference_id is not None:
        conditions.append(InventoryTransaction.reference_id == reference_id)

    rows, total = self._list_tenant_rows(
        session,
        InventoryTransaction,
        actor.tenant_id,
        page=page,
        page_size=page_size,
        conditions=conditions,
        sort_by=sort_by,
        sort_order=sort_order,
        sort_fields=_TRANSACTION_SORT_FIELDS,
        nullable_sort_fields=_NULLABLE_TRANSACTION_SORTS,
    )
```

After this `rows, total` block, leave the existing `entries_by_transaction` grouping and `_transaction_read()` hydration byte-for-byte in the same position; do not move ledger-entry loading before the parent page query.

- [ ] **Step 4: Extend `list_reservations()` with approved filters and nullable sort**

```python
conditions = []
if status is not None:
    conditions.append(InventoryReservation.status == status)
if owner_type is not None:
    conditions.append(InventoryReservation.owner_type == owner_type)
if owner_id is not None:
    conditions.append(InventoryReservation.owner_id == owner_id)

rows, total = self._list_tenant_rows(
    session,
    InventoryReservation,
    actor.tenant_id,
    page=page,
    page_size=page_size,
    conditions=conditions,
    sort_by=sort_by,
    sort_order=sort_order,
    sort_fields=_RESERVATION_SORT_FIELDS,
    nullable_sort_fields=_NULLABLE_RESERVATION_SORTS,
)
```

Keep the existing `InventoryReservationLine` hydration after parent IDs are selected.

- [ ] **Step 5: Extend `list_transfers()` with approved parent filters and nullable sorts**

```python
conditions = []
if status is not None:
    conditions.append(InventoryTransfer.status == status)
if source_warehouse_id is not None:
    conditions.append(InventoryTransfer.source_warehouse_id == source_warehouse_id)
if source_location_id is not None:
    conditions.append(InventoryTransfer.source_location_id == source_location_id)
if target_warehouse_id is not None:
    conditions.append(InventoryTransfer.target_warehouse_id == target_warehouse_id)
if target_location_id is not None:
    conditions.append(InventoryTransfer.target_location_id == target_location_id)
if reference_type is not None:
    conditions.append(InventoryTransfer.reference_type == reference_type)
if reference_id is not None:
    conditions.append(InventoryTransfer.reference_id == reference_id)
```

Pass `_TRANSFER_SORT_FIELDS` and `_NULLABLE_TRANSFER_SORTS` to `_list_tenant_rows()`. Keep line hydration after pagination.

- [ ] **Step 6: Extend `list_stocktakes()` with approved parent filters and nullable sort**

```python
conditions = []
if status is not None:
    conditions.append(InventoryStocktake.status == status)
if warehouse_id is not None:
    conditions.append(InventoryStocktake.warehouse_id == warehouse_id)
if location_id is not None:
    conditions.append(InventoryStocktake.location_id == location_id)
```

Pass `_STOCKTAKE_SORT_FIELDS` and `_NULLABLE_STOCKTAKE_SORTS` to `_list_tenant_rows()`. `snapshot_at` is non-null; only `confirmed_at` enters nullable sort handling.

- [ ] **Step 7: Pass balance sort arguments through `InventoryQueryService.list_balances()`**

Extend the signature with defaults and forward them without changing serial hydration:

```python
sort_by: str = "id",
sort_order: str = "asc",
```

Forward to repository:

```python
sort_by=sort_by,
sort_order=sort_order,
```

- [ ] **Step 8: Extend `InventoryLedgerRepository.list_balances()` with explicit SQL sort mapping**

Import `case` if it is not already imported. Inside `list_balances()` build the approved balance expressions:

```python
available_quantity = (
    InventoryBalance.on_hand_quantity
    - InventoryBalance.reserved_quantity
    - InventoryBalance.damaged_quantity
    - InventoryBalance.quarantined_quantity
)

sort_fields = {
    "id": InventoryBalance.id,
    "warehouse_id": InventoryBalance.warehouse_id,
    "spare_part_id": InventoryBalance.spare_part_id,
    "location_id": InventoryBalance.location_id,
    "lot_id": InventoryBalance.lot_id,
    "on_hand_quantity": InventoryBalance.on_hand_quantity,
    "reserved_quantity": InventoryBalance.reserved_quantity,
    "available_quantity": available_quantity,
}
sort_expression = sort_fields.get(sort_by)
if sort_expression is None:
    raise ValueError(f"unsupported sort_by: {sort_by}")
if sort_order not in {"asc", "desc"}:
    raise ValueError(f"unsupported sort_order: {sort_order}")

ordering = []
if sort_by == "lot_id":
    ordering.append(
        case((sort_expression.is_(None), 1), else_=0).asc()
    )
ordering.append(
    sort_expression.desc()
    if sort_order == "desc"
    else sort_expression.asc()
)
if sort_by != "id":
    ordering.append(
        InventoryBalance.id.desc()
        if sort_order == "desc"
        else InventoryBalance.id.asc()
    )
```

Then replace the existing `.order_by(InventoryBalance.id)` with `.order_by(*ordering)`. Keep the exact same `conditions` object for the page statement and count query.

- [ ] **Step 9: Run service GREEN tests only**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest tests/services/test_inventory_query_service.py -v
    if ($LASTEXITCODE -ne 0) { throw "Task 10.5 service GREEN failed" }
    & $python -m ruff check `
        app/services/inventory_query_service.py `
        app/repositories/inventory_ledger_repository.py `
        tests/services/test_inventory_query_service.py
    if ($LASTEXITCODE -ne 0) { throw "Task 10.5 service GREEN Ruff failed" }
} finally {
    Pop-Location
}
```

Expected: complete service query module PASS, including old summary/balance tests and new Task 10.5 tests.

---

### Task 3: GREEN — Expose Strict HTTP/OpenAPI Query Contract

**Files:**
- Modify: `extensions/maintenance-api/app/api/v1/inventory/queries.py`
- Test: `extensions/maintenance-api/tests/api/test_inventory_queries_api.py`

**Interfaces:**
- Consumes: Task 2 service signatures.
- Produces: strict typed HTTP query contract for all five lists, per-resource duplicate scalar guard, OpenAPI enum constraints.

- [ ] **Step 1: Add approved `Literal` query aliases in `queries.py`**

Extend typing imports:

```python
from typing import Annotated, Any, Literal
```

Import the existing operation type alias:

```python
from app.schemas.inventory_operation import InventoryOperationType
```

Define aliases in the API module so OpenAPI emits finite contracts without creating a new schema file:

```python
SortOrder = Literal["asc", "desc"]
BalanceSortBy = Literal[
    "id", "warehouse_id", "spare_part_id", "location_id", "lot_id",
    "on_hand_quantity", "reserved_quantity", "available_quantity",
]
TransactionSortBy = Literal["id", "operation_type", "status", "completed_at"]
ReservationSortBy = Literal["id", "status", "expires_at"]
TransferSortBy = Literal["id", "status", "dispatched_at", "completed_at"]
StocktakeSortBy = Literal["id", "status", "snapshot_at", "confirmed_at"]

TransactionStatusQuery = Literal[
    "PREVIEWED", "COMPLETED", "PARTIALLY_COMPLETED", "FAILED", "EXPIRED", "REVERSED",
]
ReservationStatusQuery = Literal[
    "ACTIVE", "PARTIALLY_ISSUED", "FULFILLED", "RELEASED", "CANCELLED", "EXPIRED",
]
TransferStatusQuery = Literal[
    "DRAFT", "DISPATCHED", "PARTIALLY_RECEIVED", "COMPLETED", "CANCELLED",
]
StocktakeStatusQuery = Literal[
    "DRAFT", "COUNTING", "REVIEWING", "CONFIRMED", "CONFLICTED", "CANCELLED",
]
```

Do not add aliases for unapproved filters/sorts.

- [ ] **Step 2: Add a per-resource duplicate scalar guard**

Keep `reject_tenant_override()` unchanged for its existing security behavior. Add:

```python
def _duplicate_query_error(
    *,
    parameter: str,
    values: list[str],
) -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "multiple_argument_values",
                "loc": ("query", parameter),
                "msg": "query parameter must be provided at most once",
                "input": values,
            }
        ]
    )


def _reject_duplicate_query_parameters(parameter_names: frozenset[str]):
    async def dependency(request: Request) -> None:
        for parameter in parameter_names:
            values = request.query_params.getlist(parameter)
            if len(values) > 1:
                raise _duplicate_query_error(
                    parameter=parameter,
                    values=values,
                )

    return dependency
```

Define exact per-resource scalar sets:

```python
_COMMON_LIST_QUERY_PARAMS = frozenset({"page", "page_size", "sort_by", "sort_order"})
_BALANCE_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {"warehouse_id", "spare_part_id", "location_id", "lot_id", "serial_item_id"}
)
_TRANSACTION_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {"operation_type", "status", "reference_type", "reference_id"}
)
_RESERVATION_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {"status", "owner_type", "owner_id"}
)
_TRANSFER_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {
        "status", "source_warehouse_id", "source_location_id",
        "target_warehouse_id", "target_location_id", "reference_type", "reference_id",
    }
)
_STOCKTAKE_LIST_QUERY_PARAMS = _COMMON_LIST_QUERY_PARAMS | frozenset(
    {"status", "warehouse_id", "location_id"}
)
```

Bind one dependency per resource:

```python
BalanceListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_BALANCE_LIST_QUERY_PARAMS)),
]
```

Create the remaining dependency aliases explicitly:

```python
TransactionListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_TRANSACTION_LIST_QUERY_PARAMS)),
]
ReservationListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_RESERVATION_LIST_QUERY_PARAMS)),
]
TransferListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_TRANSFER_LIST_QUERY_PARAMS)),
]
StocktakeListQueryGuardDep = Annotated[
    None,
    Depends(_reject_duplicate_query_parameters(_STOCKTAKE_LIST_QUERY_PARAMS)),
]
```

Unknown parameters remain governed by existing FastAPI behavior; only approved known scalar parameters are checked for duplicates.

- [ ] **Step 3: Expose balance filters and sort**

Use this exact dependency/query ordering in `list_balances()` so Python and FastAPI signatures are unambiguous:

```python
def list_balances(
    session: SessionDep,
    actor: ViewerDep,
    _tenant_guard: TenantGuardDep,
    _query_guard: BalanceListQueryGuardDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    warehouse_id: int | None = Query(default=None, gt=0),
    spare_part_id: int | None = Query(default=None, gt=0),
    location_id: int | None = Query(default=None, gt=0),
    lot_id: int | None = Query(default=None, gt=0),
    serial_item_id: int | None = Query(default=None, gt=0),
    sort_by: BalanceSortBy = Query(default="id"),
    sort_order: SortOrder = Query(default="asc"),
):
```

Forward every value to `inventory_query_service.list_balances()`; do not omit any approved filter or sort parameter.

- [ ] **Step 4: Expose transaction filters and sort**

Add:

```python
operation_type: InventoryOperationType | None = Query(default=None),
status: TransactionStatusQuery | None = Query(default=None),
reference_type: str | None = Query(
    default=None,
    min_length=1,
    max_length=64,
    pattern=r".*\S.*",
),
reference_id: str | None = Query(
    default=None,
    min_length=1,
    max_length=128,
    pattern=r".*\S.*",
),
sort_by: TransactionSortBy = Query(default="id"),
sort_order: SortOrder = Query(default="asc"),
```

Place `_query_guard: TransactionListQueryGuardDep` immediately after `_tenant_guard: TenantGuardDep` and before `page`; forward all fields exactly to `list_transactions()`.

- [ ] **Step 5: Expose reservation filters and sort**

```python
status: ReservationStatusQuery | None = Query(default=None),
owner_type: str | None = Query(
    default=None,
    min_length=1,
    max_length=64,
    pattern=r".*\S.*",
),
owner_id: str | None = Query(
    default=None,
    min_length=1,
    max_length=128,
    pattern=r".*\S.*",
),
sort_by: ReservationSortBy = Query(default="id"),
sort_order: SortOrder = Query(default="asc"),
```

Place `_query_guard: ReservationListQueryGuardDep` immediately after `_tenant_guard: TenantGuardDep` and before `page`. Do not strip or lowercase strings; `pattern` only rejects strings with no non-whitespace character. Forward the exact decoded string values.

- [ ] **Step 6: Expose transfer filters and sort**

```python
status: TransferStatusQuery | None = Query(default=None),
source_warehouse_id: int | None = Query(default=None, gt=0),
source_location_id: int | None = Query(default=None, gt=0),
target_warehouse_id: int | None = Query(default=None, gt=0),
target_location_id: int | None = Query(default=None, gt=0),
reference_type: str | None = Query(
    default=None,
    min_length=1,
    max_length=64,
    pattern=r".*\S.*",
),
reference_id: str | None = Query(
    default=None,
    min_length=1,
    max_length=128,
    pattern=r".*\S.*",
),
sort_by: TransferSortBy = Query(default="id"),
sort_order: SortOrder = Query(default="asc"),
```

Place `_query_guard: TransferListQueryGuardDep` immediately after `_tenant_guard: TenantGuardDep` and before `page`; forward exact values to `list_transfers()`.

- [ ] **Step 7: Expose stocktake filters and sort**

```python
status: StocktakeStatusQuery | None = Query(default=None),
warehouse_id: int | None = Query(default=None, gt=0),
location_id: int | None = Query(default=None, gt=0),
sort_by: StocktakeSortBy = Query(default="id"),
sort_order: SortOrder = Query(default="asc"),
```

Place `_query_guard: StocktakeListQueryGuardDep` immediately after `_tenant_guard: TenantGuardDep` and before `page`; forward exact values to `list_stocktakes()`.

- [ ] **Step 8: Keep detail routes and tenant guard unchanged**

Do not add list duplicate guards to detail routes. Keep `TenantGuardDep` on all list/detail routes exactly so existing query/body `tenant_id` rejection remains active.

- [ ] **Step 9: Run API/OpenAPI GREEN**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest tests/api/test_inventory_queries_api.py -v
    if ($LASTEXITCODE -ne 0) { throw "Task 10.5 API GREEN failed" }

    & $python -m ruff check `
        app/api/v1/inventory/queries.py `
        app/services/inventory_query_service.py `
        app/repositories/inventory_ledger_repository.py `
        tests/api/test_inventory_queries_api.py
    if ($LASTEXITCODE -ne 0) { throw "Task 10.5 API GREEN Ruff failed" }
} finally {
    Pop-Location
}
```

Expected: complete API query module PASS, including existing authentication/roles/detail/tenant/private-field contracts plus new Task 10.5 tests.

- [ ] **Step 10: Run both query modules together**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
        tests/services/test_inventory_query_service.py `
        tests/api/test_inventory_queries_api.py `
        -q
    if ($LASTEXITCODE -ne 0) { throw "Task 10.5 combined query GREEN failed" }
} finally {
    Pop-Location
}
```

Expected: all old and new tests PASS; no unexpected skip/xfailed.

---

### Task 4: Local GREEN Regression Ladder and Scope Closure

**Files:**
- Modify: none beyond the five already-approved RED/GREEN files.
- Read/verify: backend tests, Alembic metadata, Git state.

**Interfaces:**
- Consumes: Tasks 1-3 code/test changes.
- Produces: fresh SQLite/local closure evidence; no commit.

- [ ] **Step 1: Run Task 9 API/RBAC/OpenAPI regression**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
        tests/api/test_inventory_api_closure.py `
        tests/api/test_inventory_queries_api.py `
        tests/api/test_inventory_reservations_api.py `
        tests/api/test_inventory_operations_api.py `
        tests/api/test_inventory_transfers_api.py `
        tests/api/test_inventory_stocktakes_api.py `
        tests/security/test_api_rbac.py `
        -q
    if ($LASTEXITCODE -ne 0) { throw "Task 9 API/RBAC regression failed" }
} finally {
    Pop-Location
}
```

Historical baseline was `127 passed`; because Task 10.5 adds tests, do not require exactly 127. Require zero failures, all historical nodes still present, and no unexplained new skip/xfailed.

- [ ] **Step 2: Run the approved focused Inventory Backend selection**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
        tests/models/test_inventory_operation_models.py `
        tests/migrations/test_inventory_operations_migration.py `
        tests/schemas/test_inventory_operation_schemas.py `
        tests/repositories/test_inventory_ledger_immutability.py `
        tests/repositories/test_inventory_ledger_repository.py `
        tests/repositories/test_inventory_reservation_repository.py `
        tests/repositories/test_inventory_transfer_repository.py `
        tests/repositories/test_inventory_stocktake_repository.py `
        tests/services/test_inventory_mutation_plan.py `
        tests/services/test_inventory_transaction_service.py `
        tests/services/test_inventory_fefo_service.py `
        tests/services/test_inventory_reservation_service.py `
        tests/workers/test_inventory_reservation_expiry.py `
        tests/services/test_inventory_operation_preview.py `
        tests/services/test_inventory_freeze.py `
        tests/services/test_inventory_adjust.py `
        tests/services/test_inventory_reversal.py `
        tests/services/test_inventory_transfer_service.py `
        tests/services/test_inventory_stocktake_service.py `
        tests/api/test_inventory_queries_api.py `
        tests/api/test_inventory_reservations_api.py `
        tests/api/test_inventory_operations_api.py `
        tests/api/test_inventory_transfers_api.py `
        tests/api/test_inventory_stocktakes_api.py `
        tests/api/test_inventory_api_closure.py `
        tests/security/test_api_rbac.py `
        tests/integration/test_inventory_operations_workflow.py `
        -q
    if ($LASTEXITCODE -ne 0) { throw "Focused Inventory Backend regression failed" }
} finally {
    Pop-Location
}
```

Historical baseline was `373 passed`; new pass count must be greater than 373 unless test parameterization consolidation changes count with explicit review. Zero failures are mandatory, and no historical node may disappear silently.

- [ ] **Step 3: Run full Ruff**

```powershell
Push-Location $apiRoot
try {
    & $python -m ruff check app tests
    if ($LASTEXITCODE -ne 0) { throw "Full backend Ruff failed" }
} finally {
    Pop-Location
}
```

Expected: `All checks passed!`.

- [ ] **Step 4: Run full backend suite**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Full backend suite failed" }
} finally {
    Pop-Location
}
```

Historical baseline was `1227 passed, 8 deselected, 2 warnings`. Task 10.5 must have zero failures, a larger pass count unless test consolidation is explicitly explained, and no unexplained increase in skip/deselection.

- [ ] **Step 5: Verify Alembic head and no migration diff**

```powershell
Push-Location $apiRoot
try {
    $heads = @(& $python -m alembic heads)
    if ($LASTEXITCODE -ne 0) { throw "alembic heads failed" }
    if (($heads -join "`n") -notmatch "20260803_11 \(head\)") {
        throw "Task 10.5 changed Alembic head unexpectedly"
    }
} finally {
    Pop-Location
}

$migrationChanges = @(& $git -C $repoRoot diff --name-only -- extensions/maintenance-api/alembic)
if ($migrationChanges.Count -ne 0) {
    throw "Task 10.5 must not modify Alembic files"
}
```

- [ ] **Step 6: Verify exact local file scope before PostgreSQL Gate**

```powershell
$allowedAll = @(
    "extensions/maintenance-api/app/api/v1/inventory/queries.py",
    "extensions/maintenance-api/app/repositories/inventory_ledger_repository.py",
    "extensions/maintenance-api/app/services/inventory_query_service.py",
    "extensions/maintenance-api/tests/api/test_inventory_queries_api.py",
    "extensions/maintenance-api/tests/services/test_inventory_query_service.py"
)
$changed = @(& $git -C $repoRoot diff --name-only)
$unexpected = @($changed | Where-Object { $_ -notin $allowedAll })
if ($unexpected.Count -ne 0) {
    throw "Unexpected Task 10.5 files: $($unexpected -join ', ')"
}

& $git -C $repoRoot diff --check
if ($LASTEXITCODE -ne 0) { throw "git diff --check failed" }
& $git -C $repoRoot status --short
& $git -C $repoRoot diff --cached --name-only
```

Expected: exactly the five approved files may be modified; staged state remains empty.

---

### Task 5: Real PostgreSQL Focused Query Gate

**Files:**
- Repository files: read only; no tracked changes.
- Temporary files outside repository: copied query tests + adapted temporary `conftest.py` only.

**Interfaces:**
- Consumes: locally GREEN five-file Task 10.5 diff and operator-provided PostgreSQL connection environment.
- Produces: fresh real-PostgreSQL evidence for filter/sort/tie-break/NULLS LAST/count/pagination; no repository change.

- [ ] **Step 1: Require explicit PostgreSQL client credentials and binaries**

The operator must provide the same class of disposable PostgreSQL access used by the already-verified Real PostgreSQL Gate through standard libpq environment variables:

```powershell
$requiredPgEnv = @("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD")
foreach ($name in $requiredPgEnv) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Missing required PostgreSQL environment variable: $name"
    }
}

$psql = (Get-Command psql.exe -ErrorAction Stop).Source
$createdb = (Get-Command createdb.exe -ErrorAction Stop).Source
$dropdb = (Get-Command dropdb.exe -ErrorAction Stop).Source
$pgDatabase = "maintenance_plan05_4b_task105_gate"
```

Do not persist credentials in repository files or evidence logs.

- [ ] **Step 2: Create an isolated disposable database and verify server identity**

```powershell
& $dropdb --if-exists --force $pgDatabase
if ($LASTEXITCODE -ne 0) { throw "pre-gate dropdb failed" }
& $createdb $pgDatabase
if ($LASTEXITCODE -ne 0) { throw "createdb failed" }

& $psql -d $pgDatabase -v ON_ERROR_STOP=1 -Atc "select version(); show server_encoding;"
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL identity preflight failed" }
```

- [ ] **Step 3: Build a temporary pytest harness outside the repository**

The tracked `tests/conftest.py` intentionally forces SQLite, so do not edit it. Copy only the two Task 10.5 query modules and a temporary conftest:

```powershell
$pgHarness = Join-Path $env:TEMP "maintenance-plan05-4b-task105-pg-harness"
if (Test-Path -LiteralPath $pgHarness) {
    Remove-Item -LiteralPath $pgHarness -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $pgHarness "tests\services") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $pgHarness "tests\api") -Force | Out-Null

Copy-Item `
    (Join-Path $apiRoot "tests\services\test_inventory_query_service.py") `
    (Join-Path $pgHarness "tests\services\test_inventory_query_service.py")
Copy-Item `
    (Join-Path $apiRoot "tests\api\test_inventory_queries_api.py") `
    (Join-Path $pgHarness "tests\api\test_inventory_queries_api.py")
Copy-Item `
    (Join-Path $apiRoot "tests\conftest.py") `
    (Join-Path $pgHarness "tests\conftest.py")

$conftestPath = Join-Path $pgHarness "tests\conftest.py"
$conftest = Get-Content -LiteralPath $conftestPath -Raw
$sqliteAssignment = 'os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"'
$postgresAssignment = 'os.environ["DATABASE_URL"] = os.environ["TASK105_POSTGRES_URL"]'
if (-not $conftest.Contains($sqliteAssignment)) {
    throw "Temporary PostgreSQL harness could not locate the exact SQLite DATABASE_URL assignment"
}
$conftest = $conftest.Replace($sqliteAssignment, $postgresAssignment)
Set-Content -LiteralPath $conftestPath -Value $conftest -Encoding utf8

$env:TASK105_POSTGRES_URL = (& $python -c "import os; from sqlalchemy.engine import URL; print(URL.create('postgresql+psycopg', username=os.environ['PGUSER'], host=os.environ['PGHOST'], port=int(os.environ['PGPORT']), database='$pgDatabase'))").Trim()
if ([string]::IsNullOrWhiteSpace($env:TASK105_POSTGRES_URL)) { throw "Failed to construct PostgreSQL SQLAlchemy URL" }
$env:PYTHONPATH = $apiRoot
```

This adaptation occurs only in `%TEMP%`; tracked `tests/conftest.py` remains untouched.

- [ ] **Step 4: Run the Task 10.5 PostgreSQL query modules through the temporary harness**

```powershell
Push-Location $pgHarness
try {
    & $python -m pytest `
        tests/services/test_inventory_query_service.py `
        tests/api/test_inventory_queries_api.py `
        -q
    if ($LASTEXITCODE -ne 0) { throw "Task 10.5 real PostgreSQL query Gate failed" }
} finally {
    Pop-Location
}
```

Mandatory semantic coverage in these modules includes exact filters, stable tie-break, nullable NULLS LAST in both directions, filtered totals/pages, tenant isolation, HTTP validation/OpenAPI, and default `id ASC`.

- [ ] **Step 5: Verify PostgreSQL dialect/driver and database cleanup state**

```powershell
& $python -c "import os, psycopg; from sqlalchemy import create_engine; engine=create_engine(os.environ['TASK105_POSTGRES_URL']); print(engine.dialect.name); print(engine.dialect.driver); print(psycopg.__version__); c=engine.connect(); print(c.exec_driver_sql('select current_database()').scalar_one()); c.close(); engine.dispose()"
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL runtime proof failed" }
```

Expected dialect `postgresql`, driver `psycopg`.

- [ ] **Step 6: Drop the disposable database and remove the temporary harness**

```powershell
& $dropdb --force $pgDatabase
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL Gate cleanup dropdb failed" }

$exists = (& $psql -d postgres -Atc "select 1 from pg_database where datname = '$pgDatabase';").Trim()
if ($exists -eq "1") { throw "Task 10.5 Gate database still exists after cleanup" }

Remove-Item -LiteralPath $pgHarness -Recurse -Force
Remove-Item Env:TASK105_POSTGRES_URL -ErrorAction SilentlyContinue
```

- [ ] **Step 7: Verify PostgreSQL Gate made no repository changes**

```powershell
$changedAfterPg = @(& $git -C $repoRoot diff --name-only)
$unexpectedAfterPg = @($changedAfterPg | Where-Object { $_ -notin $allowedAll })
if ($unexpectedAfterPg.Count -ne 0) {
    throw "PostgreSQL Gate changed unexpected repository files: $($unexpectedAfterPg -join ', ')"
}
& $git -C $repoRoot diff --check
& $git -C $repoRoot status --short
& $git -C $repoRoot diff --cached --name-only
```

The previous 27-file PostgreSQL Inventory selection is **recommended but not mandatory** for this Task because its prior harness was intentionally temporary and removed. Do not reconstruct unrelated confirmation/concurrency fixture adaptations merely to inflate coverage. The mandatory Task 10.5 PostgreSQL query Gate above directly verifies every new cross-database semantic introduced by this Task.

---

### Task 6: Final Task 10.5 Review Bundle and Mandatory STOP

**Files:**
- Modify: none.
- Review: exactly the five approved files.

**Interfaces:**
- Consumes: fresh local regression + real PostgreSQL query Gate evidence.
- Produces: user-reviewable closure bundle; no commit/push/PR/merge.

- [ ] **Step 1: Re-run the smallest final focused check after PostgreSQL cleanup**

```powershell
Push-Location $apiRoot
try {
    & $python -m pytest `
        tests/services/test_inventory_query_service.py `
        tests/api/test_inventory_queries_api.py `
        -q
    if ($LASTEXITCODE -ne 0) { throw "Post-PostgreSQL focused verification failed" }
    & $python -m ruff check `
        app/api/v1/inventory/queries.py `
        app/services/inventory_query_service.py `
        app/repositories/inventory_ledger_repository.py `
        tests/services/test_inventory_query_service.py `
        tests/api/test_inventory_queries_api.py
    if ($LASTEXITCODE -ne 0) { throw "Post-PostgreSQL focused Ruff failed" }
} finally {
    Pop-Location
}
```

- [ ] **Step 2: Produce exact file/diff/stat evidence**

```powershell
& $git -C $repoRoot diff --check
if ($LASTEXITCODE -ne 0) { throw "final git diff --check failed" }

$changedFinal = @(& $git -C $repoRoot diff --name-only)
$unexpectedFinal = @($changedFinal | Where-Object { $_ -notin $allowedAll })
if ($unexpectedFinal.Count -ne 0) {
    throw "Unexpected final files: $($unexpectedFinal -join ', ')"
}

& $git -C $repoRoot status --short
& $git -C $repoRoot diff --stat
& $git -C $repoRoot diff -- `
    extensions/maintenance-api/app/api/v1/inventory/queries.py `
    extensions/maintenance-api/app/services/inventory_query_service.py `
    extensions/maintenance-api/app/repositories/inventory_ledger_repository.py `
    extensions/maintenance-api/tests/services/test_inventory_query_service.py `
    extensions/maintenance-api/tests/api/test_inventory_queries_api.py
& $git -C $repoRoot diff --cached --name-only
& $git -C $repoRoot rev-parse HEAD
```

Expected staged state: empty.

- [ ] **Step 3: Verify explicit no-touch boundaries**

```powershell
$forbidden = @(& $git -C $repoRoot diff --name-only -- `
    frontend `
    extensions/maintenance-api/alembic `
    extensions/maintenance-api/app/models `
    extensions/maintenance-api/app/workers)
if ($forbidden.Count -ne 0) {
    throw "Task 10.5 touched forbidden scope: $($forbidden -join ', ')"
}
```

- [ ] **Step 4: Present closure evidence and STOP before commit**

The review bundle must state, with fresh command output:

```text
- RED was valid missing-contract RED and production was untouched until GREEN approval.
- Five approved public query matrices are implemented exactly.
- Default id ASC preserved.
- Filter-before-count/page proven.
- Stable same-direction id tie-break proven.
- Nullable sort NULLS LAST proven on SQLite and real PostgreSQL.
- Duplicate known scalar query parameters return 422.
- Invalid ID/status/operation_type/sort return 422.
- OpenAPI exposes constrained enums/query parameters.
- Tenant isolation and tenant override rejection remain intact.
- Task 9 API/RBAC regression PASS.
- Focused Inventory Backend regression PASS.
- Full Ruff PASS.
- Full backend PASS.
- Real PostgreSQL Task 10.5 query Gate PASS.
- Alembic head remains 20260803_11.
- frontend/alembic/models/workers untouched.
- git diff --check PASS.
- staged EMPTY.
- commit NO, push NO, PR NO, merge NO.
```

**STOP.** Wait for explicit user approval before any commit.

---

### Task 7: Commit Only After Separate Explicit Approval

**Files:**
- Stage exactly the five verified Task 10.5 files.
- No other repository writes.

**Interfaces:**
- Consumes: user-approved final Task 10.5 review bundle.
- Produces: one local feature commit only if separately approved.

This task is not authorized by approval of this implementation plan or by approval of GREEN.

- [ ] **Step 1: Re-run commit preflight after user explicitly approves commit**

```powershell
$preCommitStatus = @(& $git -C $repoRoot status --short)
$preCommitStatus | ForEach-Object { Write-Host $_ }

& $git -C $repoRoot diff --check
if ($LASTEXITCODE -ne 0) { throw "pre-commit diff --check failed" }

Push-Location $apiRoot
try {
    & $python -m pytest `
        tests/services/test_inventory_query_service.py `
        tests/api/test_inventory_queries_api.py `
        -q
    if ($LASTEXITCODE -ne 0) { throw "pre-commit Task 10.5 focused tests failed" }
    & $python -m ruff check `
        app/api/v1/inventory/queries.py `
        app/services/inventory_query_service.py `
        app/repositories/inventory_ledger_repository.py `
        tests/services/test_inventory_query_service.py `
        tests/api/test_inventory_queries_api.py
    if ($LASTEXITCODE -ne 0) { throw "pre-commit Task 10.5 Ruff failed" }
} finally {
    Pop-Location
}
```

- [ ] **Step 2: Stage exactly five files and verify staged scope**

```powershell
& $git -C $repoRoot add -- `
    extensions/maintenance-api/app/api/v1/inventory/queries.py `
    extensions/maintenance-api/app/services/inventory_query_service.py `
    extensions/maintenance-api/app/repositories/inventory_ledger_repository.py `
    extensions/maintenance-api/tests/services/test_inventory_query_service.py `
    extensions/maintenance-api/tests/api/test_inventory_queries_api.py
if ($LASTEXITCODE -ne 0) { throw "git add failed" }

$stagedFiles = @(& $git -C $repoRoot diff --cached --name-only)
$unexpectedStaged = @($stagedFiles | Where-Object { $_ -notin $allowedAll })
if ($unexpectedStaged.Count -ne 0 -or $stagedFiles.Count -ne 5) {
    throw "Staged scope mismatch: $($stagedFiles -join ', ')"
}
& $git -C $repoRoot diff --cached --check
```

- [ ] **Step 3: Create one local commit with the approved message**

Suggested commit message:

```text
feat(maintenance): complete inventory list query contracts
```

Command, only after the user separately approves this exact commit action/message:

```powershell
$parent = (& $git -C $repoRoot rev-parse HEAD).Trim()
& $git -C $repoRoot commit -m "feat(maintenance): complete inventory list query contracts"
if ($LASTEXITCODE -ne 0) { throw "Task 10.5 commit failed" }
$newHead = (& $git -C $repoRoot rev-parse HEAD).Trim()
Write-Host "Parent: $parent"
Write-Host "Commit: $newHead"
```

- [ ] **Step 4: Verify commit scope and clean worktree**

```powershell
& $git -C $repoRoot show --stat --oneline --decorate HEAD
& $git -C $repoRoot diff-tree --no-commit-id --name-only -r HEAD
& $git -C $repoRoot status --short
```

Expected commit file set: exactly the five approved files. Expected worktree after commit: clean. Do not push, create/update PR, merge, or start frontend work.

---

## Final Definition of Done

Task 10.5 is complete only when all of the following are evidenced by fresh runs:

- Approved balances filters and sorts implemented.
- Approved transactions filters and sorts implemented.
- Approved reservations filters and sorts implemented.
- Approved transfers filters and sorts implemented.
- Approved stocktakes filters and sorts implemented.
- `page/page_size` semantics unchanged.
- Default `id ASC` unchanged.
- Non-`id` sort has same-direction `id` tie-break.
- Nullable sort uses deterministic NULLS LAST on SQLite and PostgreSQL.
- Filters apply before COUNT and pagination.
- `total/pages` describe the filtered tenant-scoped result set.
- Parent rows are paged before child hydration.
- Service sort allowlists fail closed.
- API emits strict finite `sort_by/sort_order/status/operation_type` contracts.
- Duplicate approved scalar query parameters return `422`.
- Whitespace-only approved string filters return `422` without trimming valid nonblank strings.
- `tenant_id` query/body override remains `422`.
- Legal no-match filter returns `200` empty page.
- Existing detail/read/private-preview contracts remain green.
- Task 9 API/RBAC regression passes.
- Focused Inventory Backend regression passes.
- Full Ruff passes.
- Full backend suite passes.
- Real PostgreSQL focused Task 10.5 query Gate passes.
- Alembic head remains `20260803_11`.
- No migration/index/frontend/model/worker change.
- `git diff --check` passes.
- Commit/push/PR/merge remain separately gated.
- After closure, next phase is Inventory Gap Frontend Design, not Task 11 implementation.
