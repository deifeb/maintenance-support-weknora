# Plan 05-4B Task 10.5 Inventory Server-Side List Query Contract Completion 设计规格

**状态：** 已完成逐节评审并获用户整体批准；仅授权形成设计规格文档，不授权实施计划、RED/GREEN、production 修改、frontend 修改、commit、push、PR 或 merge。

**批准日期：** 2026-08-16

**所属阶段：** Plan 05-4B Inventory Operations and Stocktake

**性质：** 05-4B 增量设计补充规格；扩展但不替换：

- `docs/superpowers/specs/2026-08-04-maintenance-plan05-04b-inventory-operations-design.md`
- `docs/superpowers/plans/2026-08-03-maintenance-plan05-04b-inventory-operations-stocktake.md`

**设计基线：** `codex/maintenance-plan05-4b` 已关闭 Backend Gate 1，并已完成真实 PostgreSQL Gate；Frontend Inventory Gap 尚未开始。设计时远端分支检查到 HEAD `dfb7498737fb7610826c36c6827946798767c6a0`（`docs(maintenance): record real postgres gate verification`）。

---

## 1. 背景

Plan 05-4B 后端核心已经完成：Inventory mutation plan、reservation、issue/return/release、reservation expiry、transfer、freeze/unfreeze/adjust/reverse、stocktake、API/RBAC、integration workflow 与真实 PostgreSQL Gate 均已形成经过验证的后端基线。

当前已经存在五类 Inventory read list：

```text
GET /api/v1/inventory/balances
GET /api/v1/inventory/transactions
GET /api/v1/inventory/reservations
GET /api/v1/inventory/transfers
GET /api/v1/inventory/stocktakes
```

以及对应 detail GET。

现有 read surface 已经实现 authentication、viewer/contributor/admin read access、`ActorContext.tenant_id` tenant scope、`tenant_id` query/body override rejection、`PageData` envelope、detail tenant isolation、transaction private preview storage filtering 等合同。

但当前五个 list route 主要只暴露 `page` / `page_size`。`InventoryQueryService.list_balances()` 已经具备 `warehouse_id`、`spare_part_id`、`location_id`、`lot_id`、`serial_item_id` 等过滤能力，但尚未形成统一 HTTP filter/sort contract；transactions、reservations、transfers、stocktakes 仍基本只有 tenant + pagination。

因此，在进入 Task 11 Inventory Gap typed frontend API / Store / UI 之前，需要先补齐已规划但当前实现缺失的 server-side filter / sort / pagination query contract。

Task 10.5 不是新的库存子系统，也不是重新打开已关闭的 Backend Gate 核心设计；它是在当前已验证 read surface 上完成一个 **additive API contract extension**。

---

## 2. 目标

Task 10.5 的目标是：

> 在不改变已经验证完成的 Inventory 写入核心、状态机、RBAC、ledger、migration 和并发语义的前提下，为五类现有 Inventory list 建立稳定、严格验证、跨 SQLite/PostgreSQL 一致、可供 Task 11 typed frontend API 使用的 server-side filter / sort / pagination contract。

统一执行模型：

```text
ActorContext.tenant_id
        ↓
tenant scope
        ↓
resource-specific filters
        ↓
COUNT(filtered rows)
        ↓
validated server-side sort
        ↓
stable ID tie-break
        ↓
OFFSET / LIMIT
        ↓
parent-page hydration
        ↓
PageData[T]
```

核心顺序固定为：

```text
FILTER → COUNT → SORT → PAGE
```

明确禁止：

```text
PAGE → Python filter
PAGE → Python sort
```

否则 `total` / `pages` 将不再代表真实服务器过滤集合。

---

## 3. 已冻结基线

Task 10.5 不重新设计以下已经实现并通过 Gate 的能力：

