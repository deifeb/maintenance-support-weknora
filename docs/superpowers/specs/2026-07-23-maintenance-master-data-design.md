# Maintenance Master Data Phase Design

## 1. 目标

在现有 `extensions/maintenance-api` 基础上，建设维修器材需求管理系统的完整静态主数据底座，覆盖装备型号、多版本装备构型、部件、维修器材、可靠性参数、多库房库存、供应商和供应商报价，并提供标准 CRUD、构型生命周期管理、受限删除、Excel 多工作表模板、全量校验和事务导入能力。

本阶段继续采用分层模块化单体，不修改 WeKnora Core。后续需求预测、资源配置优化、MCP 和问答系统通过 API 或内部 Service 调用这些主数据。

## 2. 已确认的关键决策

- 架构：规范化关系模型。
- 构型：多版本装备构型。
- 可靠性：模型主表 + 结构化参数字段 + JSON 扩展参数。
- 库存：多库房静态库存。
- 删除：启停状态 + 受限物理删除。
- 采购：供应商级采购参数。
- 导入：Excel 多工作表模板。
- 导入一致性：完整校验通过后一次性事务提交。
- Python：3.11。
- ORM：SQLAlchemy 2.x 同步模式。
- 迁移：Alembic。
- 当前数据库：SQLite，未来兼容 PostgreSQL。

## 3. 范围

### 3.1 本阶段包含

- 10 张核心静态主数据表。
- SQLAlchemy ORM 模型。
- Alembic 初始迁移。
- Repository、Service、API Router。
- 分页、筛选、排序、启停。
- 构型发布、停用、复制和树查询。
- 可靠性模型参数校验。
- 库存数量关系校验。
- 供应商首选报价冲突校验。
- 已引用记录受限删除。
- Excel 模板下载、校验和事务导入。
- 样例数据初始化脚本。
- 自动化测试和 Ruff 检查。
- Swagger 接口文档。

### 3.2 本阶段不包含

- 故障记录。
- 维修工单。
- 器材消耗记录。
- 库存出入库流水。
- 采购订单和补货执行。
- 需求预测算法。
- 资源配置优化算法。
- MCP 接口。
- WeKnora 用户鉴权。
- 单机序列号级构型。
- 批次级库存。
- 乐观锁和审计用户字段。

## 4. 总体架构

```text
FastAPI Router
    ↓
Application Service
    ↓
Repository
    ↓
SQLAlchemy ORM / Unit of Work
    ↓
SQLite / PostgreSQL
```

约束：

- Router 不直接执行 SQL。
- Repository 不承载跨表业务判断。
- Repository 不自行提交事务。
- Service 控制普通操作、构型发布、构型复制和 Excel 导入事务。
- ORM 模型只表达数据库结构和局部约束。
- Pydantic Schema 负责接口输入输出和字段级校验。

## 5. 核心数据模型

### 5.1 装备型号 `equipment_models`

字段：

```text
id                    Integer PK
code                  String(64), unique, indexed
name                  String(200)
category              String(100), nullable
manufacturer          String(200), nullable
model_series          String(100), nullable
service_life_years    Numeric(10,2), nullable
description           Text, nullable
is_active             Boolean, default true
created_at            DateTime(timezone=True)
updated_at            DateTime(timezone=True)
```

规则：

- `code` 全局唯一。
- 已被构型版本引用时禁止物理删除。
- 停用后默认列表不显示。

### 5.2 构型版本 `configuration_versions`

字段：

```text
id                    Integer PK
equipment_model_id    FK equipment_models.id
version_code          String(64)
version_name          String(200)
status                Enum(DRAFT, PUBLISHED, RETIRED)
effective_date        Date, nullable
expiry_date           Date, nullable
is_default            Boolean, default false
is_active             Boolean, default true
source_reference      String(500), nullable
description           Text, nullable
created_at            DateTime(timezone=True)
updated_at            DateTime(timezone=True)
```

约束：

