"""Development-only veto diagnostics over frozen Balanced outputs.

These are offline counterfactuals, never deployable agents. They retain the exact
archived answer inventory and cannot release an archived escalation. Request
frames must come from the independent, customer-only extraction stage, before
that stage sees answers or retrieved examples. No live model calls occur here.
"""
from __future__ import annotations

import copy
import hashlib
import html
import re

from cadence.agent.balanced import ACTIONS, render
from cadence.agent.integrity import reply_violations
from cadence.agent.policy_v2 import POLICY_V2_SHA256, evaluate_policy
from cadence.agent.request_frame import RequestFrame, validate_frame
from cadence.config import SPOTIFY_HANDLES
from cadence.data.clean import clean_text

VERSION = "balanced-development-veto-v1"
CONTROLS = ("balanced_replay", "independent_policy_veto", "prerequisite_veto", "combined_veto")
HOLDING_ID = "policy:ablation-holding"
HOLDING_REPLY = ("A human needs to review this request. I can't access accounts or contact staff here. "
                 "Please keep passwords and payment details private. /AI")
TECHNICAL = frozenset({"playback_failure", "offline_playback", "track_unplayable", "app_problem"})
PLAYLIST = frozenset({"playlist_create", "playlist_search", "playlist_collaboration", "playlist_problem"})
DIAGNOSTIC = TECHNICAL | PLAYLIST | {"downloads_missing", "library_missing", "local_files"}
KNOWN_FEATURE = PLAYLIST | {"autoplay_after_end", "smart_shuffle", "shuffle_repeats", "wrapped_updates",
                           "public_display_name", "download_howto", "explicit_version"}
BRAND_MENTION = re.compile("(?:" + "|".join(re.escape(h) for h in (*SPOTIFY_HANDLES, "@Spotify"))
                           + r")(?!\w)", re.I)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def customer_text(text: str) -> str:
    """Match Verified's customer-only extraction input, preserving abuse targets."""
    return clean_text(BRAND_MENTION.sub("Spotify", html.unescape(text))).text


def development_labels(rows):
    """The tool cannot consume scored confirmation/calibration/challenge labels."""
    if not rows or any(row.get("split") != "development" for row in rows):
        raise ValueError("Only explicitly marked development labels may be used")
    indexed = {row["id"]: row for row in rows}
    if len(indexed) != len(rows) or any(not isinstance(row.get("text"), str) for row in rows):
        raise ValueError("Unique IDs and customer text are required")
    return indexed


def _value(frame, slot):
    return str(frame.value(slot) or "").lower()


def _known(frame, slot):
    return bool(_value(frame, slot))


def _device(frame):
    return " ".join(value for value in (_value(frame, "device"), _value(frame, "platform")) if value)


def _tried(frame, words):
    return any(word in _value(frame, "attempted_steps") for word in words)


def _mentioned_attempt(text, words):
    for clause in re.split(r"[.!?;\n]", text.lower()):
        if any(word in clause for word in words) and not re.search(r"\b(?:not|never|haven['’]t|didn['’]t|can't)\b", clause):
            if re.search(r"\b(?:already|tried|restarted|updated|checked|rebooted)\b", clause):
                return True
    return False