- `ActorContext.tenant_id` 是唯一 tenant 来源；
- authentication；
- viewer / contributor / admin read access；
- `tenant_id` query/body override rejection；
- success/meta envelope；
- `PageData` response envelope；
- 五类 detail GET；
- cross-tenant detail 404；
- transaction private preview storage filtering；
- reservation 状态机；
- transfer 状态机；
- stocktake 状态机；
- FEFO；
- reservation expiry worker 与惰性 expiry；
- idempotency；
- immutable ledger；
- mutation-plan / transaction kernel；
- PostgreSQL locking / concurrency semantics。

Task 10.5 必须保持这些合同兼容。

---

## 4. 非目标

Task 10.5 不包含：

- frontend implementation；
- Inventory Gap UI；
- 新 migration；
- 新 table；
- 预先新增 index；
- generic query DSL / framework；
- cursor pagination；
- snapshot pagination；
- keyword / full-text search；
- master-data name/code search；
- multi-value filter；
- line-level spare-part filter；
- reservation / transfer / stocktake 状态机修改；
- FEFO 修改；
- ledger 修改；
- worker 修改；
- write API 修改。

若实施阶段发现必须增加 migration / index 才能完成批准合同，则必须 STOP 并返回设计审批，不得自行扩大范围。

---

## 5. 公共 Pagination Contract

所有五类 list 继续使用：

```text
page
page_size
```

约束：

```text
page >= 1
1 <= page_size <= 100
```

默认：

```text
page = 1
page_size = 20
```

保持当前 API 行为。

`PageData` 语义：

```text
items      当前页结果
page       当前请求页
page_size  当前请求页大小
total      tenant scope + filters 后、pagination 前的总记录数
pages      ceil(total / page_size)
```

若 `page` 超过末页，返回：

```text
HTTP 200
items = []
```

不返回 404。

---

## 6. 公共 Sort Contract

所有五类 list 新增统一参数：

```text
sort_by
sort_order
```

`sort_order` 仅允许：

```text
asc
desc
```

大小写敏感；公共 API 使用小写。

非法值，例如：

```text
sort_order=ASC
sort_order=DESC
sort_order=ascending
sort_order=foo
```

返回 FastAPI validation `422`，不新增业务错误码。

默认保持：

```text
sort_by = id
sort_order = asc
```

该默认行为与当前 `_list_tenant_rows()` 的 `ORDER BY id ASC` 保持兼容。Task 10.5 不把现有列表偷偷改成 latest-first。Task 11 如需最新优先，应显式发送：

```text
sort_by=id&sort_order=desc
```

---

## 7. 稳定排序

如果：

```text
sort_by=id
```

则：

```sql
ORDER BY id ASC|DESC
```

如果：

```text
sort_by != id
```

必须追加 `id` 作为稳定 tie-break，并让 tie-break 方向跟随主排序方向。

例如：

```text
sort_by=status
sort_order=asc
```

等价于：

```sql
ORDER BY status ASC, id ASC
```

下降：

```sql
ORDER BY status DESC, id DESC
```

这保证同一数据状态下跨 page 的排序确定性。

---

## 8. NULL 排序

所有 nullable sort field 统一：

> **NULL 永远排最后。**

适用字段包括但不限于：

- `lot_id`；
- `completed_at`；
- `expires_at`；
- `dispatched_at`；
- `confirmed_at`。

不得依赖 SQLite 与 PostgreSQL 的默认 NULL 排序。

推荐使用 portable ordering，例如：

```sql
ORDER BY
    CASE WHEN completed_at IS NULL THEN 1 ELSE 0 END ASC,
    completed_at DESC,
    id DESC
```

以明确保证跨数据库一致性。

---

## 9. Balances Query Contract

当前 `InventoryQueryService.list_balances()` 已经真实支持：

```text
warehouse_id
spare_part_id
location_id
lot_id
serial_item_id
```

Task 10.5 将这些现有 service 能力提升为正式 HTTP contract，并增加 server-side sort。

### 9.1 Filters

```text
warehouse_id: int > 0
spare_part_id: int > 0
location_id: int > 0
lot_id: int > 0
serial_item_id: int > 0
```

