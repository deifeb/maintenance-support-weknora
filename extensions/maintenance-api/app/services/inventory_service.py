from datetime import timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import InventoryBalance, Warehouse
from app.models.enums import WarehouseStatus
from app.repositories import (
    InventoryRepository,
    SparePartRepository,
    WarehouseRepository,
)
from app.schemas.inventory import (
    InventoryAdjustment,
    InventoryAdjustmentRead,
    InventoryQuantities,
    WarehouseInventoryCreate,
    WarehouseInventoryRead,
    WarehouseInventoryUpdate,
)
from app.security.actor import ActorContext
from app.services.inventory_query_service import (
    InventoryQueryService,
    inventory_query_service,
)
from app.services.inventory_transaction_service import (
    InventoryTransactionService,
    inventory_transaction_service,
)


class InventoryService:
    def __init__(
        self,
        *,
        query_service: InventoryQueryService | None = None,
        transaction_service: InventoryTransactionService | None = None,
    ) -> None:
        self.inventory_repository = InventoryRepository()
        self.warehouse_repository = WarehouseRepository()
        self.spare_part_repository = SparePartRepository()
        self.query_service = query_service or inventory_query_service
        self.transaction_service = (
            transaction_service or inventory_transaction_service
        )

    @staticmethod
    def _commit(session: Session) -> None:
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ConflictError(
                "warehouse_inventory conflicts with an existing record",
                details={"resource": "warehouse_inventory"},
            ) from exc

    def _warehouse(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> Warehouse:
        warehouse = self.warehouse_repository.get_by_id(
            session,
            actor.tenant_id,
            identifier,
        )
        if warehouse is None:
            raise NotFoundError("warehouse", identifier)
        return warehouse

    def _validate_references(
        self,
        session: Session,
        actor: ActorContext,
        warehouse_id: int,
        spare_part_id: int,
    ) -> Warehouse:
        warehouse = self._warehouse(
            session,
            actor,
            warehouse_id,
        )
        if self.spare_part_repository.get_by_id(
            session,
            actor.tenant_id,
            spare_part_id,
        ) is None:
            raise NotFoundError(
                "spare_part",
                spare_part_id,
            )
        return warehouse

    def _validate_state(
        self,
        warehouse: Warehouse,
    ) -> None:
        if (
            warehouse.status != WarehouseStatus.NORMAL
            or not warehouse.is_active
        ):
            raise ConflictError(
                "warehouse is not available for inventory changes"
            )

    def create_inventory(
        self,
        session: Session,
        actor: ActorContext,
        payload: WarehouseInventoryCreate,
        *,
        commit: bool = True,
    ) -> WarehouseInventoryRead:
        warehouse = self._validate_references(
            session,
            actor,
            payload.warehouse_id,
            payload.spare_part_id,
        )
        self._validate_state(warehouse)
        if self.inventory_repository.get_policy_by_business_key(
            session,
            actor.tenant_id,
            payload.warehouse_id,
            payload.spare_part_id,
        ):
            raise ConflictError(
                "inventory already exists for warehouse "
                "and spare part"
            )
        balance, _ = self.inventory_repository.create_default_identity(
            session,
            actor.tenant_id,
            warehouse_id=payload.warehouse_id,
            spare_part_id=payload.spare_part_id,
            policy_data={
                "safety_stock": payload.safety_stock,
                "reorder_point": payload.reorder_point,
                "maximum_stock": payload.maximum_stock,
                "notes": payload.notes,
            },
        )
        if commit:
            self._commit(session)
        return self.get(session, actor, balance.id)

    def get(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
    ) -> WarehouseInventoryRead:
        balance = self.inventory_repository.get_balance(
            session,
            actor.tenant_id,
            identifier,
        )
        if balance is None:
            raise NotFoundError("inventory_balance", identifier)
        page = self.query_service.list_summaries(
            session,
            actor,
            page=1,
            page_size=1,
            warehouse_id=balance.warehouse_id,
            spare_part_id=balance.spare_part_id,
        )
        if not page.items:
            raise NotFoundError("inventory_balance", identifier)
        return self._summary_read(
            session,
            actor,
            page.items[0],
            balance,
        )

    def list(
        self,
        session: Session,
        actor: ActorContext,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        include_inactive: bool,
        sort_by: str,
        sort_order: str,
        filters: dict | None = None,
    ):
        del keyword, include_inactive, sort_by, sort_order
        filters = filters or {}
        summaries = self.query_service.list_summaries(
            session,
            actor,
            page=page,
            page_size=page_size,
            warehouse_id=filters.get("warehouse_id"),
            spare_part_id=filters.get("spare_part_id"),
        )
        items = []
        for summary in summaries.items:
            balance = (
                self.inventory_repository.get_default_balance_by_business_key(
                    session,
                    actor.tenant_id,
                    summary.warehouse_id,
                    summary.spare_part_id,
                )
            )
            if balance is None:
                continue
            items.append(
                self._summary_read(
                    session,
                    actor,
                    summary,
                    balance,
                )
            )
        return summaries.model_copy(update={"items": items})

    def update_inventory(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: WarehouseInventoryUpdate,
    ) -> WarehouseInventoryRead:
        balance = self.inventory_repository.get_balance(
            session,
            actor.tenant_id,
            identifier,
        )
        if balance is None:
            raise NotFoundError("inventory_balance", identifier)
        warehouse = self._validate_references(
            session,
            actor,
            balance.warehouse_id,
            balance.spare_part_id,
        )
        self._validate_state(warehouse)
        policy = self.inventory_repository.get_policy_by_business_key(
            session,
            actor.tenant_id,
            balance.warehouse_id,
            balance.spare_part_id,
        )
        if policy is None:
            raise NotFoundError("inventory_policy", identifier)
        changes = {
            key: value
            for key, value in payload.model_dump(
                exclude_unset=True
            ).items()
            if key
            in {
                "safety_stock",
                "reorder_point",
                "maximum_stock",
                "notes",
            }
        }
        InventoryQuantities.model_validate(
            {
                "on_hand_quantity": Decimal("0"),
                "safety_stock": changes.get(
                    "safety_stock",
                    policy.safety_stock,
                ),
                "reorder_point": changes.get(
                    "reorder_point",
                    policy.reorder_point,
                ),
                "maximum_stock": changes.get(
                    "maximum_stock",
                    policy.maximum_stock,
                ),
            }
        )
        if changes:
            self.inventory_repository.update_policy(
                session,
                actor.tenant_id,
                policy,
                changes,
            )
            self._commit(session)
        return self.get(session, actor, identifier)

    def adjust(
        self,
        session: Session,
        actor: ActorContext,
        identifier: int,
        payload: InventoryAdjustment,
        *,
        idempotency_key: str,
    ) -> InventoryAdjustmentRead:
        balance = self.inventory_repository.get_balance(
            session,
            actor.tenant_id,
            identifier,
        )
        if balance is None:
            raise NotFoundError("inventory_balance", identifier)
        warehouse = self._validate_references(
            session,
            actor,
            balance.warehouse_id,
            balance.spare_part_id,
        )
        self._validate_state(warehouse)
        transaction = self.transaction_service.adjust(
            session,
            actor,
            balance_id=identifier,
            expected_version=payload.expected_version,
            deltas=payload.quantity_delta(),
            reason=payload.reason,
            idempotency_key=idempotency_key,
        )
        self._commit(session)
        return InventoryAdjustmentRead(
            transaction=transaction,
            summary=self.get(session, actor, identifier),
        )

    def _summary_read(
        self,
        session: Session,
        actor: ActorContext,
        summary,
        balance: InventoryBalance,
    ) -> WarehouseInventoryRead:
        policy = self.inventory_repository.get_policy_by_business_key(
            session,
            actor.tenant_id,
            summary.warehouse_id,
            summary.spare_part_id,
        )
        if policy is None:
            raise NotFoundError("inventory_policy", balance.id)
        return WarehouseInventoryRead.model_validate(
            {
                "id": balance.id,
                "version": balance.version,
                "policy_version": policy.version,
                "warehouse_id": summary.warehouse_id,
                "spare_part_id": summary.spare_part_id,
                "on_hand_quantity": summary.on_hand_quantity,
                "reserved_quantity": summary.reserved_quantity,
                "damaged_quantity": summary.damaged_quantity,
                "quarantined_quantity": summary.quarantined_quantity,
                "in_transit_quantity": summary.in_transit_quantity,
                "safety_stock": summary.safety_stock,
                "reorder_point": summary.reorder_point,
                "maximum_stock": summary.maximum_stock,
                "last_counted_at": None,
                "notes": policy.notes,
                "created_at": balance.created_at,
                "updated_at": max(
                    balance.updated_at,
                    policy.updated_at,
                    key=lambda value: (
                        value.replace(tzinfo=timezone.utc)
                        if value.tzinfo is None
                        else value
                    ),
                ),
            }
        )


inventory_service = InventoryService()
