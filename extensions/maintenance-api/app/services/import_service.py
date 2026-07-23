from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Callable

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessValidationError
from app.importers.parser import (
    WorkbookParser,
    normalize_code,
    parse_bool,
    parse_date,
    parse_datetime,
    parse_decimal,
    parse_int,
    parse_json,
)
from app.importers.template import SHEET_SPECS, create_template_bytes
from app.models import (
    ConfigurationItem,
    ConfigurationVersion,
    EquipmentModel,
    Part,
    ReliabilityProfile,
    SparePart,
    Supplier,
    SupplierOffer,
    Warehouse,
    WarehouseInventory,
)
from app.models.enums import (
    ConfigurationStatus,
    CriticalityLevel,
    DataSourceType,
    ImportOperation,
    ReliabilityModelType,
    WarehouseStatus,
)
from app.schemas.catalog import PartCreate, SparePartCreate
from app.schemas.equipment import (
    ConfigurationItemCreate,
    ConfigurationVersionCreate,
    EquipmentModelCreate,
)
from app.schemas.import_data import ImportExecutionResult, ImportIssue, ImportValidationResult
from app.schemas.inventory import WarehouseCreate, WarehouseInventoryCreate
from app.schemas.reliability import ReliabilityProfileCreate
from app.schemas.supplier import SupplierCreate, SupplierOfferCreate

SHEET_EQUIPMENT = "01_装备型号"
SHEET_CONFIGURATION = "02_构型版本"
SHEET_PART = "03_部件"
SHEET_SPARE = "04_维修器材"
SHEET_ITEM = "05_构型明细"
SHEET_RELIABILITY = "06_可靠性参数"
SHEET_WAREHOUSE = "07_库房"
SHEET_INVENTORY = "08_库存"
SHEET_SUPPLIER = "09_供应商"
SHEET_OFFER = "10_供应商报价"


