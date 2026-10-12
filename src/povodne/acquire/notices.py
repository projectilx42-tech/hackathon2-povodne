"""Notices of the acquire step: warnings and explanations with a stable code, for the dashboard (D-M1-05).

A Notice is a plain string (the English message, so it still fits `run.json.warnings`) that also carries a code,
a severity and machine-readable details. The full list of codes and how the UI should show them is in docs/NOTICES.md.

Severity:
- "error":   an answer the user asked for will be missing (no flood map, or no damage / cut-off analysis);
- "warning": the answer exists but may be less reliable or less complete;
- "info":    what the system decided and why (no action needed).
"""
from __future__ import annotations

SEVERITY = {
    # errors
    "cdse_credentials": "error",
    "acquire_failed": "error",
    "s1_no_post": "error",
    "s1_no_pair": "error",
    "s1_no_clean_pre": "error",
    "osm_failed": "error",
    "osm_key_missing": "error",
    # warnings
    "s1_partial_coverage": "warning",
    "s1_alt_missing": "warning",
    "better_view_soon": "warning",
    "pre_may_be_flooded": "warning",
    "pre_window_after_rise": "warning",
    "pre_check_blind": "warning",
    "valley_visibility_unavailable": "warning",
    "s2_none": "warning",
    "s2_cloudy": "warning",
    "s2_failed": "warning",
    # info
    "post_image_date": "info",
    "perm_water_ref_short": "warning",
    "pre_rise_detected": "info",
    "event_day_pass_used": "info",
    "event_day_pass_dropped": "info",
    "main_track_by_visibility": "info",
}


class Notice(str):
    """English message (behaves as a normal string) + `code`, `severity` and `details` for the UI."""

    def __new__(cls, code: str, message: str, **details):
        if code not in SEVERITY:
            raise ValueError(f"unknown notice code {code!r}; add it to SEVERITY and docs/NOTICES.md")
        obj = super().__new__(cls, message)
        obj.code, obj.severity, obj.details = code, SEVERITY[code], details
        return obj

    def to_json(self, step: str = "acquire") -> dict:
        return {"step": step, "code": self.code, "severity": self.severity, "message": str(self), "details": self.details}
