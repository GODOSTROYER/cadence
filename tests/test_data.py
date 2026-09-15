"""Tests for cadence.data (cleaning, language, threads, links, templates, sampling). No network, < 5 s."""

from __future__ import annotations

import pandas as pd
import pytest

from cadence.data.clean import asks_dm, clean_text, detect_language
from cadence.data.links import (
    LinkResolution,
    best_url,
    collect_links,
    extract_title,
    homepage_rate,
    is_homepage,
    resolve_links,
    success_rate,
)
from cadence.data.load import brand_subgraph, parse_created_at, split_response_ids, to_iso_utc
from cadence.data.sample import (
    RANDOM_BUCKET,
    SHORT_BUCKET,
    SamplingPlan,
    assign_bucket,
    compile_keyword,
    is_short_or_media,
    load_intent_keywords,
    sample_candidates,
    to_candidate_rows,
)
from cadence.data.summarize import compute_stats, normalize_reply, openers_table, reply_templates
from cadence.data.threads import build_threads

BRAND = "SpotifyCares"
TS = "Tue Oct 31 22:10:47 +0000 2017"


def _ts(minute: int) -> str:
    return f"Tue Oct 31 22:{minute:02d}:00 +0000 2017"


# ---------------------------------------------------------------------------
# §3.1 cleaning rules
# ---------------------------------------------------------------------------
def test_rule1_html_unescape():
    assert clean_text("Tom &amp; Jerry &lt;3").text == "Tom & Jerry <3"


def test_rule2_spotify_handles_removed_case_insensitive():
    res = clean_text("@SpotifyCares @spotifycares @SPOTIFYCARES @115888 @117168 @117153 hi")
    assert res.text == "hi"


def test_rule2_does_not_clip_longer_numeric_handles():
    assert clean_text("@1158889 hello").text == "@user hello"


def test_rule3_other_handles_become_user():
    assert clean_text("@SpotifyCares @559359 it broke @bob_1").text == "@user it broke @user"


def test_rule4_urls_replaced_and_recorded():
    res = clean_text("see https://t.co/abc123. and http://x.y/z?q=1")
    assert res.text == "see <url>. and <url>"
    assert res.has_link is True
    assert res.n_links == 2
    assert res.links == ["https://t.co/abc123", "http://x.y/z?q=1"]


def test_rule4_no_link():
    res = clean_text("no links here")
    assert (res.has_link, res.n_links, res.links) == (False, 0, [])


def test_rule5_agent_sig_trailing():
    res = clean_text("@115712 Hey there! Try a clean reinstall /JI", role="brand")
    assert res.text == "@user Hey there! Try a clean reinstall"
    assert res.agent_sig == "JI"


def test_rule5_agent_sig_before_url():
    res = clean_text("Send us a DM /JI https://t.co/x", role="brand")
    assert res.text == "Send us a DM <url>"
    assert res.agent_sig == "JI"
    assert res.links == ["https://t.co/x"]


def test_rule5_agent_sig_not_stripped_for_customers():
    res = clean_text("my app is dead /JI", role="customer")
    assert res.text == "my app is dead /JI"
    assert res.agent_sig is None


def test_rule5_agent_sig_only_at_end():
    res = clean_text("Try 1/2 of the steps. Cheers /A", role="brand")
    assert res.text == "Try 1/2 of the steps. Cheers"
    assert res.agent_sig == "A"
    assert clean_text("A/B test is running", role="brand").agent_sig is None


def test_rule6_whitespace_collapsed_emoji_kept():
    res = clean_text("  so   sad 😭 !!\n\n please  ")
    assert res.text == "so sad 😭 !! please"


def test_clean_text_handles_none_and_bad_role():
    assert clean_text(None).text == ""
    with pytest.raises(ValueError):
        clean_text("x", role="robot")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Can you DM us your email?", True),
        ("Please send us a direct message", True),
        ("Check your DMs!", True),
        ("Try a clean reinstall", False),
        ("The admin dmed you", False),
        (None, False),
    ],
)
def test_asks_dm(text, expected):
    assert asks_dm(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("my app keeps crashing since the update <url>", "en"),
        ("Would you ever consider adding a jpop category?", "en"),
        ("why is my playlist gone after the update? this is the third time", "en"),
        ("hola no puedo iniciar sesión en mi cuenta", "other"),
        ("não consigo ouvir músicas offline no aplicativo", "other"),
        ("tolong dibantu saya tidak bisa log in ke akun saya", "other"),
    ],
)
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_detect_language_short_texts_default_english():
    assert detect_language("<url>") == "en"
    assert detect_language("help") == "en"
    assert detect_language("") == "en"


