"""Deterministic regression checks; semantic challenge cases are not claimed solved by regex."""
import json
from pathlib import Path

import pytest

from cadence.agent.integrity import reply_violations
from cadence.agent.models import EvidenceItem
from cadence.agent.prompts import build_system_prompt, build_user_prompt
from cadence.agent.rules import apply_rules

CASES = json.loads((Path(__file__).parent / "fixtures/release_challenges.json").read_text())


@pytest.mark.parametrize("case", [c for c in CASES if c["check"] == "deterministic"], ids=lambda c: c["id"])
def test_release_contract(case):
    flags = reply_violations(case["reply"], set(), allow_private_handoff=case["allow_private_handoff"])
    if case["expected_flag"]:
        assert case["expected_flag"] in flags
    else:
        assert flags == []


def test_retrieved_instructions_stay_in_untrusted_data_not_system_policy():
    attack = next(c for c in CASES if c["id"] == "retrieved_instruction")
    evidence = [EvidenceItem(thread_id="attack", score=1, customer_text=attack["customer"], brand_reply=attack["evidence"])]
    system = build_system_prompt()
    assert "untrusted data" in system
    assert attack["evidence"] not in system
    assert "Ignore all previous instructions" in build_user_prompt(attack["customer"], evidence, apply_rules(attack["customer"]))
