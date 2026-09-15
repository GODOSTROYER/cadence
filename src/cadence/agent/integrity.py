"""Conservative reply release checks. These are guards, not semantic grounding proofs."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

URL = re.compile(r"https?://[^\s<>]+", re.I)
ALLOWED_HOSTS = {"support.spotify.com", "community.spotify.com", "accounts.spotify.com"}
SAFE_HOLDING_REPLY = "Hey there! A human needs to review this before we suggest a fix. Please don't share passwords, payment details or security codes here. /AI"
RESOURCE = re.compile(
    r"\b(help article|this guide|this link|these steps|steps under|suggest it in our community|more info here)\b",
    re.I,
)
SENSITIVE_REQUEST = re.compile(
    r"\b(send|share|give|post|provide|dm|tell)\b[^.!?]{0,60}\b(password|card number|cvv|security code|verification code)\b",
    re.I,
)
PROMISE = re.compile(
    r"\b(we(?:'ll| will| have|'ve)|i(?:'ll| will| have|'ve))\b[^.!?]{0,35}\b(refund|credit|compensat|cancelled|canceled|fixed your account)\w*",
    re.I,
)


def useful_link(url: str) -> bool:
    try:
        parsed = urlsplit(url.strip())
        return (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_HOSTS
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
            and bool(parsed.path.strip("/"))
        )
    except ValueError:
        return False


def reply_violations(reply: str, allowed_urls: set[str]) -> list[str]:
    flags = []
    urls = {m.group().rstrip(".,;!?)") for m in URL.finditer(reply)}
    if any(not useful_link(u) or u not in allowed_urls for u in urls):
        flags.append("unsupported_link")
    if "<url>" in reply or "@user" in reply:
        flags.append("placeholder")
    if RESOURCE.search(reply) and not urls:
        flags.append("missing_resource_link")
    # Remove explicit prohibitions before checking requests for secrets.
    affirmative = re.sub(r"\b(?:never|do not|don't)\b[^.!?]*(?:[.!?]|$)", "", reply, flags=re.I)
    if SENSITIVE_REQUEST.search(affirmative):
        flags.append("requests_sensitive_data")
    if PROMISE.search(reply):
        flags.append("unauthorized_commitment")
    if len(reply) > 280 or not reply.endswith(" /AI"):
        flags.append("format")
    if len(re.sub(r"Hey there|Hi there|Hello|/AI|\W", "", reply, flags=re.I)) < 12:
        flags.append("empty_reply")
    return flags