多个 filter 使用 `AND`。

### 9.2 Sorts

```text
id
warehouse_id
spare_part_id
location_id
lot_id
on_hand_quantity
reserved_quantity
available_quantity
```

`available_quantity` 必须使用数据库表达式：

```text
on_hand_quantity
- reserved_quantity
- damaged_quantity
- quarantined_quantity
```

不能先分页后使用 Python `sorted()`。

Task 10.5 暂不把 `damaged_quantity`、`quarantined_quantity`、`in_transit_quantity` 扩大为永久公共 sort contract；未来如有明确 UI 需求可 additive extension。

---

## 10. Transactions Query Contract

当前 transaction 聚合已稳定包含：

```text
operation_type
status
reference_type
reference_id
completed_at
```

### 10.1 Filters

```text
operation_type
status
reference_type
reference_id
```

`operation_type` 复用既有 Inventory operation type 公共集合：

```text
OPENING
ADJUST
RESERVE
UNRESERVE
ISSUE
RETURN
TRANSFER_DISPATCH
TRANSFER_RECEIVE
FREEZE
UNFREEZE
REVERSE
STOCKTAKE_CONFIRM
```

`status` 只允许当前 transaction 状态：

```text
PREVIEWED
COMPLETED
PARTIALLY_COMPLETED
FAILED
EXPIRED
REVERSED
```

### 10.2 Sorts

```text
id
operation_type
status
completed_at
```

以下内部字段不得进入查询 contract：

```text
request_hash
response_snapshot_json
confirmation_token_hash
actor_roles_json
```

以及其他 private preview storage。

---

## 11. Reservations Query Contract

当前 reservation 聚合包含：

```text
owner_type
owner_id
status
expires_at
allow_partial
```

### 11.1 Filters

```text
status
owner_type
owner_id
```

`status` 只允许：

```text
ACTIVE
PARTIALLY_ISSUED
FULFILLED
RELEASED
CANCELLED
EXPIRED
```

### 11.2 Sorts

```text
id
status
expires_at
```

Task 10.5 不新增：

```text
expires_before
expires_after
```

以避免提前扩大到 datetime range / timezone query contract。

---

## 12. Transfers Query Contract

当前 transfer 聚合直接保存：

```text
status
source_warehouse_id
source_location_id
target_warehouse_id
target_location_id
reference_type
reference_id
dispatched_at
completed_at
```

### 12.1 Filters

```text
status
source_warehouse_id
source_location_id
target_warehouse_id
target_location_id
reference_type
reference_id
```

`status` 只允许：

```text
DRAFT
DISPATCHED
PARTIALLY_RECEIVED
COMPLETED
CANCELLED
```

### 12.2 Sorts

```text
id
status
dispatched_at
completed_at
```

---

## 13. Stocktakes Query Contract

当前 stocktake 聚合直接保存：

```text
warehouse_id
location_id
status
snapshot_at
confirmed_at
```

### 13.1 Filters

```text
status
warehouse_id
location_id
```

`status` 只允许：

```text
DRAFT
COUNTING
REVIEWING
CONFIRMED
CONFLICTED
CANCELLED
```

### 13.2 Sorts

```text
id
status
snapshot_at
confirmed_at
```

---

## 14. 完整 Contract Matrix

| Resource | Filters | Sorts |
|---|---|---|
| balances | `warehouse_id`, `spare_part_id`, `location_id`, `lot_id`, `serial_item_id` | `id`, `warehouse_id`, `spare_part_id`, `location_id`, `lot_id`, `on_hand_quantity`, `reserved_quantity`, `available_quantity` |
| transactions | `operation_type`, `status`, `reference_type`, `reference_id` | `id`, `operation_type`, `status`, `completed_at` |
| reservations | `status`, `owner_type`, `owner_id` | `id`, `status`, `expires_at` |
| transfers | `status`, `source_warehouse_id`, `source_location_id`, `target_warehouse_id`, `target_location_id`, `reference_type`, `reference_id` | `id`, `status`, `dispatched_at`, `completed_at` |
| stocktakes | `status`, `warehouse_id`, `location_id` | `id`, `status`, `snapshot_at`, `confirmed_at` |