- `(equipment_model_id, version_code)` 唯一。
- 同一装备型号最多一个启用且已发布的默认构型。
- `expiry_date` 晚于 `effective_date`。
- DRAFT 可编辑和物理删除。
- PUBLISHED 不允许直接修改构型明细。
- RETIRED 保留历史，不物理删除。
- 发布前至少存在一条构型明细。
- 发布时所有引用的部件和器材必须启用。

### 5.3 部件 `parts`

字段：

```text
id                    Integer PK
code                  String(64), unique, indexed
name                  String(200)
part_type             String(100), nullable
specification         String(500), nullable
manufacturer          String(200), nullable
unit                  String(32), default "件"
drawing_number        String(100), nullable
maintenance_level     String(64), nullable
description           Text, nullable
is_active             Boolean, default true
created_at            DateTime(timezone=True)
updated_at            DateTime(timezone=True)
```

规则：

- `code` 全局唯一。
- 被构型明细引用时禁止物理删除。

### 5.4 维修器材 `spare_parts`

字段：

```text
id                    Integer PK
code                  String(64), unique, indexed
name                  String(200)
specification         String(500), nullable
category              String(100), nullable
unit                  String(32)
manufacturer          String(200), nullable
material_code         String(100), nullable
national_standard     String(100), nullable
shelf_life_months     Integer, nullable
is_serialized         Boolean, default false
is_repairable         Boolean, default false
is_critical           Boolean, default false
default_service_level Numeric(10,6), nullable
description           Text, nullable
is_active             Boolean, default true
created_at            DateTime(timezone=True)
updated_at            DateTime(timezone=True)
```

规则：

- `code` 全局唯一。
- `shelf_life_months >= 0`。
- `default_service_level` 范围 `(0, 1]`。
- 被构型、可靠性、库存或报价引用时禁止物理删除。

### 5.5 构型明细 `configuration_items`

字段：

```text
id                       Integer PK
configuration_version_id FK configuration_versions.id
item_code                String(64)
parent_item_id           FK configuration_items.id, nullable
part_id                  FK parts.id
spare_part_id            FK spare_parts.id, nullable
install_quantity         Numeric(18,4)
position_code            String(100), nullable
position_name            String(200), nullable
criticality_level        Enum(LOW, MEDIUM, HIGH, CRITICAL)
replacement_ratio        Numeric(10,6), default 1
maintenance_level        String(64), nullable
is_mandatory             Boolean, default true
sort_order               Integer, default 0
notes                    Text, nullable
created_at               DateTime(timezone=True)
updated_at               DateTime(timezone=True)
```

约束：

- `(configuration_version_id, item_code)` 唯一。
- `install_quantity > 0`。
- `replacement_ratio` 范围 `[0, 1]`。
- 父节点必须属于同一构型版本。
- 禁止形成循环层级。
- 已发布构型不允许修改或删除明细。

### 5.6 可靠性参数 `reliability_profiles`

字段：

```text
id                          Integer PK
profile_code                String(64), unique
spare_part_id               FK spare_parts.id
configuration_version_id    FK configuration_versions.id, nullable
model_type                  Enum(
                              EXPONENTIAL,
                              WEIBULL,
                              BINOMIAL,
                              NEGATIVE_BINOMIAL,
                              EMPIRICAL
                            )
failure_rate                Numeric(20,10), nullable
mtbf_hours                  Numeric(20,10), nullable
weibull_shape               Numeric(20,10), nullable
weibull_scale               Numeric(20,10), nullable
binomial_trials             Integer, nullable
binomial_probability        Numeric(20,10), nullable
negative_binomial_r         Numeric(20,10), nullable
negative_binomial_p         Numeric(20,10), nullable
empirical_mean              Numeric(20,10), nullable
empirical_variance          Numeric(20,10), nullable
extension_parameters_json   JSON, nullable
operating_condition_json    JSON, nullable
data_source_type            Enum(
                              DESIGN_PARAMETER,
                              MAINTENANCE_RECORD,
                              TEST_DATA,
                              MANUAL_ESTIMATE,
                              LITERATURE,
                              EXPERT_JUDGMENT
                            )
data_source_reference       String(500), nullable
sample_size                 Integer, nullable
confidence_level            Numeric(10,6), nullable
estimated_at                DateTime(timezone=True), nullable
valid_from                  Date, nullable
valid_to                    Date, nullable
notes                       Text, nullable
is_active                   Boolean, default true
created_at                  DateTime(timezone=True)
updated_at                  DateTime(timezone=True)
```

