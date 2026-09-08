# Plan 05-4A Inventory Ledger Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用库位、批次/序列号、余额、事务和不可变账本建立权威库存事实，并把所有现有库存读取和导入导出迁移到新合同。

**Architecture:** `InventoryQueryService` 负责聚合读取，`InventoryTransactionService` 是唯一余额写入口，repository 负责 tenant-scoped 查询与固定顺序加锁。迁移将旧 `warehouse_inventories` 映射到 `DEFAULT` 库位和 opening ledger 后删除旧表；旧 API 保持查询兼容，但调整改走 admin-only 账本命令。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2、Alembic、Pydantic、pytest、SQLite 测试/PostgreSQL 生产。

## Global Constraints

- 基线为 `ca59e7e24eff3c52da2b0d887dfd74f23e1f1173`；迁移 revision 固定为 `20260803_08`，`down_revision = "20260731_07"`。
- 数量使用 `Decimal`/`Numeric(18,4)`，API 使用十进制字符串；禁止 float 进入数量运算。
- `available = on_hand - reserved - damaged - quarantined`；`in_transit` 不可用，所有分量非负，且 `reserved + damaged + quarantined <= on_hand`。
- `InventoryTransactionService` 是生产代码唯一可修改 balance/lot/serial state 的入口；ledger entry 只追加、不更新、不删除。
- 所有写命令从 actor 取 tenant，要求 `Idempotency-Key` 与 expected version；相同 key/不同 request hash 返回 `IDEMPOTENCY_KEY_REUSED`。
- 多余额锁按 balance ID 升序；事务内重新校验版本、policy、lot/serial 与数量。
- 本阶段不实现 FEFO、reservation、issue/return、transfer、stocktake、review 或 allocation。
- 每个 Task 严格先执行 RED 测试并观察预期失败，再写最小实现；不得一次性实现后补测试。

---

## Task 1: 建立库存模型与迁移链

**Files:**

- Create: `extensions/maintenance-api/app/models/inventory_ledger.py`
- Modify: `extensions/maintenance-api/app/models/inventory.py`
- Modify: `extensions/maintenance-api/app/models/__init__.py`
- Create: `extensions/maintenance-api/alembic/versions/20260803_08_inventory_ledger_foundation.py`
- Create: `extensions/maintenance-api/tests/migrations/test_inventory_ledger_migration.py`
- Create: `extensions/maintenance-api/tests/models/test_inventory_ledger_models.py`

- [ ] **Step 1: 写迁移 RED 测试**

在 `test_inventory_ledger_migration.py` 创建旧版 `warehouse_inventories` 数据，升级到 `20260803_08` 后断言：每个 warehouse 有唯一 `DEFAULT` location；policy/balance 数量保持；transaction 类型是 `MIGRATION_OPENING`；ledger delta 与 before/after state 守恒；旧表不存在。再覆盖 downgrade/re-upgrade，以及存在非 DEFAULT location、lot 或 serial 时 downgrade 抛出明确 `CommandError`。

```python
def test_upgrade_backfills_default_location_and_opening_ledger(connection):
    upgrade_to(connection, "20260731_07")
    seed_legacy_inventory(connection, on_hand="12.500", reserved="2.000")
    upgrade_to(connection, "20260803_08")

    location = one(connection, "warehouse_locations")
    balance = one(connection, "inventory_balances")
    entry = one(connection, "inventory_ledger_entries")
    assert location["code"] == "DEFAULT"
    assert str(balance["on_hand_quantity"]) == "12.5000"
    assert str(entry["reserved_delta"]) == "2.0000"
    assert not table_exists(connection, "warehouse_inventories")
```

- [ ] **Step 2: 运行 RED**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_inventory_ledger_migration.py tests/models/test_inventory_ledger_models.py -q
```

预期：revision 和 `app.models.inventory_ledger` 尚不存在而失败。

- [ ] **Step 3: 写最小模型与迁移**

模型必须包含规格第 6.1 节的八张表和唯一约束。核心事务/账本字段固定如下：

```python
class InventoryTransaction(Base, TimestampMixin):
    __tablename__ = "inventory_transactions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "operation_type", "idempotency_key",
            name="uq_inventory_tx_tenant_operation_idempotency",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    operation_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    reference_type: Mapped[str | None] = mapped_column(String(64))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(String(500))
    confirmation_token_hash: Mapped[str | None] = mapped_column(String(64))
    confirmation_expires_at: Mapped[datetime | None]
    actor_user_id: Mapped[str] = mapped_column(String(128))
    actor_roles_json: Mapped[list[str]] = mapped_column(JSON)
    request_id: Mapped[str] = mapped_column(String(128))
    reversed_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"))
    version: Mapped[int] = mapped_column(default=1)
    completed_at: Mapped[datetime | None]
    failed_at: Mapped[datetime | None]