# ---------------------------------------------------------------------------
# load helpers
# ---------------------------------------------------------------------------
def test_parse_created_at_iso():
    ts = parse_created_at(pd.Series([TS, "garbage"]))
    assert to_iso_utc(ts.iloc[0]) == "2017-10-31T22:10:47Z"
    assert to_iso_utc(ts.iloc[1]) is None


def test_split_response_ids():
    out = split_response_ids(pd.Series(["1,2", None, "3", " 4 ,x"], dtype="string"))
    assert sorted(out.tolist()) == [1, 2, 3, 4]


def _synthetic_df() -> pd.DataFrame:
    """Ten rows: a multi-turn thread (1-2-3-4-5 with cycle 4<->2), an unrelated brand chat, noise."""
    rows = [
        # multi-turn: opener 1 -> brand 2 -> customer 3 -> brand 4 (4 also points back to 2: cycle) -> customer 5
        (1, "c1", True, _ts(0), "@SpotifyCares app crashing since update https://t.co/z1", "2,9", None),
        (2, BRAND, False, _ts(1), "@c1 Hey! Which device? /AB", "3", 1.0),
        (3, "c1", True, _ts(2), "@SpotifyCares iPhone 7", "4", 2.0),
        (4, BRAND, False, _ts(3), "@c1 Try a clean reinstall /AB https://t.co/help1", "5,2", 3.0),
        (5, "c1", True, _ts(4), "@SpotifyCares that worked, thanks!", None, 4.0),
        # third party replying to the opener: must not join the thread
        (9, "c9", True, _ts(5), "@c1 same here", None, 1.0),
        # single-turn thread whose parent points to a tweet absent from the data (id 999)
        (6, "c2", True, _ts(6), "@SpotifyCares charged twice this month", "7", 999.0),
        (7, BRAND, False, _ts(7), "@c2 Can you DM us? /CD https://t.co/dm", None, 6.0),
        # inbound with no brand reply anywhere -> not a thread
        (8, "c3", True, _ts(8), "@SpotifyCares hello?", None, None),
        # unrelated brand's tweet
        (10, "AppleSupport", False, _ts(9), "@c4 hi", None, None),
    ]
    df = pd.DataFrame(
        rows,
        columns=[
            "tweet_id",
            "author_id",
            "inbound",
            "created_at",
            "text",
            "response_tweet_id",
            "in_response_to_tweet_id",
        ],
    )
    df["author_id"] = df["author_id"].astype("string")
    df["response_tweet_id"] = df["response_tweet_id"].astype("string")
    df["text"] = df["text"].astype("string")
    df["in_response_to_tweet_id"] = df["in_response_to_tweet_id"].astype("float64")
    return df


def test_brand_subgraph_reaches_all_connected_tweets():
    sub = brand_subgraph(_synthetic_df(), BRAND)
    assert sorted(sub["tweet_id"].tolist()) == [1, 2, 3, 4, 5, 6, 7, 9]


def test_brand_subgraph_unknown_brand():
    with pytest.raises(ValueError):
        brand_subgraph(_synthetic_df(), "Nobody")