模型校验：

- EXPONENTIAL：至少提供 `failure_rate > 0` 或 `mtbf_hours > 0`。
- WEIBULL：`weibull_shape > 0` 且 `weibull_scale > 0`。
- BINOMIAL：`binomial_trials > 0` 且 `0 <= p <= 1`。
- NEGATIVE_BINOMIAL：`r > 0` 且 `0 < p <= 1`。
- EMPIRICAL：均值和方差均非负。
- `confidence_level` 范围 `(0, 1]`。
- `valid_to` 晚于 `valid_from`。
- 同一器材、构型、模型类型和有效区间不得存在冲突启用记录。

### 5.7 库房 `warehouses`

字段：

```text
id                    Integer PK
code                  String(64), unique, indexed
name                  String(200)
warehouse_type        String(100), nullable
location              String(500), nullable
organization          String(200), nullable
responsible_person    String(100), nullable
contact               String(100), nullable
status                Enum(NORMAL, FROZEN, COUNTING)
description           Text, nullable
is_active             Boolean, default true
created_at            DateTime(timezone=True)
updated_at            DateTime(timezone=True)
```

规则：

- `code` 全局唯一。
- FROZEN 或 COUNTING 状态下允许查询，不允许库存调整。

### 5.8 库存 `warehouse_inventories`

字段：

```text
id                    Integer PK
warehouse_id          FK warehouses.id
spare_part_id         FK spare_parts.id
on_hand_quantity      Numeric(18,4)
reserved_quantity     Numeric(18,4), default 0
damaged_quantity      Numeric(18,4), default 0
quarantined_quantity  Numeric(18,4), default 0
in_transit_quantity   Numeric(18,4), default 0
safety_stock          Numeric(18,4), default 0
reorder_point         Numeric(18,4), default 0
maximum_stock         Numeric(18,4), nullable
last_counted_at       DateTime(timezone=True), nullable
notes                 Text, nullable
created_at            DateTime(timezone=True)
updated_at            DateTime(timezone=True)
```

派生字段：

```text
available_quantity =
on_hand_quantity
- reserved_quantity
- damaged_quantity
- quarantined_quantity
```

约束：

- `(warehouse_id, spare_part_id)` 唯一。
- 所有数量非负。
- 占用、损坏和隔离数量之和不得大于现存数量。
- `maximum_stock >= reorder_point >= safety_stock`。
- 不提供普通删除接口。

### 5.9 供应商 `suppliers`

字段：

```text
id                    Integer PK
code                  String(64), unique, indexed
name                  String(200)
supplier_type         String(100), nullable
contact_person        String(100), nullable
phone                 String(100), nullable
email                 String(200), nullable
address               String(500), nullable
credit_code           String(100), nullable
rating                Numeric(5,2), nullable
qualification_status  String(100), nullable
description           Text, nullable
is_active             Boolean, default true
created_at            DateTime(timezone=True)
updated_at            DateTime(timezone=True)
```

规则：

- `code` 全局唯一。
- `rating` 范围 `[0, 100]`。
- 被报价引用时禁止物理删除。

### 5.10 供应商报价 `supplier_offers`

字段：

```text
id                         Integer PK
offer_code                 String(64), unique
supplier_id                FK suppliers.id
spare_part_id              FK spare_parts.id
unit_price                 Numeric(18,4)
currency                   String(3), default "CNY"
tax_rate                   Numeric(10,6), nullable
price_includes_tax         Boolean, default true
lead_time_days             Integer
minimum_order_quantity     Numeric(18,4), default 1
order_multiple             Numeric(18,4), default 1
maximum_supply_quantity    Numeric(18,4), nullable
warranty_months            Integer, nullable
quality_level              String(100), nullable
is_preferred               Boolean, default false
valid_from                 Date, nullable
valid_to                   Date, nullable
notes                      Text, nullable
is_active                  Boolean, default true
created_at                 DateTime(timezone=True)
updated_at                 DateTime(timezone=True)
```

