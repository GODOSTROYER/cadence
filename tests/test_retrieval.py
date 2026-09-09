"""Tests for cadence.retrieval (tokeniser, BM25 index, usefulness re-ranking, persistence)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from cadence.retrieval.bm25 import BM25Index, tokenize, top_indices
from cadence.retrieval.index import (
    DM_ONLY_PENALTY,
    SUBSTANTIVE_BOOST,
    Hit,
    Retriever,
    is_dm_only,
    usefulness_multiplier,
)

DM_REPLY = "Hey there! Can you DM us your account's email address? We'll take a look backstage"
HELP_URL = "https://support.spotify.com/article/reinstallation-of-spotify/"


def make_thread(
    n: int,
    customer: str,
    reply: str,
    *,
    resolved_links: tuple[str, ...] = (),
    asks_dm: bool = False,
) -> dict[str, Any]:
    """A processed thread (CONTRACT.md §3) with the fields the retriever reads."""
    tid = f"t_{n}"
    return {
        "thread_id": tid,
        "opener_tweet_id": n,
        "created_at": "2017-10-31T22:10:47Z",
        "customer_author_id": str(100000 + n),
        "customer_text_raw": f"@SpotifyCares {customer}",
        "customer_text": customer,
        "has_link": "<url>" in customer,
        "n_words": len(customer.split()),
        "language": "en",
        "brand_replies": [
            {
                "tweet_id": n + 1,
                "created_at": "2017-10-31T22:20:00Z",
                "text_raw": f"@{100000 + n} {reply} /JI",
                "text": f"@user {reply}",
                "agent_sig": "JI",
                "links": ["https://t.co/x"] if resolved_links else [],
                "resolved_links": list(resolved_links),
                "asks_dm": asks_dm,
            }
        ],
        "turns": [
            {"role": "customer", "tweet_id": n, "created_at": "2017-10-31T22:10:47Z", "text": customer},
            {
                "role": "brand",
                "tweet_id": n + 1,
                "created_at": "2017-10-31T22:20:00Z",
                "text": reply,
                "agent_sig": "JI",
            },
        ],
        "n_brand_replies": 1,
        "n_turns": 2,
        "first_reply_text": f"@user {reply}",
        "first_reply_asks_dm": asks_dm,
    }


def synthetic_threads() -> list[dict[str, Any]]:
    """30 threads across the support topics, with a mix of DM-only, linked and informational replies."""
    rows: list[tuple[str, str, dict[str, Any]]] = [
        ("my app keeps crashing since the update", "What device, OS and Spotify version are you on?", {}),
        (
            "the app crashes every time i open it",
            "Try a clean reinstall using the steps here <url>",
            {"resolved_links": (HELP_URL,)},
        ),
        ("spotify crashes when i share a song", DM_REPLY, {"asks_dm": True}),
        ("downloads vanished", DM_REPLY, {"asks_dm": True}),
        (
            "all my downloads vanished from the phone",
            "Check the steps under Downloads unexpectedly removed here <url>",
            {"resolved_links": (HELP_URL,)},
        ),
        ("offline mode is not working on my ipad", "Is your device online at least once every 30 days?", {}),
        ("i cant log in with facebook anymore", DM_REPLY, {"asks_dm": True}),
        (
            "forgot my password and lost the email",
            "Head to the password reset page here <url>",
            {"resolved_links": (HELP_URL,)},
        ),
        (
            "someone else is playing music on my account",
            "Change your password and sign out everywhere, then DM us",
            {"asks_dm": True},
        ),
        ("my account got hacked", DM_REPLY, {"asks_dm": True}),
        ("charged twice this month for premium", DM_REPLY, {"asks_dm": True}),
        (
            "i want a refund for the charge",
            "We've just sent a DM your way. Let's carry on chatting there",
            {"asks_dm": True},
        ),
        (
            "student discount says im not eligible",
            "You need to be enrolled at an accredited college; more here <url>",
            {"resolved_links": (HELP_URL,)},
        ),
        ("family plan wont let me invite my sister", DM_REPLY, {"asks_dm": True}),
        (
            "how do i cancel my subscription",
            "To cancel head to your account page <url>",
            {"resolved_links": (HELP_URL,)},
        ),
        ("hulu bundle not showing on my account", DM_REPLY, {"asks_dm": True}),
        (
            "songs greyed out in my playlist",
            "Greyed out tracks are unavailable in your region or removed by the label",
            {},
        ),
        (
            "spotify is not available in my country",
            "We're launching in new countries as often as possible!",
            {},
        ),
        ("please add this artist to spotify", "Artists and labels choose where their music is available", {}),
        (
            "my playlist got deleted",
            "Playlists can be recovered from your account page here <url>",
            {"resolved_links": (HELP_URL,)},
        ),
        ("my whole library disappeared", DM_REPLY, {"asks_dm": True}),
        ("wrapped 2017 isnt showing up for me", "Keep your eyes peeled, more info soon!", {}),
        (
            "the shuffle plays the same songs over and over",
            "We've recently made some improvements to our shuffle algorithm",
            {},
        ),
        (
            "web player not playing anything in chrome",
            "Does clearing your browser cache and cookies help?",
            {},
        ),
        ("spotify connect wont find my speaker", "Are both devices on the same wifi network?", {}),
        ("podcasts not loading on android", "Podcasts are available on Android; try updating the app", {}),
        ("it would be nice to have a sleep timer", "Thanks for the feedback! We've passed it on", {}),
        (
            "hola no puedo escuchar musica",
            "We can help in English here; for Spanish head to <url>",
            {"resolved_links": (HELP_URL,)},
        ),
        ("thanks for the quick help", "You're welcome!", {}),
        ("love this app", "Happy listening!", {}),
    ]
    return [
        make_thread(1000 + i * 10, customer, reply, **extra)
        for i, (customer, reply, extra) in enumerate(rows)
    ]


@pytest.fixture(scope="module")
def threads() -> list[dict[str, Any]]:
    return synthetic_threads()


@pytest.fixture(scope="module")
def retriever(threads: list[dict[str, Any]]) -> Retriever:
    return Retriever.build(threads)


# ------------------------------------------------------------------------------------ tokeniser
class TestTokenize:
    def test_lowercases_and_drops_placeholders_and_stopwords(self) -> None:
        assert tokenize("My Spotify APP is crashing <url> @user, and it just won't play") == [
            "spotify", "app", "crash", "won't", "play",
        ]  # fmt: skip

    def test_conservative_stemming_only_beyond_four_chars(self) -> None:
        assert tokenize("songs crashes devices playlists tried updating") == [
            "song", "crash", "device", "playlist", "tri", "updat",
        ]  # fmt: skip
        # short tokens and "ss" endings are left alone
        assert tokenize("this was bass boss apps") == ["bass", "boss", "apps"]

    def test_keeps_numbers_and_contractions(self) -> None:
        assert tokenize("charged 2 times on 10/31 and 2017 wrapped isn't here") == [
            "charg", "2", "time", "10", "31", "2017", "wrapp", "isn't", "here",
        ]  # fmt: skip

    def test_stopword_contractions_and_empty(self) -> None:
        assert tokenize("I'm can't im cant") == []
        assert tokenize("") == []
        assert tokenize("<url> @user") == []


# ------------------------------------------------------------------------------------ BM25 core
class TestBM25Index:
    def test_rare_terms_outscore_common_ones(self) -> None:
        docs = [["app", "crash"], ["app", "refund"], ["app", "login"], ["app", "crash", "crash"]]
        index = BM25Index.build(docs)
        scores = index.score(["crash"])
        assert scores[3] > scores[0] > 0 and scores[1] == 0 and scores[2] == 0
        assert index.score(["app"]).max() < scores[0]  # 'app' is in every doc: low idf
        assert not index.score(["unknown"]).any()

    def test_scores_are_length_normalised(self) -> None:
        index = BM25Index.build([["crash"], ["crash", "when", "sharing", "a", "song", "on", "pixel"]])
        scores = index.score(["crash"])
        assert scores[0] > scores[1]

    def test_top_indices_orders_and_breaks_ties_by_position(self) -> None:
        scores = np.array([0.0, 3.0, 5.0, 3.0, 0.0], dtype=np.float32)
        assert top_indices(scores, 10).tolist() == [2, 1, 3]
        assert top_indices(scores, 2).tolist() == [2, 1]
        assert top_indices(np.zeros(3, dtype=np.float32), 5).size == 0

    def test_empty_collection_rejected(self) -> None:
        with pytest.raises(ValueError):
            BM25Index.build([])


# ---------------------------------------------------------------------------------- retriever
class TestRetrieverSearch:
    def test_len_and_get(self, retriever: Retriever, threads: list[dict[str, Any]]) -> None:
        assert len(retriever) == 30
        assert retriever.get("t_1000") is threads[0]
        assert retriever.get("t_nope") is None

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("app crashing after the update", "t_1000"),
            ("web player wont play in chrome", "t_1230"),
            ("greyed out songs", "t_1160"),
            ("cancel subscription", "t_1140"),
            ("someone is using my account playing music", "t_1080"),
        ],
    )
    def test_expected_top_hit(self, retriever: Retriever, query: str, expected: str) -> None:
        hits = retriever.search(query, k=3)
        assert hits and isinstance(hits[0], Hit)
        assert hits[0].thread_id == expected
        assert hits[0].thread["thread_id"] == expected
        assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)

    def test_returns_at_most_k_and_only_matching_threads(self, retriever: Retriever) -> None:
        assert len(retriever.search("shuffle songs playlist account app", k=4)) == 4
        assert retriever.search("xylophone quantum", k=5) == []
        assert retriever.search("", k=5) == []
        assert retriever.search("crash", k=0) == []

    def test_exclude_thread_ids(self, retriever: Retriever) -> None:
        top = retriever.search("app crashing after the update", k=1)[0].thread_id
        assert top == "t_1000"
        hits = retriever.search("app crashing after the update", k=5, exclude_thread_ids={"t_1000"})
        assert hits and all(h.thread_id != "t_1000" for h in hits)
        assert hits[0].thread_id == "t_1010"
        without_all = retriever.search("app crashing", k=5, exclude_thread_ids={"t_1000", "t_1010", "t_1020"})
        assert all(h.thread_id not in {"t_1000", "t_1010", "t_1020"} for h in without_all)

    def test_exclusion_of_unknown_id_is_harmless(self, retriever: Retriever) -> None:
        assert retriever.search("crash", k=2, exclude_thread_ids={"t_missing"}) == retriever.search(
            "crash", k=2
        )


class TestUsefulnessReranking:
    def test_multipliers(self) -> None:
        linked = make_thread(1, "downloads gone", "See here <url>", resolved_links=(HELP_URL,))
        substantive = make_thread(
            2, "downloads gone", "Try re-downloading after toggling offline mode off and on again in settings"
        )
        dm_only = make_thread(3, "downloads gone", DM_REPLY, asks_dm=True)
        dm_short = make_thread(4, "downloads gone", "We've sent you a DM", asks_dm=True)
        dm_with_steps = make_thread(
            5,
            "downloads gone",
            "Try a clean reinstall first; if that doesn't help send us a DM",
            asks_dm=True,
        )
        thanks = make_thread(6, "love it", "Happy listening!")
        assert usefulness_multiplier(linked) == SUBSTANTIVE_BOOST
        assert usefulness_multiplier(substantive) == SUBSTANTIVE_BOOST
        assert usefulness_multiplier(dm_only) == DM_ONLY_PENALTY
        assert usefulness_multiplier(dm_short) == DM_ONLY_PENALTY
        assert usefulness_multiplier(dm_with_steps) == SUBSTANTIVE_BOOST
        assert usefulness_multiplier(thanks) == 1.0
        assert usefulness_multiplier({"thread_id": "t_x", "customer_text": "hi", "brand_replies": []}) == 1.0

    def test_is_dm_only(self) -> None:
        assert is_dm_only(DM_REPLY)
        assert is_dm_only("@user Hi! We've just sent a DM your way. Let's carry on chatting there")
        assert not is_dm_only("Try a clean reinstall first; if that doesn't help send us a DM")
        assert not is_dm_only("Head to your account page and toggle offline mode; DM us if it persists")

    def test_linked_reply_outranks_dm_only_reply(
        self, retriever: Retriever, threads: list[dict[str, Any]]
    ) -> None:
        assert [h.thread_id for h in retriever.search("downloads vanished", k=2)] == ["t_1040", "t_1030"]
        # customer-only index: raw BM25 prefers the shorter DM-only thread, the re-ranking flips it
        customer_only = Retriever.build(threads, include_reply=False)
        raw = customer_only._index.score(tokenize("downloads vanished"))
        assert raw[3] > raw[4] > 0
        hits = customer_only.search("downloads vanished", k=2)
        assert [h.thread_id for h in hits] == ["t_1040", "t_1030"]
        assert hits[0].score == pytest.approx(raw[4] * SUBSTANTIVE_BOOST, rel=1e-5)
        assert hits[1].score == pytest.approx(raw[3] * DM_ONLY_PENALTY, rel=1e-5)

    def test_near_duplicate_customer_texts_are_collapsed(self) -> None:
        threads = synthetic_threads() + [
            make_thread(9000, "My app keeps crashing since the update!", DM_REPLY, asks_dm=True),
            make_thread(
                9010,
                "my app keeps crashing since the update",
                "Try reinstalling via <url>",
                resolved_links=(HELP_URL,),
            ),
        ]
        r = Retriever.build(threads)
        hits = r.search("app keeps crashing since the update", k=5)
        ids = [h.thread_id for h in hits]
        dupes = {"t_1000", "t_9000", "t_9010"}
        assert len(dupes & set(ids)) == 1
        assert ids[0] == "t_9010"  # the best-scoring (linked) copy is the one kept
        assert len(ids) == len(set(ids))


class TestPersistence:
    def test_save_load_roundtrip(self, retriever: Retriever, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "bm25_index.pkl"
        retriever.save(path)
        assert path.exists()
        loaded = Retriever.load(path)
        assert len(loaded) == len(retriever)
        assert loaded.include_reply == retriever.include_reply
        assert loaded.vocab_size == retriever.vocab_size
        assert loaded.get("t_1120") == retriever.get("t_1120")
        for query in ("charged twice for premium", "cancel subscription", "podcasts android"):
            a = [
                (h.thread_id, round(h.score, 5))
                for h in retriever.search(query, k=4, exclude_thread_ids={"t_1100"})
            ]
            b = [
                (h.thread_id, round(h.score, 5))
                for h in loaded.search(query, k=4, exclude_thread_ids={"t_1100"})
            ]
            assert a == b

    def test_load_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            Retriever.load(tmp_path / "nope.pkl")

    def test_build_rejects_bad_input(self) -> None:
        with pytest.raises(ValueError):
            Retriever.build([])
        with pytest.raises(ValueError):
            Retriever.build([{"customer_text": "no id"}])
