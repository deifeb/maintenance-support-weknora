from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.ai_report_repository import (
    AIReportRepository,
    ai_report_repository,
)
from app.schemas.ai_report import AIReportCreateRequest
from app.schemas.common import PageData
from app.schemas.report_center import (
    ReportCenterItemRead,
    ReportCenterLatestVersionRead,
    ReportCenterQuery,
    ReportJobCreateRequest,
    ReportJobStatusRead,
    ReportVersionSummaryRead,
)
from app.security.actor import ActorContext
from app.services.ai_report_service import (
    AIReportService,
    ai_report_service,
)


class ReportCenterQueryService:
    def __init__(
        self,
        repository: AIReportRepository | None = None,
        report_service: AIReportService | None = None,
    ) -> None:
        self.repository = repository or ai_report_repository
        self.report_service = (
            report_service or ai_report_service
        )

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

    @staticmethod
    def _version_summary(version) -> ReportVersionSummaryRead:
        return ReportVersionSummaryRead(
            id=version.id,
            version_number=version.version_number,
            status=version.status,
            parent_version_id=version.parent_version_id,
            template_version=version.template_version,
            content_digest=version.content_digest,
            input_digest=version.input_digest,
            generation_mode=version.generation_mode,
            generated_at=version.generated_at,
        )

    def _job_status_read(
        self,
        job,
        version,
    ) -> ReportJobStatusRead:
        return ReportJobStatusRead(
            report_id=job.id,
            report_code=job.report_code,
            report_type=job.report_type,
            job_status=job.status,
            title=job.title,
            progress_percent=job.progress_percent,
            error_code=job.error_code,
            latest_version=self._version_summary(
                version
            ),
        )

    def create_job(
        self,
        session: Session,
        actor: ActorContext,
        payload: ReportJobCreateRequest,
    ) -> ReportJobStatusRead:
        job = self.report_service.create(
            session,
            actor,
            AIReportCreateRequest(
                **payload.model_dump(mode="json")
            ),
        )
        version = self.report_service.latest_version(
            session,
            actor,
            job.id,
        )
        return self._job_status_read(
            job,
            version,
        )

    def job_status(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> ReportJobStatusRead:
        job = self.report_service.get_job(
            session,
            actor,
            report_job_id,
        )
        version = self.report_service.latest_version(
            session,
            actor,
            report_job_id,
        )
        return self._job_status_read(
            job,
            version,
        )

    def detail(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> dict[str, Any]:
        return self.report_service.read(
            session,
            actor,
            report_job_id,
        )

    def versions(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> list[ReportVersionSummaryRead]:
        rows = self.report_service.list_versions(
            session,
            actor,
            report_job_id,
        )
        return [
            self._version_summary(row)
            for row in rows
        ]

    def regenerate(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
    ) -> ReportJobStatusRead:
        version = self.report_service.regenerate(
            session,
            actor,
            report_job_id,
        )
        job = self.report_service.get_job(
            session,
            actor,
            report_job_id,
        )
        return self._job_status_read(
            job,
            version,
        )

    def export(
        self,
        session: Session,
        actor: ActorContext,
        report_job_id: int,
        export_format: str,
    ) -> tuple[bytes, str, str]:
        return self.report_service.export(
            session,
            actor,
            report_job_id,
            export_format,
        )


report_center_query_service = ReportCenterQueryService()