def test_build_threads_multi_turn_and_cycle():
    link_map = {"https://t.co/help1": {"url": "https://support.spotify.com/article/reinstall/", "count": 1}}
    threads = build_threads(_synthetic_df(), BRAND, link_map)
    assert [t["opener_tweet_id"] for t in threads] == [1, 6]

    t1 = threads[0]
    assert t1["thread_id"] == "t_1"
    assert t1["created_at"] == "2017-10-31T22:00:00Z"
    assert t1["customer_author_id"] == "c1"
    assert t1["customer_text"] == "app crashing since update <url>"
    assert t1["has_link"] is True
    assert t1["n_words"] == 4  # URL placeholders carry no issue information.
    assert t1["language"] == "en"
    assert [turn["tweet_id"] for turn in t1["turns"]] == [1, 2, 3, 4, 5]
    assert [turn["role"] for turn in t1["turns"]] == ["customer", "brand", "customer", "brand", "customer"]
    assert t1["n_turns"] == 5
    assert t1["n_brand_replies"] == 2
    assert t1["first_reply_text"] == "@user Hey! Which device?"
    assert t1["first_reply_asks_dm"] is False
    second = t1["brand_replies"][1]
    assert second["agent_sig"] == "AB"
    assert second["links"] == ["https://t.co/help1"]
    assert second["resolved_links"] == ["https://support.spotify.com/article/reinstall/"]
    assert t1["turns"][1]["agent_sig"] == "AB"
    assert "agent_sig" not in t1["turns"][0]

    t6 = threads[1]
    assert t6["n_turns"] == 2
    assert t6["first_reply_asks_dm"] is True
    assert t6["brand_replies"][0]["resolved_links"] == []


def test_build_threads_without_link_map():
    threads = build_threads(_synthetic_df(), BRAND)
    assert all(r["resolved_links"] == [] for t in threads for r in t["brand_replies"])


# ---------------------------------------------------------------------------
# links (offline)
# ---------------------------------------------------------------------------
def test_collect_links_counts_tco_only():
    counts = collect_links(["go https://t.co/aaa /JI", "https://t.co/aaa. and https://example.com/x", None])
    assert counts == {"https://t.co/aaa": 2}


def test_extract_title():
    html = b"<html><head><title>\n Spotify &amp; you \n</title></head><body>" + b"x" * 100000
    assert extract_title(html) == "Spotify & you"
    assert extract_title("<html><body>no title</body></html>") is None
    assert extract_title(None) is None


def test_resolve_links_with_injected_fetcher_and_rates():
    calls: list[str] = []

    def fake(url: str) -> LinkResolution:
        calls.append(url)
        if url.endswith("bad"):
            return LinkResolution(url=None, title=None, status=None, error="Timeout: boom")
        chain = (url, "https://support.spotify.com/article/x/", "https://open.spotify.com/")
        return LinkResolution(url=chain[-1], title="Spotify", status=200, original_url=chain[1], chain=chain)

    counts = {"https://t.co/bad": 5, "https://t.co/ok": 9, "https://t.co/skip": 1}
    link_map = resolve_links(counts, top_n=2, workers=2, fetch=fake, retries=1)
    assert list(link_map) == ["https://t.co/ok", "https://t.co/bad"]
    assert calls.count("https://t.co/bad") == 2  # one retry pass, failures only
    assert calls.count("https://t.co/ok") == 1
    assert link_map["https://t.co/ok"]["count"] == 9
    assert link_map["https://t.co/ok"]["original_url"] == "https://support.spotify.com/article/x/"
    assert link_map["https://t.co/ok"]["chain"][-1] == "https://open.spotify.com/"
    assert link_map["https://t.co/bad"]["url"] is None
    assert link_map["https://t.co/bad"]["error"].startswith("Timeout")
    assert success_rate(link_map) == 0.5
    assert homepage_rate(link_map) == 1.0
    assert success_rate({}) == 0.0


def test_best_url_prefers_original_when_final_is_homepage():
    assert is_homepage("https://open.spotify.com/") and not is_homepage("https://open.spotify.com/track/1")
    entry = {"url": "https://open.spotify.com/", "original_url": "https://support.spotify.com/article/x/"}
    assert best_url(entry) == "https://support.spotify.com/article/x/"
    assert (
        best_url({"url": "https://community.spotify.com/t5/x", "original_url": "https://a/b"})
        == "https://community.spotify.com/t5/x"
    )
    # a shortener hop (spoti.fi) is no more informative than the homepage it now points to
    assert (
        best_url({"url": "https://open.spotify.com/", "original_url": "https://spoti.fi/1WOnKTD"})
        == "https://open.spotify.com/"
    )
    assert best_url({"url": None, "original_url": None}) is None


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------
def test_normalize_reply_and_templates():
    assert normalize_reply("@user Hey there! DM us <url> /ab") == "hey there! dm us"
    first = [
        ("@user Hey there! Can you DM us your email? <url>", "raw1"),
        ("Hey there! Can you DM us your email?", "raw2"),
        ("Fingers crossed we'll have it soon <url>", "raw3"),
    ]
    templates = reply_templates(first, top_n=5)
    assert templates[0]["template"] == "hey there! can you dm us your email?"
    assert templates[0]["count"] == 2
    assert templates[0]["asks_dm"] is True
    assert templates[0]["example_raw"] == "raw1"
    assert templates[0]["share"] == pytest.approx(2 / 3)
    assert templates[1]["asks_dm"] is False


