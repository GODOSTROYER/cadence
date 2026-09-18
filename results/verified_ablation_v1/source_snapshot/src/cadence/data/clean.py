"""Tweet cleaning rules (CONTRACT.md §3.1), the ``asks_dm`` predicate and a stopword language heuristic.

All functions are pure and deterministic so they can be applied row-by-row or via ``Series.map``.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Literal

from cadence.config import SPOTIFY_HANDLES
from cadence.utils.text import normalize_ws

Role = Literal["customer", "brand"]

URL_TOKEN = "<url>"
USER_TOKEN = "@user"

# Handles that all refer to Spotify accounts are removed outright (case-insensitive).
_SPOTIFY_HANDLE_RE = re.compile(
    "(?:" + "|".join(re.escape(h) for h in SPOTIFY_HANDLES) + r")(?!\w)",
    re.IGNORECASE,
)
_OTHER_HANDLE_RE = re.compile(r"@\w+")
# A URL runs to the next whitespace, but trailing sentence punctuation is left in the text
# ("see https://t.co/abc." -> "see <url>."), so the captured link is the bare URL.
_URL_RE = re.compile(r"https?://\S+?(?=[.,;:!?)\]'\"]*(?:\s|$))")
# Trailing agent signature " /JI", optionally followed only by (already tokenised) URLs.
_AGENT_SIG_RE = re.compile(r"\s*/([A-Z]{1,3})(?=(?:\s*" + re.escape(URL_TOKEN) + r")*\s*$)")
_ASKS_DM_RE = re.compile(r"\b(dm|direct message|dms)\b")
_TOKEN_RE = re.compile(r"[a-zà-ÿ']+")

# English function words plus a few support-domain words that only occur in English messages.
_EN_STOPWORDS: frozenset[str] = frozenset(
    """
    the i i'm im i've ive i'd my me is it it's its to and not can can't cant cannot you your you're
    youre please pls plz why when what what's whats how an of on in for with have has had do does
    doesn't doesnt don't dont did didn't didnt was were are am be been being this that that's there
    here they them their we our us from but so if or at by just still again get got getting keep
    keeps kept won't wont isn't isnt aren't arent wasn't wasnt couldn't couldnt wouldn't wouldnt
    shouldn't shouldnt because any every some all only also even ever never always sometimes
    would could should will shall might must may going gonna wanna want wants wanted need needs
    know knows think thought make makes made use using used try tried trying tell told say says
    said see seen show new now one two back down up out off over into than then these those which
    who where while about after before since last first other another thing things anyone someone
    something anything nothing everything everyone nobody like love hate good bad great really very
    much many more most well ok okay yes yeah hey hi hello help fix fixed fixing work working works
    worked play playing plays played listen listening song songs music playlist playlists account
    app phone device update updated adding add added remove removed consider category way days
    today yesterday week month year time times long ago still though anymore whenever wrong
    """.split()
)
# Frequent function words in the non-English languages present in the corpus
# (Spanish, Portuguese, Indonesian, French, German, Dutch, Italian, Turkish).
_FOREIGN_MARKERS: frozenset[str] = frozenset(
    """
    hola gracias por favor porque que qué como cómo pero mi mis una uno unos unas los las del con
    para está estoy tengo puedo quiero cuenta ayuda hace desde también siempre nada ya sin sobre
    não nao obrigado obrigada você voce vocês minha meu meus minhas conta ajuda aplicativo consigo
    estou tenho isso mas está muito quando fazer ainda aqui pelo pela nem já
    saya tidak bisa aku ini itu yang dan di ke dari untuk kenapa gimana tolong sudah bagaimana ada
    kok nya dong gak nggak sama akun bayar
    je ne pas est vous les mon mais pour une des sur avec suis
    ich nicht und das ist ein eine mit auf meine kann habe
    het een niet ik van dat mijn maar wordt
    non che sono della nel per una gli anche
    bir ve bu için ama değil hesap yok ben
    """.split()
)
_ACCENTED_RE = re.compile(r"[ãõçñáéíóúàèìòùâêôûäöüß]")


@dataclass(frozen=True)
class CleanResult:
    """Outcome of :func:`clean_text`.

    Attributes:
        text: cleaned text (handles normalised, URLs tokenised, signature stripped, whitespace collapsed).
        has_link: whether the raw text contained at least one URL.
        n_links: number of URLs found.
        links: the raw URLs in order of appearance (trailing punctuation removed).
        agent_sig: agent initials stripped from a brand reply (e.g. ``"JI"``), else ``None``.
    """

    text: str
    has_link: bool = False
    n_links: int = 0
    links: list[str] = field(default_factory=list)
    agent_sig: str | None = None


def clean_text(text: str | None, role: Role = "customer") -> CleanResult:
    """Apply the six cleaning rules of CONTRACT.md §3.1 in order.

    1. Unescape HTML entities.
    2. Remove Spotify handles.
    3. Replace any other ``@handle`` with ``@user``.
    4. Replace URLs with ``<url>`` (recording them).
    5. For ``role == "brand"`` only, strip a trailing ``/XX`` agent signature (it may precede a URL).
    6. Collapse whitespace; emoji and punctuation are kept.
    """
    if role not in ("customer", "brand"):
        raise ValueError(f"role must be 'customer' or 'brand', got {role!r}")
    raw = html.unescape(str(text) if text is not None else "")
    raw = _SPOTIFY_HANDLE_RE.sub(" ", raw)
    raw = _OTHER_HANDLE_RE.sub(USER_TOKEN, raw)
    links = _URL_RE.findall(raw)
    raw = _URL_RE.sub(URL_TOKEN, raw)
    agent_sig: str | None = None
    if role == "brand":
        match = _AGENT_SIG_RE.search(raw)
        if match:
            agent_sig = match.group(1)
            raw = raw[: match.start()] + raw[match.end() :]
    return CleanResult(
        text=normalize_ws(raw),
        has_link=bool(links),
        n_links=len(links),
        links=links,
        agent_sig=agent_sig,
    )


def asks_dm(text: str | None) -> bool:
    """True when a brand reply asks the customer to move to a direct message."""
    return bool(_ASKS_DM_RE.search((text or "").lower()))


def detect_language(text: str | None) -> Literal["en", "other"]:
    """Cheap English-vs-other classifier (CONTRACT.md §3).

    Counts English stopword hits against a list of frequent non-English function words and
    accented characters. English needs one hit for texts of up to six words and two hits beyond
    that, and must out-score the foreign evidence. Very short texts with no foreign evidence and
    only ASCII letters (``"help"``, ``"<url>"``) are treated as English so they are not dropped.
    """
    tokens = _TOKEN_RE.findall((text or "").lower())
    n_words = len(tokens)
    en_hits = sum(1 for t in tokens if t in _EN_STOPWORDS)
    foreign_hits = sum(1 for t in tokens if t in _FOREIGN_MARKERS) + len(_ACCENTED_RE.findall(text or ""))
    if foreign_hits > en_hits:
        return "other"
    needed = 2 if n_words > 6 else 1
    if en_hits >= needed:
        return "en"
    if n_words <= 3 and foreign_hits == 0:
        return "en"
    return "other"


__all__ = ["CleanResult", "Role", "URL_TOKEN", "USER_TOKEN", "asks_dm", "clean_text", "detect_language"]