所有资源另外统一拥有：

```text
page
page_size
sort_by
sort_order
```

---

## 15. Filter 语义

第一版全部使用：

```text
single exact value
```

多个 filter：

```text
AND
```

字符串 filter 使用 exact、case-sensitive equality。

暂不支持：

```text
status=A&status=B
status=A,B
keyword
q
search
ILIKE
contains
prefix search
```

不自动 lower，也不自动 trim。

---

## 16. Master-Data 与 Child-Row 边界

Task 10.5 不新增：

```text
warehouse_code
warehouse_name
spare_part_code
spare_part_name
```

Task 11 应通过已有 master-data selector 获得 ID，再发送：

```text
warehouse_id
spare_part_id
location_id
```

Task 10.5 同样暂不增加：

```text
reservation spare_part_id
transfer spare_part_id
stocktake spare_part_id
```

因为这些字段属于 line-level 数据，需要 `EXISTS` / child join，会把本 Task 扩大为跨聚合查询设计。

---

## 17. API Validation

API 层负责：

```text
HTTP typing
range validation
enum validation
string length
duplicate scalar guard
tenant override guard
```

### 17.1 ID 参数

以下 ID filter 统一要求 `int > 0`：

```text
warehouse_id
spare_part_id
location_id
lot_id
serial_item_id
source_warehouse_id
source_location_id
target_warehouse_id
target_location_id
```

非法：

```text
0
-1
abc
```

→ `422`。

合法但不存在：

```text
warehouse_id=999999
```

→ `200` + empty page，不是 404。

### 17.2 字符串长度

```text
owner_type      1..64
owner_id        1..128
reference_type  1..64
reference_id    1..128
```

empty / whitespace-only 输入视为非法 query，返回 `422`。

字符串不自动 trim；`"WO-123"` 与 `" WO-123 "` 不等价。

---

## 18. Duplicate Single-Value Query Contract

第一版明确是 single-value query，因此重复已知 scalar parameter 统一拒绝：

```text
status=ACTIVE&status=EXPIRED
page=1&page=2
sort_by=id&sort_by=status
sort_order=asc&sort_order=desc
```

→ `422`。

不得让 FastAPI 的 first-wins / last-wins 偶然 scalar parsing 成为公共合同。

---

## 19. Unknown Query Parameters

Task 10.5 不顺带建立全局 strict-query policy。

继续保留已经存在的安全特殊规则：

```text
tenant_id query/body → 422
```

因为 tenant 只能来自 `ActorContext.tenant_id`。

其他 unknown query parameter 的全局策略不属于本 Task。

---

## 20. API → Service → Repository 职责边界

冻结架构：

```text
queries.py
│
├─ public HTTP contract
├─ enum/range validation
├─ duplicate scalar guard
└─ tenant override guard
        ↓
InventoryQueryService
│
├─ actor.tenant_id
├─ resource filter semantics
├─ explicit sort allowlist
├─ fail closed
└─ aggregate hydration
        ↓
SQL / existing repository
```

Task 10.5 不建立 Generic Query Framework。

---

## 21. Balance Repository 边界

balances 继续使用：

```text
InventoryLedgerRepository.list_balances()
```

因为现有 repository 已负责 balance identity、`serial_item_id` filtering、count 与 pagination。

Task 10.5 只在现有路径上扩展 approved server-side sorting，不重新搬迁架构。

---

## 22. 其他四类聚合的 Parent-Page Hydration

transactions / reservations / transfers / stocktakes 继续沿用现有 service 结构：

```text
query/filter parent
→ sort parent
→ paginate parent
→ parent IDs
→ load child rows
→ group child rows
→ build read model
```

禁止：

```text
JOIN child rows
→ paginate joined rows
```

否则一个 parent 多条 line 会导致：

