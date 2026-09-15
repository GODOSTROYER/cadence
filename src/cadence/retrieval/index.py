"""The :class:`Retriever` — BM25 over SpotifyCares threads with usefulness re-ranking (CONTRACT.md §15.2).

Search pipeline
---------------
1. Tokenise the query with :func:`cadence.retrieval.bm25.tokenize` and BM25-score every thread.
2. Drop ``exclude_thread_ids`` (a golden example must never retrieve its own thread) and take the
   top ``CANDIDATE_POOL`` (50) candidates.
3. Re-weight each candidate by how *useful* its first brand reply is as evidence:
   ``× 1.25`` when the reply is substantive (carries a resolved help link, or has ≥ 12 words and is
   not merely a "please DM us" request), ``× 0.85`` when the reply only asks for a DM and has no link.
4. Walk the re-scored candidates best-first and drop any whose ``customer_text`` is near-identical
   (``rapidfuzz.fuzz.ratio > 90``) to an already-kept hit, so the evidence shown to the agent covers
   distinct historical cases rather than five copies of the same complaint.
5. Return the top ``k`` as :class:`Hit` objects carrying the full processed thread dict (§3).

Document text decision (customer_text alone vs customer_text + first_reply_text)
--------------------------------------------------------------------------------
Both variants were built over the 27,627 processed threads and compared on 20 hand-written queries
(``python scripts/02_build_index.py --compare-doc-text`` reprints the side-by-side table) plus two
automatic leave-one-out proxies on 1,000 threads (keyword pseudo-intent agreement of the top hits with
the query thread; ``token_set_ratio`` of the top-1 reply to the true reply). Verdict: **index
``customer_text + first_reply_text``** (``INCLUDE_REPLY_TEXT = True``). The hand check favoured the
combined text 5–3 with 12 ties (pseudo-intent agreement 0.586 vs 0.576 top-1, 0.551 vs 0.557 top-3;
reply similarity 59.4 vs 60.5 — a wash). The wins come from sparse-vocabulary queries where the
customer side barely names the topic but the brand reply does, and they surface threads whose reply
actually contains guidance; the losses are boilerplate words in replies ("update", "open", "feature")
pulling in one off-topic hit. Three example comparisons (top-3 customer_text → reply):

* ``"podcasts not loading on android"`` — combined wins clearly.
  customer-only: "Is it just me or is not loading", "Website is not loading / loads very very slow",
  "So is just not loading for everyone" (no podcast thread in the top 3);
  combined: "since when did have podcasts?" → info link, "iPad app does not have podcasts?" → platform
  availability answer, "why can't i listen to podcasts on my ipad" → same answer.
* ``"my app keeps crashing every time i open it since the update"`` — customer-only wins.
  customer-only: "app keeps crashing every time I try to share a song", "can't open my app since most
  recent update", "keep pausing every time I open snapchat" (all crash/playback threads);
  combined: top-1 is "Are you going to update your website or app so I can update my payment options?"
  (matched "update"/"app" in a payment thread) before two genuine crash threads.
* ``"charged twice this month for premium"`` — tie: both put the same two double-charge threads
  first ("i've been charged twice this month for premium???", "y'all are charging me twice a month")
  and differ only in the third hit, which is a double-charge thread either way.
"""

from __future__ import annotations

import pickle
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from rapidfuzz import fuzz

from cadence.agent.integrity import useful_link
from cadence.config import Paths
from cadence.retrieval.bm25 import BM25Index, tokenize, top_indices
from cadence.utils.log import get_logger
from cadence.utils.text import word_count

log = get_logger(__name__)

INCLUDE_REPLY_TEXT: bool = True
"""Whether the indexed document text appends ``first_reply_text`` (see module docstring for the decision)."""
CANDIDATE_POOL: int = 50
"""BM25 candidates considered by the re-ranker before truncating to ``k``."""
SUBSTANTIVE_BOOST: float = 1.25
DM_ONLY_PENALTY: float = 0.85
MIN_SUBSTANTIVE_WORDS: int = 12
NEAR_DUPLICATE_RATIO: float = 90.0
"""``rapidfuzz.fuzz.ratio`` above which two customer texts count as the same complaint."""
INDEX_FORMAT_VERSION: int = 2