def applicable(action: str, frame: RequestFrame, text: str) -> tuple[bool, str]:
    """Applicability of the OLD EXACT card, not the new registry's changed text.

    This deliberately ignores risk, confidence and source freshness. E1 tests risk;
    E2 tests issue/slot/attempt constraints. Current authority is a separate E4
    change. Old questions asking two facts are rejected when either fact is known;
    unlike Verified this diagnostic cannot render a narrower replacement question.
    """
    issues = set(frame.issues)
    known_music = any(_known(frame, slot) for slot in ("artist", "release", "track"))
    mobile = bool(re.search(r"\b(?:mobile|android|ios|iphone|ipad|phone|tablet)\b", _device(frame)))
    premium = bool(re.search(r"\bpremium\b", _value(frame, "plan")))
    bad = "Old exact card has unmet issue/slot/prior-step prerequisites"
    good = "Old exact card satisfies the declared development applicability contract"
    if action not in ACTIONS:
        return False, "Unrecognized frozen Balanced card"
    # Handoffs are not candidates for automatic release in the historical agent.
    if action in {"handoff", "student_handoff"}:
        return False, "A handoff card cannot authorize automatic handling"
    checks = {
        "ask_device": bool(issues & DIAGNOSTIC) and not (_device(frame) or _known(frame, "app_version")),
        "ask_error": bool(issues & (TECHNICAL | {"playlist_problem", "student_bundle_linking"}))
                     and not _known(frame, "error") and bool(re.search(r"\b(?:error|message|says|code)\b", text, re.I)),
        "ask_playlist_owner": bool(issues & {"playlist_problem", "playlist_recommendations"})
                              and not re.search(r"\b(?:my (?:own )?playlist|I (?:made|created)|Spotify(?:'s)? playlist)\b", text, re.I),
        "ask_catalog_item": bool(issues & {"catalog_missing", "track_unplayable"}) and not known_music,
        "ask_reproduction": bool(issues & DIAGNOSTIC) and not (_known(frame, "error") or _known(frame, "affected_scope")),
        "restart_playback": bool(issues & TECHNICAL) and not (_device(frame) or _known(frame, "app_version"))
                            and not (_tried(frame, ("restart", "reboot", "reopen"))
                                     or _mentioned_attempt(text, ("restart", "reboot", "reopen"))),
        "update_playback": bool(issues & TECHNICAL) and not _known(frame, "error")
                           and not (_tried(frame, ("updat", "latest")) or _mentioned_attempt(text, ("updat",)))
                           and not re.search(r"\b(?:latest|newest|current|up.to.date)\b", _value(frame, "app_version")),
        "profile_name": "public_display_name" in issues and "account_identifier" not in issues
                        and not re.search(r"\b(?:user\s?name|login|identifier|recover|hacked)\b", text, re.I),
        "family_household": "family_household" in issues,
        "wrapped_updates": "wrapped_updates" in issues and not (issues & DIAGNOSTIC),
        "feature_idea": "feature_request" in issues and not (issues & (DIAGNOSTIC | KNOWN_FEATURE
                         | {"metadata_attribution", "catalog_missing", "student_bundle_linking"}))
                        and not _known(frame, "error"),
        "catalog_availability": "catalog_missing" in issues and not (issues & {
            "track_unplayable", "metadata_attribution", "library_missing", "downloads_missing", "offline_playback"}),
        "student_browser": "student_verification" in issues and "student_bundle_linking" not in issues
                           and not _tried(frame, ("private", "incognito"))
                           and not _mentioned_attempt(text, ("private", "incognito")),
        "ask_playback_mode": "playlist_recommendations" in issues
                             and not (_known(frame, "affected_scope") or _known(frame, "plan")),
        "ask_plan": bool(issues & {"playlist_recommendations", "smart_shuffle", "shuffle_repeats"})
                    and not _known(frame, "plan"),
        "autoplay_off": "autoplay_after_end" in issues and "smart_shuffle" not in issues,
        "smart_shuffle_off": "smart_shuffle" in issues and mobile and premium,
        "shuffle_repeats": "shuffle_repeats" in issues and premium,
        "explicit_version": "explicit_version" in issues and "metadata_attribution" not in issues,
        "library_filters": "library_missing" in issues and mobile
                           and not (issues & {"downloads_missing", "offline_playback", "local_files"})
                           and not re.search(r"\b(?:downloads?|downloaded|offline|local files?)\b", text, re.I)
                           and not (_tried(frame, ("filter",)) or _mentioned_attempt(text, ("filter",))),
        "ask_symptom": bool(issues & DIAGNOSTIC) and not (_known(frame, "error") or _known(frame, "affected_scope")),
        "ask_playback_scope": bool(issues & TECHNICAL) and not (known_music or _known(frame, "affected_scope")),
        "social_thanks": frame.social_closure and issues <= {"social_closure"},
    }
    if set(checks) != set(ACTIONS) - {"handoff", "student_handoff"}:
        raise ValueError("Balanced inventory changed; review all old-card applicability contracts")
    return bool(checks[action]), good if checks[action] else bad


def identify_card(reply):
    matches = [name for name in ACTIONS if render(name) == reply]
    return matches[0] if len(matches) == 1 else None


def validate_frame_record(record, label):
    if record["id"] != label["id"] or record.get("text") != customer_text(label["text"]):
        raise ValueError("Frame must bind the exact customer-only extraction input")
    if record.get("status") != "valid":
        raise ValueError("Extraction failed or was unavailable")
    if record.get("policy_sha256") != POLICY_V2_SHA256:
        raise ValueError("Frame was extracted under a different policy")
    frame = RequestFrame.model_validate(record["frame"])
    validate_frame(frame, record["text"])
    if record.get("frame_sha256") != digest(frame.model_dump_json()):
        raise ValueError("Frame content hash mismatch")
    return frame