- duplicate parent；
- `total` 错误；
- `page_size` 错误；
- stable pagination 错误。

---

## 23. SQL Sort 安全

公共 `sort_by` 必须通过显式映射：

```text
"id"           → Model.id
"status"       → Model.status
"completed_at" → Model.completed_at
...
```

禁止：

```python
getattr(model, sort_by)
text(sort_by)
literal_column(sort_by)
f"ORDER BY {sort_by}"
```

客户端永远不能直接决定 SQL identifier。

现有 Inventory export 已使用显式 sort expression whitelist；Task 10.5 延续这一项目风格。

---

## 24. 双层 Fail-Closed

即使 API 已经 validation，service 仍必须维护自己的 sort allowlist。

目的：

```text
HTTP caller
    → API validation

internal caller
    → service allowlist
```

非法内部调用不能 silently fallback 到 `id`，而应失败。

正常 HTTP 流程仍由 API validation 返回 `422`；不新增新的 HTTP business error code。

---

## 25. Filter SQL 与 COUNT 一致性

所有 filter 必须进入 SQL `WHERE`，并在 pagination 前执行。

页面查询与 count query 必须共享完全相同的 `conditions`：

```sql
SELECT ...
FROM resource
WHERE tenant_condition
  AND filter_1
  AND filter_2
ORDER BY ...
OFFSET ...
LIMIT ...
```

对应：

```sql
SELECT count(*)
FROM resource
WHERE tenant_condition
  AND filter_1
  AND filter_2
```

因此：

```text
total = filtered tenant rows
```

而不是 tenant 的所有 rows。

---

## 26. SQLite / PostgreSQL 一致性

Task 10.5 必须保证两个数据库具有相同 API 语义：

```text
tenant filtering
exact equality
COUNT semantics
sort direction
ID tie-break
NULL placement
pagination
```

明确禁止依赖：

- database default NULL ordering；
- unordered SELECT；
- database-specific collation assumption；
- Python post-sort。

---

## 27. Pagination Consistency Level

Task 10.5 继续使用：

```text
OFFSET / LIMIT
```

不改成 cursor pagination。

稳定排序只保证：

> 在同一数据状态下，分页顺序确定。

不保证用户从 page 1 翻到 page 2 期间发生写入时，两页仍属于同一数据库快照。

即：

```text
stable ordering ≠ snapshot pagination
```

Task 10.5 不引入 cursor、snapshot token 或 repeatable-read browsing session。

---

## 28. COUNT Consistency Level

继续使用：

```text
COUNT query
+
page SELECT query
```

不为普通 read list 引入 `SERIALIZABLE` / `REPEATABLE READ`。

极端并发下两个 statement 之间如发生写入，`total` 与 `items` 理论上可能观察到相邻数据库状态；这是当前普通 read-committed list semantics，可接受。

---

## 29. OpenAPI Contract

完成后 OpenAPI 必须显式公开：

```text
page
page_size
sort_by
sort_order
resource-specific filters
```

其中：

```text
status
operation_type
sort_by
sort_order
```

必须表现为有限 enum / constrained values，而不是无约束 string。

Task 11 typed frontend API 应基于该冻结 HTTP/OpenAPI contract，不应靠阅读 Python service signature 推测参数。

---

## 30. HTTP 错误合同

Task 10.5 不新增业务错误码。

| 条件 | 结果 |
|---|---|
| 未认证 | `401` |
| 不满足既有读取权限 | 保持现有权限错误合同 |
| `tenant_id` override | `422` |
| `page=0` | `422` |
| `page_size=101` | `422` |
| invalid status | `422` |
| invalid operation_type | `422` |
| invalid sort_by | `422` |
| invalid sort_order | `422` |
| invalid ID | `422` |
| duplicate single-value query | `422` |
| legal filter but no rows | `200` + empty page |
| page beyond last page | `200` + empty items |
| detail ID missing / cross-tenant | 保持现有 `404` |

明确禁止：

