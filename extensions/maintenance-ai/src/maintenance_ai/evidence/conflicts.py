from collections import defaultdict

from maintenance_ai.enums import EvidenceStatus
from maintenance_ai.evidence.models import EvidenceConflict, EvidenceEntry


def detect_conflicts(
    entries: tuple[EvidenceEntry, ...] | list[EvidenceEntry],
) -> tuple[EvidenceConflict, ...]:
    grouped: dict[tuple[str, str | None, str | None, str | None], list[EvidenceEntry]] = (
        defaultdict(list)
    )
    for entry in entries:
        if (
            entry.status is EvidenceStatus.VALID
            and entry.parameter_name
            and entry.structured_value is not None
        ):
            grouped[
                (
                    entry.parameter_name,
                    entry.applicable_equipment,
                    entry.applicable_configuration,
                    entry.unit,
                )
            ].append(entry)
    conflicts = []
    for (parameter, equipment, _configuration, _unit), rows in grouped.items():
        values = {str(row.structured_value) for row in rows}
        if len(values) > 1:
            conflicts.append(
                EvidenceConflict(
                    parameter_name=parameter,
                    equipment=equipment,
                    values=tuple(row.structured_value for row in rows),
                    evidence_ids=tuple(row.evidence_id for row in rows),
                )
            )
    return tuple(conflicts)