约束：

- 单价、交期、订购数量、最大供应量、质保月数非负。
- `order_multiple > 0`。
- `tax_rate` 范围 `[0, 1]`。
- `valid_to` 晚于 `valid_from`。
- 同一器材同一时点最多一个启用首选报价。
- 历史报价保留，不覆盖和物理删除。

## 6. 生命周期和删除规则

### 6.1 启停

所有主数据具有 `is_active`。默认列表只返回启用数据，`include_inactive=true` 可查询停用记录。

### 6.2 物理删除

```text
未被引用
→ 允许物理删除

已被引用
→ HTTP 409 RESOURCE_IN_USE
→ 建议使用停用
```

### 6.3 构型状态

```text
DRAFT
→ 可编辑、可删除、可发布

PUBLISHED
→ 明细锁定、可复制、可停用

RETIRED
→ 只读、保留历史
```

## 7. API 设计

统一前缀：

```text
/api/v1/master-data
```

资源：

```text
/equipment-models
/configuration-versions
/configuration-items
/parts
/spare-parts
/reliability-profiles
/warehouses
/inventories
/suppliers
/supplier-offers
```

每类主数据提供：

```text
POST    创建
GET     分页查询
GET     按 ID 查询
PUT     完整更新
PATCH   局部更新或启停
DELETE  受限物理删除
```

构型专用接口：

```text
POST /configuration-versions/{id}/publish
POST /configuration-versions/{id}/retire
POST /configuration-versions/{id}/clone
GET  /configuration-versions/{id}/tree
```

库存专用接口：

```text
POST /inventories/{id}/adjust
```

## 8. 分页、筛选和排序

通用参数：

```text
page=1
page_size=20
keyword
is_active
include_inactive=false
sort_by
sort_order=asc
```

最大 `page_size=200`。

资源专用筛选：

```text
equipment_model_id
configuration_version_id
spare_part_id
warehouse_id
supplier_id
model_type
status
valid_at
code
```

分页响应：

```json
{
  "success": true,
  "data": {
    "items": [],
    "page": 1,
    "page_size": 20,
    "total": 0,
    "pages": 0
  },
  "message": "Query completed"
}
```

## 9. Service 和 Repository

Service：

```text
EquipmentService
ConfigurationService
PartService
SparePartService
ReliabilityService
WarehouseService
InventoryService
SupplierService
SupplierOfferService
MasterDataImportService
```

Repository：

```text
equipment_repository.py
configuration_repository.py
part_repository.py
spare_part_repository.py
reliability_repository.py
warehouse_repository.py
inventory_repository.py
supplier_repository.py
supplier_offer_repository.py
```

Repository 标准接口：

```text
get_by_id
get_by_code
list
create
update
delete
exists
count_references
```

事务原则：

- Repository 不提交。
- Service 成功后提交。
- 业务异常回滚。
- Excel 整文件单事务。
- 数据库异常转换为受控错误，不泄露 SQL 和路径。

## 10. Excel 模板和导入

模板包含 10 个工作表：

```text
01_装备型号
02_构型版本
03_部件
04_维修器材
05_构型明细
06_可靠性参数
07_库房
08_库存
09_供应商
10_供应商报价
```

关联使用业务编码，不填写数据库 ID。

统一操作列：

```text
operation
```

允许：

```text
CREATE
UPDATE
UPSERT
```

接口：

```text
GET  /api/v1/master-data/import/template
POST /api/v1/master-data/import/validate
POST /api/v1/master-data/import/execute
```

### 10.1 校验流程