```text
invalid sort_by → silently use id
invalid status  → silently return []
```

---

## 31. 性能边界

Task 10.5 默认：

```text
NO migration
NO new index
```

理由：

- `page_size <= 100`；
- 当前聚合已经存在 tenant/status 等已有索引；
- balance identity 与常用列已有索引；
- 尚无真实性能证据证明必须做 schema 变化。

若后续实际性能测试证明某个 approved query 需要 index，再做证据驱动的独立优化设计。

---

## 32. 测试架构

Task 10.5 测试分为四层：

1. Service semantic contract；
2. API / OpenAPI contract；
3. Existing backend regression；
4. Real PostgreSQL incremental query gate。

核心目标：证明新增 query contract，同时保护已经关闭的 Backend/PostgreSQL Gate 合同。

---

## 33. Service Semantic Contract

主要文件：

```text
extensions/maintenance-api/tests/services/test_inventory_query_service.py
```

### 33.1 Balances

必须覆盖：

- `warehouse_id`；
- `spare_part_id`；
- `location_id`；
- `lot_id`；
- `serial_item_id`；
- `sort_by`；
- `sort_order`；
- `page` / `page_size`；
- `available_quantity` SQL sort；
- filtered total；
- tenant isolation；
- stable tie-break。

### 33.2 Transactions

必须覆盖：

- `operation_type`；
- `status`；
- `reference_type`；
- `reference_id`；
- sort；
- page；
- filtered total；
- tenant isolation。

fixture 至少包含：

```text
tenant-a matching rows >= 2
tenant-a non-matching row >= 1
tenant-b matching row >= 1
```

### 33.3 Reservations

必须覆盖：

- `status`；
- `owner_type`；
- `owner_id`；
- `expires_at` NULLS LAST。

无论 asc / desc，NULL `expires_at` 都必须排最后。

### 33.4 Transfers

必须覆盖：

- `status`；
- source warehouse/location；
- target warehouse/location；
- `reference_type` / `reference_id`；
- `dispatched_at` / `completed_at` NULLS LAST。

### 33.5 Stocktakes

必须覆盖：

- `status`；
- `warehouse_id`；
- `location_id`；
- `snapshot_at`；
- `confirmed_at` NULLS LAST。

---

## 34. Stable Pagination Test

必须制造多个具有相同主排序值的 parent：

```text
id=10 status=ACTIVE
id=11 status=ACTIVE
id=12 status=ACTIVE
```

请求：

```text
sort_by=status
sort_order=desc
page_size=1
```

必须：

```text
page 1 → id 12
page 2 → id 11
page 3 → id 10
```

证明稳定 `id DESC` tie-break，而不是数据库偶然顺序。

---

## 35. Filter-Before-Pagination Test

必须设计能够区分“正确 server filter”与“错误 page 后 filter”的 fixture。

示例：

```text
10 transactions total
3 rows status=FAILED
```

请求：

```text
status=FAILED
page=2
page_size=2
```

必须：

```text
total=3
pages=2
page 2 items=1
```

---

## 36. API / OpenAPI Contract Tests

主要文件：

```text
extensions/maintenance-api/tests/api/test_inventory_queries_api.py
```

必须证明五个 endpoint 公开批准后的 query parameters，并验证 `status`、`operation_type`、`sort_by`、`sort_order` 是 constrained contract。

不能只做 OpenAPI introspection；还必须有真实 HTTP behavior test，证明 route 真正把 filter/sort/page 绑定到 service。

---

## 37. API Validation Matrix

至少覆盖：

```text
page=0            → 422
page=-1           → 422
page_size=0       → 422
page_size=101     → 422
warehouse_id=0    → 422
warehouse_id=-1   → 422
warehouse_id=abc  → 422
sort_order=ASC    → 422
sort_order=DESC   → 422
sort_order=foo    → 422
invalid sort_by   → 422
invalid status    → 422
duplicate scalar  → 422
```

合法但不存在的 filter：

```text
200 + empty page
```

---

