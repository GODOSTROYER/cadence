"""FastAPI server for Cadence (CONTRACT.md §10) plus the helpers shared with the UI export script."""

from cadence.api.decisions import parse_decision_log
from cadence.api.merge import merge_golden

__all__ = ["merge_golden", "parse_decision_log"]