```text
文件类型和大小
→ 工作表存在性
→ 表头完整性
→ 字段类型
→ 单表唯一性
→ 跨表编码引用
→ 数据库冲突
→ 构型层级和循环
→ 可靠性参数组合
→ 库存数量关系
→ 报价有效期与首选冲突
→ 导入预览
```

### 10.2 写入顺序

```text
装备型号
→ 部件、维修器材、库房、供应商
→ 构型版本
→ 构型明细
→ 可靠性参数
→ 库存
→ 供应商报价
```

任意错误均不写入。执行接口重新校验，不信任之前的校验结果。

### 10.3 安全限制

- 只接受 `.xlsx`。
- 最大 10 MB。
- 每个工作表最多 10,000 行。
- 不执行公式。
- 不接受 `.xlsm`。
- 不读取宏。
- 临时文件结束后删除。
- 错误响应不返回本地临时路径。

## 11. Alembic

新增：

```text
alembic.ini
alembic/env.py
alembic/script.py.mako
alembic/versions/<initial_revision>.py
```

初始迁移一次建立 10 张表、索引、外键、唯一约束和 Check Constraint。

验证：

```text
空数据库 upgrade head
→ 10 张表存在
→ downgrade -1
→ upgrade head
```

## 12. 数值与类型

```text
库存与安装数量        Numeric(18,4)
采购价格              Numeric(18,4)
可靠性参数            Numeric(20,10)
概率、比例和税率      Numeric(10,6)
交付周期、样本数      Integer
```

Python 层使用 `Decimal`，不使用 `float` 直接持久化金额和关键参数。

枚举在数据库中保存可读字符串。JSON 使用 SQLAlchemy JSON 类型。

## 13. 样例数据

命令：

```powershell
python -m app.scripts.seed_master_data
```

至少生成：

- 2 个装备型号。
- 每个装备 2 个构型版本。
- 15 个部件。
- 20 种维修器材。
- 30 条构型明细。
- 5 种可靠性模型示例。
- 3 个库房。
- 多库房库存。
- 4 个供应商。
- 多供应商报价。

脚本幂等，不生成重复编码，不包含真实企业数据。

## 14. 测试

新增约 60～90 个测试，目录：

```text
tests/models
tests/repositories
tests/services
tests/api
tests/imports
tests/migrations
```

覆盖：

- ORM 字段和数据库约束。
- 唯一编码。
- 外键引用。
- 构型循环和父子层级。
- 构型发布、复制和停用。
- 可靠性模型参数组合。
- 库存数量关系。
- 首选报价冲突。
- 受限删除。
- 分页、筛选和排序。
- Excel 模板。
- Excel 表头、类型、重复和引用错误。
- 导入失败事务回滚。
- 导入成功数量和关联。
- 迁移升级、回退和再次升级。
- API 不泄露 SQL、路径和堆栈。
- 实施计划 01 的 9 个测试继续通过。

## 15. 依赖

新增运行依赖：

```text
alembic
openpyxl
python-multipart
```

保持 Python 3.11、FastAPI、Pydantic 2、SQLAlchemy 2 同步模式。

## 16. 批量实施方式

提供 ZIP：

```text
apply-master-data-phase.ps1
payload/
```

脚本：

```text
检查仓库和 .venv
→ 备份受影响文件
→ 写入源码和迁移
→ 安装新增依赖
→ 创建测试数据库
→ Alembic upgrade/downgrade/upgrade
→ 运行全部测试
→ Ruff 检查
→ 生成 Excel 模板
→ 输出 Git 检查和提交命令
```

脚本不自动执行 Git commit 或 push。任一验证失败立即停止。

## 17. 验收标准

- 10 张核心表存在。
- 迁移升级、回退和再次升级成功。
- CRUD API 可用。
- 构型发布、复制、停用和树查询可用。
- 非法可靠性、库存和报价被拒绝。
- 已引用主数据不能物理删除。
- Excel 模板可下载。
- Excel 校验和全事务导入可用。
- 样例数据可重复初始化。
- 全部测试通过。
- Ruff 无错误。
- 原有 9 个测试继续通过。
- Swagger 展示全部新增接口。
