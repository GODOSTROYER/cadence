"""Scoped claim changes preserve the measured v2 registry and source bytes."""
from cadence.config import Paths
from cadence.knowledge import ClaimScope, KnowledgeStore


def test_v3_keeps_sources_and_only_declared_claim_changes():
    original = KnowledgeStore.load(Paths.CONFIG / "knowledge" / "v2.json")
    revised = KnowledgeStore.load(Paths.CONFIG / "knowledge" / "v3.json")
    assert revised.registry.sources == original.registry.sources
    for previous in original.registry.claims:
        current = revised.claims[previous.id]
        if previous.id == "feature_ideas":
            expected_scope = previous.scope.model_copy(update={"issues": ("feature_request", "feedback_submission")})
            assert current == previous.model_copy(update={"scope": expected_scope})
        elif previous.id in {"offline_downloads", "smart_shuffle", "smart_shuffle_disable", "shuffle_repeats"}:
            expected_scope = previous.scope.model_copy(update={"plans": (*previous.scope.plans, "premium_family")})
            assert current == previous.model_copy(update={"scope": expected_scope})
        else:
            assert current == previous
    assert len(revised.registry.claims) == len(original.registry.claims) + 1
    assert original.get("family_separate_accounts", "2026-09-18") is None
    claim = revised.get_current("family_separate_accounts", "2026-09-18")
    assert claim.source_id == "family-plan"
    assert "does not establish the cause" in " ".join(claim.limits)


def test_family_account_clarification_requires_known_supported_context():
    store = KnowledgeStore.load(Paths.CONFIG / "knowledge" / "v3.json")
    context = {"plan": "premium_family", "region": "US", "issues": ["connect_unwanted_takeover"]}
    assert store.get_applicable("family_separate_accounts", "2026-09-18", **context)
    for invalid in ({"plan": "premium"}, {"plan": None}, {"region": None}, {"region": "IN"},
                    {"issues": ["spotify_connect"]}, {"issues": ["security"]}, {"issues": []}):
        assert store.get_applicable("family_separate_accounts", "2026-09-18", **(context | invalid)) is None
    assert store.get_applicable("family_separate_accounts", "2026-10-18", **context) is None


def test_feedback_submission_uses_verified_workflow_not_feature_absence():
    store = KnowledgeStore.load(Paths.CONFIG / "knowledge" / "v3.json")
    claim = store.get_applicable("feature_ideas", "2026-09-18", issues=["feedback_submission"])
    assert claim
    assert claim.source_id == "suggest-feature"
    assert "existing feature" in " ".join(claim.limits)
    assert store.get_applicable("feature_ideas", "2026-09-18", issues=["playlist_create"]) is None


def test_explicit_family_subtype_preserves_generic_premium_guidance():
    store = KnowledgeStore.load(Paths.CONFIG / "knowledge" / "v3.json")
    for claim_id, issue in (("offline_downloads", "download_howto"), ("smart_shuffle", "smart_shuffle"),
                            ("smart_shuffle_disable", "smart_shuffle"), ("shuffle_repeats", "shuffle_repeats")):
        assert store.get_applicable(claim_id, "2026-09-18", plan="premium_family", device="mobile", issues=[issue])
    assert store.get_applicable("smart_shuffle_disable", "2026-09-18", plan="free", device="mobile", issues=["smart_shuffle"]) is None


def test_family_subtype_never_inherits_individual_only_terms():
    individual = ClaimScope(plans=("premium_individual",), issues=("plan_information",))
    assert individual.matches(plan="premium_individual", issues=["plan_information"])
    assert not individual.matches(plan="premium_family", issues=["plan_information"])
    # No universal Family-to-Premium remap: each reviewed claim must include Family explicitly.
    plain_premium = ClaimScope(plans=("premium",), issues=("plan_information",))
    assert not plain_premium.matches(plan="premium_family", issues=["plan_information"])
