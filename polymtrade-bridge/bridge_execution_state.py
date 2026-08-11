"""Classify Bridge execution outcomes without weakening trade guards."""

from __future__ import annotations


STATUS_PENDING = "PENDING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"
STATUS_FAILED_RETRYABLE = "FAILED_RETRYABLE"
STATUS_SUBMITTED_UNVERIFIED = "SUBMITTED_UNVERIFIED"


_RETRYABLE_PRE_SUBMIT_MARKERS = (
    "could not open buy dialog",
    "could not open sell dialog",
    "target market content never appeared",
    "target event ",
)

_SKIP_MARKERS = (
    "skipped",
    "blocked buy before submit",
    "portfolio risk blocked",
    "support_sell=false",
    "no copy-trading config matches",
)


def is_retryable_pre_submit_failure(reason: str | None) -> bool:
    """Return true only for failures known to happen before an order submit."""
    text = (reason or "").strip().lower()
    if not text:
        return False
    if text.startswith("target event ") and "never appeared" in text:
        return True
    return any(marker in text for marker in _RETRYABLE_PRE_SUBMIT_MARKERS)


def status_for_failure(reason: str | None) -> str:
    """Separate expected safety decisions from retryable and unknown failures."""
    if is_retryable_pre_submit_failure(reason):
        return STATUS_FAILED_RETRYABLE
    text = (reason or "").strip().lower()
    if any(marker in text for marker in _SKIP_MARKERS):
        return STATUS_SKIPPED
    return STATUS_FAILED
