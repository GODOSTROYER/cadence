"""Reproduce descriptive, message-clustered analysis of a frozen AI retrieval review.

No model calls, new ratings, candidate changes, gold labels, or reserved data reads.
Historical usefulness and current authority remain separate measurements.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from cadence.eval.provenance import sha256

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("raw_text", "request_frame", "request_frame_token_rerank")
VIEWS = ("first_brand_reply", "last_later_brand_reply")
METRICS = ("same_issue", "any_relevance", "useful_diagnostic_pattern", "supports_proposed_action")
IDENTITY = {"review_id", "run_id", "rubric_version", "selection_lock_sha256", "item_sha256"}


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def unique(rows, fields):
    result = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in result:
            raise ValueError(f"Duplicate identity on {fields}: {key}")
        result[key] = row
    return result


def load_joined(directory, submission):
    spec = importlib.util.spec_from_file_location(
        "_retrieval_review_validator", Path(__file__).with_name("verified_retrieval_review.py"))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    paths = [directory / name for name in (
        "blind_packet.jsonl", "private_mapping.jsonl", "PACKET.lock.json", "SELECTION.lock.json", "rubric.json")]
    paths += [submission, Path(__file__), Path(helper.__file__)]
    bindings = {path.resolve().relative_to(ROOT).as_posix() if path.resolve().is_relative_to(ROOT)
                else str(path.resolve()): sha256(path) for path in paths}
    validation = helper.validate_ratings(directory, submission, reviewer_type="ai")
    packet = unique(read_rows(directory / "blind_packet.jsonl"), ("review_id",))
    ratings = unique(read_rows(submission), ("review_id",))
    mapping = unique(read_rows(directory / "private_mapping.jsonl"), ("review_id",))
    if packet.keys() != ratings.keys() or packet.keys() != mapping.keys():
        raise ValueError("Packet, mapping, and ratings must have exact identity coverage")
    lock = json.loads((directory / "SELECTION.lock.json").read_text(encoding="utf-8"))["payload"]
    if lock["phase"] != "development" or tuple(lock["arms"]) != ARMS or lock["k"] != 3:
        raise ValueError("This summary requires the development three-arm top-three design")
    ids = sorted(lock["selected_ids"])
    if len(ids) != len(set(ids)) or len(ids) != lock["sample_size"]:
        raise ValueError("Invalid locked message identities")
    joined = []
    for key, p in packet.items():
        r, m = ratings[key], mapping[key]
        if m["item_sha256"] != p["item_sha256"]:
            raise ValueError("Mapping item hash mismatch")
        if helper.digest({k: v for k, v in p.items() if k != "item_sha256"}) != p["item_sha256"]:
            raise ValueError("Packet item content hash mismatch")
        expected_id = helper.digest([p["run_id"], m["id"], m["arm"], m["rank"], m["reply_kind"]])[:24]
        if expected_id != m["review_id"]:
            raise ValueError("Mapping identity does not bind to the sealed message/arm/rank/view")
        joined.append({"map": m, "packet": p, "rating": r})
    cells = unique([x["map"] for x in joined], ("id", "arm", "rank", "reply_kind"))
    expected = {(i, arm, rank, view) for i in ids for arm in ARMS for rank in (1, 2, 3) for view in VIEWS}
    if set(cells) != expected:
        raise ValueError("Incomplete or extra message/arm/rank/reply-view cells")
    for i in ids:
        xs = [x for x in joined if x["map"]["id"] == i]
        if len({(x["packet"]["customer_text"], x["packet"]["proposed_action"],
                 x["map"]["prediction_sha256"]) for x in xs}) != 1:
            raise ValueError("Customer/proposed-action context differs between arms")
        for arm in ARMS:
            if len({cells[(i, arm, rank, VIEWS[0])]["thread_id"] for rank in (1, 2, 3)}) != 3:
                raise ValueError("Repeated thread within an arm's top three")
            for rank in (1, 2, 3):
                first, later = [cells[(i, arm, rank, view)] for view in VIEWS]
                if any(first[k] != later[k] for k in ("thread_id", "thread_sha256")):
                    raise ValueError("First/later views do not belong to the same candidate")
    for path, expected_hash in bindings.items():
        if sha256(ROOT / path) != expected_hash:
            raise ValueError("Analysis input changed while loading: " + path)
    return joined, ids, validation, bindings


def available(row):
    return row["packet"]["availability"] == "available"


def positive(row, metric):
    if not available(row):
        return False  # An absent slot supplies no hit; it is not a negative content rating.
    rating = row["rating"]
    if metric == "same_issue":
        return str(rating["issue_relevance"]) == "2"
    if metric == "any_relevance":
        return str(rating["issue_relevance"]) in {"1", "2"}
    return rating[metric] == "yes"


def proportion(numerator, denominator):
    return numerator / denominator if denominator else None


def arm_cell(rows, ids):
    shown = [x for x in rows if available(x)]
    available_ids = {x["map"]["id"] for x in shown}
    result = {"selected_messages": len(ids), "candidate_slots": len(rows),
              "available_candidates": len(shown), "absent_candidates": len(rows) - len(shown),
              "messages_with_available_candidates": len(available_ids),
              "messages_without_available_candidates": len(ids) - len(available_ids)}
    result["metrics"] = {}
    for metric in METRICS:
        hits = {x["map"]["id"] for x in shown if positive(x, metric)}
        count = sum(positive(x, metric) for x in shown)
        result["metrics"][metric] = {
            "positive_candidates": count, "positive_rate_among_available_candidates": proportion(count, len(shown)),
            "messages_with_hit": len(hits), "hit_rate_all_selected_messages": proportion(len(hits), len(ids)),
            "hit_rate_messages_with_available_candidates": proportion(len(hits), len(available_ids)),
        }
    result["rating_counts_available_only"] = {
        field: dict(sorted(Counter(str(x["rating"][field]) for x in shown).items()))
        for field in ("issue_relevance", "useful_diagnostic_pattern", "supports_proposed_action", "context_sufficient")}
    return result


def paired(left, right, ids, repetitions, seed):
    """One Bernoulli hit per message and arm; resample whole paired messages."""
    deltas = [int(right[i]) - int(left[i]) for i in ids]
    n = len(ids)
    rng = random.Random(seed)
    draws = sorted(sum(rng.choices(deltas, k=n)) / n for _ in range(repetitions)) if n else []

    def quantile(q):
        index = (len(draws) - 1) * q
        lo = int(index)
        return draws[lo] + (draws[min(lo + 1, len(draws) - 1)] - draws[lo]) * (index - lo)

    return {"n_message_clusters": n, "left_positive_messages": sum(left[i] for i in ids),
            "right_positive_messages": sum(right[i] for i in ids),
            "right_only": deltas.count(1), "left_only": deltas.count(-1), "ties": deltas.count(0),
            "difference_right_minus_left": proportion(sum(deltas), n),
            "descriptive_paired_bootstrap_95_interval": [quantile(.025), quantile(.975)] if n else None,
            "message_deltas": dict(zip(ids, deltas, strict=True))}


def reply_contrast(rows, all_ids, repetitions, seed):
    """Match the same message/thread and count each thread once across supplied arms."""
    by_candidate = defaultdict(dict)
    for row in rows:
        m = row["map"]
        key = (m["id"], m["thread_id"])
        previous = by_candidate[key].get(m["reply_kind"])
        if previous is not None:
            for field in ("packet", "rating"):
                a = {k: v for k, v in previous[field].items() if k not in IDENTITY}
                b = {k: v for k, v in row[field].items() if k not in IDENTITY}
                if a != b:
                    raise ValueError("Duplicate substantive context has conflicting ratings or content")
        by_candidate[key][m["reply_kind"]] = row
    pairs = {key: views for key, views in by_candidate.items()
             if all(view in views and available(views[view]) for view in VIEWS)}
    ids = sorted({i for i, _ in pairs})
    result = {"unique_message_thread_candidates": len(by_candidate), "matched_available_pairs": len(pairs),
              "unmatched_candidates": len(by_candidate) - len(pairs), "paired_messages": len(ids),
              "selected_messages_without_matched_pairs": len(all_ids) - len(ids), "metrics": {}}
    for metric in METRICS:
        left = {i: any(positive(v[VIEWS[0]], metric) for (j, _), v in pairs.items() if j == i) for i in ids}
        right = {i: any(positive(v[VIEWS[1]], metric) for (j, _), v in pairs.items() if j == i) for i in ids}
        transitions = Counter((positive(v[VIEWS[0]], metric), positive(v[VIEWS[1]], metric))
                              for v in pairs.values())
        result["metrics"][metric] = {
            "first_positive_candidates": sum(a * count for (a, _), count in transitions.items()),
            "later_positive_candidates": sum(b * count for (_, b), count in transitions.items()),
            "later_only_candidates": transitions[(False, True)], "first_only_candidates": transitions[(True, False)],
            "both_positive_candidates": transitions[(True, True)], "neither_positive_candidates": transitions[(False, False)],
            "paired_message_hit": paired(left, right, ids, repetitions, seed),
        }
    return result


def summarize(directory, submission, repetitions=20000, seed=2026091815):
    if repetitions < 1000:
        raise ValueError("Use at least 1000 descriptive bootstrap repetitions")
    rows, ids, validation, bindings = load_joined(directory, submission)
    arms, hit_sets = {}, {}
    for arm in ARMS:
        arms[arm] = {}
        for view in VIEWS:
            arms[arm][view] = {}
            for k in (1, 3):
                xs = [x for x in rows if x["map"]["arm"] == arm and x["map"]["reply_kind"] == view
                      and x["map"]["rank"] <= k]
                arms[arm][view][f"top{k}"] = arm_cell(xs, ids)
                for metric in METRICS:
                    hit_sets[(arm, view, k, metric)] = {
                        i: any(positive(x, metric) for x in xs if x["map"]["id"] == i) for i in ids}
    comparisons = {}
    for left, right in ((ARMS[0], ARMS[1]), (ARMS[1], ARMS[2]), (ARMS[0], ARMS[2])):
        comparisons[f"{right}_minus_{left}"] = {
            view: {f"top{k}": {metric: paired(hit_sets[(left, view, k, metric)],
                                             hit_sets[(right, view, k, metric)], ids, repetitions, seed)
                               for metric in METRICS} for k in (1, 3)} for view in VIEWS}
    substantive = Counter(json.dumps({k: v for k, v in x["packet"].items() if k not in IDENTITY}, sort_keys=True)
                          for x in rows)
    later = {arm: reply_contrast([x for x in rows if x["map"]["arm"] == arm], ids, repetitions, seed)
             for arm in ARMS}
    later["union_across_arms_deduplicated"] = reply_contrast(rows, ids, repetitions, seed)
    return {
        "version": "verified-retrieval-descriptive-summary-v1", "phase": "development", "validation": validation,
        "inputs_logical_sha256": bindings, "selected_message_ids": ids, "n_messages": len(ids),
        "n_packet_rows": len(rows), "n_unique_substantive_contexts": len(substantive),
        "duplicate_group_size_counts": dict(sorted(Counter(substantive.values()).items())),
        "analysis_contract": {
            "primary_relevance": "same_issue means issue_relevance=2; any_relevance means 1 or 2",
            "top_k": "At least one positive candidate among ranks 1..k, separately for each reply view",
            "absence": "No retrieved hit, not a negative content rating; available-only rates also reported",
            "uncertain": "Reported separately in rating counts; never counted as a positive yes",
            "inference_unit": "Selected customer message; never the 360 rows or 244 reviewed contexts",
            "arm_pairing": "All arms paired on the same selected messages, including absent slots as no hit",
            "reply_pairing": "Only same message/thread with both views available; deduplicated across arms in union",
            "interval": "Descriptive paired message-cluster percentile bootstrap; not confirmatory or multiplicity-adjusted",
            "bootstrap_repetitions": repetitions, "bootstrap_seed": seed,
            "input_hashing": "cadence.eval.provenance.sha256 normalizes CRLF text; original packet raw-byte seals validate independently",
            "later_view_limit": "Later views include preceding turns (often the first reply), so differences cannot isolate the later reply",
            "authority": "Historical support is never combined with current-authority ratings",
            "review_limit": "AI-only development judgments; no human validation, independent outcome observation, or promotion",
        },
        "arms": arms, "paired_arm_comparisons": comparisons, "matched_first_vs_later": later,
        "current_authority_counts": dict(sorted(Counter(x["rating"]["current_authority"] for x in rows).items())),
    }


def findings(s):
    names = dict(zip(ARMS, ("Raw text", "Request frame", "Frame + token rerank"), strict=True))
    n = s["n_messages"]
    first = {arm: s["arms"][arm][VIEWS[0]] for arm in ARMS}

    def hits(arm, metric, k=3):
        return first[arm][f"top{k}"]["metrics"][metric]["messages_with_hit"]

    diagnostic = [hits(a, "useful_diagnostic_pattern") for a in ARMS]
    support = [hits(a, "supports_proposed_action") for a in ARMS]
    lines = ["# Verified retrieval: frozen AI development review", "",
             "## Findings", "",
             f"For first replies, top-three diagnostic hits were {diagnostic[0]}/{n} for raw text, {diagnostic[1]}/{n} for the "
             f"request frame, and {diagnostic[2]}/{n} after token reranking. Proposed-action support was "
             f"{support[0]}/{n}, {support[1]}/{n}, and {support[2]}/{n}, respectively. "
             "The frame query shows no gain on these top-three outcomes in this sample; token reranking reduces "
             "diagnostic and action-support coverage. "
             "Later views must be compared on available matched candidates and include earlier turns, so their "
             "ratings do not isolate the usefulness of the final reply.", "",
             f"These are **AI-only descriptive findings on {n} development messages**, not human verification or a "
             f"promotion decision. The {s['n_packet_rows']} packet rows contain {s['n_unique_substantive_contexts']} "
             "unique substantive contexts; neither count is an "
             "independent sample size. Ratings were frozen before the private arm mapping was opened.", "",
             "## First replies: message-level retrieval hits", "",
             "A hit means at least one qualifying candidate at rank 1 or within ranks 1–3. Relevance is strictly "
             "the same issue (`2`); partly relevant (`1`) is reported separately in the JSON. All first-reply slots "
             f"were available. Each count below has the same {n}-message denominator.", "",
             "| Arm | Top 1 same issue | Top 3 same issue | Top 1 diagnostic | Top 3 diagnostic | Top 1 action support | Top 3 action support |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        cells = s["arms"][arm][VIEWS[0]]
        values = [cells[f"top{k}"]["metrics"][metric]["messages_with_hit"]
                  for metric in ("same_issue", "useful_diagnostic_pattern", "supports_proposed_action") for k in (1, 3)]
        lines.append(f"| {names[arm]} | " + " | ".join(f"{v}/{n}" for v in values) + " |")
    lines += ["", f"At the looser threshold of at least partly relevant (`1` or `2`), frame querying increases "
              f"top-one hits from {hits(ARMS[0], 'any_relevance', 1)}/{n} to "
              f"{hits(ARMS[1], 'any_relevance', 1)}/{n}, and top-three hits from "
              f"{hits(ARMS[0], 'any_relevance')}/{n} to {hits(ARMS[1], 'any_relevance')}/{n}. "
              "That broader topic overlap does not establish a gain in the top-three same-issue, diagnostic, or "
              "action-support outcomes. First-reply top-one same-issue hits do increase slightly, "
              f"from {hits(ARMS[0], 'same_issue', 1)}/{n} to {hits(ARMS[1], 'same_issue', 1)}/{n}.", "",
              "### Paired top-three differences", "",
              "Differences are right arm minus left arm, paired by customer message. Intervals resample whole paired "
              f"messages ({s['analysis_contract']['bootstrap_repetitions']:,} replicates, fixed seed); "
              "they are descriptive percentile intervals, not adjusted "
              "confirmatory tests. They do not measure AI reviewer error. The small development sample and AI "
              "judgment uncertainty limit generalization.", "",
              "| Comparison | Metric | Gained / lost messages | Difference | Descriptive 95% interval |",
              "|---|---|---:|---:|---:|"]
    for left, right in ((ARMS[0], ARMS[1]), (ARMS[1], ARMS[2]), (ARMS[0], ARMS[2])):
        for metric in ("same_issue", "useful_diagnostic_pattern", "supports_proposed_action"):
            p = s["paired_arm_comparisons"][f"{right}_minus_{left}"][VIEWS[0]]["top3"][metric]
            lo, hi = p["descriptive_paired_bootstrap_95_interval"]
            lines.append(f"| {names[right]} − {names[left]} | {metric.replace('_', ' ')} | "
                         f"{p['right_only']} / {p['left_only']} | {100*p['difference_right_minus_left']:+.0f} pp | "
                         f"[{100*lo:+.0f}, {100*hi:+.0f}] pp |")
    lines += ["", "Frame querying changes which messages benefit; equal total diagnostic coverage does not mean "
              "identical hits. The simple token-overlap reranker has no supported improvement claim here. These "
              "results concern retrieval of historical examples for the already-proposed response, not changes to "
              "the response itself, current factual accuracy, or downstream support outcomes.", "",
              "## Later views: coverage and matched comparison", "",
              "| Arm | Available / absent later slots (top 3) | Messages with any later view | Same-issue hit | Diagnostic hit | Action-support hit |",
              "|---|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        cell = s["arms"][arm][VIEWS[1]]["top3"]
        counts = [cell["metrics"][m]["messages_with_hit"] for m in
                  ("same_issue", "useful_diagnostic_pattern", "supports_proposed_action")]
        lines.append(f"| {names[arm]} | {cell['available_candidates']} / {cell['absent_candidates']} | "
                     f"{cell['messages_with_available_candidates']}/{n} | " + " | ".join(f"{v}/{n}" for v in counts) + " |")
    lines += ["", "The table uses all selected messages to measure delivered coverage; an absent later reply is "
              "not a negative content rating. The JSON also gives positive-candidate rates conditional on availability, "
              "available-message hit rates, top-one results, and full yes/no/uncertain distributions.", "",
              "For a content comparison, keep only the same historical candidates with both views available. "
              "The union below counts each `(current message, historical thread)` once across arms.", "",
              "| Matched set | Candidate pairs | Paired messages | First / later diagnostic candidates | Later-only / first-only candidates | First / later messages with diagnostic hit |",
              "|---|---:|---:|---:|---:|---:|"]
    for arm, contrast in s["matched_first_vs_later"].items():
        d = contrast["metrics"]["useful_diagnostic_pattern"]
        p = d["paired_message_hit"]
        lines.append(f"| {names.get(arm, 'Deduplicated union')} | {contrast['matched_available_pairs']} | "
                     f"{contrast['paired_messages']} | {d['first_positive_candidates']} / {d['later_positive_candidates']} | "
                     f"{d['later_only_candidates']} / {d['first_only_candidates']} | "
                     f"{p['left_positive_messages']} / {p['right_positive_messages']} |")
    union = s["matched_first_vs_later"]["union_across_arms_deduplicated"]
    p = union["metrics"]["useful_diagnostic_pattern"]["paired_message_hit"]
    lo, hi = p["descriptive_paired_bootstrap_95_interval"]
    lines += ["", f"In the deduplicated matched union, diagnostic message hits change by "
              f"{100*p['difference_right_minus_left']:+.1f} percentage points "
              f"(descriptive paired 95% interval [{100*lo:+.1f}, {100*hi:+.1f}]; "
              f"{p['n_message_clusters']} eligible message clusters). "
              f"{union['selected_messages_without_matched_pairs']} selected messages have no matched available pair and "
              "are excluded from this conditional comparison.", "",
              "**Interpretation:** the later view is a larger context window and can retain diagnostics from the first "
              "reply. A gain therefore reflects usefulness of the supplied view, not the isolated final reply or a "
              "resolved customer issue. Availability is selective, and this matched analysis does not remove that bias.", "",
              "## Provenance and reproduction", "",
              "- The existing `validate_ratings(..., reviewer_type=\"ai\")` helper validates the frozen packet and all ratings. "
              "The analysis additionally checks exact packet/mapping/rating identity coverage, item hashes, alias bindings, "
              "the complete message/arm/rank/view grid, and first/later candidate identities.",
              f"- Current authority is a separate field: all {s['n_packet_rows']} rows are `unsupported`. Historical action support "
              "does not authenticate current URLs, product availability, promotional terms, or a successful outcome.",
              "- The summary binds source files and analysis/validator code with the repository's portable "
              "SHA256 helper (CRLF normalized for text). The original packet's raw-byte seals are validated "
              "separately. No ratings are edited, no "
              "candidate implementation changes are made, and no reserved sample text or gold labels are read.",
              "- Full counts and paired message deltas: [summary.json](../results/verified_retrieval_dev_v2/summary.json). "
              "Review process: [AI_REVIEW_NOTES.md](../results/verified_retrieval_dev_v2/AI_REVIEW_NOTES.md).", "",
              "```powershell", "python analysis_tools/summarize_verified_retrieval.py", 
              "python analysis_tools/summarize_verified_retrieval.py --check", "```", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "results/verified_retrieval_dev_v2")
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--findings", type=Path, default=ROOT / "docs/VERIFIED_RETRIEVAL_FINDINGS.md")
    parser.add_argument("--check", action="store_true", help="Compare reproduced outputs without writing")
    args = parser.parse_args()
    summary = summarize(args.directory, args.submission or args.directory / "ai_review_submission.jsonl")
    outputs = {args.directory / "summary.json": json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
               args.findings: findings(summary)}
    for path, content in outputs.items():
        if args.check:
            if path.read_text(encoding="utf-8") != content:
                raise SystemExit("Reproduction mismatch: " + str(path))
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    print(f"{'Checked' if args.check else 'Wrote'} summary and findings: {summary['n_messages']} message clusters, "
          f"{summary['n_packet_rows']} rows; AI-only descriptive analysis.")


if __name__ == "__main__":
    main()