def test_openers_table_and_stats():
    threads = build_threads(_synthetic_df(), BRAND)
    openers = openers_table(threads)
    assert len(openers) == 2
    assert str(openers["created_at"].dtype).startswith("datetime64")
    assert openers.loc[0, "first_reply_agent_sig"] == "AB"
    assert bool(openers.loc[1, "first_reply_has_link"]) is True
    stats = compute_stats(
        openers, n_rows_total=10, n_brand_tweets=3, n_subgraph_tweets=8, link_map={}, timings={"x": 1.234}
    )
    assert stats["n_threads"] == 2
    assert stats["share_multi_turn"] == 0.5
    assert stats["share_first_reply_asks_dm"] == 0.5
    assert stats["openers_per_month"] == {"2017-10": 2}
    assert stats["date_min"] == "2017-10-31"
    assert set(stats["reply_length_quantiles"]) == {"p10", "p25", "p50", "p75", "p90"}
    assert stats["timings_s"] == {"x": 1.23}


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------
_INTENTS = {
    "intents": [
        {"id": "playback_or_app_bug", "keywords": ["crash", "bug", "not working"]},
        {"id": "billing_or_charge", "keywords": ["charge", "refund", "$", "pay"]},
        {"id": "other", "keywords": ["help", "<url>"]},
    ]
}


def test_compile_keyword_boundary_vs_substring():
    assert compile_keyword("pay").search("i will pay")
    assert not compile_keyword("pay").search("payment")  # short keyword -> word boundary
    assert compile_keyword("crash").search("crashing")  # long keyword -> substring
    assert compile_keyword("$").search("$10 charge")  # symbol -> substring


def test_assign_bucket_most_hits_tie_earlier_none():
    matchers = load_intent_keywords(_INTENTS)
    assert assign_bucket("my app keeps crashing, such a bug", matchers) == "kw:playback_or_app_bug"
    assert assign_bucket("crash charge", matchers) == "kw:playback_or_app_bug"  # tie -> earlier intent
    assert assign_bucket("charged twice, refund please", matchers) == "kw:billing_or_charge"
    assert assign_bucket("what am i supposed to do? <url>", matchers) == "kw:other"
    assert assign_bucket("where is Garth Brooks", matchers) is None


def test_is_short_or_media():
    assert is_short_or_media("<url>", 1)
    assert is_short_or_media("<url> <url>", 2)
    assert is_short_or_media("help me now", 3)
    assert not is_short_or_media("my app keeps crashing daily", 5)


_FILLER = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa "
    "quebec romeo sierra tango uniform victor whiskey xray yankee zulu apple banana cherry damson elder "
    "fig grape honeydew kiwi lemon mango nectarine olive peach quince raspberry sloe tamarind ugli vanilla"
).split()