_ACTION_PREFIXES: tuple[str, ...] = (
    "try", "tri", "reinstall", "restart", "reboot", "updat", "clear", "log", "sign", "setting",
    "offline", "delet", "remov", "download", "turn", "switch", "toggl", "uninstall", "reset", "chang",
    "follow", "step", "click", "select", "tap", "disabl", "enabl", "cache", "install", "version", "browser",
    "device", "wifi", "storage", "mode", "renew", "cancel", "resubscrib", "upgrad", "verif", "confirm",
    "region", "countr", "label", "artist", "playlist", "password", "premium", "subscri",
    "payment", "refund", "facebook", "head", "open",
)  # fmt: skip
"""Lower-cased word prefixes that mark a brand reply as containing actual guidance, not only a DM request."""

_DM_BOILERPLATE: frozenset[str] = frozenset(
    {
        # greetings / sign-offs / filler
        "hey", "hi", "hello", "there", "we", "us", "our", "we'll", "we're", "we'd", "we've", "you're",
        "you've", "well", "sorry", "apologies", "apologise", "apologize", "delay", "hear", "about", "let",
        "know", "if", "have", "any", "questions", "question", "thank", "thanks", "please", "could", "would",
        "up", "more", "your", "so", "then", "will", "what", "what's", "happening", "going", "on", "of",
        "asap", "sort", "sorted", "via", "quick", "quickly", "further", "soon", "possible", "way", "happy",
        "glad", "again", "still", "no", "worries", "worry", "not", "yet", "one", "when", "did", "do",
        "does", "how", "which", "who", "why", "where", "keep", "posted", "ready", "time", "team", "spotify",
        "app", "user", "url", "be", "some", "that", "this", "with", "and", "the", "a", "an", "to", "in",
        "for", "you", "me", "my", "i", "it", "is", "are", "was", "can", "at", "as", "lets", "let's",
        "can't", "cant", "dont", "don't", "want", "need", "like", "see", "just", "there's", "isn't", "ok",
        "okay", "sure", "right", "yeah", "yep", "oh", "hmm", "ah", "ahh", "aw", "them", "they", "him",
        "her", "his", "their", "its", "it's", "should", "might", "but", "also", "too", "all", "very",
        "really", "much", "many", "been", "being", "gonna", "along", "bit", "little", "now", "here",
        "over", "out", "from", "into", "back", "got", "get", "cool", "good", "great", "that's", "doesn't",
        "sound", "sounds", "cavalry", "rescue", "arrived", "help", "help's", "helps", "helping", "helped",
        "come", "came", "hand", "assist", "closer", "look", "looking", "take", "dig", "deeper", "backstage",
        "suggest", "recommend", "figure", "happen", "happens", "happened", "wrong", "issue", "issues",
        "problem", "problems", "trouble", "case",
        # the DM request itself
        "send", "sent", "sending", "shoot", "fire", "drop", "pop", "reach", "touch", "give", "dm", "dms",
        "dm'd", "direct", "message", "messages", "reply", "replied", "replying", "respond", "response",
        "responded", "carry", "continue", "chat", "chatting", "conversation", "go", "ahead",
        "details", "detail", "info", "information", "address", "email", "e", "mail", "username", "account",
        "account's", "accounts", "exactly", "specifically", "screenshot", "screenshots",
        "check", "inbox", "wait", "waiting", "shortly", "under", "hood", "linked", "both", "plan", "owner",
        "owner's", "addresses", "everything", "fixed", "make", "cover", "bases", "use", "link", "currently",
        "telephone", "phone", "support", "twitter", "getting", "error", "errors",
    }
)  # fmt: skip
"""Words that make up the templated "send us a DM" replies; anything else counts as content."""

_WORD_RE = re.compile(r"[a-z0-9']+")


def _words(text: str) -> list[str]:
    """Lower-cased word tokens of a reply, placeholders removed, apostrophes kept for contractions."""
    lowered = text.lower().replace("<url>", " ").replace("@user", " ")
    return [w.strip("'") for w in _WORD_RE.findall(lowered) if w.strip("'")]


@dataclass
class Hit:
    """One retrieved historical thread (CONTRACT.md §15.2)."""

    thread_id: str
    score: float
    thread: dict[str, Any]


def document_text(thread: dict[str, Any], *, include_reply: bool = INCLUDE_REPLY_TEXT) -> str:
    """The text indexed for a thread: the cleaned customer opener, optionally followed by the first reply."""
    customer = str(thread.get("customer_text") or "")
    if not include_reply:
        return customer
    reply = str(thread.get("first_reply_text") or "")
    return f"{customer} {reply}".strip()


