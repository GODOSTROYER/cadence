"""Prospective request policy with deterministic and semantic escalation vetoes.

The return value is immutable. A later answer selection may escalate more cases,
but must never clear a required decision. Historical comparators do not import
this policy and keep their own versioned behavior.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict

from cadence.agent.request_frame import (
    POLICY_V2_BYTES,
    POLICY_V2_SHA256,
    RISK_KINDS,
    RequestFrame,
    RiskFinding,
    validate_frame,
)

POLICY = json.loads(POLICY_V2_BYTES)
POLICY_VERSION = POLICY["version"]


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    required: bool
    reason_code: str | None = None
    reason: str = "No mandatory risk established; a supported response still needs validation."
    flags: tuple[str, ...] = ()
    policy_version: str = POLICY_VERSION
    policy_sha256: str = POLICY_V2_SHA256


# Rules intentionally match events/assertions rather than the v0 bag of words.
# Semantic extraction complements these patterns; they do not prove exhaustivity.
_PATTERNS: dict[str, tuple[str, ...]] = {
    "legal_safety": (
        r"\bdiscriminat(?:e[ds]?|ing|ion|ory)\b",
        r"\b(?:suing|lawsuit|legal action|harass(?:ed|ing|ment)|stalking)\b",
        r"\b(?:contact|involve|consult|bringing|bring|speak to) (?:my |a |an |the )?(?:lawyer|attorney)\b",
        r"\b(?:sue (?:you|spotify|the company)|kill(?:ing)? myself|hurt(?:ing)? myself|self[- ]harm|suicid(?:e|al)|kill you|death threat|threaten(?:ed|ing|s)? (?:me|us))\b",
    ),
    "security": (
        r"\b(?:hack(?:ed|ing)|compromised|unauthori[sz]ed (?:access|charge|change|device|login)|stolen (?:my |the |our )?(?:account|password|identity))\b",
        r"\b(?:someone|somebody|a stranger)(?: else)?(?: has| is| keeps| has been)? (?:changed?|changing|replaced|altered|stolen|using|logged (?:in|into)|accessing)\b",
        r"\b(?:my|the) (?:email|password|login) (?:was|has been) changed\b",
        r"\b(?:device|login|sign[- ]in)(?: that)? (?:i (?:do not|don't|cannot|can't) (?:recognize|recognise)|i (?:do not|don't) own)\b",
        r"\b(?:unknown|unrecognised|unrecognized) (?:device|login|sign[- ]in)\b",
        r"\b(?:my password is|password\s*:|my (?:card number|cvv) is)\b",
    ),
    "money": (
        r"\b(?:charg(?:e|ed|ing) me|(?:i|we) (?:was|were|got|am|are) (?:being )?charged|(?:double|twice|wrongly|incorrectly)[ -]charg(?:e|ed|ing)|charged (?:twice|again|double|for))\b",
        r"\b(?:refund (?:me|my|the)|(?:want|need|request(?:ing)?|awaiting|waiting for|where is|where's) (?:a |my |the )?refund|(?:my |the )?refund (?:failed|missing|never|has not|hasn't|didn't))\b",
        r"\b(?:payment (?:failed|declined|was declined|did not|didn't)|card (?:was )?declined|(?:took|taking|stole) (?:my |our )?money|billing (?:error|dispute|problem)|charged\s+[$£€]\s*\d)\b",
        r"\b(?:i|we) (?:have |already )?paid\b.{0,80}\b(?:still|but|not|no|never|free|missing)\b",
    ),
    "account_intervention": (
        r"\b(?:locked out|(?:cannot|can't|unable to) (?:log ?in|sign ?in|access my account)|forgot(?:ten)? (?:my |the )?password|recover (?:my |the )?account)\b",
        r"\b(?:need|want|ask(?:ing)?) (?:you|support)(?: to)? (?:change|restore|recover|reset|delete|approve|verify|check) (?:my |the |this )?(?:account|username|password|eligibility|identity)\b",
        r"\b(?:verify|approve|check|restore|recover|reset) my (?:eligibility|identity|account|password)\b",
        r"\b(?:verification|eligibility|family invite|invitation) (?:failed|rejected|denied|not working)\b",
        r"\b(?:my|the) (?:student|family|premium) (?:account|subscription|plan|invite|invitation)\b.{0,50}\b(?:rejected|denied|not activated|missing|not received)\b",
    ),
    "directed_abuse": (
        r"\b(?:fuck|f\*+k|screw) (?:you|spotify|your (?:team|staff|support))\b",
        r"\b(?:you(?:'re| are)?|spotify(?: is)?|(?:your|the) (?:support(?: team)?|staff|agents?|company)(?: is| are)?)\s+(?:(?:all|a|an|fucking|utter|complete|totally|absolutely)\s+){0,3}(?:idiots?|morons?|assholes?|bastards?|useless|worthless|pathetic|scammers?)\b",
        r"\b(?:idiots?|morons?|assholes?|bastards?) (?:at|working (?:at|for)) (?:spotify|support)\b",
    ),
    "churn": (
        r"\b(?:i(?:'m| am)|we(?:'re| are))\s+(?:(?:finally|definitely|now|seriously)\s+)?(?:cancell?ing|leaving|quitting)\s+(?:my |our |the )?(?:premium|subscription|account|spotify|service)\b",
        r"\b(?:i|we) (?:will|intend to|plan to|am going to|are going to) (?:cancel|leave|quit)\b",
        r"\b(?:i|we) (?:have |just )?cancell?ed (?:my |our )?(?:subscription|premium|account)\b",
        r"\b(?:switch(?:ing)?|mov(?:e|ing)|going) (?:over )?to (?:apple music|tidal|deezer|youtube music|amazon music|pandora)\b",
        r"\b(?:cancel my (?:subscription|premium)|(?:lost|losing) (?:me|us) as (?:a |your )?customers?)\b",
    ),
    "repeated_contact": (
        r"\b(?:third|second|fourth|3rd|2nd|4th) (?:message|email|request|contact|time (?:asking|contacting|messaging|emailing))\b(?=[^.!?;]{0,60}\b(?:support|you|your team|customer service)\b)",
        r"\b(?:contacted|messaged|emailed|tweeted|asked)\b.{0,35}\b(?:support|you|your team|customer service)\b.{0,35}\b(?:again|twice|repeatedly|three times|two times|several times|multiple times)\b",
        r"\b(?:still|again)\b.{0,20}\b(?:waiting for (?:your|a) (?:reply|response)|no (?:reply|response) from (?:support|you))\b",
        r"\b(?:support|you|your team)\b.{0,35}\b(?:ignoring|ignored|never (?:reply|respond)|not (?:replying|responding))\b",
        r"\b(?:my|our) (?:messages|emails|requests)\b.{0,25}\b(?:unanswered|ignored)\b",
    ),
    "support_requested": (
        r"\b(?:speak|talk|connect me) to (?:a |an |some)?(?:human|real person|agent|someone|actual person)\b",
        r"\b(?:want|need|request) (?:a |an )?(?:human|real person|support agent)\b",
        r"\b(?:please )?(?:check|read|reply to|respond to) (?:my|your|our|the) (?:dm|dms|private message)\b",
    ),
}
_COMPILED = {kind: tuple(re.compile(pattern, re.I) for pattern in patterns)
             for kind, patterns in _PATTERNS.items()}
_QUOTED = re.compile(r'"[^"\n]{1,200}"|“[^”\n]{1,200}”|(?<!\w)\'[^\'\n]{1,200}\'(?!\w)')
_TITLE_CONTEXT = re.compile(
    r"\b(?:song|track|album|playlist|podcast|lyrics?|title|article|book|movie)\s+(?:(?:called|named|titled|says|is|of|to|for)\s+){0,2}$",
    re.I,
)
_NEGATION = re.compile(
    r"\b(?:not|never|no longer|nobody|no one|isn't|aren't|wasn't|weren't|haven't|hasn't|didn't|don't|doesn't|won't|wouldn't)\s+"
    r"(?:(?:been|being|getting|actually|currently|ever|really|have|has|had|alleging|threaten|threatening|wanting|want|to|plan|going)\s+){0,4}$",
    re.I,
)


def _rule_text(text: str) -> str:
    """Preserve offsets while masking narrowly attributed titles, not threats."""
    normalized = text.replace("’", "'").replace("‘", "'")
    chars = list(normalized)
    for match in _QUOTED.finditer(normalized):
        prefix = normalized[max(0, match.start() - 65):match.start()]
        surrounding = normalized[max(0, match.start() - 100):match.start()] + normalized[match.end():match.end() + 100]
        reported_threat = re.search(r"\b(?:threats?|threaten(?:ed|ing|s)?|harass(?:ed|ing|ment)|stalking)\b", surrounding, re.I)
        if _TITLE_CONTEXT.search(prefix) and not reported_threat:
            chars[match.start():match.end()] = " " * (match.end() - match.start())
    return "".join(chars)


def _benign_context(kind: str, text: str, match: re.Match[str]) -> bool:
    prefix = text[max(0, match.start() - 80):match.start()]
    phrase = match.group(0).lower()
    if _NEGATION.search(prefix):
        return True
    if re.search(r"\b(?:not|never|don't|didn't|won't)\s+(?:need|want|ask|require)\s+(?:support|you)\s+to\s*$", prefix, re.I):
        return True
    # Rules beginning at the subject need an in-phrase negation check as well.
    if re.search(r"\b(?:nobody|no one)\b", phrase):
        return True
    if kind in {"security", "legal_safety"}:
        if re.search(r"\bhow (?:can|do|should) (?:i|we|you) (?:prevent|avoid)\s*$", prefix, re.I):
            return True
        if (not phrase.startswith(("someone", "somebody", "a stranger"))
                and re.search(r"\b(?:how (?:can|do|should) (?:i|we|you)|ways to)\b[^.!?;]{0,45}\b(?:prevent|avoid|protect against|protect myself from)\b[^.!?;]{0,35}$", prefix, re.I)):
            return True
    if kind == "repeated_contact":
        suffix = re.split(r"[.!?;]|\bbut\b", text[match.end():match.end() + 90], maxsplit=1, flags=re.I)[0]
        if re.search(r"\b(?:fixed|resolved|sorted) (?:it|the (?:problem|issue))\b", suffix, re.I) and not re.search(r"\b(?:not|never|didn't)\b", suffix, re.I):
            return True
    if kind == "churn":
        # A neutral how-to is different from an explicit decision to leave.
        if re.search(r"\b(?:how (?:can|do|would) i|can i|where (?:can|do) i)\s*$", prefix, re.I):
            return True
        if re.search(r"\b(?:how (?:can|do|would) i|can i)\b[^.!?;]{0,35}$", prefix, re.I) and phrase.startswith("switch"):
            return True
    return False


def deterministic_risks(customer_text: str) -> tuple[RiskFinding, ...]:
    """Return evidence-bearing hard findings, independently of model output."""
    text = _rule_text(customer_text)
    findings = []
    for kind in POLICY["risk_priority"]:
        for pattern in _COMPILED[kind]:
            match = next((m for m in pattern.finditer(text) if not _benign_context(kind, text, m)), None)
            if match is not None:
                findings.append(RiskFinding(
                    kind=kind, state="present", quote=customer_text[match.start():match.end()],
                    reason="Independent deterministic evidence matched the prospective policy.",
                ))
                break
    return tuple(findings)


def evaluate_policy(customer_text: str, frame: RequestFrame) -> PolicyDecision:
    """Merge hard and semantic findings; never use confidence to clear risk."""
    hard = deterministic_risks(customer_text)
    flags = [f"deterministic:{finding.kind}" for finding in hard]
    try:
        validate_frame(frame, customer_text)
    except ValueError:
        # Still retain the primary known risk when extraction is invalid.
        flags.append("invalid_request_frame")
        if hard:
            rule = POLICY["risks"][hard[0].kind]
            return PolicyDecision(required=True, flags=tuple(flags), **rule)
        return PolicyDecision(required=True, reason_code="ambiguous_or_media_only",
                              reason="The request extraction failed its evidence-integrity checks.", flags=tuple(flags))

    present = {finding.kind for finding in hard}
    unknown = []
    for kind in RISK_KINDS:
        finding = frame.risk(kind)
        if finding.state == "present":
            present.add(kind)
            flags.append(f"semantic:{kind}")
        elif finding.state == "unknown":
            unknown.append(kind)
            flags.append(f"risk_unknown:{kind}")
    if frame.intent == "account_hacked_or_security" or frame.secondary_intent == "account_hacked_or_security":
        present.add("security")
        flags.append("security_intent")
    if present:
        kind = next(kind for kind in POLICY["risk_priority"] if kind in present)
        return PolicyDecision(required=True, flags=tuple(flags), **POLICY["risks"][kind])
    if unknown:
        return PolicyDecision(required=True, reason_code="ambiguous_or_media_only",
                              reason="Material risk is unresolved: " + ", ".join(unknown) + ".", flags=tuple(flags))
    if frame.language_supported is not True or frame.intent == "non_english":
        return PolicyDecision(required=True, reason_code="out_of_scope",
                              reason="The supported language could not be established.", flags=tuple(flags + ["unsupported_language"]))
    visible = re.sub(r"https?://\S+|<url>|@\w+", " ", customer_text).strip(" \t\r\n.,!?:;")
    if (frame.media_only or frame.intelligible is not True or not visible
            or re.fullmatch(r"(?:help|hi|hello|hey|please help|pls help)", visible, re.I)):
        return PolicyDecision(required=True, reason_code="ambiguous_or_media_only",
                              reason="The available text does not establish an interpretable support request or closure.",
                              flags=tuple(flags + ["unavailable_request_context"]))
    if frame.social_closure:
        flags.append("social_closure_eligible")
    return PolicyDecision(required=False, flags=tuple(flags))


__all__ = ["POLICY_VERSION", "POLICY_V2_SHA256", "PolicyDecision", "deterministic_risks", "evaluate_policy"]
