"""Executable response contracts for the experimental VerifiedAgent.

The model may choose among these exact, already eligible outputs. It cannot supply
missing prerequisites or write a procedure. Source expiry blocks procedures while
source-independent, necessary clarification remains available. Historical agents
do not import this registry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cadence.agent.models import EvidenceItem

if TYPE_CHECKING:
    from cadence.agent.request_frame import RequestFrame
    from cadence.knowledge import KnowledgeStore


ResponseKind = Literal["resolution", "clarification", "handoff", "social"]
POLICY_ID = "policy:verified-response-v1"
TECHNICAL = frozenset({"playback_failure", "offline_playback", "track_unplayable", "app_problem"})
PLAYLIST = frozenset({"playlist_create", "playlist_search", "playlist_collaboration", "playlist_problem"})
DIAGNOSTIC = TECHNICAL | PLAYLIST | {"downloads_missing", "library_missing", "local_files"}
CONTROLS = frozenset({"autoplay_after_end", "smart_shuffle"})
RISK_KINDS = frozenset({"account_intervention", "security", "money", "legal_safety", "directed_abuse",
                        "churn", "repeated_contact", "support_requested"})


class ActionCandidate(BaseModel):
    """Exact immutable public wording plus its applicability/source record."""

    model_config = ConfigDict(frozen=True)
    id: str
    reply: str
    citations: list[str]
    evidence: list[EvidenceItem]
    response_kind: ResponseKind
    eligibility_reasons: list[str] = Field(default_factory=list)
    required_claims: list[str] = Field(default_factory=list)

    @field_validator("reply")
    @classmethod
    def exact_public_text(cls, value: str) -> str:
        if len(value) > 280 or not value.endswith(" /AI") or "\n" in value:
            raise ValueError("An approved response must be complete, <=280 characters and signed /AI")
        return value


@dataclass(frozen=True)
class ActionSpec:
    """Declarative part of a contract; the action-specific checks below are mandatory."""

    id: str
    issues: frozenset[str]
    kind: ResponseKind
    claim: str | None = None
    required_slots: tuple[str, ...] = ()
    forbidden_issues: frozenset[str] = frozenset()
    excluded_steps: tuple[str, ...] = ()


def _spec(name, issues, kind="resolution", claim=None, slots=(), forbidden=(), tried=()):
    return ActionSpec(name, frozenset(issues), kind, claim, tuple(slots), frozenset(forbidden), tuple(tried))


# The inventory is inspectable, but eligibility is computed, never taken from a model-selected id.
ACTION_SPECS = (
    _spec("ask_metadata", {"metadata_attribution"}, "clarification"),
    _spec("ask_device", DIAGNOSTIC | CONTROLS, "clarification"),
    _spec("ask_error", TECHNICAL | {"student_bundle_linking", "playlist_problem"}, "clarification"),
    _spec("ask_playback_scope", TECHNICAL, "clarification"),
    _spec("ask_playlist_problem", {"playlist_collaboration", "playlist_problem"}, "clarification"),
    _spec("ask_catalog_item", {"catalog_missing", "track_unplayable"}, "clarification"),
    _spec("ask_country", {"country_availability", "student_bundle_linking", "family_household"}, "clarification"),
    _spec("ask_plan", {"download_howto", "student_bundle_linking", "smart_shuffle", "shuffle_repeats"}, "clarification"),
    _spec("ask_recommendation_timing", {"playlist_recommendations"}, "clarification"),
    _spec("restart_playback", TECHNICAL, claim="app_restart", tried=("restart", "reboot", "close and reopen")),
    _spec("update_playback", TECHNICAL, claim="app_update", tried=("updat", "latest version")),
    _spec("library_filters", {"library_missing"}, claim="library_filters", slots=("device",),
          forbidden={"downloads_missing", "offline_playback", "local_files"}, tried=("filter",)),
    _spec("playlist_create", {"playlist_create"}, claim="playlist_create"),
    _spec("playlist_search", {"playlist_search"}, claim="playlist_search", slots=("device",)),
    _spec("playlist_collaborate", {"playlist_collaboration"}, claim="playlist_collaborate"),
    _spec("download_guide", {"download_howto"}, claim="offline_downloads", slots=("plan",),
          forbidden={"downloads_missing", "offline_playback"}),
    _spec("download_loss_guidance", {"downloads_missing"}, claim="offline_download_loss"),
    _spec("catalog_availability", {"catalog_missing"}, claim="catalog_availability",
          forbidden={"track_unplayable", "metadata_attribution", "library_missing", "downloads_missing"}),
    _spec("service_countries", {"country_availability"}, claim="service_countries"),
    _spec("metadata_report", {"metadata_attribution"}, "handoff", "metadata_attribution",
          slots=("artist",)),
    _spec("public_display_name", {"public_display_name"}, claim="public_display_name",
          forbidden={"account_identifier"}),
    _spec("student_bundle_linking", {"student_bundle_linking"}, claim="student_hulu_linking",
          slots=("plan", "country"), forbidden={"student_verification"}),
    _spec("family_household", {"family_household"}, claim="family_household", slots=("country",)),
    _spec("wrapped_updates", {"wrapped_updates"}, claim="wrapped"),
    _spec("autoplay_off", {"autoplay_after_end"}, claim="autoplay", slots=("device", "affected_scope"),
          forbidden={"smart_shuffle"}),
    _spec("smart_shuffle_off", {"smart_shuffle"}, claim="smart_shuffle_disable", slots=("device", "plan")),
    _spec("shuffle_repeats", {"shuffle_repeats"}, claim="shuffle_repeats", slots=("plan",)),
    _spec("explicit_version", {"explicit_version"}, claim="explicit_versions", forbidden={"metadata_attribution"}),
    _spec("feature_idea", {"feature_request"}, "handoff", "feature_ideas",
          forbidden=DIAGNOSTIC | {"metadata_attribution", "catalog_missing", "student_bundle_linking"}),
    _spec("social_thanks", {"social_closure"}, "social"),
)
SPECS_BY_ID = {spec.id: spec for spec in ACTION_SPECS}
CORE_ACTION_IDS = frozenset(spec.id for spec in ACTION_SPECS
                           if spec.kind in {"clarification", "social"} or spec.id in {"restart_playback", "update_playback"})


def _issues(frame) -> set[str]:
    return set(frame.issues)


def _value(frame, slot: str) -> str:
    value = frame.value(slot)
    if value is None and slot == "device":
        value = frame.value("platform")
    return str(value or "").strip()


def _known(frame, slot: str) -> bool:
    return bool(_value(frame, slot))


def _mobile(frame) -> bool:
    return bool(re.search(r"\b(?:android|ios|iphone|ipad|mobile|phone|tablet)\b", _value(frame, "device"), re.I))


def _desktop(frame) -> bool:
    return bool(re.search(r"\b(?:desktop|windows|mac|macos|linux|computer|pc)\b", _value(frame, "device"), re.I))


def _blocked(frame) -> bool:
    if frame.language_supported is not True or frame.intelligible is not True or frame.media_only:
        return True
    return any(frame.risk(kind).state in {"present", "unknown"} for kind in RISK_KINDS)


def _was_tried(frame, words: tuple[str, ...]) -> bool:
    attempted = _value(frame, "attempted_steps").lower()
    return bool(attempted) and any(word in attempted for word in words)


def _explicitly_tried(text: str, words: tuple[str, ...]) -> bool:
    """Catch common omitted attempt facts without treating negated plans as attempts."""
    for clause in re.split(r"[.!?;\n]", text.lower()):
        if not any(word in clause for word in words):
            continue
        if re.search(r"\b(?:not|never|haven['’]t|didn['’]t|cannot|can['’]t|won['’]t)\b", clause):
            continue
        if re.search(r"\b(?:already|tried|restarted|rebooted|updated|checked|reinstalled)\b", clause):
            return True
    return False


def _public_howto(frame, text: str) -> bool:
    """Concrete symptom reports cannot become generic feature instructions."""
    return bool(re.search(r"\b(?:how (?:do|can|to)|where (?:do|can|is)|instructions|show me how|"
                          r"(?:want|wanna|wish|like) to (?:create|make|share|search)|"
                          r"way to (?:create|make|share|search)|can I (?:create|make|share|search))\b", text, re.I))


def _policy_evidence(kind: str) -> EvidenceItem:
    return EvidenceItem(thread_id=POLICY_ID, customer_text="Cadence verified-response policy v1; local response policy",
                        brand_reply=("Ask only genuinely missing, relevant nonprivate context. Never claim an action was "
                                     "performed. An honest scoped handoff does not claim a referral was sent. "
                                     "Social acknowledgments and handoffs are not support resolutions. "
                                     f"This response is classified as {kind}."))


def _source(knowledge, claim_id: str, as_of=None, *, frame=None) -> list[EvidenceItem]:
    claim = knowledge.get(claim_id, as_of=as_of)
    if claim is None:
        return []
    if frame is not None:
        device = "mobile" if _mobile(frame) else "desktop" if _desktop(frame) else None
        if device is None and re.search(r"\b(?:web|browser)\b", _value(frame, "device"), re.I):
            device = "web"
        raw_plan = _value(frame, "plan").lower()
        plan = ("premium_student" if "student" in raw_plan else "premium" if "premium" in raw_plan
                else "free" if "free" in raw_plan else None)
        region = _value(frame, "country") or None
        if region and region.lower() in {"us", "usa", "united states", "united states of america"}:
            region = "US"
        if knowledge.get_applicable(claim_id, as_of=as_of, device=device, plan=plan, region=region,
                                    issues=frame.issues, required_role="current_official") is None:
            return []
    elif knowledge.get_applicable(claim_id, as_of=as_of, required_role="current_official") is None:
        return []
    records = knowledge.evidence([claim_id], as_of=as_of)
    return [row if isinstance(row, EvidenceItem) else EvidenceItem.model_validate(row) for row in records]


def _candidate(spec: ActionSpec, body: str, evidence: list[EvidenceItem], reasons: list[str]) -> ActionCandidate:
    return ActionCandidate(id=spec.id, reply=body + " /AI", response_kind=spec.kind,
                           evidence=evidence, citations=[e.thread_id for e in evidence],
                           eligibility_reasons=reasons, required_claims=[spec.claim] if spec.claim else [])


def _contract(spec: ActionSpec, frame, text: str) -> tuple[bool, list[str]]:
    issues = _issues(frame)
    if not (issues & spec.issues) or issues & spec.forbidden_issues:
        return False, []
    if (any(not _known(frame, slot) for slot in spec.required_slots)
            or _was_tried(frame, spec.excluded_steps) or _explicitly_tried(text, spec.excluded_steps)):
        return False, []
    # A secondary technical fault takes precedence over general catalog/feature/profile guidance.
    if issues & TECHNICAL and spec.id not in {
        "ask_device", "ask_error", "ask_playback_scope", "ask_catalog_item", "restart_playback", "update_playback"
    }:
        return False, []
    name = spec.id
    if name == "ask_device" and _known(frame, "device") and _known(frame, "app_version"):
        return False, []
    if name == "ask_device" and _known(frame, "device") and (
        issues & CONTROLS or _public_howto(frame, text) and not issues & TECHNICAL
    ):
        return False, []
    if name == "update_playback" and re.search(r"\b(?:latest|newest|current|up.to.date)\b", _value(frame, "app_version"), re.I):
        return False, []
    if name == "ask_error" and (_known(frame, "error") or not re.search(r"\b(?:error|message|says|code)\b", text, re.I)):
        return False, []
    if name == "ask_playback_scope" and (_known(frame, "affected_scope") or _known(frame, "track") or _known(frame, "release")):
        return False, []
    if name == "ask_metadata" and _known(frame, "artist") and (_known(frame, "release") or _known(frame, "track")):
        return False, []
    if name == "ask_catalog_item" and (_known(frame, "artist") or _known(frame, "track") or _known(frame, "release")):
        return False, []
    if name == "ask_country" and _known(frame, "country"):
        return False, []
    if name == "ask_plan" and _known(frame, "plan"):
        return False, []
    if name == "ask_recommendation_timing" and _known(frame, "affected_scope"):
        return False, []
    if name == "ask_playlist_problem" and (_known(frame, "error") or _known(frame, "affected_scope") or _public_howto(frame, text)):
        return False, []
    if name == "library_filters" and not _mobile(frame):
        return False, []
    if name == "library_filters" and re.search(r"\b(?:downloads?|downloaded|offline|local files?)\b", text, re.I):
        return False, []
    if name == "playlist_search" and not (_mobile(frame) or _desktop(frame)):
        return False, []
    if name in {"playlist_create", "playlist_search", "playlist_collaborate", "download_guide"} and not _public_howto(frame, text):
        return False, []
    if name == "public_display_name" and re.search(r"\b(?:user\s?name|login|identifier|recover|hacked)\b", text, re.I):
        return False, []
    if name == "student_bundle_linking" and (
        not re.search(r"\bstudent\b", _value(frame, "plan"), re.I)
        or _value(frame, "country").lower() not in {"us", "usa", "united states", "united states of america"}
        or not _public_howto(frame, text)
        or re.search(r"\b(?:anymore|reconnect|stopped|cannot|can['’]t|failed|error|rejected)\b", text, re.I)
    ):
        return False, []
    if name == "autoplay_off" and not re.search(
        r"\b(?:after|once)\b.*\b(?:ends?|finish(?:es|ed)?|over|last (?:song|track))\b",
        _value(frame, "affected_scope"), re.I
    ):
        return False, []
    if name == "feature_idea" and (_public_howto(frame, text) or _known(frame, "error")):
        return False, []
    if name == "social_thanks" and (not frame.social_closure or issues - {"social_closure"}):
        return False, []
    return True, ["supported issue: " + ", ".join(sorted(issues & spec.issues)),
                  "required facts present; contraindications and repeated steps absent"]


def _render(spec: ActionSpec, frame, url: str, text: str = "") -> str:
    name = spec.id
    if name == "ask_device":
        subject = ("offline playback" if "offline_playback" in _issues(frame) else
                   "the missing downloads" if "downloads_missing" in _issues(frame) else
                   "playlist search" if "playlist_search" in _issues(frame) else
                   "this playback problem" if _issues(frame) & TECHNICAL else "this issue")
        if _issues(frame) & CONTROLS or not (_issues(frame) & TECHNICAL) and _public_howto(frame, text):
            return "Which device are you using? The relevant controls depend on the device."
        if _known(frame, "device"):
            return f"Which Spotify app version are you using when {subject} occurs?"
        if _known(frame, "app_version"):
            return f"Which device are you using when {subject} occurs?"
        return f"Which device and Spotify app version are you using for {subject}?"
    if name == "ask_metadata":
        if _known(frame, "artist"):
            return "Which track or release is credited incorrectly? A public Spotify link would help identify the attribution problem."
        if _known(frame, "track") or _known(frame, "release"):
            return "Which artist should this release be credited to, and which artist is shown instead?"
        return "Which track or release has the incorrect artist credit, and who should it be credited to? Please share only public release details."
    bodies = {
        "ask_error": "What exact error text appears? Please leave out passwords, payment information and other private account details.",
        "ask_playback_scope": "Does the playback problem affect every track or only some? Please share a track title if only some are affected.",
        "ask_playlist_problem": "What happens when you try to use the playlist, and what would you like to do? Please describe the problem without private account details.",
        "ask_catalog_item": "Which artist, track or album are you looking for? Please share only public music details.",
        "ask_country": ("Which country is your Premium Student plan registered in? The bundle-linking guidance is country-specific."
                        if "student_bundle_linking" in _issues(frame) else
                        "Which country is your subscription registered in? Family-plan guidance is market-specific."
                        if "family_household" in _issues(frame) else
                        "Which country are you asking about? That is needed to check the relevant service-availability guidance."),
        "ask_plan": "Are you using Spotify Free, Premium, or Premium Student? The relevant guidance depends on your plan.",
        "ask_recommendation_timing": "Do the extra songs play after the playlist ends, or between its tracks?",
        "restart_playback": "Try closing and reopening the Spotify app. If playback still fails, describe what happens next.",
        "update_playback": f"Try updating the Spotify app. If playback still fails, describe what happens next. Official steps: {url}",
        "library_filters": f"On mobile, check Your Library's filters to see whether they are hiding saved music. This concerns saved library items, not downloaded copies: {url}",
        "playlist_create": f"You can create your own playlist in Spotify. Follow the steps for your device here: {url}",
        "playlist_collaborate": f"To invite people to a playlist you own, use Invite collaborators. Official instructions and access controls: {url}",
        "download_guide": f"Download options depend on your plan and device. Use the official guide for the supported download steps and requirements: {url}",
        "download_loss_guidance": f"Missing downloads are different from missing saved music. Spotify lists possible causes and download checks here: {url} I can't confirm the cause from this message alone.",
        "catalog_availability": f"Music availability can change over time and by country. I can't confirm why a particular release is missing or when it will return: {url}",
        "service_countries": f"Spotify's current supported countries and regions are listed here: {url} I can't confirm a future launch date.",
        "metadata_report": f"For a release credited to the wrong artist, use the reporting guidance here: {url} I can't change the credit or submit a report for you.",
        "public_display_name": f"Your display name appears on your profile and playlists; it does not change your login username. Official editing instructions: {url}",
        "student_bundle_linking": f"For US Premium Student, use the Hulu activation and linking steps here: {url} I can't access or reconnect accounts for you.",
        "family_household": f"For US Premium Family, members must live with the plan manager and use the same home address. I can't approve individual eligibility or an exception: {url}",
        "wrapped_updates": f"Wrapped is Spotify's annual personalized listening experience, including playlists. Eligibility varies; I can't confirm an upcoming release date: {url}",
        "autoplay_off": f"If similar songs play after your selection ends, you can turn off Autoplay in Spotify's settings. Device-specific steps: {url}",
        "smart_shuffle_off": f"On Premium mobile, open Settings and privacy, then Playback, and switch off Include Smart Shuffle in play modes: {url}",
        "shuffle_repeats": f"Premium offers a Fewer repeats shuffle style. It reduces repeats rather than eliminating them: {url}",
        "explicit_version": f"Search for another version of the release. E or EXPLICIT identifies explicit content; an alternative version may not exist: {url}",
        "feature_idea": f"You can search Spotify's Community Ideas, vote for an existing request or submit yours. I can't forward it or promise a release: {url}",
        "social_thanks": "You're welcome! Enjoy the music.",
    }
    if name == "playlist_search":
        lead = "On mobile, pull down inside the playlist to reveal its search." if _mobile(frame) else "On desktop, use the search at the top of the playlist."
        return f"{lead} Official guide: {url}"
    return bodies[name]


def shortlist(frame: RequestFrame, text: str, knowledge: KnowledgeStore, max_choices: int = 4,
              *, as_of=None) -> list[ActionCandidate]:
    """Return only deterministically eligible exact alternatives, in stable priority order.

    The caller must apply policy_v2 first. This repeats material-risk checks as a
    defensive barrier, without treating a response inventory as a risk assessor.
    """
    if max_choices <= 0 or _blocked(frame):
        return []
    candidates = []
    for spec in ACTION_SPECS:
        eligible, reasons = _contract(spec, frame, text)
        if not eligible:
            continue
        evidence = _source(knowledge, spec.claim, as_of, frame=frame) if spec.claim else [_policy_evidence(spec.kind)]
        if not evidence or (spec.claim and not evidence[0].resolved_links):
            continue
        url = evidence[0].resolved_links[0] if spec.claim else ""
        if spec.claim:
            reasons.append("verified unexpired current claim: " + spec.claim)
        try:
            candidate = _candidate(spec, _render(spec, frame, url, text), evidence, reasons)
        except ValueError:
            # A changed source URL cannot cause silent clipping of a required condition or warning.
            continue
        candidates.append(candidate)
    # Specific public how-to answers precede generic technical questions. On actual
    # malfunctions, clarification precedes procedures and cannot be crowded out.
    if _public_howto(frame, text) and not (_issues(frame) & TECHNICAL):
        candidates.sort(key=lambda candidate: candidate.response_kind != "resolution")
    return candidates[:max_choices]


def handoff(frame: RequestFrame, reason, knowledge: KnowledgeStore, *, text: str = "", as_of=None) -> ActionCandidate:
    """Return a source-validated human destination, never a claim that referral occurred."""
    from cadence.agent.policy_v2 import PolicyDecision

    reason_code = str(getattr(reason, "reason_code", reason))
    risks = {risk.kind for risk in frame.risks if risk.state in {"present", "unknown"}}
    flags = set(getattr(reason, "flags", ()))
    risks.update(flag.split(":", 1)[-1] for flag in flags)
    if reason_code in {"account_security", "billing_dispute", "legal_or_safety"}:
        risks.add({"account_security": "security", "billing_dispute": "money", "legal_or_safety": "legal_safety"}[reason_code])
    verification = (isinstance(reason, PolicyDecision)
                    and reason.reason_code in {None, "needs_account_lookup"}
                    and "invalid_request_frame" not in flags
                    and "student_verification" in _issues(frame)
                    and "student_bundle_linking" not in _issues(frame)
                    and not risks & {"money", "security", "legal_safety", "directed_abuse", "churn",
                                     "repeated_contact", "support_requested"}
                    and not re.search(r"\b(?:hulu|bundle|reconnect|linking)\b", text, re.I))
    if verification:
        evidence = _source(knowledge, "student_verification", as_of, frame=frame)
        if evidence and evidence[0].resolved_links:
            body = ("For student-verification help, use the SheerID help route linked on Spotify's official page. "
                    "I can't approve eligibility: " + evidence[0].resolved_links[0])
            spec = _spec("student_verification_handoff", {"student_verification"}, "handoff", "student_verification")
            try:
                return _candidate(spec, body, evidence, ["explicit student verification; no bundle/money/security conflict", reason_code])
            except ValueError:
                pass
    evidence = _source(knowledge, "contact_support", as_of, frame=frame)
    if evidence and evidence[0].resolved_links:
        limitation = ("I can't access accounts or contact staff here." if risks & {"account_intervention", "money", "security"}
                      else "I don't have a verified answer for this request here.")
        body = (limitation + " You can contact Spotify support: "
                + evidence[0].resolved_links[0] + " Don't post passwords or payment details.")
        spec = _spec("contact_support", set(), "handoff", "contact_support")
        try:
            return _candidate(spec, body, evidence, ["verified official support route", reason_code])
        except ValueError:
            pass
    # Even the contact URL must remain verified. Honest fallback supplies no stale procedure or destination.
    return _candidate(_spec("scoped_handoff", set(), "handoff"),
                      "This needs human review. I can't access accounts, contact staff, or verify a current support route here. Please keep passwords and payment details private.",
                      [_policy_evidence("handoff")], ["no verified current destination", reason_code])


__all__ = ["ACTION_SPECS", "CORE_ACTION_IDS", "ActionCandidate", "ActionSpec", "handoff", "shortlist"]
