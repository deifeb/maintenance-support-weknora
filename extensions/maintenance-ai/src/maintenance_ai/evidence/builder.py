from maintenance_ai.evidence.conflicts import detect_conflicts
from maintenance_ai.evidence.models import EvidenceEntry, EvidencePackage


class EvidencePackageBuilder:
    def build(
        self,
        entries: list[EvidenceEntry] | tuple[EvidenceEntry, ...] | None = None,
        *,
        items: list[EvidenceEntry] | tuple[EvidenceEntry, ...] | None = None,
        query_text: str | None = None,
        missing_evidence: tuple[str, ...] = (),
        retrieval_metadata: dict | None = None,
    ) -> EvidencePackage:
        del query_text
        selected = entries if entries is not None else (items or ())
        unique = {entry.evidence_id: entry for entry in selected}
        rows = tuple(unique.values())
        return EvidencePackage(
            entries=rows,
            conflicts=detect_conflicts(rows),
            missing_evidence=missing_evidence,
            retrieval_metadata=retrieval_metadata or {},
        )