class InventoryLedgerEntry(Base, TimestampMixin):
    __tablename__ = "inventory_ledger_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("inventory_transactions.id"))
    balance_id: Mapped[int] = mapped_column(ForeignKey("inventory_balances.id"))
    spare_part_id: Mapped[int]
    warehouse_id: Mapped[int]
    location_id: Mapped[int]
    lot_id: Mapped[int | None]
    serial_item_id: Mapped[int | None]
    on_hand_delta: Mapped[Decimal]
    reserved_delta: Mapped[Decimal]
    damaged_delta: Mapped[Decimal]
    quarantined_delta: Mapped[Decimal]
    in_transit_delta: Mapped[Decimal]
    state_before_json: Mapped[dict] = mapped_column(JSON)
    state_after_json: Mapped[dict] = mapped_column(JSON)
    before_balance_version: Mapped[int]
    resulting_balance_version: Mapped[int]
```

迁移 backfill 在一个 upgrade transaction 中完成。事务状态约束使用 `PREVIEWED`、`COMPLETED`、`PARTIALLY_COMPLETED`、`FAILED`、`EXPIRED`、`REVERSED`；lot quality 和 serial state 使用规格 6.1 的完整枚举。downgrade 先检测新域是否只剩可无损聚合的 DEFAULT/no-lot/no-serial 数据，不满足就 `raise CommandError("inventory ledger contains granular facts")`。

- [ ] **Step 4: 运行 GREEN 与迁移往返**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_inventory_ledger_migration.py tests/models/test_inventory_ledger_models.py -q
.\.venv\Scripts\python.exe -m alembic upgrade 20260803_08
.\.venv\Scripts\python.exe -m alembic downgrade 20260731_07
.\.venv\Scripts\python.exe -m alembic upgrade 20260803_08
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/models extensions/maintenance-api/alembic/versions/20260803_08_inventory_ledger_foundation.py extensions/maintenance-api/tests/migrations/test_inventory_ledger_migration.py extensions/maintenance-api/tests/models/test_inventory_ledger_models.py
git commit -m "feat(maintenance): add inventory ledger schema"
```

## Task 2: 建立 tenant-scoped repository 与聚合查询合同

**Files:**

- Create: `extensions/maintenance-api/app/repositories/inventory_ledger_repository.py`
- Create: `extensions/maintenance-api/app/schemas/inventory_ledger.py`
- Create: `extensions/maintenance-api/app/services/inventory_query_service.py`
- Create: `extensions/maintenance-api/tests/repositories/test_inventory_ledger_repository.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_query_service.py`

- [ ] **Step 1: 写 RED 测试**

覆盖 tenant A 永远看不到 tenant B；warehouse/part/location/lot/serial 过滤；分页 total/pages；聚合后与旧 API 数量口径一致；`lock_balances()` 无论输入顺序如何都按 ID 排序。SQLite 断言生成的锁顺序，PostgreSQL 方言编译断言包含 `FOR UPDATE`。

```python
def test_summary_aggregates_only_actor_tenant(session, actor_context):
    seed_balance(session, tenant_id="tenant-a", on_hand="8")
    seed_balance(session, tenant_id="tenant-b", on_hand="99")
    page = inventory_query_service.list_summaries(
        session, actor_context(tenant_id="tenant-a"), page=1, page_size=20
    )
    assert page.total == 1
    assert page.items[0].on_hand_quantity == Decimal("8")
```

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repositories/test_inventory_ledger_repository.py tests/services/test_inventory_query_service.py -q
```

预期：repository/query service 尚不存在。

- [ ] **Step 3: 写最小实现**

`InventoryBalanceRead` 同时返回物理分量、`available_quantity`、`version`、location/lot/serial identity；`InventorySummaryRead` 按 warehouse+part 聚合并保留旧 API 所需 policy 字段。所有 repository 方法第一个业务过滤条件必须是 `tenant_id == actor.tenant_id`。

```python
def lock_balances(self, session, tenant_id: str, balance_ids: Sequence[int]):
    ids = sorted(set(balance_ids))
    return list(session.scalars(
        select(InventoryBalance)
        .where(InventoryBalance.tenant_id == tenant_id, InventoryBalance.id.in_(ids))
        .order_by(InventoryBalance.id)
        .with_for_update()
    ))