def first_reply(thread: dict[str, Any]) -> dict[str, Any]:
    """The first brand reply object of a thread (empty dict when the thread has none)."""
    replies = thread.get("brand_replies") or []
    return replies[0] if replies and isinstance(replies[0], dict) else {}


def reply_has_link(thread: dict[str, Any]) -> bool:
    """True when the first brand reply carries a resolved (non t.co) link."""
    return any(useful_link(url) for url in first_reply(thread).get("resolved_links") or [])


def is_dm_only(reply_text: str) -> bool:
    """True when a reply is essentially just a "send us a DM" request with no actionable guidance.

    A reply is DM-only when none of its words starts with an action prefix (try, reinstall, update,
    log, settings, ...) and, boilerplate removed, fewer than three content words remain.
    ``"Hey! Send us a DM with your account email and we'll take a look"`` is DM-only;
    ``"Try a clean reinstall first — if that doesn't help, DM us"`` is not.
    """
    words = _words(reply_text)
    if any(w.startswith(_ACTION_PREFIXES) for w in words):
        return False
    return sum(1 for w in words if w not in _DM_BOILERPLATE) < 3


def usefulness_multiplier(thread: dict[str, Any]) -> float:
    """Re-ranking factor for a thread based on how helpful its first brand reply is as evidence.

    * ``SUBSTANTIVE_BOOST`` (1.25): the reply links to a resolved help article, or has at least
      ``MIN_SUBSTANTIVE_WORDS`` words and is not merely a DM request.
    * ``DM_ONLY_PENALTY`` (0.85): the reply asks for a DM, has no link and is not substantive.
    * ``1.0`` otherwise (short acknowledgement without a link, e.g. "Thanks for the feedback!").
    """
    reply_text = str(thread.get("first_reply_text") or first_reply(thread).get("text") or "")
    has_link = reply_has_link(thread)
    asks_dm = bool(thread.get("first_reply_asks_dm", first_reply(thread).get("asks_dm", False)))
    if has_link:
        return SUBSTANTIVE_BOOST
    if word_count(reply_text) >= MIN_SUBSTANTIVE_WORDS and not (asks_dm and is_dm_only(reply_text)):
        return SUBSTANTIVE_BOOST
    if asks_dm:
        return DM_ONLY_PENALTY
    return 1.0


def is_near_duplicate(text: str, others: Iterable[str]) -> bool:
    """True when ``text`` is near-identical (ratio > ``NEAR_DUPLICATE_RATIO``) to any of ``others``."""
    return any(fuzz.ratio(text, other) > NEAR_DUPLICATE_RATIO for other in others)


