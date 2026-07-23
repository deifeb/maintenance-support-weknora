# Maintenance Support API

维修器材需求管理系统的独立 Python 业务服务。当前版本提供配置读取、SQLite/SQLAlchemy 连接、健康检查、系统信息、统一响应和异常处理。

## 环境要求

- Python 3.11
- Windows PowerShell
- Git

## 创建环境

```powershell
cd E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

## 启动服务

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

## 地址

- 根接口：`http://127.0.0.1:8100/`
- 健康检查：`http://127.0.0.1:8100/health`
- 系统信息：`http://127.0.0.1:8100/api/v1/system/info`
- Swagger：`http://127.0.0.1:8100/docs`

## 测试

```powershell
python -m pytest -v
python -m ruff check app tests
```

## 数据库

默认数据库文件为 `data/maintenance.db`。可通过 `.env` 中的 `DATABASE_URL` 切换为其他 SQLite 文件或 PostgreSQL。数据库文件、虚拟环境和 `.env` 不应提交到 Git。