```

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repositories/test_inventory_ledger_repository.py tests/services/test_inventory_query_service.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/repositories/inventory_ledger_repository.py extensions/maintenance-api/app/schemas/inventory_ledger.py extensions/maintenance-api/app/services/inventory_query_service.py extensions/maintenance-api/tests/repositories/test_inventory_ledger_repository.py extensions/maintenance-api/tests/services/test_inventory_query_service.py
git commit -m "feat(maintenance): add inventory ledger queries"
```

## Task 3: 建立 opening/adjust 事务核心与不可变账本

**Files:**

- Create: `extensions/maintenance-api/app/services/inventory_transaction_service.py`
- Create: `extensions/maintenance-api/app/repositories/inventory_transaction_repository.py`
- Modify: `extensions/maintenance-api/app/schemas/inventory_ledger.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_transaction_service.py`
- Create: `extensions/maintenance-api/tests/repositories/test_inventory_ledger_immutability.py`

- [ ] **Step 1: 写 RED 测试**

覆盖 OPENING 与 ADJUST：tenant 来自 actor；contributor 不能 adjust；expected balance version 冲突；负余额拒绝；delta 合计等于 state before/after；相同幂等请求返回同一 transaction；key 重用不同 payload 报错；rollback 不留下 transaction/entry；禁止 repository 更新或删除 ledger entry。

```python
def test_adjust_is_idempotent_and_balanced(session, actor_admin, balance):
    first = inventory_transaction_service.adjust(
        session, actor_admin, balance_id=balance.id,
        expected_version=balance.version,
        deltas=InventoryQuantityDelta(on_hand=Decimal("3")),
        reason="cycle correction", idempotency_key="adj-1",
    )
    replay = inventory_transaction_service.adjust(
        session, actor_admin, balance_id=balance.id,
        expected_version=balance.version,
        deltas=InventoryQuantityDelta(on_hand=Decimal("3")),
        reason="cycle correction", idempotency_key="adj-1",
    )
    assert replay.id == first.id
    assert first.entries[0].state_after_json["on_hand"] == "3.0000"
```

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_transaction_service.py tests/repositories/test_inventory_ledger_immutability.py -q
```

- [ ] **Step 3: 写最小事务实现**

规范化 payload 用排序 JSON + SHA-256。先查询幂等记录，再锁 balance，比较 expected version，构造 before/after，验证所有分量非负及 `reserved + damaged + quarantined <= on_hand`，写 balance、transaction、entry 和响应快照，最后由 caller transaction commit。数量操作至少一个 delta 非零；冻结等未来零 delta 操作必须有不同的 before/after state。

```python
with session.begin_nested():
    existing = tx_repo.get_idempotent(session, actor.tenant_id, operation, key)
    if existing:
        return replay_or_raise(existing, request_hash)
    balance = ledger_repo.lock_one(session, actor.tenant_id, balance_id)
    require_version(balance.version, expected_version)
    before = quantity_state(balance)
    after = apply_delta(before, deltas)
    validate_non_negative(after)
    transaction = tx_repo.create(
        session,
        tenant_id=actor.tenant_id,
        operation_type=operation,
        idempotency_key=key,
        request_hash=request_hash,
        actor=actor,
    )
    ledger_repo.append_entry(transaction, balance, before, after, deltas)
```

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_inventory_transaction_service.py tests/repositories/test_inventory_ledger_immutability.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/inventory_transaction_service.py extensions/maintenance-api/app/repositories/inventory_transaction_repository.py extensions/maintenance-api/app/schemas/inventory_ledger.py extensions/maintenance-api/tests/services/test_inventory_transaction_service.py extensions/maintenance-api/tests/repositories/test_inventory_ledger_immutability.py
git commit -m "feat(maintenance): add inventory transaction core"
```

## Task 4: 迁移库存 API 并关闭 contributor 直接调整

**Files:**

- Modify: `extensions/maintenance-api/app/api/v1/master_data/inventories.py`
- Modify: `extensions/maintenance-api/app/services/inventory_service.py`
- Modify: `extensions/maintenance-api/app/repositories/inventory_repository.py`
- Modify: `extensions/maintenance-api/app/schemas/inventory.py`
- Modify: `extensions/maintenance-api/tests/security/test_api_rbac.py`
- Create: `extensions/maintenance-api/tests/api/test_inventory_ledger_api.py`
- Modify: `extensions/maintenance-api/tests/security/test_master_data_crud_call_contracts.py`

