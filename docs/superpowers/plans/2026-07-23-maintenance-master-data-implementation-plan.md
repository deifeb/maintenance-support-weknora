# Maintenance Master Data Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete static maintenance master-data subsystem to `extensions/maintenance-api`, including ten normalized tables, Alembic migrations, CRUD and lifecycle APIs, Excel validation/import, seed data, and automated verification.

**Architecture:** Extend the existing layered FastAPI modular monolith. SQLAlchemy ORM models define storage, repositories isolate persistence, services enforce cross-table rules and transactions, and routers expose versioned APIs. Excel import parses and validates the whole workbook before a single transaction writes any row.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2 synchronous API, Alembic, SQLite/PostgreSQL-compatible SQL, openpyxl, python-multipart, pytest, HTTPX, Ruff.

## Global Constraints

- Work only on branch `feature/maintenance-foundation` or another isolated feature branch; never implement on `main`.
- Do not modify WeKnora core modules.
- Preserve all nine foundation tests.
- Database access remains synchronous SQLAlchemy 2.x.
- Routes must not execute raw SQL directly.
- Repository methods never commit; service methods own transaction boundaries.
- Monetary, inventory, and reliability values use `Decimal`/`Numeric`, not persisted `float`.
- Excel execution performs full validation again and commits the entire workbook atomically.
- `.env`, `.venv`, SQLite files, imported workbooks, and enterprise data remain ignored by Git.

---

## File Map

**Create or extend:**

```text
extensions/maintenance-api/
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/<revision>_create_master_data_schema.py
├── app/
│   ├── models/{__init__,enums,mixins,equipment,catalog,reliability,inventory,supplier}.py
│   ├── repositories/{base,equipment_repository,configuration_repository,part_repository,
│   │                 spare_part_repository,reliability_repository,warehouse_repository,
│   │                 inventory_repository,supplier_repository,supplier_offer_repository}.py
│   ├── services/{base,equipment_service,configuration_service,part_service,
│   │              spare_part_service,reliability_service,warehouse_service,
│   │              inventory_service,supplier_service,supplier_offer_service,
│   │              import_service}.py
│   ├── schemas/{base,equipment,catalog,reliability,inventory,supplier,import_data}.py
│   ├── importers/{__init__,template,parser}.py
│   ├── api/v1/master_data/{__init__,router,equipment_models,configurations,parts,
│   │                        spare_parts,reliability,warehouses,inventories,suppliers,
│   │                        supplier_offers,imports}.py
│   └── scripts/{__init__,seed_master_data,generate_import_template}.py
├── templates/master_data_import_template.xlsx
└── tests/{models,repositories,services,api,imports,migrations}/...
```

**Modify:**

```text
app/core/exceptions.py
app/db/base.py
app/api/v1/router.py
app/schemas/common.py
requirements.txt
requirements-dev.txt
pyproject.toml
README.md
.gitignore
```

---

### Task 1: Dependency and Database Foundation

**Files:** `requirements*.txt`, `app/db/base.py`, `app/core/exceptions.py`, `app/schemas/common.py`.

**Produces:** Alembic/openpyxl/multipart dependencies, shared timestamps, paginated response type, and controlled 404/409/422 errors.

- [ ] Add failing tests for `PageData`, `NotFoundError`, `ConflictError`, and `ResourceInUseError`.
- [ ] Run `python -m pytest tests/test_common.py -v`; verify missing types fail.
- [ ] Implement the types and handlers without changing the existing response envelope.
- [ ] Run the focused tests, then all existing tests.
- [ ] Commit: `feat: prepare master data infrastructure`.

### Task 2: Enumerations and Ten ORM Models

**Files:** `app/models/*.py`, `app/models/__init__.py`, `app/db/base.py`.

**Produces:** `EquipmentModel`, `ConfigurationVersion`, `ConfigurationItem`, `Part`, `SparePart`, `ReliabilityProfile`, `Warehouse`, `WarehouseInventory`, `Supplier`, and `SupplierOffer`.

- [ ] Write failing model tests for table names, unique constraints, numeric checks, relationships, available inventory calculation, and enums.
- [ ] Run `python -m pytest tests/models -v`; verify imports/tables fail.
- [ ] Implement models with the exact fields and constraints in the approved design.
- [ ] Run model tests against a temporary SQLite database.
- [ ] Commit: `feat: add maintenance master data models`.

### Task 3: Alembic Initial Migration

**Files:** `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/*.py`.

**Produces:** a deterministic initial migration containing all ten tables, indexes, foreign keys, checks, and unique constraints.

- [ ] Write a migration test that upgrades an empty database, asserts all ten tables, downgrades, and upgrades again.
- [ ] Run it and verify failure because Alembic is not configured.
- [ ] Configure Alembic to read `DATABASE_URL` and `Base.metadata`.
- [ ] Generate and review the initial revision with `python -m alembic revision --autogenerate`.
- [ ] Run `upgrade head`, `downgrade base`, and `upgrade head` in the test.
- [ ] Commit: `feat: add master data database migration`.

### Task 4: Pydantic Schemas and Validation

**Files:** `app/schemas/base.py`, `equipment.py`, `catalog.py`, `reliability.py`, `inventory.py`, `supplier.py`.

**Produces:** create, update, read, active-patch, adjustment, clone, and tree schemas.

- [ ] Write failing parameterized tests for code normalization, date order, reliability model combinations, inventory quantity relationships, service levels, tax rates, and supplier quantities.
- [ ] Implement model validators using `Decimal`.
- [ ] Run schema tests and verify all invalid combinations are rejected.
- [ ] Commit: `feat: add validated master data schemas`.

