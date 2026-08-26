"""Frozen, outcome-blind exception-reading selection."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


READINGS = ("defeater_or", "conjunctive", "refuse")


class ExceptionReadingError(ValueError):
    """Raised when a selection set is not frozen or is outcome-contaminated."""


def select_reading(
    alternatives: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    criterion: str = "source_annotation_agreement",
    frozen: bool = True,
) -> dict[str, Any]:
    """Select one reading from pre-registered, non-outcome labels.

    Each candidate score must be computed from source annotations only.  The
    function refuses outcome fields so J1B cannot silently tune semantics to
    downstream instrument results.
    """
    if not frozen:
        raise ExceptionReadingError("exception alternatives must be frozen before selection")
    if set(alternatives) != set(READINGS):
        raise ExceptionReadingError(f"alternatives must contain exactly {list(READINGS)}")
    scores: dict[str, float] = {}
    for reading, records in alternatives.items():
        if not records:
            raise ExceptionReadingError(f"reading {reading!r} has no source annotations")
        values = []
        for record in records:
            if not isinstance(record, Mapping) or criterion not in record:
                raise ExceptionReadingError(f"reading {reading!r} missing criterion {criterion!r}")
            if any(key in record for key in ("oe", "afs", "instrument", "downstream")):
                raise ExceptionReadingError("selection criterion must not include outcome fields")
            value = record[criterion]
            if isinstance(value, bool):
                values.append(float(value))
            elif isinstance(value, (int, float)) and 0 <= value <= 1:
                values.append(float(value))
            else:
                raise ExceptionReadingError(f"invalid criterion value for reading {reading!r}")
        scores[reading] = sum(values) / len(values)
    selected = max(READINGS, key=lambda reading: (scores[reading], -READINGS.index(reading)))
    return {"schema_version": "exception-reading/1.0", "status": "selected", "criterion": criterion,
            "selected": selected, "scores": scores, "outcome_blind": True, "claimable": True}
