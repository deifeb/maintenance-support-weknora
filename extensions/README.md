# Maintenance Support Extensions

## 说明

该目录用于扩展 WeKnora 的维修保障业务能力。

WeKnora 核心功能（知识库、GraphRAG、Agent、MCP、用户管理等）保持不变。

所有维修器材需求推算、资源配置优化、数据库查询及报告生成等业务能力均放置于本目录中，通过 REST API 或 MCP 与 WeKnora 集成。

---

## 目录规划

```
extensions/
├── maintenance-api/        # FastAPI业务接口
├── maintenance-mcp/        # MCP工具服务
├── demand-engine/          # 需求推算算法
├── allocation-engine/      # 资源配置优化算法
├── database-service/       # 数据查询服务
├── report-service/         # 报告生成
└── shared/                 # 公共工具
```

---

## 开发原则

- 尽量不修改 WeKnora Core
- Python 服务独立部署
- 通过 REST API 或 MCP 接入
- 保持与官方版本兼容