- [ ] **Step 1: 写 RED API/RBAC 测试**

断言现有 list/get 响应由新 summary 提供；create/update 只维护 policy/DEFAULT identity，不能直接设置物理数量；`POST /master-data/inventories/{id}/adjust` 需要 admin、Idempotency-Key 和 expected_version，并返回 transaction/最新 summary；跨 tenant ID 是 404；精确 route inventory 仍通过。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_inventory_ledger_api.py tests/security/test_api_rbac.py tests/security/test_master_data_crud_call_contracts.py -q
```

预期：旧 adjust 仍接受 contributor/直接改 `WarehouseInventory`，测试失败。

- [ ] **Step 3: 改为 query/transaction service**

route 保留 URL 兼容，但 dependency 改为 `AdminDep`；请求体使用 `expected_version`、五类 delta 和 reason；route 只调用 service，不 `session.get()` 后直接赋数量。同步精确 RBAC 映射。

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_inventory_ledger_api.py tests/security/test_api_rbac.py tests/security/test_master_data_crud_call_contracts.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/api/v1/master_data/inventories.py extensions/maintenance-api/app/services/inventory_service.py extensions/maintenance-api/app/repositories/inventory_repository.py extensions/maintenance-api/app/schemas/inventory.py extensions/maintenance-api/tests/api/test_inventory_ledger_api.py extensions/maintenance-api/tests/security/test_api_rbac.py extensions/maintenance-api/tests/security/test_master_data_crud_call_contracts.py
git commit -m "refactor(maintenance): route inventory adjustments through ledger"
```

## Task 5: 迁移 Dashboard、需求计算和 AI 库存读取

**Files:**

- Modify: `extensions/maintenance-api/app/services/dashboard_service.py`
- Modify: `extensions/maintenance-api/app/services/demand_calculation_service.py`
- Modify: `extensions/maintenance-api/app/services/ai_tool_adapters.py`
- Modify: `extensions/maintenance-api/app/repositories/warehouse_repository.py`
- Modify: `extensions/maintenance-api/app/repositories/spare_part_repository.py`
- Modify: `extensions/maintenance-api/app/models/catalog.py`
- Modify: `extensions/maintenance-api/tests/services/test_dashboard_service.py`
- Modify: `extensions/maintenance-api/tests/services/test_inventory_gap_service.py`
- Create: `extensions/maintenance-api/tests/services/test_inventory_consumers_use_ledger.py`

- [ ] **Step 1: 写 RED 消费者测试**

只 seed 新 balance/lot/location，不创建旧 row，断言 dashboard 低库存、demand calculation inventory snapshot、AI tool inventory response、warehouse/spare-part 删除保护均正确；tenant B 数量不泄漏。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_dashboard_service.py tests/services/test_inventory_gap_service.py tests/services/test_inventory_consumers_use_ledger.py -q
```

- [ ] **Step 3: 注入统一查询合同**

所有消费者调用 `InventoryQueryService.summary_for_part()`/`summaries_for_parts()`；移除 `WarehouseInventory` relationship 和运行时 import。需求计算快照继续使用相同 JSON key，但来源改为新聚合。

- [ ] **Step 4: 运行 GREEN 并扫描旧引用**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_dashboard_service.py tests/services/test_inventory_gap_service.py tests/services/test_inventory_consumers_use_ledger.py -q
rg -n "WarehouseInventory|warehouse_inventories" app --glob "*.py"
```

