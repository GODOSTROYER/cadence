"""Verify local knowledge evidence; optionally check official article drift.

No source is silently renewed or rewritten. A changed/unavailable page requires
a fresh offline source snapshot and a new explicit review before authorizing it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cadence.knowledge import KnowledgeStore  # noqa: E402

EXTRACTION = "spotify-rendered-article-text-v1"


class ArticleText(HTMLParser):
    """Keep the rendered article from its title through its help/footer boundary."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.started = False
        self.skipping = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            self.started = True
        if tag in {"script", "style", "svg"}:
            self.skipping += 1
        if self.started and not self.skipping and tag == "img":
            alt = dict(attrs).get("alt", "")
            if alt:
                self.parts.append(alt)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg"} and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if self.started and not self.skipping:
            self.parts.append(data)


def normalize_article(html: str) -> str:
    parser = ArticleText()
    parser.feed(html)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    for marker in ("Related Articles", "Was this article helpful?"):
        text = text.split(marker, 1)[0].strip()
    if len(text) < 50 or len(text) > 45000:
        raise ValueError("article extraction did not produce a bounded support article")
    return text + "\n"


def fetch_article(url: str) -> dict:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "support.spotify.com":
        raise ValueError("online checks only fetch official Spotify support articles")
    request = urllib.request.Request(url, headers={"User-Agent": "Cadence-Source-Verification/2.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        final = response.url
        final_parts = urlsplit(final)
        if final_parts.scheme != "https" or final_parts.hostname != "support.spotify.com":
            raise ValueError("source redirected outside the approved support origin")
        if response.headers.get_content_type() != "text/html":
            raise ValueError("official source did not return HTML")
        raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError("source exceeds fetch size limit")
    normalized = normalize_article(raw.decode("utf-8"))
    return {
        "url": url, "final_url": final, "fetched_at": datetime.now(UTC).isoformat(),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "normalized_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "extraction": EXTRACTION, "text": normalized,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--as-of", help="Explicit frozen-study date; live checks default to UTC today")
    parser.add_argument("--online", action="store_true", help="Read official sources and report drift without rewriting")
    args = parser.parse_args()
    store = KnowledgeStore.load(args.registry)
    checks = store.verify(args.as_of)
    online = {}
    if args.online:
        for source in store.sources.values():
            if source.role != "current_official":
                continue
            try:
                fetched = fetch_article(source.url)
                online[source.id] = ("unchanged" if fetched["normalized_sha256"] == source.normalized_sha256
                                     else "changed_requires_review")
            except (OSError, ValueError) as exc:
                online[source.id] = "unavailable: " + str(exc)
    result = {"version": store.registry.version, "fingerprint": store.fingerprint(),
              "as_of": args.as_of or datetime.now(UTC).date().isoformat(),
              "claims": checks, "online": online,
              "review_renewed": False}
    print(json.dumps(result, indent=2))
    return int(any(checks.values()) or any(value != "unchanged" for value in online.values()))


if __name__ == "__main__":
    raise SystemExit(main())
