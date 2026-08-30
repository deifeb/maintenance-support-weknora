from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.ai_report_repository import (
    AIReportRepository,
    ai_report_repository,
)
from app.schemas.common import PageData
from app.schemas.report_center import (
    ReportCenterItemRead,
    ReportCenterLatestVersionRead,
    ReportCenterQuery,
)
from app.security.actor import ActorContext


class ReportCenterQueryService:
    def __init__(
        self,
        repository: AIReportRepository | None = None,
    ) -> None:
        self.repository = repository or ai_report_repository

    def list(
        self,
        session: Session,
        actor: ActorContext,
        query: ReportCenterQuery | None = None,
        **query_values,
    ) -> PageData[ReportCenterItemRead]:
        if query is None:
            query = ReportCenterQuery(**query_values)
        elif query_values:
            query = ReportCenterQuery(
                **{
                    **query.model_dump(),
                    **query_values,
                }
            )

        rows, total = self.repository.list_report_center_page(
            session,
            actor.tenant_id,
            page=query.page,
            page_size=query.page_size,
            keyword=query.keyword,
            report_type=query.report_type,
            job_status=query.job_status,
            version_status=query.version_status,
            session_id=query.session_id,
            scenario_version_id=query.scenario_version_id,
            calculation_run_id=query.calculation_run_id,
            review_run_id=query.review_run_id,
            sort_by=query.sort_by,
            sort_order=query.sort_order,
        )

        items: list[ReportCenterItemRead] = []
        for job, version in rows:
            latest = None
            if version is not None:
                latest = ReportCenterLatestVersionRead(
                    id=version.id,
                    version_number=version.version_number,
                    status=version.status,
                    created_at=version.created_at,
                )
            items.append(
                ReportCenterItemRead(
                    report_id=job.id,
                    report_code=job.report_code,
                    session_id=job.session_id,
                    report_type=job.report_type,
                    job_status=job.status,
                    title=job.title,
                    progress_percent=job.progress_percent,
                    error_code=job.error_code,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    latest_version=latest,
                )
            )

        return PageData(
            items=items,
            page=query.page,
            page_size=query.page_size,
            total=total,
            pages=(
                (total + query.page_size - 1) // query.page_size
                if total
                else 0
            ),
        )


report_center_query_service = ReportCenterQueryService()