def _openers_frame() -> pd.DataFrame:
    rows = []
    templates = {
        "playback": "my app keeps crashing since the update",
        "billing": "you charged me twice, refund please",
        "none": "where is the new album by that artist",
    }
    i = 0
    for month in ("2017-10", "2017-11"):
        for tpl in templates.values():
            for _ in range(12):
                i += 1
                text = f"{tpl} {' '.join(_FILLER[(3 * i) % 40 : (3 * i) % 40 + 7])} {i}"
                rows.append(
                    {
                        "thread_id": f"t_{i}",
                        "opener_tweet_id": i,
                        "created_at": f"{month}-{(i % 27) + 1:02d}T10:00:00Z",
                        "customer_text": text,
                        "customer_text_raw": "@SpotifyCares " + text,
                        "language": "en",
                        "n_brand_replies": 1,
                        "n_words": 10,
                        "has_link": False,
                    }
                )
    for j in range(6):
        i += 1
        rows.append(
            {
                "thread_id": f"t_{i}",
                "opener_tweet_id": i,
                "created_at": "2017-11-05T10:00:00Z",
                "customer_text": "<url>" if j % 2 else f"help {j}",
                "customer_text_raw": "https://t.co/x",
                "language": "en",
                "n_brand_replies": 1,
                "n_words": 1 if j % 2 else 2,
                "has_link": bool(j % 2),
            }
        )
    # non-English and exact duplicate rows must be excluded
    rows.append({**rows[0], "thread_id": "t_dup", "opener_tweet_id": 9001})
    rows.append(
        {
            **rows[1],
            "thread_id": "t_es",
            "opener_tweet_id": 9002,
            "language": "other",
            "customer_text": "hola",
        }
    )
    return pd.DataFrame(rows)


def test_sample_candidates_buckets_shares_and_determinism():
    matchers = load_intent_keywords(_INTENTS)
    plan = SamplingPlan(target=40, per_bucket=8, n_short=3, min_random_share=0.30, dedupe_ratio=92.0)
    a = sample_candidates(_openers_frame(), matchers, plan)
    b = sample_candidates(_openers_frame(), matchers, plan)
    assert a["thread_id"].tolist() == b["thread_id"].tolist()
    counts = a["sampling_bucket"].value_counts().to_dict()
    assert counts[SHORT_BUCKET] == 3
    assert counts["kw:playback_or_app_bug"] == 8
    assert counts["kw:billing_or_charge"] == 8
    assert counts[RANDOM_BUCKET] >= 0.30 * len(a)
    assert len(a) >= plan.target
    assert a["thread_id"].is_unique
    assert "t_dup" not in set(a["thread_id"]) and "t_es" not in set(a["thread_id"])
    # short bucket only takes messages that test the media-only policy
    short = a[a["sampling_bucket"] == SHORT_BUCKET]
    assert all(is_short_or_media(t, n) for t, n in zip(short["customer_text"], short["n_words"], strict=True))
    # months spread within a keyword bucket
    playback = a[a["sampling_bucket"] == "kw:playback_or_app_bug"]
    assert playback["month"].nunique() == 2


def test_sample_dedupes_near_duplicates():
    matchers = load_intent_keywords(_INTENTS)
    base = _openers_frame().head(20)
    clones = base.assign(  # near-identical variants (one trailing character differs) of the first 20 rows
        thread_id=lambda d: "x_" + d["thread_id"],
        opener_tweet_id=lambda d: d["opener_tweet_id"] + 5000,
        customer_text=lambda d: d["customer_text"] + "!",
    )
    frame = pd.concat([_openers_frame(), clones], ignore_index=True)
    plan = SamplingPlan(target=30, per_bucket=8, n_short=2, dedupe_ratio=92.0)
    out = sample_candidates(frame, matchers, plan)
    texts = out["customer_text"].tolist()
    from rapidfuzz import fuzz

    assert all(
        fuzz.ratio(texts[i], texts[j]) <= 92 for i in range(len(texts)) for j in range(i + 1, len(texts))
    )


def test_to_candidate_rows_schema():
    matchers = load_intent_keywords(_INTENTS)
    sampled = sample_candidates(_openers_frame(), matchers, SamplingPlan(target=10, per_bucket=2, n_short=1))
    threads = {
        tid: {"first_reply_text": "Hey! DM us", "turns": [{"role": "customer", "text": "x"}]}
        for tid in sampled["thread_id"]
    }
    rows = to_candidate_rows(sampled, threads)
    assert [r["id"] for r in rows][:3] == ["c_001", "c_002", "c_003"]
    keys = {
        "id",
        "thread_id",
        "text",
        "text_raw",
        "created_at",
        "historical_brand_reply",
        "historical_thread",
        "sampling_bucket",
        "n_words",
        "has_link",
        "n_brand_replies",
    }
    assert all(set(r) == keys for r in rows)
    assert rows[0]["created_at"].endswith("Z")
    with pytest.raises(KeyError):
        to_candidate_rows(sampled, {})