## 38. Security Regression

每类 query semantic fixture 都必须包含：

```text
tenant-a matching row
tenant-a non-matching row
tenant-b matching row
```

确保新 filter 永远不能绕过 tenant scope。

既有：

```text
?tenant_id=tenant-b
GET body {"tenant_id":"tenant-b"}
```

→ `422` 合同继续保持。

transaction private preview storage tests 必须继续 PASS。

---

## 39. Default Backward Compatibility Test

必须有明确测试证明：

> 未传 `sort_by` / `sort_order` 时，结果仍按 `id ASC`。

Task 10.5 不能把 additive extension 变成 breaking default-order change。

---

## 40. RED 阶段边界

正式 RED 阶段只允许修改：

```text
extensions/maintenance-api/tests/services/test_inventory_query_service.py
extensions/maintenance-api/tests/api/test_inventory_queries_api.py
```

RED 阶段禁止修改：

```text
app/**
frontend/**
alembic/**
migration
docs
```

必须同时产生三类 RED 证据：

```text
Service semantic RED
API/OpenAPI RED
real HTTP behavior RED
```

---

## 41. 有效 RED

有效 RED failure 包括：

- service signature 不接受批准后的参数；
- OpenAPI 缺少批准参数；
- route 没有绑定 service filter/sort；
- filter 行为错误；
- sort / tie-break 错误；
- NULL ordering 错误；
- filtered total/pages 错误；
- tenant scope 错误；
- validation 错误。

必须证明失败来自：

> 当前 production 尚未实现已批准 query contract。

---

## 42. 无效 RED / Harness Failure

以下 failure 不允许进入 GREEN：

```text
SyntaxError
IndentationError
ImportError
ModuleNotFoundError
fixture not found
database table missing
seed IntegrityError caused by test setup
auth helper failure
invalid TestClient usage
test collection error
```

RED 执行前必须先证明测试文件自身可解析并通过静态检查；只有 production contract failure 才是有效 RED。

---

## 43. RED Gate / STOP

有效 RED 得到后必须 STOP，并提交证据：

```text
test nodes
pytest command
failure count
failure signatures
missing-contract explanation
harness health proof
git diff
git diff --check
git status
staged state
HEAD
```

然后等待单独批准：

> **批准 Task 10.5 GREEN**

不得因为 RED 正确就自动修改 production。

---

## 44. GREEN 原则

GREEN 只实现本设计批准合同。

禁止顺手增加：

```text
keyword search
multi-status
cursor pagination
line-level filters
migration
index
frontend
generic query framework
```

---

## 45. GREEN Verification Ladder

### Gate A — Task 10.5 Focused

运行 Task 10.5 service + API/OpenAPI contracts。

要求：全部 PASS。

### Gate B — Full Query Modules

```text
tests/services/test_inventory_query_service.py
tests/api/test_inventory_queries_api.py
```

要求：全部 PASS。

### Gate C — Task 9 API/RBAC Regression

运行原 Task 9 API/RBAC/OpenAPI selection。

历史基线：

```text
127 passed
```

新增 Task 10.5 tests 后不要求固定 127，而要求：

```text
所有历史合同仍 PASS
新增合同 PASS
无 unexpected skip/xfailed
```

### Gate D — Focused Inventory Backend

原 Backend Gate focused Inventory 历史基线：

```text
373 passed
```

新增测试后要求：

```text
pass count > 373
0 failures
无历史测试消失或无解释 skip
```

### Gate E — Ruff

```text
python -m ruff check app tests
```

要求：

```text
All checks passed!
```

### Gate F — Full Backend

历史基线：

```text
1227 passed
8 deselected
2 warnings
```

新增测试后要求：

```text
0 failures
pass count > 1227
无未解释 skip/deselection 增加
```

历史 pass count 只是基线，不是新增测试后的固定数字。

---

## 46. Real PostgreSQL Incremental Query Gate

Task 10.5 不重新证明未修改的：