class MasterDataImportService:
    def __init__(self) -> None:
        settings = get_settings()
        self.parser = WorkbookParser(
            max_size_mb=settings.max_import_size_mb,
            max_rows_per_sheet=settings.max_import_rows_per_sheet,
        )

    def template_bytes(self) -> bytes:
        return create_template_bytes()

    def _issue_from_validation(
        self, sheet: str, row: int, error: ValidationError
    ) -> list[ImportIssue]:
        issues: list[ImportIssue] = []
        for item in error.errors():
            field = ".".join(str(part) for part in item["loc"])
            issues.append(
                ImportIssue(
                    sheet=sheet,
                    row=row,
                    field=field,
                    code="FIELD_VALIDATION_ERROR",
                    message=item["msg"],
                )
            )
        return issues

    def _safe_build(
        self,
        *,
        sheet: str,
        row: dict[str, Any],
        factory: Callable[[dict[str, Any]], Any],
        errors: list[ImportIssue],
    ) -> dict[str, Any] | None:
        try:
            result = factory(row)
            if hasattr(result, "model_dump"):
                return result.model_dump()
            return result
        except ValidationError as exc:
            errors.extend(self._issue_from_validation(sheet, row["_row"], exc))
        except (ValueError, TypeError) as exc:
            errors.append(
                ImportIssue(
                    sheet=sheet,
                    row=row["_row"],
                    code="FIELD_CONVERSION_ERROR",
                    message=str(exc),
                )
            )
        return None

    def _equipment(self, row: dict[str, Any]) -> EquipmentModelCreate:
        return EquipmentModelCreate(
            code=normalize_code(row.get("code")),
            name=str(row.get("name") or "").strip(),
            category=row.get("category"),
            manufacturer=row.get("manufacturer"),
            model_series=row.get("model_series"),
            service_life_years=parse_decimal(row.get("service_life_years")),
            description=row.get("description"),
            is_active=parse_bool(row.get("is_active"), True),
        )

    def _configuration(self, row: dict[str, Any]) -> dict[str, Any]:
        equipment_code = normalize_code(row.get("equipment_code"))
        payload = ConfigurationVersionCreate(
            equipment_model_id=1,
            version_code=normalize_code(row.get("version_code")),
            version_name=str(row.get("version_name") or "").strip(),
            status=ConfigurationStatus.DRAFT,
            effective_date=parse_date(row.get("effective_date")),
            expiry_date=parse_date(row.get("expiry_date")),
            is_default=parse_bool(row.get("is_default"), False),
            is_active=parse_bool(row.get("is_active"), True),
            source_reference=row.get("source_reference"),
            description=row.get("description"),
        ).model_dump()
        payload["equipment_code"] = equipment_code
        payload.pop("equipment_model_id")
        return payload

    def _part(self, row: dict[str, Any]) -> PartCreate:
        return PartCreate(
            code=normalize_code(row.get("code")),
            name=str(row.get("name") or "").strip(),
            part_type=row.get("part_type"),
            specification=row.get("specification"),
            manufacturer=row.get("manufacturer"),
            unit=str(row.get("unit") or "件").strip(),
            drawing_number=row.get("drawing_number"),
            maintenance_level=row.get("maintenance_level"),
            description=row.get("description"),
            is_active=parse_bool(row.get("is_active"), True),
        )

    def _spare(self, row: dict[str, Any]) -> SparePartCreate:
        return SparePartCreate(
            code=normalize_code(row.get("code")),
            name=str(row.get("name") or "").strip(),
            specification=row.get("specification"),
            category=row.get("category"),
            unit=str(row.get("unit") or "件").strip(),
            manufacturer=row.get("manufacturer"),
            material_code=row.get("material_code"),
            national_standard=row.get("national_standard"),
            shelf_life_months=parse_int(row.get("shelf_life_months")),
            is_serialized=parse_bool(row.get("is_serialized"), False),
            is_repairable=parse_bool(row.get("is_repairable"), False),
            is_critical=parse_bool(row.get("is_critical"), False),
            default_service_level=parse_decimal(row.get("default_service_level")),
            description=row.get("description"),
            is_active=parse_bool(row.get("is_active"), True),
        )

    def _item(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = ConfigurationItemCreate(
            configuration_version_id=1,
            item_code=normalize_code(row.get("item_code")),
            parent_item_id=None,
            part_id=1,
            spare_part_id=None,
            install_quantity=parse_decimal(row.get("install_quantity")),
            position_code=row.get("position_code"),
            position_name=row.get("position_name"),
            criticality_level=CriticalityLevel(
                normalize_code(row.get("criticality_level") or CriticalityLevel.MEDIUM)
            ),
            replacement_ratio=parse_decimal(row.get("replacement_ratio"), Decimal("1")),
            maintenance_level=row.get("maintenance_level"),
            is_mandatory=parse_bool(row.get("is_mandatory"), True),
            sort_order=parse_int(row.get("sort_order"), 0),
            notes=row.get("notes"),
        ).model_dump()
        payload.pop("configuration_version_id")
        payload.pop("parent_item_id")
        payload.pop("part_id")
        payload.pop("spare_part_id")
        payload.update(
            {
                "equipment_code": normalize_code(row.get("equipment_code")),
                "version_code": normalize_code(row.get("version_code")),
                "parent_item_code": normalize_code(row.get("parent_item_code"))
                if row.get("parent_item_code")
                else None,
                "part_code": normalize_code(row.get("part_code")),
                "spare_part_code": normalize_code(row.get("spare_part_code"))
                if row.get("spare_part_code")
                else None,
            }
        )
        return payload

    def _reliability(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = ReliabilityProfileCreate(
            profile_code=normalize_code(row.get("profile_code")),
            spare_part_id=1,
            configuration_version_id=None,
            model_type=ReliabilityModelType(normalize_code(row.get("model_type"))),
            failure_rate=parse_decimal(row.get("failure_rate")),
            mtbf_hours=parse_decimal(row.get("mtbf_hours")),
            weibull_shape=parse_decimal(row.get("weibull_shape")),
            weibull_scale=parse_decimal(row.get("weibull_scale")),
            binomial_trials=parse_int(row.get("binomial_trials")),
            binomial_probability=parse_decimal(row.get("binomial_probability")),
            negative_binomial_r=parse_decimal(row.get("negative_binomial_r")),
            negative_binomial_p=parse_decimal(row.get("negative_binomial_p")),
            empirical_mean=parse_decimal(row.get("empirical_mean")),
            empirical_variance=parse_decimal(row.get("empirical_variance")),
            extension_parameters_json=parse_json(row.get("extension_parameters_json")),
            operating_condition_json=parse_json(row.get("operating_condition_json")),
            data_source_type=DataSourceType(normalize_code(row.get("data_source_type"))),
            data_source_reference=row.get("data_source_reference"),
            sample_size=parse_int(row.get("sample_size")),
            confidence_level=parse_decimal(row.get("confidence_level")),
            estimated_at=parse_datetime(row.get("estimated_at")),
            valid_from=parse_date(row.get("valid_from")),
            valid_to=parse_date(row.get("valid_to")),
            notes=row.get("notes"),
            is_active=parse_bool(row.get("is_active"), True),
        ).model_dump()
        payload.pop("spare_part_id")
        payload.update(
            {
                "spare_part_code": normalize_code(row.get("spare_part_code")),
                "equipment_code": normalize_code(row.get("equipment_code"))
                if row.get("equipment_code")
                else None,
                "version_code": normalize_code(row.get("version_code"))
                if row.get("version_code")
                else None,
            }
        )
        return payload

    def _warehouse(self, row: dict[str, Any]) -> WarehouseCreate:
        return WarehouseCreate(
            code=normalize_code(row.get("code")),
            name=str(row.get("name") or "").strip(),
            warehouse_type=row.get("warehouse_type"),
            location=row.get("location"),
            organization=row.get("organization"),
            responsible_person=row.get("responsible_person"),
            contact=row.get("contact"),
            status=WarehouseStatus(normalize_code(row.get("status") or WarehouseStatus.NORMAL)),
            description=row.get("description"),
            is_active=parse_bool(row.get("is_active"), True),
        )

    def _inventory(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = WarehouseInventoryCreate(
            warehouse_id=1,
            spare_part_id=1,
            on_hand_quantity=parse_decimal(row.get("on_hand_quantity")),
            reserved_quantity=parse_decimal(row.get("reserved_quantity"), Decimal("0")),
            damaged_quantity=parse_decimal(row.get("damaged_quantity"), Decimal("0")),
            quarantined_quantity=parse_decimal(row.get("quarantined_quantity"), Decimal("0")),
            in_transit_quantity=parse_decimal(row.get("in_transit_quantity"), Decimal("0")),
            safety_stock=parse_decimal(row.get("safety_stock"), Decimal("0")),
            reorder_point=parse_decimal(row.get("reorder_point"), Decimal("0")),
            maximum_stock=parse_decimal(row.get("maximum_stock")),
            last_counted_at=parse_datetime(row.get("last_counted_at")),
            notes=row.get("notes"),
        ).model_dump()
        payload.pop("warehouse_id")
        payload.pop("spare_part_id")
        payload.update(
            {
                "warehouse_code": normalize_code(row.get("warehouse_code")),
                "spare_part_code": normalize_code(row.get("spare_part_code")),
            }
        )
        return payload

    def _supplier(self, row: dict[str, Any]) -> SupplierCreate:
        return SupplierCreate(
            code=normalize_code(row.get("code")),
            name=str(row.get("name") or "").strip(),
            supplier_type=row.get("supplier_type"),
            contact_person=row.get("contact_person"),
            phone=row.get("phone"),
            email=row.get("email"),
            address=row.get("address"),
            credit_code=row.get("credit_code"),
            rating=parse_decimal(row.get("rating")),
            qualification_status=row.get("qualification_status"),
            description=row.get("description"),
            is_active=parse_bool(row.get("is_active"), True),
        )

    def _offer(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = SupplierOfferCreate(
            offer_code=normalize_code(row.get("offer_code")),
            supplier_id=1,
            spare_part_id=1,
            unit_price=parse_decimal(row.get("unit_price")),
            currency=str(row.get("currency") or "CNY").strip().upper(),
            tax_rate=parse_decimal(row.get("tax_rate")),
            price_includes_tax=parse_bool(row.get("price_includes_tax"), True),
            lead_time_days=parse_int(row.get("lead_time_days")),
            minimum_order_quantity=parse_decimal(
                row.get("minimum_order_quantity"), Decimal("1")
            ),
            order_multiple=parse_decimal(row.get("order_multiple"), Decimal("1")),
            maximum_supply_quantity=parse_decimal(row.get("maximum_supply_quantity")),
            warranty_months=parse_int(row.get("warranty_months")),
            quality_level=row.get("quality_level"),
            is_preferred=parse_bool(row.get("is_preferred"), False),
            valid_from=parse_date(row.get("valid_from")),
            valid_to=parse_date(row.get("valid_to")),
            notes=row.get("notes"),
            is_active=parse_bool(row.get("is_active"), True),
        ).model_dump()
        payload.pop("supplier_id")
        payload.pop("spare_part_id")
        payload.update(
            {
                "supplier_code": normalize_code(row.get("supplier_code")),
                "spare_part_code": normalize_code(row.get("spare_part_code")),
            }
        )
        return payload

    def _normalized_rows(
        self, parsed: dict[str, list[dict[str, Any]]], errors: list[ImportIssue]
    ) -> dict[str, list[dict[str, Any]]]:
        builders: dict[str, Callable[[dict[str, Any]], Any]] = {
            SHEET_EQUIPMENT: self._equipment,
            SHEET_CONFIGURATION: self._configuration,
            SHEET_PART: self._part,
            SHEET_SPARE: self._spare,
            SHEET_ITEM: self._item,
            SHEET_RELIABILITY: self._reliability,
            SHEET_WAREHOUSE: self._warehouse,
            SHEET_INVENTORY: self._inventory,
            SHEET_SUPPLIER: self._supplier,
            SHEET_OFFER: self._offer,
        }
        result: dict[str, list[dict[str, Any]]] = {sheet: [] for sheet in SHEET_SPECS}
        for sheet, rows in parsed.items():
            builder = builders[sheet]
            for row in rows:
                normalized = self._safe_build(
                    sheet=sheet, row=row, factory=builder, errors=errors
                )
                if normalized is not None:
                    normalized["operation"] = row["operation"]
                    normalized["_row"] = row["_row"]
                    result[sheet].append(normalized)
        return result

    def _duplicate_key_checks(
        self, normalized: dict[str, list[dict[str, Any]]], errors: list[ImportIssue]
    ) -> None:
        key_functions: dict[str, Callable[[dict[str, Any]], Any]] = {
            SHEET_EQUIPMENT: lambda row: row["code"],
            SHEET_CONFIGURATION: lambda row: (row["equipment_code"], row["version_code"]),
            SHEET_PART: lambda row: row["code"],
            SHEET_SPARE: lambda row: row["code"],
            SHEET_ITEM: lambda row: (
                row["equipment_code"],
                row["version_code"],
                row["item_code"],
            ),
            SHEET_RELIABILITY: lambda row: row["profile_code"],
            SHEET_WAREHOUSE: lambda row: row["code"],
            SHEET_INVENTORY: lambda row: (row["warehouse_code"], row["spare_part_code"]),
            SHEET_SUPPLIER: lambda row: row["code"],
            SHEET_OFFER: lambda row: row["offer_code"],
        }
        for sheet, rows in normalized.items():
            seen: set[Any] = set()
            for row in rows:
                key = key_functions[sheet](row)
                if key in seen:
                    errors.append(
                        ImportIssue(
                            sheet=sheet,
                            row=row["_row"],
                            code="DUPLICATE_WORKBOOK_KEY",
                            message=f"Duplicate business key in workbook: {key}",
                        )
                    )
                seen.add(key)

    def _existing_codes(self, session: Session, model: type, field_name: str) -> set[str]:
        field = getattr(model, field_name)
        return {str(value) for value in session.scalars(select(field)).all()}

    def _operation_checks(
        self, session: Session, normalized: dict[str, list[dict[str, Any]]], errors: list[ImportIssue]
    ) -> None:
        existing: dict[str, set[Any]] = {
            SHEET_EQUIPMENT: self._existing_codes(session, EquipmentModel, "code"),
            SHEET_PART: self._existing_codes(session, Part, "code"),
            SHEET_SPARE: self._existing_codes(session, SparePart, "code"),
            SHEET_RELIABILITY: self._existing_codes(session, ReliabilityProfile, "profile_code"),
            SHEET_WAREHOUSE: self._existing_codes(session, Warehouse, "code"),
            SHEET_SUPPLIER: self._existing_codes(session, Supplier, "code"),
            SHEET_OFFER: self._existing_codes(session, SupplierOffer, "offer_code"),
        }
        existing[SHEET_CONFIGURATION] = {
            (equipment_code, version_code)
            for equipment_code, version_code in session.execute(
                select(EquipmentModel.code, ConfigurationVersion.version_code).join(
                    ConfigurationVersion,
                    ConfigurationVersion.equipment_model_id == EquipmentModel.id,
                )
            ).all()
        }
        existing[SHEET_ITEM] = {
            (equipment_code, version_code, item_code)
            for equipment_code, version_code, item_code in session.execute(
                select(
                    EquipmentModel.code,
                    ConfigurationVersion.version_code,
                    ConfigurationItem.item_code,
                )
                .join(ConfigurationVersion, ConfigurationVersion.equipment_model_id == EquipmentModel.id)
                .join(ConfigurationItem, ConfigurationItem.configuration_version_id == ConfigurationVersion.id)
            ).all()
        }
        existing[SHEET_INVENTORY] = {
            (warehouse_code, spare_code)
            for warehouse_code, spare_code in session.execute(
                select(Warehouse.code, SparePart.code)
                .join(WarehouseInventory, WarehouseInventory.warehouse_id == Warehouse.id)
                .join(SparePart, WarehouseInventory.spare_part_id == SparePart.id)
            ).all()
        }
        key_functions: dict[str, Callable[[dict[str, Any]], Any]] = {
            SHEET_EQUIPMENT: lambda row: row["code"],
            SHEET_CONFIGURATION: lambda row: (row["equipment_code"], row["version_code"]),
            SHEET_PART: lambda row: row["code"],
            SHEET_SPARE: lambda row: row["code"],
            SHEET_ITEM: lambda row: (
                row["equipment_code"],
                row["version_code"],
                row["item_code"],
            ),
            SHEET_RELIABILITY: lambda row: row["profile_code"],
            SHEET_WAREHOUSE: lambda row: row["code"],
            SHEET_INVENTORY: lambda row: (row["warehouse_code"], row["spare_part_code"]),
            SHEET_SUPPLIER: lambda row: row["code"],
            SHEET_OFFER: lambda row: row["offer_code"],
        }
        for sheet, rows in normalized.items():
            for row in rows:
                key = key_functions[sheet](row)
                operation = ImportOperation(row["operation"])
                exists = key in existing[sheet]
                if operation == ImportOperation.CREATE and exists:
                    errors.append(ImportIssue(sheet=sheet, row=row["_row"], code="CREATE_CONFLICT", message=f"Record already exists: {key}"))
                if operation == ImportOperation.UPDATE and not exists:
                    errors.append(ImportIssue(sheet=sheet, row=row["_row"], code="UPDATE_TARGET_MISSING", message=f"Record does not exist: {key}"))

    def _cross_reference_checks(
        self, session: Session, normalized: dict[str, list[dict[str, Any]]], errors: list[ImportIssue]
    ) -> None:
        equipment_codes = self._existing_codes(session, EquipmentModel, "code") | {
            row["code"] for row in normalized[SHEET_EQUIPMENT]
        }
        part_codes = self._existing_codes(session, Part, "code") | {
            row["code"] for row in normalized[SHEET_PART]
        }
        spare_codes = self._existing_codes(session, SparePart, "code") | {
            row["code"] for row in normalized[SHEET_SPARE]
        }
        warehouse_codes = self._existing_codes(session, Warehouse, "code") | {
            row["code"] for row in normalized[SHEET_WAREHOUSE]
        }
        supplier_codes = self._existing_codes(session, Supplier, "code") | {
            row["code"] for row in normalized[SHEET_SUPPLIER]
        }
        configuration_keys = {
            (equipment_code, version_code)
            for equipment_code, version_code in session.execute(
                select(EquipmentModel.code, ConfigurationVersion.version_code).join(
                    ConfigurationVersion,
                    ConfigurationVersion.equipment_model_id == EquipmentModel.id,
                )
            ).all()
        } | {
            (row["equipment_code"], row["version_code"])
            for row in normalized[SHEET_CONFIGURATION]
        }
        item_keys = {
            (row["equipment_code"], row["version_code"], row["item_code"])
            for row in normalized[SHEET_ITEM]
        }
        for sheet, rows in normalized.items():
            for row in rows:
                row_number = row["_row"]
                def missing(field: str, value: Any, message: str) -> None:
                    errors.append(ImportIssue(sheet=sheet, row=row_number, field=field, code="MISSING_REFERENCE", message=message))
                if sheet == SHEET_CONFIGURATION and row["equipment_code"] not in equipment_codes:
                    missing("equipment_code", row["equipment_code"], "Referenced equipment model does not exist")
                elif sheet == SHEET_ITEM:
                    config_key = (row["equipment_code"], row["version_code"])
                    if config_key not in configuration_keys:
                        missing("version_code", config_key, "Referenced configuration version does not exist")
                    if row["part_code"] not in part_codes:
                        missing("part_code", row["part_code"], "Referenced part does not exist")
                    if row["spare_part_code"] and row["spare_part_code"] not in spare_codes:
                        missing("spare_part_code", row["spare_part_code"], "Referenced spare part does not exist")
                    if row["parent_item_code"]:
                        parent_key = (*config_key, row["parent_item_code"])
                        if parent_key not in item_keys:
                            missing("parent_item_code", parent_key, "Referenced parent item does not exist in workbook")
                elif sheet == SHEET_RELIABILITY:
                    if row["spare_part_code"] not in spare_codes:
                        missing("spare_part_code", row["spare_part_code"], "Referenced spare part does not exist")
                    if row["version_code"]:
                        config_key = (row["equipment_code"], row["version_code"])
                        if config_key not in configuration_keys:
                            missing("version_code", config_key, "Referenced configuration version does not exist")
                elif sheet == SHEET_INVENTORY:
                    if row["warehouse_code"] not in warehouse_codes:
                        missing("warehouse_code", row["warehouse_code"], "Referenced warehouse does not exist")
                    if row["spare_part_code"] not in spare_codes:
                        missing("spare_part_code", row["spare_part_code"], "Referenced spare part does not exist")
                elif sheet == SHEET_OFFER:
                    if row["supplier_code"] not in supplier_codes:
                        missing("supplier_code", row["supplier_code"], "Referenced supplier does not exist")
                    if row["spare_part_code"] not in spare_codes:
                        missing("spare_part_code", row["spare_part_code"], "Referenced spare part does not exist")

        parent_by_key = {
            (row["equipment_code"], row["version_code"], row["item_code"]): row.get("parent_item_code")
            for row in normalized[SHEET_ITEM]
        }
        for key in parent_by_key:
            seen: set[tuple[str, str, str]] = set()
            cursor = key
            while cursor in parent_by_key and parent_by_key[cursor]:
                if cursor in seen:
                    errors.append(ImportIssue(sheet=SHEET_ITEM, code="CONFIGURATION_CYCLE", message=f"Configuration hierarchy contains a cycle at {key}"))
                    break
                seen.add(cursor)
                cursor = (cursor[0], cursor[1], parent_by_key[cursor])

    def validate(
        self, session: Session, *, content: bytes, filename: str
    ) -> ImportValidationResult:
        parsed, errors = self.parser.parse(content, filename)
        normalized = self._normalized_rows(parsed, errors)
        self._duplicate_key_checks(normalized, errors)
        self._operation_checks(session, normalized, errors)
        self._cross_reference_checks(session, normalized, errors)
        counts = {sheet: len(rows) for sheet, rows in normalized.items()}
        preview = {
            sheet: [
                {key: value for key, value in row.items() if key not in {"_row"}}
                for row in rows[:20]
            ]
            for sheet, rows in normalized.items()
        }
        return ImportValidationResult(
            valid=not errors,
            sheet_counts=counts,
            errors=errors,
            warnings=[],
            preview=preview,
        )

    @staticmethod
    def _apply(instance: Any, data: dict[str, Any], excluded: set[str]) -> None:
        for key, value in data.items():
            if key not in excluded:
                setattr(instance, key, value)

    def execute(
        self, session: Session, *, content: bytes, filename: str
    ) -> ImportExecutionResult:
        validation = self.validate(session, content=content, filename=filename)
        if not validation.valid:
            raise BusinessValidationError(
                "Workbook validation failed",
                details=[issue.model_dump() for issue in validation.errors],
                code="IMPORT_VALIDATION_FAILED",
            )
        parsed, errors = self.parser.parse(content, filename)
        normalized = self._normalized_rows(parsed, errors)
        created: defaultdict[str, int] = defaultdict(int)
        updated: defaultdict[str, int] = defaultdict(int)

        def upsert_simple(sheet: str, model: type, code_field: str = "code") -> None:
            for row in normalized[sheet]:
                code = row[code_field]
                instance = session.scalar(select(model).where(getattr(model, code_field) == code))
                data = {k: v for k, v in row.items() if k not in {"operation", "_row"}}
                if instance is None:
                    instance = model(**data)
                    session.add(instance)
                    created[sheet] += 1
                else:
                    self._apply(instance, data, set())
                    updated[sheet] += 1
                session.flush()

        try:
            upsert_simple(SHEET_EQUIPMENT, EquipmentModel)
            upsert_simple(SHEET_PART, Part)
            upsert_simple(SHEET_SPARE, SparePart)
            upsert_simple(SHEET_WAREHOUSE, Warehouse)
            upsert_simple(SHEET_SUPPLIER, Supplier)

            equipment_by_code = {item.code: item for item in session.scalars(select(EquipmentModel)).all()}
            part_by_code = {item.code: item for item in session.scalars(select(Part)).all()}
            spare_by_code = {item.code: item for item in session.scalars(select(SparePart)).all()}
            warehouse_by_code = {item.code: item for item in session.scalars(select(Warehouse)).all()}
            supplier_by_code = {item.code: item for item in session.scalars(select(Supplier)).all()}

            for row in normalized[SHEET_CONFIGURATION]:
                equipment = equipment_by_code[row["equipment_code"]]
                instance = session.scalar(
                    select(ConfigurationVersion).where(
                        ConfigurationVersion.equipment_model_id == equipment.id,
                        ConfigurationVersion.version_code == row["version_code"],
                    )
                )
                data = {
                    key: value
                    for key, value in row.items()
                    if key not in {"operation", "_row", "equipment_code"}
                }
                data["equipment_model_id"] = equipment.id
                data["status"] = ConfigurationStatus.DRAFT
                if instance is None:
                    instance = ConfigurationVersion(**data)
                    session.add(instance)
                    created[SHEET_CONFIGURATION] += 1
                else:
                    if instance.status != ConfigurationStatus.DRAFT:
                        raise BusinessValidationError(
                            "Published or retired configurations cannot be updated by import"
                        )
                    self._apply(instance, data, set())
                    updated[SHEET_CONFIGURATION] += 1
                session.flush()

            configuration_by_key = {
                (equipment_code, version.version_code): version
                for equipment_code, version in session.execute(
                    select(EquipmentModel.code, ConfigurationVersion).join(
                        ConfigurationVersion,
                        ConfigurationVersion.equipment_model_id == EquipmentModel.id,
                    )
                ).all()
            }
            item_by_key: dict[tuple[str, str, str], ConfigurationItem] = {}
            for row in normalized[SHEET_ITEM]:
                config_key = (row["equipment_code"], row["version_code"])
                version = configuration_by_key[config_key]
                if version.status != ConfigurationStatus.DRAFT:
                    raise BusinessValidationError(
                        "Published or retired configuration items cannot be updated by import"
                    )
                key = (*config_key, row["item_code"])
                instance = session.scalar(
                    select(ConfigurationItem).where(
                        ConfigurationItem.configuration_version_id == version.id,
                        ConfigurationItem.item_code == row["item_code"],
                    )
                )
                data = {
                    k: v
                    for k, v in row.items()
                    if k
                    not in {
                        "operation",
                        "_row",
                        "equipment_code",
                        "version_code",
                        "parent_item_code",
                        "part_code",
                        "spare_part_code",
                    }
                }
                data.update(
                    {
                        "configuration_version_id": version.id,
                        "part_id": part_by_code[row["part_code"]].id,
                        "spare_part_id": spare_by_code[row["spare_part_code"]].id
                        if row["spare_part_code"]
                        else None,
                        "parent_item_id": None,
                    }
                )
                if instance is None:
                    instance = ConfigurationItem(**data)
                    session.add(instance)
                    created[SHEET_ITEM] += 1
                else:
                    self._apply(instance, data, set())
                    updated[SHEET_ITEM] += 1
                session.flush()
                item_by_key[key] = instance
            for row in normalized[SHEET_ITEM]:
                if row["parent_item_code"]:
                    key = (row["equipment_code"], row["version_code"], row["item_code"])
                    parent_key = (
                        row["equipment_code"],
                        row["version_code"],
                        row["parent_item_code"],
                    )
                    item_by_key[key].parent_item_id = item_by_key[parent_key].id
            session.flush()

            for row in normalized[SHEET_RELIABILITY]:
                spare = spare_by_code[row["spare_part_code"]]
                config = (
                    configuration_by_key[(row["equipment_code"], row["version_code"])]
                    if row["version_code"]
                    else None
                )
                instance = session.scalar(
                    select(ReliabilityProfile).where(
                        ReliabilityProfile.profile_code == row["profile_code"]
                    )
                )
                data = {
                    k: v
                    for k, v in row.items()
                    if k
                    not in {
                        "operation",
                        "_row",
                        "spare_part_code",
                        "equipment_code",
                        "version_code",
                    }
                }
                data.update(
                    {
                        "spare_part_id": spare.id,
                        "configuration_version_id": config.id if config else None,
                    }
                )
                if instance is None:
                    instance = ReliabilityProfile(**data)
                    session.add(instance)
                    created[SHEET_RELIABILITY] += 1
                else:
                    self._apply(instance, data, set())
                    updated[SHEET_RELIABILITY] += 1
                session.flush()

            for row in normalized[SHEET_INVENTORY]:
                warehouse = warehouse_by_code[row["warehouse_code"]]
                spare = spare_by_code[row["spare_part_code"]]
                instance = session.scalar(
                    select(WarehouseInventory).where(
                        WarehouseInventory.warehouse_id == warehouse.id,
                        WarehouseInventory.spare_part_id == spare.id,
                    )
                )
                data = {
                    k: v
                    for k, v in row.items()
                    if k
                    not in {
                        "operation",
                        "_row",
                        "warehouse_code",
                        "spare_part_code",
                    }
                }
                data.update({"warehouse_id": warehouse.id, "spare_part_id": spare.id})
                if instance is None:
                    instance = WarehouseInventory(**data)
                    session.add(instance)
                    created[SHEET_INVENTORY] += 1
                else:
                    self._apply(instance, data, set())
                    updated[SHEET_INVENTORY] += 1
                session.flush()

            for row in normalized[SHEET_OFFER]:
                supplier = supplier_by_code[row["supplier_code"]]
                spare = spare_by_code[row["spare_part_code"]]
                instance = session.scalar(
                    select(SupplierOffer).where(SupplierOffer.offer_code == row["offer_code"])
                )
                data = {
                    k: v
                    for k, v in row.items()
                    if k
                    not in {
                        "operation",
                        "_row",
                        "supplier_code",
                        "spare_part_code",
                    }
                }
                data.update({"supplier_id": supplier.id, "spare_part_id": spare.id})
                if instance is None:
                    instance = SupplierOffer(**data)
                    session.add(instance)
                    created[SHEET_OFFER] += 1
                else:
                    self._apply(instance, data, set())
                    updated[SHEET_OFFER] += 1
                session.flush()

            session.commit()
        except Exception:
            session.rollback()
            raise

        return ImportExecutionResult(
            imported=True,
            created=dict(created),
            updated=dict(updated),
            total_rows=sum(validation.sheet_counts.values()),
        )


master_data_import_service = MasterDataImportService()