预期：扫描只允许 Alembic 历史兼容说明；`app/` 运行时代码为零引用。

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/dashboard_service.py extensions/maintenance-api/app/services/demand_calculation_service.py extensions/maintenance-api/app/services/ai_tool_adapters.py extensions/maintenance-api/app/repositories/warehouse_repository.py extensions/maintenance-api/app/repositories/spare_part_repository.py extensions/maintenance-api/app/models/catalog.py extensions/maintenance-api/tests/services
git commit -m "refactor(maintenance): read inventory from ledger balances"
```

## Task 6: 迁移主数据导入、导出与 seed

**Files:**

- Modify: `extensions/maintenance-api/app/services/import_service.py`
- Modify: `extensions/maintenance-api/app/exporters/master_data_excel.py`
- Modify: `extensions/maintenance-api/app/scripts/seed_master_data.py`
- Modify: `extensions/maintenance-api/tests/imports/test_import_task_worker.py`
- Modify: `extensions/maintenance-api/tests/imports/test_import_tenant_scope.py`
- Modify: `extensions/maintenance-api/tests/exporters/test_master_data_excel.py`
- Create: `extensions/maintenance-api/tests/imports/test_inventory_import_ledger.py`

- [ ] **Step 1: 写 RED 兼容测试**

`08_库存` 仍接受现有模板字段，但导入通过 OPENING/ADJUST transaction 写 DEFAULT balance 和 ledger；重复任务不重复入账；跨 tenant 不覆盖；导出聚合值与导入一致；seed 重跑幂等。

- [ ] **Step 2: 运行 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/imports/test_inventory_import_ledger.py tests/imports/test_import_task_worker.py tests/imports/test_import_tenant_scope.py tests/exporters/test_master_data_excel.py -q
```

- [ ] **Step 3: 写最小 adapter**

导入 service 将每一行规范化为 inventory command，幂等 key 使用 `import:{task_id}:08_库存:{row_number}`；禁止 bulk update balance。导出通过 query service 聚合为旧模板列。seed 使用固定 `seed:inventory:{tenant}:{warehouse}:{part}` key。

- [ ] **Step 4: 运行 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/imports/test_inventory_import_ledger.py tests/imports/test_import_task_worker.py tests/imports/test_import_tenant_scope.py tests/exporters/test_master_data_excel.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add extensions/maintenance-api/app/services/import_service.py extensions/maintenance-api/app/exporters/master_data_excel.py extensions/maintenance-api/app/scripts/seed_master_data.py extensions/maintenance-api/tests/imports extensions/maintenance-api/tests/exporters/test_master_data_excel.py
git commit -m "refactor(maintenance): migrate inventory import export to ledger"
```

## Task 7: 05-4A 集成 Gate 与关闭复审

**Files:**

- Create: `extensions/maintenance-api/tests/integration/test_inventory_ledger_foundation.py`
- Create: `docs/superpowers/reviews/2026-08-03-maintenance-plan05-04a-closure-review.md`

- [ ] **Step 1: 写端到端 RED 测试**

通过 API 建 policy/DEFAULT balance、admin adjustment，再从 dashboard、demand snapshot 和 export 读取同一事实；断言 transaction/ledger audit 完整，tenant B 404，重放不重复。

- [ ] **Step 2: 运行 RED 并补最小接线**

```powershell
cd extensions/maintenance-api
.\.venv\Scripts\python.exe -m pytest tests/integration/test_inventory_ledger_foundation.py -q
```

只修复集成暴露的 wiring，不加入 05-4B 行为。

- [ ] **Step 3: 运行阶段 Gate**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/migrations/test_inventory_ledger_migration.py tests/models/test_inventory_ledger_models.py tests/repositories/test_inventory_ledger_repository.py tests/repositories/test_inventory_ledger_immutability.py tests/services/test_inventory_query_service.py tests/services/test_inventory_transaction_service.py tests/services/test_inventory_consumers_use_ledger.py tests/api/test_inventory_ledger_api.py tests/imports/test_inventory_import_ledger.py tests/integration/test_inventory_ledger_foundation.py tests/security/test_api_rbac.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic heads
rg -n "WarehouseInventory|warehouse_inventories" app --glob "*.py"
```

预期：一个 head `20260803_08`；全量通过；运行时旧库存引用为零。

- [ ] **Step 4: 请求审查并写 Closure Review**

使用 `superpowers:requesting-code-review`。Review 必须逐项核对规格 05-4A、记录新鲜测试数量/warning、迁移 downgrade 拒绝证据、旧消费者扫描结果和残留风险。

- [ ] **Step 5: 验证并提交关闭文档**

使用 `superpowers:verification-before-completion` 重跑 Gate 后：

```powershell
git add extensions/maintenance-api/tests/integration/test_inventory_ledger_foundation.py docs/superpowers/reviews/2026-08-03-maintenance-plan05-04a-closure-review.md
git commit -m "test(maintenance): close plan05-4a inventory ledger"
git status --short
```

- [ ] **Step 6: 停止并请求批准**

报告 commits、Gate 和 Closure Review；等待用户分别批准 05-4A push/PR 更新及进入 05-4B。不得自动开始下一阶段。