- migration round-trip；
- mutation locking；
- idempotency race；
- expiry race；
- transaction kernel 并发设计。

这些已经由 Real PostgreSQL Gate 验证。

但 Task 10.5 新定义了跨数据库查询语义，因此必须在真实 PostgreSQL 上增量验证：

```text
filter
sort
stable tie-break
NULLS LAST
filtered total
pagination
```

最低必需：

```text
Task 10.5 focused PostgreSQL query tests
```

Closure 推荐再运行原 PostgreSQL Inventory focused selection。

历史基线：

```text
368 passed
7 skipped
```

七个 skip 是明确的 SQLite-only `PRAGMA foreign_keys` model tests；不得无解释扩大 skip 范围。

---

## 47. Migration Contract

Task 10.5：

```text
NO MIGRATION
```

最终 Alembic head 必须仍为：

```text
20260803_11
```

纯查询变化不需要重新执行完整 migration round-trip；如果最终需要 migration，则必须返回设计审批。

---

## 48. Repository Scope Gate

Task 10.5 closure 必须证明：

```text
frontend/**           untouched
alembic/**            untouched
migration             untouched
inventory write core  untouched
FEFO                   untouched
worker                 untouched
```

预计 production 修改区域仅限查询合同需要的现有层：

```text
app/api/v1/inventory/queries.py
app/services/inventory_query_service.py
app/repositories/inventory_ledger_repository.py
```

但这不是 RED 或 GREEN 的预授权文件清单；最终精确实施文件范围必须在后续 Implementation Plan 中再次冻结并单独审批。

---

## 49. Definition of Done

只有以下全部满足，Task 10.5 才允许宣布完成：

1. 五类 approved filters 全部实现；
2. 五类 approved sorts 全部实现；
3. `sort_by` / `sort_order` 严格验证；
4. 默认仍为 `id ASC`；
5. 非 id 排序有稳定 id tie-break；
6. nullable sort 字段跨 DB 始终 NULLS LAST；
7. filter 在 pagination 前执行；
8. `total` / `pages` 基于过滤后集合；
9. tenant isolation 对所有新 filter 成立；
10. duplicate single-value query → `422`；
11. invalid ID / status / sort → `422`；
12. legal no-match → `200` empty page；
13. OpenAPI 完整描述新合同；
14. query module regression PASS；
15. Task 9 API/RBAC regression PASS；
16. focused Inventory backend PASS；
17. Ruff PASS；
18. full backend PASS；
19. real PostgreSQL focused query Gate PASS；
20. PostgreSQL Inventory focused regression（closure 推荐）无回归；
21. Alembic head 仍为 `20260803_11`；
22. no migration；
23. no frontend change；
24. `git diff --check` PASS；
25. scope 可审计；
26. commit / push / PR / merge 均仍需分别明确批准。

---

## 50. Task 10.5 Closure 后的状态转换

Task 10.5 closure 后 **不直接实施 Task 11**。

正确流程：

```text
Task 10.5 Backend Query Contract
        ✓
        ↓
Backend API Frozen for Inventory Gap
        ↓
Inventory Gap Frontend Design
        ↓
用户逐节审批
        ↓
正式 Frontend Design Spec
        ↓
用户整体批准
        ↓
Frontend Implementation Plan
        ↓
用户批准
        ↓
Task 11+ RED / Implementation
```

因此 Task 10.5 是正式进入 Inventory Gap 前端设计前的最后一道后端查询合同门。

---

## 51. 审批与执行边界

本设计规格的批准只表示：

- Task 10.5 设计语义已冻结；
- 可以形成正式设计文档；
- 在用户审阅正式文档后，可以开始编写详细 Implementation Plan。

本批准 **不表示**：

- 批准 RED；
- 批准 GREEN；
- 批准修改 production；
- 批准修改 frontend；
- 批准 commit；
- 批准 push；
- 批准创建/更新 PR；
- 批准 merge；
- 批准自动进入 Task 11。

后续所有 Gate 继续保持独立审批。
