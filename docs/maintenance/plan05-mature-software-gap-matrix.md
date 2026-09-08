# Plan 05 Mature Software Gap Matrix

This assessment maps selected mature EAM patterns to known Plan 05 work. It is
planning evidence, not a claim of feature parity or proof of runtime behavior.

| 功能域 | 成熟软件能力 | 本项目必要性 | 现有能力 | Plan 05 实现 | 前端页面 | 后端接口 | 数据表 | 权限 | 验收案例 | 状态 | 延后原因 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| item master | Maximo-inspired controlled item master | 维修物料识别与追溯所必需 | 备件、替代件和套件主数据 | Plan 05-02 主数据 | SparePartsPage | /api/v1/spare-parts | spare_parts | maintenance:read | 备件主数据创建和查询 | adopted | 不适用；已纳入 Plan 05 |
| storeroom | Maximo-inspired storeroom hierarchy | 库存归属与运营所必需 | 仓库主数据 | Plan 05-02 主数据 | WarehousesPage | /api/v1/warehouses | warehouses | maintenance:read | 仓库创建和查询 | adopted | 不适用；已纳入 Plan 05 |
| balance | Maximo-inspired on-hand, reserved and available balance | 分配与领用决策所必需 | 库存汇总和账本投影 | Plan 05-04 库存账本 | InventoryBalanceDetail | /api/v1/inventory/balances | inventory_balances | inventory:read | 可用量与在库量展示 | adopted | 不适用；已纳入 Plan 05 |
| reservation | Maximo-inspired inventory reservation | 任务物料保障所必需 | 预留服务设计 | Plan 05-04 预留执行 | InventoryTransactionPage | /api/v1/inventory/reservations | inventory_reservations | inventory:operate | 预留后可用量减少 | adopted | 不适用；已纳入 Plan 05 |
| issue/return | Maximo-inspired issue and return transactions | 账本可审计性所必需 | 库存事务服务设计 | Plan 05-04 库存事务 | InventoryOperationDialog | /api/v1/inventory/transactions | inventory_transactions | inventory:operate | 领用与退回生成账本 | adopted | 不适用；已纳入 Plan 05 |
| transfer | Maximo-inspired inter-storeroom transfer | 跨仓调配所必需 | 库存事务服务设计 | Plan 05-04 库存事务 | InventoryTransactionPage | /api/v1/inventory/transactions | inventory_transactions | inventory:operate | 调拨生成双向账本 | adopted | 不适用；已纳入 Plan 05 |
| stocktake | Maximo-inspired controlled stocktake | 库存校验所必需 | 盘点服务设计 | Plan 05-04 盘点 | StocktakePage | /api/v1/inventory/stocktakes | stocktakes | inventory:operate | 盘点确认创建调整 | adopted | 不适用；已纳入 Plan 05 |
| repairable asset | Maximo-inspired repairable serial tracking | 关键件全生命周期追溯所必需 | 序列号主数据 | Plan 05-02 和 Plan 05-04 批次序列 | LotsSerialsTab | /api/v1/inventory/balances | inventory_lots | maintenance:read | 关键件按序列号查询 | partial | 返修闭环和维修履历不在本阶段 |
| maintenance task material linkage | SAP-inspired maintenance task material linkage | 需求计算和执行所必需 | 任务需求与清单设计 | Plan 05-03 需求清单 | DemandListDetail | /api/v1/demand-lists | demand_list_items | maintenance:read | 任务物料需求生成 | adapted | 不适用；按需求清单模型适配 |
| stock/non-stock distinction | SAP-inspired stock and non-stock classification | 采购边界与库存决策所必需 | 备件分类主数据 | Plan 05-02 主数据 | SparePartsPage | /api/v1/spare-parts | spare_parts | maintenance:read | 库存属性筛选 | partial | 非库存采购流程不在本阶段 |
| availability check | SAP-inspired availability check | 分配前承诺所必需 | 库存缺口预览 | Plan 05-04 分配与缺口 | InventoryGapPage | /api/v1/inventory/balances | inventory_balances | inventory:read | 可用量不足提示 | adopted | 不适用；已纳入 Plan 05 |
| high-priority reassignment | SAP-inspired high-priority reassignment | 紧急任务保障所必需 | 可配置优先级和竞争分配 | Plan 05-04 分配规则 | AllocationPlanDetail | /api/v1/inventory/reservations | inventory_reservations | inventory:operate | 高优先级计划重算后确认 | adapted | 不适用；按确认式分配模型适配 |
| warehouse/location/lot/serial reservation | Oracle-inspired reservation at warehouse, location, lot and serial level | 精确履约所必需 | 仓库、库位、批次和序列数据 | Plan 05-04 FEFO 预留 | LotSerialSelector | /api/v1/inventory/reservations | inventory_balances; inventory_lots; inventory_reservations | inventory:operate | 指定批次预留并校验版本 | adopted | 不适用；已纳入 Plan 05 |
| pick/issue | Oracle-inspired pick and issue execution | 物料出库所必需 | 预留领用服务设计 | Plan 05-04 预留领用 | InventoryOperationDialog | /api/v1/inventory/transactions | inventory_transactions; inventory_ledger_entries | inventory:operate | 按预留领用减少在库和预留 | adopted | 不适用；已纳入 Plan 05 |
| return | Oracle-inspired return execution | 退料可审计性所必需 | 退回事务服务设计 | Plan 05-04 库存事务 | InventoryOperationDialog | /api/v1/inventory/transactions | inventory_transactions; inventory_ledger_entries | inventory:operate | 退回恢复可用量并记录账本 | adopted | 不适用；已纳入 Plan 05 |
| procurement | 采购申请、订单和供应商履约 | 非 Plan 05 库存运营范围 | 供应商主数据仅供参考 | deferred | 无 | 无 | 无 | 无 | 无 | deferred | 采购工作流由后续采购范围负责 |
| accounting ledger | 财务会计分类账与凭证过账 | 非 Plan 05 维修库存范围 | 库存业务账本不是财务账本 | deferred | 无 | 无 | 无 | 无 | 无 | deferred | 财务分类账和凭证集成由财务范围负责 |
| full WMS | 全仓储管理系统，包括波次和库内作业 | 超出维修库存运营范围 | 仅覆盖维修库存库位与预留 | deferred | 无 | 无 | 无 | 无 | 无 | deferred | 完整 WMS 需要独立仓储产品范围 |
| offline scanning | 离线移动扫码和断网同步 | 超出当前 Web 交付范围 | 在线页面与接口 | deferred | 无 | 无 | 无 | 无 | 无 | deferred | 离线客户端、冲突同步和设备管理留待后续阶段 |
