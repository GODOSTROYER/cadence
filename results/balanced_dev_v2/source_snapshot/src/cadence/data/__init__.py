"""Data pipeline: raw TWCS csv -> cleaned SpotifyCares threads, link map, templates, candidates.

Public surface:
- :mod:`cadence.data.clean`   — text cleaning rules (CONTRACT §3.1), ``asks_dm``, ``detect_language``.
- :mod:`cadence.data.load`    — typed CSV loader and brand reply-graph extraction.
- :mod:`cadence.data.threads` — opener detection and thread assembly (CONTRACT §3).
- :mod:`cadence.data.links`   — t.co collection and one-time HTTP resolution.
- :mod:`cadence.data.summarize` — openers table, reply templates and stats.
- :mod:`cadence.data.sample`  — stratified golden-set candidate sampling.
"""

from cadence.data.clean import CleanResult, asks_dm, clean_text, detect_language

__all__ = ["CleanResult", "asks_dm", "clean_text", "detect_language"]