class Retriever:
    """BM25 retriever over processed SpotifyCares threads (CONTRACT.md §15.2)."""

    def __init__(
        self,
        threads: Sequence[dict[str, Any]],
        index: BM25Index,
        *,
        include_reply: bool = INCLUDE_REPLY_TEXT,
    ) -> None:
        if len(threads) != index.n_docs:
            raise ValueError(f"index has {index.n_docs} documents but {len(threads)} threads were given")
        self._threads: list[dict[str, Any]] = list(threads)
        self._index = index
        self._include_reply = include_reply
        self._thread_ids: list[str] = [str(t["thread_id"]) for t in self._threads]
        self._position: dict[str, int] = {tid: i for i, tid in enumerate(self._thread_ids)}
        self._multipliers: np.ndarray = np.fromiter(
            (usefulness_multiplier(t) for t in self._threads), dtype=np.float32, count=len(self._threads)
        )

    # ----------------------------------------------------------------------------- construction
    @classmethod
    def build(cls, threads: list[dict], *, include_reply: bool = INCLUDE_REPLY_TEXT) -> Retriever:
        """Index ``threads`` (processed thread dicts, §3). Threads without a ``thread_id`` are rejected."""
        if not threads:
            raise ValueError("Retriever.build needs at least one thread")
        missing = [i for i, t in enumerate(threads) if not t.get("thread_id")]
        if missing:
            raise ValueError(f"{len(missing)} threads lack a thread_id (first at position {missing[0]})")
        t0 = time.perf_counter()
        documents = [tokenize(document_text(t, include_reply=include_reply)) for t in threads]
        index = BM25Index.build(documents)
        retriever = cls(threads, index, include_reply=include_reply)
        log.info(
            "built BM25 index: %d threads, %d terms, %.2fs",
            len(threads),
            len(index.vocab),
            time.perf_counter() - t0,
        )
        return retriever

    @classmethod
    def load(cls, path: Path = Paths.BM25_INDEX) -> Retriever:
        """Load an index written by :meth:`save`."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"BM25 index not found at {path}; run scripts/02_build_index.py first")
        t0 = time.perf_counter()
        # The pickle is a local build artefact written by `save` (CONTRACT.md §1 mandates the format);
        # it is never fetched from an untrusted source, and `make index` rebuilds it in about a second.
        with open(path, "rb") as f:
            payload = pickle.load(f)
        version = payload.get("format_version")
        if version != INDEX_FORMAT_VERSION:
            raise ValueError(
                f"{path} has index format {version!r}; expected {INDEX_FORMAT_VERSION} — rebuild it"
            )
        index = BM25Index(
            vocab=payload["vocab"],
            weights=payload["weights"],
            doc_lengths=payload["doc_lengths"],
            idf=payload["idf"],
        )
        threads = payload["threads"]
        if [str(t["thread_id"]) for t in threads] != list(payload["thread_ids"]):
            raise ValueError(f"{path} is inconsistent: thread_ids do not match the thread store")
        retriever = cls(threads, index, include_reply=bool(payload.get("include_reply", INCLUDE_REPLY_TEXT)))
        log.info(
            "loaded BM25 index from %s (%d threads) in %.2fs", path, len(retriever), time.perf_counter() - t0
        )
        return retriever

    def save(self, path: Path = Paths.BM25_INDEX) -> None:
        """Pickle the index (sparse weights, vocab, doc lengths, idf) and the full thread store."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format_version": INDEX_FORMAT_VERSION,
            "include_reply": self._include_reply,
            "thread_ids": self._thread_ids,
            "vocab": self._index.vocab,
            "weights": self._index.weights,
            "doc_lengths": self._index.doc_lengths,
            "idf": self._index.idf,
            "threads": self._threads,
        }
        with open(path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        log.info("saved BM25 index to %s (%.1f MB)", path, path.stat().st_size / 1e6)

    # ---------------------------------------------------------------------------------- queries
    def search(self, query: str, k: int = 6, exclude_thread_ids: set[str] | None = None) -> list[Hit]:
        """Top-``k`` useful, de-duplicated historical threads for ``query`` (see module docstring)."""
        if k <= 0 or not query or not query.strip():
            return []
        scores = self._index.score(tokenize(query))
        for tid in exclude_thread_ids or ():
            pos = self._position.get(tid)
            if pos is not None:
                scores[pos] = 0.0
        candidates = top_indices(scores, CANDIDATE_POOL)
        if candidates.size == 0:
            return []
        reranked = scores[candidates] * self._multipliers[candidates]
        order = np.lexsort((candidates, -reranked))
        ranked = [(int(candidates[i]), float(reranked[i])) for i in order]
        if exclude_thread_ids:
            ranked = [(pos, score) for pos, score in ranked
                      if not is_near_duplicate(str(self._threads[pos].get("customer_text", "")).casefold(), [query.casefold()])]
        return self._dedupe(ranked, k)

    def _dedupe(self, ranked: Sequence[tuple[int, float]], k: int) -> list[Hit]:
        """Keep the best-scoring representative of each near-identical customer text, up to ``k`` hits."""
        hits: list[Hit] = []
        kept_texts: list[str] = []
        for pos, score in ranked:
            thread = self._threads[pos]
            text = str(thread.get("customer_text") or "")
            if is_near_duplicate(text, kept_texts):
                continue
            hits.append(Hit(thread_id=self._thread_ids[pos], score=score, thread=thread))
            kept_texts.append(text)
            if len(hits) == k:
                break
        return hits

    def get(self, thread_id: str) -> dict | None:
        """The processed thread dict for ``thread_id``, or ``None`` when it is not indexed."""
        pos = self._position.get(thread_id)
        return None if pos is None else self._threads[pos]

    def __len__(self) -> int:
        return len(self._threads)

    @property
    def include_reply(self) -> bool:
        """Whether this index was built over ``customer_text + first_reply_text``."""
        return self._include_reply

    @property
    def vocab_size(self) -> int:
        return len(self._index.vocab)