def overlay(base, record, label, control):
    """Replay a single exact archived output with zero additional model calls."""
    development_labels([label])
    if control not in CONTROLS or base.get("system") != "balanced" or base["id"] != label["id"]:
        raise ValueError("A known control and matching frozen Balanced prediction are required")
    if base.get("input_text") not in {customer_text(label["text"]), clean_text(label["text"]).text}:
        raise ValueError("Archived prediction and development message differ")
    if base.get("decision") not in {"auto_handle", "escalate", None}:
        raise ValueError("Invalid archived decision")
    row = copy.deepcopy(base)
    source_runtime = {key: row.pop(key) for key in ("trace", "measurement", "latency_ms", "cached") if key in row}
    row["system"] = control
    row["outcome"] = base.get("outcome", "success")
    info = {"version": VERSION, "mode": "offline_development_counterfactual", "source_system": "balanced",
            "source_reply_sha256": digest(base.get("reply_draft", "")), "changed": False,
            "source_runtime": source_runtime, "fresh_latency_ms": None, "additional_model_calls": 0,
            "frame_extraction_cost": "Reused separately measured customer-only stage; not free in a live wrapper",
            "frame_sha256": record.get("frame_sha256"), "blocked_by": [],
            "source_policy_sha256": record.get("policy_sha256")}
    row["ablation"] = info
    if control == "balanced_replay" or row["outcome"] != "success" or row["decision"] != "auto_handle":
        return row
    try:
        frame = validate_frame_record(record, label)
    except (ValueError, KeyError):
        # A missing stage result is a failed wrapper, never a successful safe route.
        info["blocked_by"].append("frame_unavailable")
        row["outcome"] = "failed"
    else:
        if control in {"independent_policy_veto", "combined_veto"}:
            policy = evaluate_policy(record["text"], frame)
            info["policy"] = policy.model_dump()
            if policy.required:
                info["blocked_by"].append("policy:" + str(policy.reason_code))
        if control in {"prerequisite_veto", "combined_veto"}:
            action = identify_card(base.get("reply_draft", ""))
            allowed, reason = applicable(action, frame, record["text"])
            info.update(action_id=action, applicability_reason=reason)
            if not allowed:
                info["blocked_by"].append("action_prerequisites")
    if info["blocked_by"]:
        evidence = [{"thread_id": HOLDING_ID, "customer_text": "Local response limitation",
                     "brand_reply": "Acknowledge that human review is needed without claiming to send a referral.",
                     "resolved_links": [], "cited": True, "score": 0.0}]
        if reply_violations(HOLDING_REPLY, set()):
            raise ValueError("The common exact holding response failed integrity checks")
        row.update(decision="escalate", reply_draft=HOLDING_REPLY, citations=[HOLDING_ID], evidence=evidence,
                   grounding_notes="Development veto: " + ", ".join(info["blocked_by"]),
                   escalation={"reason_code": "development_veto", "reason": ", ".join(info["blocked_by"])})
        info["changed"] = True
    return row


def routing_counts(labels, rows):
    labels_by_id = {row["id"]: row for row in labels}
    rows_by_id = {row["id"]: row for row in rows}
    if (not labels or len(labels_by_id) != len(labels) or len(rows_by_id) != len(rows)
            or set(labels_by_id) != set(rows_by_id)):
        raise ValueError("Routing report needs the same complete unique message population")
    result = dict(n=len(labels), automatic=0, required=0, missed_escalations=0,
                  unnecessary_escalations=0, failed=0)
    for identity, label in labels_by_id.items():
        required = label["gold"]["should_escalate"]
        if type(required) is not bool:
            raise ValueError("Routing gold must be an explicit boolean")
        row = rows_by_id[identity]
        failed = row.get("outcome", "success") != "success" or row.get("decision") not in {"auto_handle", "escalate"}
        automatic = not failed and row["decision"] == "auto_handle"
        escalated = not failed and row["decision"] == "escalate"
        result["required"] += required
        result["automatic"] += automatic
        result["failed"] += failed
        result["missed_escalations"] += required and not escalated
        result["unnecessary_escalations"] += not required and escalated
    return result


def policy_rescore(old_labels, new_labels, predictions):
    """Same outputs and calls; only the routing target changes. No generated repair."""
    development_labels(new_labels)
    old = {row["id"]: row for row in old_labels}
    if (set(old) != {row["id"] for row in new_labels} or len(old) != len(old_labels)
            or any(customer_text(old[row["id"]]["text"]) != customer_text(row["text"]) for row in new_labels)):
        raise ValueError("Policy rescoring requires the same exact messages under both labels")
    return {"control": "unchanged_output_policy_rescore", "behavior_changed": False,
            "additional_model_calls": 0, "fresh_latency_ms": None,
            "old_policy": routing_counts(old_labels, predictions),
            "new_policy": routing_counts(new_labels, predictions),
            "label_route_changed_ids": [row["id"] for row in new_labels
                                        if row["gold"]["should_escalate"] != old[row["id"]]["gold"]["should_escalate"]]}
