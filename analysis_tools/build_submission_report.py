"""Build the six-page Cadence submission report from committed evidence. No model calls.

Optional authoring dependencies: reportlab, fonttools; bundled static fonts have OFL licenses.
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/pdf/Cadence-Arnav-Bule-Report.pdf"
ASSETS = ROOT / "docs/report_assets"
W, H = 595.276, 841.89
M, CW = 42, 511.276
BG, PANEL, INK, MUTED, GREEN, LINE = "#101214", "#191d20", "#eeeae1", "#b2bab5", "#20df72", "#303735"
REPO = "https://github.com/GODOSTROYER/cadence/blob/main/"
SITE = "https://www.arnavbule.in/hiver-assignment/"


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def register_fonts():
    for name, filename in [
        ("Display", "InstrumentSerif-Regular.ttf"),
        ("DisplayItalic", "InstrumentSerif-Italic.ttf"),
        ("Body", "Geist-Regular.ttf"),
        ("Bold", "Geist-Semibold.ttf"),
        ("Mono", "GeistMono-Regular.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, str(ASSETS / "fonts" / filename)))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Bold", italic="Body", boldItalic="Bold")


class Report:
    def __init__(self):
        OUT.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(OUT), pagesize=(W, H), pageCompression=1)
        self.c.setTitle("Cadence | Evidence, decisions, and limits")
        self.c.setAuthor("Arnav Bule")
        self.c.setSubject("Hiver SDE Intern take-home | six-page technical report")
        self.page_number = 0
        self.layout = []

    def rect(self, x, y, w, h, fill=PANEL, radius=0):
        self.c.setFillColor(HexColor(fill))
        self.c.roundRect(x, H - y - h, w, h, radius, stroke=0, fill=1)

    def line(self, x, y, width=CW, color=LINE):
        self.c.setStrokeColor(HexColor(color))
        self.c.setLineWidth(0.55)
        self.c.line(x, H - y, x + width, H - y)

    def text(self, text, x, y, size=10, font="Body", color=INK):
        self.c.setFillColor(HexColor(color))
        self.c.setFont(font, size)
        self.c.drawString(x, H - y - size, text)

    def para(self, text, x, y, width=CW, size=10.2, leading=14.5, color=MUTED, max_height=None):
        style = ParagraphStyle(
            "body",
            fontName="Body",
            fontSize=size,
            leading=leading,
            textColor=HexColor(color),
            alignment=TA_LEFT,
            splitLongWords=False,
        )
        p = Paragraph(text, style)
        _, height = p.wrap(width, H)
        if y + height > 790 or (max_height is not None and height > max_height):
            raise ValueError(f"Layout overflow page {self.page_number}, y={y}, h={height}: {text[:65]}")
        p.drawOn(self.c, x, H - y - height)
        self.layout.append({"page": self.page_number, "x": x, "y": y, "width": width, "height": height})
        return y + height

    def label(self, text, y, x=M):
        self.text(text.upper(), x, y, 8, "Mono", GREEN)

    def link(self, label, target, x, y, size=9):
        self.text(label, x, y, size, "Body", GREEN)
        self.c.linkURL(
            target,
            (x, H - y - size - 3, x + pdfmetrics.stringWidth(label, "Body", size), H - y + 2),
            relative=0,
        )

    def page(self, section, title=None, subtitle=None):
        if self.page_number:
            self.footer()
            self.c.showPage()
        self.page_number += 1
        self.rect(0, 0, W, H, BG)
        self.c.bookmarkPage(str(self.page_number))
        self.c.addOutlineEntry(section, str(self.page_number), 0)
        for i, height in enumerate([8, 16, 23, 12]):
            self.rect(M + i * 5, 33 - height, 2.7, height, GREEN, 1)
        self.text("Cadence", M + 28, 12, 24, "DisplayItalic")
        self.text(section.upper(), 348, 23, 8, "Mono", MUTED)
        self.line(M, 53)
        if title:
            self.text(title, M, 76, 35, "DisplayItalic")
        if subtitle:
            self.para(subtitle, M, 124, size=10.1, leading=14)

    def footer(self):
        self.line(M, 803)
        self.text("ARNAV BULE  /  HIVER SDE INTERN", M, 813, 7.2, "Mono", MUTED)
        self.text(f"{self.page_number:02d} / 06", 505, 812, 8, "Mono", GREEN)

    def table(self, columns, rows, x, y, widths, row_height=31):
        self.rect(x, y, sum(widths), 28, PANEL)
        xx = x
        for col, width in zip(columns, widths, strict=True):
            self.text(col, xx + 9, y + 8, 8.3, "Bold", INK)
            xx += width
        y += 28
        for row in rows:
            xx = x
            for value, width in zip(row, widths, strict=True):
                self.text(str(value), xx + 9, y + 9, 9, "Body", GREEN if str(value).startswith("+") else INK)
                xx += width
            self.line(x, y + row_height, sum(widths))
            y += row_height
        return y

    def stat(self, x, y, value, label, caption, width=160):
        self.line(x, y, width, GREEN)
        self.text(value, x, y + 10, 31, "Display")
        self.text(label, x, y + 53, 9.5, "Bold")
        self.para(caption, x, y + 71, width, size=8.5, leading=11.8)


def pct(v):
    return f"{v * 100:.1f}%"


def main():
    register_fonts()
    balanced_publication = read("results/published/balanced.json")
    balanced = balanced_publication["current"]
    report = Report()
    r = report
    r.page("01 / the brief")
    r.label("Hiver SDE Intern take-home / 18 September 2026", 78)
    r.text("An AI support agent", M, 101, 45, "DisplayItalic")
    r.text("that earns its answer.", M, 151, 45, "DisplayItalic")
    r.para(
        "Built by <b>Arnav Bule</b>. Cadence classifies customer messages, drafts grounded replies and explains when a human must take over.",
        M,
        217,
        468,
        size=12,
        leading=17,
        color=INK,
    )
    r.c.saveState()
    crop = r.c.beginPath()
    crop.rect(M, H - 514, CW, 230)
    r.c.clipPath(crop, stroke=0)
    r.c.drawImage(str(ASSETS / "cadence-gates.png"), M, H - 565, width=CW, height=CW * 2 / 3)
    r.c.restoreState()
    r.text("CLASSIFY", 61, 495, 8, "Mono", INK)
    r.text("GROUND", 235, 495, 8, "Mono", INK)
    r.text("DECIDE", 429, 495, 8, "Mono", INK)
    r.stat(
        M,
        546,
        "27,627",
        "Real support threads",
        "SpotifyCares conversations from the 2017 Twitter support corpus.",
    )
    r.stat(
        218,
        546,
        "200",
        "Frozen benchmark cases",
        "Four matched systems. Labels and scores reviewed by Arnav Bule.",
    )
    r.stat(
        394,
        546,
        str(balanced["n"]),
        "Latest confirmation cases",
        "Separated from inspected data; AI labels frozen before inference.",
    )
    r.para(
        "<b>The engineering question:</b> How much support can the system usefully handle automatically while missing as few necessary escalations as possible? Fluency and intent accuracy alone do not answer that question.",
        M,
        677,
        size=11,
        leading=16,
    )
    r.link("Live demo", SITE, M, 758)
    r.link("Repository and runnable evidence", "https://github.com/GODOSTROYER/cadence", 149, 758)

    r.page(
        "02 / method & provenance",
        "Start with the customer.",
        "A small, inspectable pipeline; explicit labels; separate evidence for each version.",
    )
    r.label("Problem framing", 178)
    r.para(
        "SpotifyCares has recurring technical questions and account-specific requests. “Good” means relevant, supported, useful and appropriately escalated. The agent drafts public replies; it has no account tools and never posts tweets, refunds money or contacts staff.",
        M,
        202,
        241,
    )
    r.para(
        "Twelve intents cover playback, playlists, plans, billing, login, security, downloads, catalog, artist metadata, feedback, language and other requests. Billing/security defaults and deterministic safety rules override model confidence. The threshold is frozen at 0.90.",
        312,
        202,
        241,
    )
    r.label("Versioned implementations, explicit handoffs", 317)
    steps = [
        ("DEPLOYED REFERENCE", "Rules + BM25 k6 + one structured model call + release checks."),
        (
            "BALANCED CANDIDATE",
            "Joint route + approved answer selection; preserve request scope; check the exact reply in a second call.",
        ),
        (
            "HUMAN HANDOFF",
            "Return a reason and a real support contact route. Never claim an action was performed.",
        ),
    ]
    yy = 341
    for label, body in steps:
        r.rect(M, yy, CW, 58, PANEL, 6)
        r.text(label, M + 14, yy + 10, 8, "Mono", GREEN)
        r.para(body, M + 14, yy + 26, CW - 28, size=9.5, leading=13)
        yy += 68
    r.label("Annotation chain", 569)
    r.table(
        ["Evidence", "Origin and review", "Use"],
        [
            ("Historical 250", "AI labels; repeatedly inspected", "Training / regression"),
            ("Frozen 200", "AI labels; Arnav approved", "Frozen benchmark"),
            ("100 reply ratings", "Astra xhigh; Arnav verified", "Judge calibration audit"),
            ("New 60 + 80", "Astra xhigh before inference", "Versioned confirmation"),
        ],
        M,
        592,
        [125, 239, 147],
        row_height=28,
    )
    r.para(
        "Sampling excludes prior candidate, golden, taxonomy and benchmark cases; confirmation also excludes development messages. Conversation overlap and >=85% fuzzy text matches are rejected. This is an English-focused customer-message sample, not traffic-weighted demand.",
        M,
        743,
        size=8.7,
        leading=12,
    )

    r.page(
        "03 / benchmark evidence",
        "The headline, with context.",
        "The archived 200-case benchmark is kept immutable. New measurements do not overwrite it.",
    )
    r.table(
        ["System", "Accuracy", "Macro-F1", "Recall", "Auto", "Misses"],
        [
            ("Majority / escalate", "11.5%", "0.017", "100%", "0/200", "0"),
            ("Keyword / nearest", "60.0%", "0.601", "34.6%", "166/200", "53"),
            ("Same prompt, k0", "80.0%", "0.826", "100%", "0/200", "0"),
            ("Retrieval, k6", "77.0%", "0.789", "93.8%", "70/200", "5"),
        ],
        M,
        179,
        [160, 72, 72, 70, 72, 65],
        row_height=34,
    )
    r.para(
        "<b>Read recall together with coverage.</b> Always escalating misses nothing and resolves nothing automatically. The k0 arm also has zero coverage because the citation gate vetoes uncited replies; it is not a clean retrieval-safety ablation.",
        M,
        359,
        size=10.5,
        leading=15,
    )
    r.stat(M, 439, "0.789", "Intent macro-F1", "Paired bootstrap 95% interval: 0.647 to 0.836.", width=153)
    r.stat(
        220,
        439,
        "93.8%",
        "Escalation recall",
        "76 / 81 required escalations caught. Bootstrap interval: 88.2% to 98.8%.",
        width=153,
    )
    r.stat(
        398,
        439,
        "5 / 70",
        "Misses among auto",
        "A fluent automatic response can still require a human.",
        width=153,
    )
    r.label("A high judge score was not enough", 603)
    r.para(
        "The original Gemini judge scored agent replies <b>4.11/5</b> versus <b>2.69/5</b> for the simple baseline, but approved an obsolete limit and a fictional DM action. Preference order consistency was only <b>73.5%</b>. Retrieval did not establish a classification improvement: k6 - k0 accuracy was -3.0 points (95% interval -7.5 to +1.0).",
        M,
        626,
        size=10.3,
        leading=14.7,
    )
    r.para(
        "<b>Calibration audit:</b> 100 exact replies on 50 matched messages were first rated by GPT-6 Astra at extra-high reasoning, then verified unchanged by Arnav Bule. Agreement against both Gemini orders: weighted kappa <b>0.137</b>, exact <b>28%</b>, within one <b>53%</b>. The human saw AI scores; the stricter later rubric is a disclosed audit, not an independent blind replication.",
        M,
        704,
        size=9.4,
        leading=13,
    )

    r.page(
        "04 / failure-driven repairs",
        "Fix the reply, not the score.",
        "Five recurring defects explain the candidate design. Known cases remain regression evidence.",
    )
    failures = [
        (
            "01",
            "Unsupported actions",
            "h_168 claims a DM was sent; d2_003 claims feedback forwarding. Hypothesis: copied staff actions become promises.",
            "Server-rendered actions prevent arbitrary operational promises. Rules and exact-text semantic review add checks.",
        ),
        (
            "02",
            "Wrong-issue guidance",
            "d2_007 confuses customer and Spotify-created playlists. Hypothesis: lexical overlap outranks issue fit.",
            "Classify before retrieval. Review whether the exact proposed step addresses the customer’s stated issue.",
        ),
        (
            "03",
            "Stale procedures",
            "h_003 repeats an old limit; d2_009/010 copy developer-work claims. Hypothesis: history becomes current policy.",
            "Treat history as examples, not current policy. Dated official sources authorize a narrow set of present procedures.",
        ),
        (
            "04",
            "Unhelpful handoffs",
            "d2_010/d2_013 give no path forward. Hypothesis: abstention suppresses useful guidance.",
            "Use an honest limitation and Spotify’s verified support contact page; ask only necessary, specific questions.",
        ),
        (
            "05",
            "Risk and ambiguity",
            "h_079/h_105 expose frustration and churn misses. Hypothesis: coarse confidence masks escalation risk.",
            "Keep rules, primary/secondary policy defaults and low-confidence escalation. A semantic checker cannot prove safety.",
        ),
    ]
    yy = 181
    for num, title, example, repair in failures:
        r.line(M, yy)
        r.text(num, M, yy + 13, 12, "Mono", GREEN)
        r.text(title, M + 39, yy + 10, 21, "Display")
        r.para(escape(example), M + 39, yy + 40, 205, size=9.1, leading=12.5)
        r.para(escape(repair), 312, yy + 40, 241, size=9.1, leading=12.5)
        yy += 103
    r.rect(M, 709, CW, 66, PANEL, 6)
    r.para(
        "<b>Review before release:</b> the semantic check sees the exact finalized public text, including trimming and links. Failed checks produce a contact handoff. BalancedAgent uses one or two calls; tokens and latency are measured rather than assumed.",
        M + 14,
        724,
        CW - 28,
        size=9.5,
        leading=13.5,
    )

    r.page(
        "05 / controlled tests",
        "Measure useful coverage.",
        "Development selects a hypothesis. Fresh confirmation tests the frozen implementation.",
    )
    r.label("Before / the earlier 60-case confirmation", 177)
    r.para(
        "The earlier quality candidate reduced missed escalations from 4 to 0, but automatic replies fell from 22/60 to 4/60. Useful replies rose only from 3/60 to 4/60. That coverage loss motivated a broader set of verified answers and joint routing. The reference and quality versions remain unchanged.",
        M, 199, size=9.4, leading=13,
    )
    r.label(f"Now / {balanced['n']} new cases / all three arms / AI labels and review", 267)
    names = {"agent": "Reference", "quality": "Quality candidate", "balanced": "Balanced candidate"}
    r.table(
        ["System", "Auto", "Useful auto", "Resolution-style", "Misses"],
        [(name, f"{balanced['counts'][key]['automatic']}/{balanced['n']}",
          f"{balanced['counts'][key]['useful_automatic']}/{balanced['n']}",
          str(balanced['counts'][key]['useful_resolution']),
          str(balanced['counts'][key]['missed_escalations'])) for key, name in names.items()],
        M, 291, [139, 90, 101, 96, 85], row_height=30,
    )
    r.label("Cost and latency / successful end-to-end predictions", 432)
    r.table(
        ["Runtime", "Reference", "Quality", "Balanced"],
        [("p95 seconds", *[f"{balanced['runtime'][key]['p95_ms']/1000:.2f}" for key in names]),
         ("Input + output tokens", *[f"{balanced['runtime'][key]['prompt_tokens']+balanced['runtime'][key]['output_tokens']:,}" for key in names])],
        M, 456, [169, 114, 114, 114], row_height=27,
    )
    timing = ("All recorded calls were fresh. " if balanced['gates']['latency_observations_fully_fresh'] else
              "Some predictions used cached calls; the freshness gate failed. ")
    if balanced.get('execution'):
        timing += "Timing spans " + ', '.join(balanced['execution']['receipt_dates_utc']) + " (UTC). "
    timing += "Failed attempts and interruption time are excluded."
    r.para(
        "<b>Useful automatic</b> requires ship, grounding/safety/next-step scores >=4 and no flags. Clarifications count; resolution-style replies are reviewer judgments, not observed outcomes. Handoffs/social replies are excluded. Misses count even when text looks harmless. " + timing,
        M, 550, size=9.1, leading=12.4,
    )
    r.rect(M, 647, CW, 130, PANEL, 6)
    gate_labels = {
        'no_more_misses_than_either': 'missed-escalation bound',
        'no_reviewer_flagged_unsafe_automatic': 'zero flagged automatic replies',
    }
    failed = [gate_labels.get(key, key.replace('_', ' ')) for key, passed in balanced['gates'].items()
              if not passed and key != 'new_reply_reviews_verified_by_human']
    r.para(
        "<b>Acceptance:</b> " + ("Technical gates passed. " if balanced['technical_gates_pass'] else "Technical gates failed. ")
        + escape(balanced['decision'])
        + (" Failed: " + escape('; '.join(failed)) + "." if failed else "")
        + f" Balanced automatic replies flagged by review: {balanced['counts']['balanced']['flagged_automatic']}."
        + " " + escape(balanced_publication["review_note"])
        + " Development iterations are preserved. Code was frozen before confirmation; no tuning followed these outcomes.",
        M + 14, 661, CW - 28, size=9.2, leading=12.6,
    )

    r.page(
        "06 / limits & reproduction",
        "Make the claim reproducible.",
        "The evidence is worth more than the demo. Reproduce saved results without an API key.",
    )
    r.label("What is misleading about my headline number?", 177)
    caveats = [
        "<b>Coverage hides utility.</b> An automatic decision can be irrelevant, obsolete or unsafe. Report useful coverage and missed escalations alongside recall.",
        "<b>Confidence is not calibrated risk.</b> A 0.90 intent threshold is a policy setting. The original selector used its F2 fallback, not the claimed recall target.",
        "<b>Labels and samples limit the claim.</b> Original AI labels were reviewed by Arnav; new confirmation labels are AI-only. De-duplication and English sampling change the population.",
        "<b>Review independence matters.</b> Arnav verified visible Astra ratings. The later rubric is stricter than the original judge. Agreement does not establish independent hand-labeling.",
        "<b>Replay is not a fresh model run.</b> Saved receipts prove what ran. Inspected examples are regressions; timing covers successful local requests, not a production SLA.",
    ]
    yy = 200
    for text in caveats:
        yy = r.para(text, M, yy, CW, size=9.2, leading=12.6) + 10
    r.label("With one more week", yy + 4)
    yy = (
        r.para(
            "Obtain an independent blind human pass on the new replies; calibrate routing against useful coverage; broaden current-source coverage with expiry checks; run a larger locked benchmark and a small deployment canary. Keep account actions and autonomous posting outside this prototype.",
            M,
            yy + 27,
            size=9.6,
            leading=13.4,
        )
        + 23
    )
    r.label("Reproduce / Python 3.12 / zero new model calls", yy)
    yy += 25
    for command in [
        'python -m pip install -e ".[dev]"',
        "python analysis_tools/reproduce_benchmark.py",
        "python analysis_tools/reproduce_balanced.py",
        "python -m pytest -q",
    ]:
        r.text(command, M, yy, 8.5, "Mono", INK)
        yy += 18
    r.para(
        "README documents the under-15-minute replay path. The repository contains the full rubric, per-example rationales, failures, cached receipts, input hashes and 15 non-obvious decisions. The hosted app is a demonstration; form submission is intentionally left to the author.",
        M,
        yy + 7,
        size=9,
        leading=12.5,
    )
    r.link("Evidence & decision log", REPO + "DECISION_LOG.md", M, 736)
    r.link(
        "Dataset: Customer Support on Twitter",
        "https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter",
        252,
        736,
    )
    r.link(
        "Spotify: current playback guidance",
        "https://support.spotify.com/us/article/spotify-not-playing/",
        M,
        756,
    )
    r.link(
        "Spotify: official support contact", "https://support.spotify.com/us/article/contact-us/", 312, 756
    )
    r.footer()
    r.c.save()
    (OUT.parent / "layout-check.json").write_text(
        json.dumps({"pages": r.page_number, "blocks": r.layout}, indent=2)
    )
    print(OUT)


if __name__ == "__main__":
    main()
