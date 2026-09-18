"""BM25 scoring over a sparse term matrix (Okapi BM25, k1=1.5, b=0.75).

The tokeniser and the index are deliberately tiny and dependency-light (numpy + scipy.sparse) so a
query over ~27k documents scores every document in a couple of milliseconds:

* :func:`tokenize` — lowercase, drop the ``<url>`` / ``@user`` placeholders produced by the cleaning
  step, keep ``[a-z0-9']+`` runs, drop a short stopword list, and apply conservative suffix stemming
  (``s``, ``es``, ``ed``, ``ing``) to tokens longer than four characters. Numbers are kept.
* :class:`BM25Index` — holds the per-(document, term) BM25 weights as a CSC matrix so scoring a query
  is a column gather plus a sparse matrix–vector product. Every term's contribution is precomputed
  at build time, which is what makes the per-query work so small.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp

K1: float = 1.5
"""BM25 term-frequency saturation parameter."""
B: float = 0.75
"""BM25 document-length normalisation parameter."""

STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "and", "or", "to", "of", "in", "on", "my", "i", "is", "it", "for", "you",
        "me", "this", "that", "with", "at", "be", "are", "was", "so", "just", "can", "cant", "can't",
        "im", "i'm",
    }
)  # fmt: skip
"""Function words dropped before indexing; kept short so topical words such as 'not' survive."""

PLACEHOLDER_TOKENS: frozenset[str] = frozenset({"<url>", "@user"})
"""Placeholders inserted by ``cadence.data.clean`` that carry no topical signal."""

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_MIN_STEM_LEN = 5
_ES_STEM_ENDINGS: tuple[str, ...] = ("s", "sh", "ch", "x", "z")


def _stem(token: str) -> str:
    """Strip one of ``ing``/``ed``/``es``/``s`` from tokens of five or more characters.

    ``es`` is only removed when the remainder ends in ``s``/``sh``/``ch``/``x``/``z`` (the English
    ``-es`` plural rule), so ``crashes`` → ``crash`` while ``devices`` → ``device`` (matching the
    singular). ``'s`` possessives are dropped first. Short tokens are left alone so ``this``/``was``
    style words are not mangled.
    """
    if token.endswith("'s"):
        token = token[:-2]
    if len(token) < _MIN_STEM_LEN:
        return token
    for suffix in ("ing", "ed"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    if token.endswith("es") and token[:-2].endswith(_ES_STEM_ENDINGS):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Turn cleaned tweet text into BM25 tokens.

    >>> tokenize("My Spotify app keeps crashing since the update <url> @user 2017")
    ['spotify', 'app', 'keep', 'crash', 'since', 'update', '2017']
    """
    if not text:
        return []
    lowered = text.lower()
    for placeholder in PLACEHOLDER_TOKENS:
        lowered = lowered.replace(placeholder, " ")
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(lowered):
        token = raw.strip("'")
        if not token or token in STOPWORDS:
            continue
        tokens.append(_stem(token))
    return tokens


@dataclass
class BM25Index:
    """Precomputed BM25 weights for a fixed document collection.

    Attributes:
        vocab: term → column index (terms sorted alphabetically for determinism).
        weights: ``n_docs × n_terms`` CSC matrix of BM25 per-term contributions.
        doc_lengths: token count per document (kept for diagnostics and persistence).
        idf: inverse document frequency per term (aligned with ``vocab`` columns).
    """

    vocab: dict[str, int]
    weights: sp.csc_matrix
    doc_lengths: np.ndarray
    idf: np.ndarray

    @property
    def n_docs(self) -> int:
        return int(self.weights.shape[0])

    @classmethod
    def build(cls, documents: Sequence[Sequence[str]], *, k1: float = K1, b: float = B) -> BM25Index:
        """Build the index from already-tokenised documents."""
        if not documents:
            raise ValueError("BM25Index.build needs at least one document")
        vocab = _build_vocab(documents)
        tf = _term_frequency_matrix(documents, vocab)
        doc_lengths = np.asarray(tf.sum(axis=1)).ravel().astype(np.float32)
        idf = _idf(tf)
        weights = _bm25_weights(tf, doc_lengths, idf, k1=k1, b=b)
        return cls(vocab=vocab, weights=weights, doc_lengths=doc_lengths, idf=idf)

    def score(self, query_tokens: Iterable[str]) -> np.ndarray:
        """BM25 score of every document for ``query_tokens`` (repeated query terms count once each).

        Returns a dense ``float32`` vector of length ``n_docs``; all zeros when no token is in the
        vocabulary.
        """
        columns = sorted({self.vocab[t] for t in query_tokens if t in self.vocab})
        if not columns:
            return np.zeros(self.n_docs, dtype=np.float32)
        query_vec = np.ones(len(columns), dtype=np.float32)
        return np.asarray(self.weights[:, columns] @ query_vec, dtype=np.float32).ravel()


def _build_vocab(documents: Sequence[Sequence[str]]) -> dict[str, int]:
    terms: set[str] = set()
    for doc in documents:
        terms.update(doc)
    return {term: i for i, term in enumerate(sorted(terms))}


def _term_frequency_matrix(documents: Sequence[Sequence[str]], vocab: dict[str, int]) -> sp.csr_matrix:
    """Sparse ``n_docs × n_terms`` raw term-frequency matrix."""
    indptr = [0]
    indices: list[int] = []
    data: list[int] = []
    for doc in documents:
        counts = Counter(vocab[t] for t in doc)
        indices.extend(counts.keys())
        data.extend(counts.values())
        indptr.append(len(indices))
    return sp.csr_matrix(
        (
            np.asarray(data, dtype=np.float32),
            np.asarray(indices, dtype=np.int32),
            np.asarray(indptr, dtype=np.int64),
        ),
        shape=(len(documents), len(vocab)),
    )


def _idf(tf: sp.csr_matrix) -> np.ndarray:
    """Okapi idf with the +1 inside the log (Lucene variant) so it is never negative."""
    n_docs = tf.shape[0]
    df = np.bincount(tf.indices, minlength=tf.shape[1]).astype(np.float32)
    return np.log(1.0 + (n_docs - df + 0.5) / (df + 0.5)).astype(np.float32)


def _bm25_weights(
    tf: sp.csr_matrix, doc_lengths: np.ndarray, idf: np.ndarray, *, k1: float, b: float
) -> sp.csc_matrix:
    """Turn raw term frequencies into per-cell BM25 contributions, stored column-major for query gathers."""
    avg_len = float(doc_lengths.mean()) if doc_lengths.size else 1.0
    norm = k1 * (1.0 - b + b * doc_lengths / max(avg_len, 1e-9))  # per document
    tf = tf.tocoo()
    saturated = tf.data * (k1 + 1.0) / (tf.data + norm[tf.row])
    weighted = saturated * idf[tf.col]
    return sp.csc_matrix((weighted.astype(np.float32), (tf.row, tf.col)), shape=tf.shape)


def top_indices(scores: np.ndarray, n: int) -> np.ndarray:
    """Indices of the ``n`` highest positive scores, best first (ties broken by lower index)."""
    positive = np.flatnonzero(scores > 0)
    if positive.size == 0:
        return positive
    if positive.size > n:
        part = np.argpartition(-scores[positive], n - 1)[:n]
        positive = positive[part]
    order = np.lexsort((positive, -scores[positive]))
    return positive[order]