### Task 5: Repository Layer

**Files:** `app/repositories/*.py`.

**Produces:** generic pagination plus resource-specific lookup and reference-count methods.

- [ ] Write failing repository tests for create/get/list/filter/sort/count/delete without implicit commit.
- [ ] Implement `BaseRepository` and nine focused repositories.
- [ ] Verify uncommitted changes roll back and committed service transactions persist.
- [ ] Commit: `feat: add master data repositories`.

### Task 6: CRUD and Restricted-Delete Services

**Files:** equipment, part, spare-part, warehouse, and supplier services.

**Produces:** create/list/get/update/activate/deactivate/delete behavior and 409 restrictions.

- [ ] Write failing service tests for unique codes, not-found, inactive filtering, reference checks, and physical deletion of unreferenced records.
- [ ] Implement transaction-owning services and database error translation.
- [ ] Run service tests plus all prior tests.
- [ ] Commit: `feat: add master data CRUD services`.

### Task 7: Configuration Lifecycle Service

**Files:** `configuration_service.py`, configuration repository and schemas.

**Produces:** draft editing, tree validation, cycle rejection, publish, retire, default switching, clone, and tree output.

- [ ] Write failing tests for same-version parent enforcement, cycle detection, empty publish, inactive references, published-item lock, clone parent remapping, and one default configuration.
- [ ] Implement lifecycle operations in one transaction each.
- [ ] Run focused tests and verify cloned trees preserve structure.
- [ ] Commit: `feat: add configuration lifecycle management`.

### Task 8: Reliability, Inventory, and Supplier Offer Services

**Files:** reliability, inventory, supplier-offer services and repositories.

**Produces:** interval conflict detection, inventory adjustments, warehouse-state checks, and preferred-offer conflict checks.

- [ ] Write failing tests for all five reliability models, overlapping active profiles, invalid stock relations, frozen/counting warehouses, and overlapping preferred offers.
- [ ] Implement the three services.
- [ ] Run focused tests and all service tests.
- [ ] Commit: `feat: enforce reliability inventory and offer rules`.

### Task 9: Versioned Master-Data API

**Files:** `app/api/v1/master_data/*.py`, `app/api/v1/router.py`.

**Produces:** CRUD endpoints under `/api/v1/master-data`, configuration operations, inventory adjustment, pagination, filtering, sorting, and controlled errors.

- [ ] Write failing API tests for each resource create/list/get/update/patch/delete path and specialized operations.
- [ ] Implement routers using `Depends(get_db_session)` and services only.
- [ ] Verify Swagger route registration and that responses never include SQL, filesystem paths, or credentials.
- [ ] Commit: `feat: expose maintenance master data APIs`.

### Task 10: Excel Template, Validation, and Atomic Import

**Files:** `app/importers/*.py`, `app/services/import_service.py`, `app/schemas/import_data.py`, import API.

**Produces:** ten-sheet template, `.xlsx` security limits, row/field errors, cross-sheet validation, preview, and CREATE/UPDATE/UPSERT transaction execution.

- [ ] Write failing tests for template sheet names and headers.
- [ ] Write failing tests for missing sheets, invalid headers, duplicate codes, invalid references, formulas, row limits, configuration cycles, invalid reliability/inventory/offer data, rollback, and successful import.
- [ ] Implement template generation and parser with `data_only=True`, no macros, 10 MB limit, and 10,000-row limit.
- [ ] Implement validate and execute endpoints; execute must revalidate and use one transaction.
- [ ] Generate `templates/master_data_import_template.xlsx`.
- [ ] Commit: `feat: add atomic Excel master data import`.

### Task 11: Seed Data and Documentation

**Files:** `app/scripts/seed_master_data.py`, `generate_import_template.py`, `README.md`, `.env.example`, `.gitignore`.

**Produces:** idempotent non-sensitive demo data and exact local commands.

- [ ] Write a failing idempotency test that runs seed twice and compares counts.
- [ ] Implement at least 2 equipment models, 4 versions, 15 parts, 20 spare parts, 30 configuration items, five reliability model examples, three warehouses, four suppliers, inventories, and offers.
- [ ] Update documentation for migration, seed, API, template, validation, and execution.
- [ ] Commit: `docs: document and seed master data phase`.

### Task 12: Batch Installer and Final Verification

**Files:** `apply-master-data-phase.ps1`, `payload/**`, generated ZIP.

**Produces:** a repeatable installer that backs up changed files, applies payload, installs dependencies, runs migrations, tests, Ruff, template generation, and prints Git commands without committing.

- [ ] Build the payload from the verified workspace.
- [ ] Run the installer against a disposable copy of the foundation project.
- [ ] Run `python -m pytest -v`; require all foundation and phase-two tests to pass.
- [ ] Run `python -m ruff check app tests`; require zero errors.
- [ ] Run migration upgrade/downgrade/upgrade and import/seed smoke tests.
- [ ] Package `maintenance-master-data-phase-batch.zip`.

## Final Verification Commands

```powershell
cd E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
python -m pytest -v
python -m ruff check app tests
python -m app.scripts.generate_import_template
python -m app.scripts.seed_master_data
python -m app.scripts.seed_master_data
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

Expected: migrations complete without errors, all tests pass, Ruff reports `All checks passed!`, template exists, seed is idempotent, and Swagger exposes all master-data endpoints.
