"""Source identity and scope are release conditions, not advisory model context."""
from __future__ import annotations

import importlib.util
import json
from datetime import date

import pytest
from pydantic import ValidationError

from cadence.agent.models import EvidenceItem
from cadence.config import Paths
from cadence.knowledge import KnowledgeRegistry, KnowledgeStore

AS_OF = date(2026, 9, 18)


@pytest.fixture
def sandbox_registry(tmp_path):
    original = KnowledgeStore.load()
    data = original.registry.model_dump(mode="json")
    for source in original.sources.values():
        destination = tmp_path / source.snapshot
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(original.source_path(source).read_bytes())
    path = tmp_path / "v2.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


def write_registry(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return KnowledgeStore.load(path)


def test_all_bundled_claims_have_reviewed_official_evidence():
    store = KnowledgeStore.load()
    assert len(store.sources) >= 20
    assert not any(store.verify(AS_OF).values())
    assert all(source.role == "current_official" and source.reviewer_type == "ai"
               for source in store.sources.values())
    for record in store.evidence(store.claims, as_of=AS_OF):
        item = EvidenceItem.model_validate(record)
        assert item.thread_id.startswith("current:")
        assert "reviewer_type=ai" in item.customer_text
        assert item.resolved_links[0].startswith("https://support.spotify.com/")


def test_expiry_and_future_date_block_authority():
    store = KnowledgeStore.load()
    assert store.get("playlist_search", "2026-09-17") is None
    assert store.get("playlist_search", "2026-10-17") is not None
    assert store.get("playlist_search", "2026-10-18") is None
    assert store.get("playlist_search", "2027-01-01") is None
    assert store.evidence(["playlist_search"], "2027-01-01") == []


def test_unavailable_source_never_authorizes_claim(sandbox_registry):
    path, data = sandbox_registry
    source_id = next(c["source_id"] for c in data["claims"] if c["id"] == "library_filters")
    next(s for s in data["sources"] if s["id"] == source_id)["review_status"] = "unavailable"
    store = write_registry(path, data)
    assert store.unavailable_reason("library_filters", AS_OF) == "unreviewed_source"
    assert store.get("library_filters", AS_OF) is None


def test_tampered_snapshot_revokes_claim_and_changes_fingerprint(sandbox_registry):
    path, _ = sandbox_registry
    store = KnowledgeStore.load(path)
    before = store.fingerprint()
    source = store.sources[store.claims["playlist_search"].source_id]
    store.source_path(source).write_text("invented procedure", encoding="utf-8")
    assert store.get("playlist_search", AS_OF) is None
    assert store.unavailable_reason("playlist_search", AS_OF) == "snapshot_hash_mismatch"
    assert store.fingerprint() != before
    assert store.get("contact_support", AS_OF) is not None


def test_missing_snapshot_blocks_source(sandbox_registry):
    path, _ = sandbox_registry
    store = KnowledgeStore.load(path)
    store.source_path(store.sources[store.claims["contact_support"].source_id]).unlink()
    assert store.get("contact_support", AS_OF) is None
    assert store.evidence(["contact_support"], AS_OF) == []


def test_source_path_cannot_escape_registry(sandbox_registry):
    path, data = sandbox_registry
    data["sources"][0]["snapshot"] = "../outside.txt"
    store = write_registry(path, data)
    claim = next(c for c in store.claims.values() if c.source_id == data["sources"][0]["id"])
    assert store.unavailable_reason(claim.id, AS_OF) == "missing_or_invalid_snapshot"


def test_historical_text_cannot_authorize_current_procedure(sandbox_registry):
    path, data = sandbox_registry
    data["sources"][0]["role"] = "historical"
    store = write_registry(path, data)
    claim = next(c for c in store.claims.values() if c.source_id == data["sources"][0]["id"])
    assert store.unavailable_reason(claim.id, AS_OF) == "historical_source_not_current_authority"


@pytest.mark.parametrize("url", ["http://support.spotify.com/us/article/test/",
                                  "https://support.spotify.com.attacker.example/article/test/",
                                  "https://example.org/spotify-help/",
                                  "https://username:secret@support.spotify.com/us/article/test/"])
def test_unofficial_or_unsafe_origin_rejected(sandbox_registry, url):
    _, data = sandbox_registry
    data["sources"][0]["final_url"] = url
    with pytest.raises(ValidationError):
        KnowledgeRegistry.model_validate(data)


def test_duplicate_claim_and_missing_source_rejected(sandbox_registry):
    _, data = sandbox_registry
    data["claims"].append(data["claims"][0])
    with pytest.raises(ValidationError, match="duplicate"):
        KnowledgeRegistry.model_validate(data)
    data["claims"].pop()
    data["claims"][0]["source_id"] = "unknown"
    with pytest.raises(ValidationError, match="unknown source"):
        KnowledgeRegistry.model_validate(data)


def test_review_dates_cannot_precede_actual_fetch(sandbox_registry):
    _, data = sandbox_registry
    data["sources"][0]["verified_on"] = "2026-09-17"
    with pytest.raises(ValidationError, match="dates must be ordered"):
        KnowledgeRegistry.model_validate(data)


def test_scope_requires_known_matching_device_and_plan():
    store = KnowledgeStore.load()
    assert store.get_applicable("library_filters", AS_OF, device="mobile", issues=["library_missing"])
    assert store.get_applicable("library_filters", AS_OF, device="desktop", issues=["library_missing"]) is None
    assert store.get_applicable("library_filters", AS_OF, issues=["library_missing"]) is None
    assert store.get_applicable("playlist_search", AS_OF, device="desktop", issues=["playlist_search"])
    assert store.get_applicable("playlist_search", AS_OF, device="web", issues=["playlist_search"]) is None
    assert store.get_applicable("smart_shuffle_disable", AS_OF, device="mobile", plan="premium", issues=["smart_shuffle"])
    assert store.get_applicable("smart_shuffle_disable", AS_OF, device="mobile", plan="free", issues=["smart_shuffle"]) is None
    assert store.get_applicable("smart_shuffle_disable", AS_OF, plan="premium", issues=["smart_shuffle"]) is None


def test_hulu_activation_scope_is_distinct_from_student_verification():
    store = KnowledgeStore.load()
    assert store.get_applicable("student_hulu_linking", AS_OF, plan="premium_student", region="US", issues=["student_bundle_linking"])
    assert store.get_applicable("student_hulu_linking", AS_OF, plan="premium_student", region="IN", issues=["student_bundle_linking"]) is None
    assert store.get_applicable("student_hulu_linking", AS_OF, plan="premium", region="US", issues=["student_bundle_linking"]) is None
    assert store.get_applicable("student_hulu_linking", AS_OF, plan="premium_student", issues=["student_bundle_linking"]) is None
    assert "student_verification" not in store.get("student_hulu_linking", AS_OF).scope.issues


@pytest.mark.parametrize("issues", [None, [], ["downloads_missing"], ["playlist_search"]])
def test_issue_scope_must_be_present_and_match(issues):
    store = KnowledgeStore.load()
    # Authority-only introspection remains available; it does not authorize a response.
    assert store.get("library_filters", AS_OF)
    assert store.get_applicable("library_filters", AS_OF, device="mobile", issues=issues) is None


def test_issue_scope_accepts_one_relevant_issue_but_not_unrelated_ones():
    store = KnowledgeStore.load()
    assert store.get_applicable("library_filters", AS_OF, device="mobile", issues={"library_missing", "feature_request"})
    assert store.get_applicable("app_update", AS_OF, issues={"offline_playback"})
    assert store.get_applicable("app_restart", AS_OF, issues={"track_unplayable"})
    assert store.get_applicable("app_update", AS_OF, issues={"playlist_problem"}) is None
    assert store.get_applicable("app_restart", AS_OF, issues={"catalog_missing"}) is None
    assert store.get_applicable("contact_support", AS_OF)  # Unrestricted support destination.


def test_local_policy_with_official_url_cannot_authorize_procedure(sandbox_registry):
    path, data = sandbox_registry
    source_id = next(c["source_id"] for c in data["claims"] if c["id"] == "app_update")
    source = next(s for s in data["sources"] if s["id"] == source_id)
    source["role"] = "local_policy"
    source["authority"] = "Cadence local policy"
    store = write_registry(path, data)
    assert store.get("app_update", AS_OF)  # Metadata access makes no procedural-authority claim.
    assert store.get_applicable("app_update", AS_OF, issues=["playback_failure"]) is None
    assert store.get_applicable("app_update", AS_OF, issues=["playback_failure"], required_role="current_official") is None


def test_current_authority_lookup_does_not_invent_missing_prerequisites():
    store = KnowledgeStore.load()
    # Looking up an official claim to decide what to ask is different from releasing it.
    assert store.get_current("smart_shuffle_disable", AS_OF)
    assert store.get_applicable("smart_shuffle_disable", AS_OF, issues=["smart_shuffle"]) is None
    assert store.get_current("smart_shuffle_disable", "2026-10-18") is None
    assert store.get_current("unknown_claim", AS_OF) is None


def test_current_authority_lookup_rejects_local_policy_and_tampering(sandbox_registry):
    path, data = sandbox_registry
    source_id = next(c["source_id"] for c in data["claims"] if c["id"] == "smart_shuffle_disable")
    source = next(s for s in data["sources"] if s["id"] == source_id)
    source["role"] = "local_policy"
    store = write_registry(path, data)
    assert store.get("smart_shuffle_disable", AS_OF)
    assert store.get_current("smart_shuffle_disable", AS_OF) is None
    source["role"] = "current_official"
    store = write_registry(path, data)
    store.source_path(store.sources[source_id]).write_text("changed source", encoding="utf-8")
    assert store.get_current("smart_shuffle_disable", AS_OF) is None


def test_unknown_claims_have_no_evidence():
    store = KnowledgeStore.load()
    assert store.get("invented_procedure", AS_OF) is None
    assert store.evidence(["invented_procedure"], AS_OF) == []
    assert store.audit_record("invented_procedure", AS_OF)["unavailable_reason"] == "unknown_claim"


def test_evidence_is_deduplicated_and_preserves_source_limits():
    store = KnowledgeStore.load()
    evidence = store.evidence(["app_reinstall", "app_reinstall"], AS_OF)
    assert len(evidence) == 1
    assert "downloaded again" in evidence[0]["brand_reply"]
    assert "loss-of-downloads warning" in evidence[0]["brand_reply"]
    assert store.audit_record("app_reinstall", AS_OF)["source"]["response_sha256"]


def test_normalized_hash_is_checked_independently(sandbox_registry):
    path, data = sandbox_registry
    data["sources"][0]["normalized_sha256"] = "0" * 64
    store = write_registry(path, data)
    claim = next(c for c in store.claims.values() if c.source_id == data["sources"][0]["id"])
    assert store.unavailable_reason(claim.id, AS_OF) == "normalized_hash_mismatch"


def test_article_extraction_excludes_navigation_and_footer():
    spec = importlib.util.spec_from_file_location("verify_knowledge", Paths.ROOT / "scripts/verify_knowledge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    html = ('<nav>Noise</nav><h1>Example</h1><p>Follow the device instructions to configure the supported feature.</p>'
            '<svg><text>hidden</text></svg><h2>Related Articles</h2><p>Unrelated guidance</p><footer>Footer</footer>')
    normalized = module.normalize_article(html)
    assert normalized == "Example Follow the device instructions to configure the supported feature.\n"
