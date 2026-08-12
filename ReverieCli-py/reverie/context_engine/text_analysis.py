"""Code-aware text analysis shared by the content index and the retriever.

Full-text engines such as `alibaba/zvec <https://github.com/alibaba/zvec>`_
model analysis as a *pipeline*: a tokenizer produces tokens, then token
filters normalise or expand them before anything reaches the posting lists.
The important property is that indexing and querying run the same pipeline, so
the two sides always agree on the vocabulary.

SQLite FTS5 only offers ``porter unicode61``, which splits on underscores but
keeps ``ModelAdmin`` as the single opaque token ``modeladmin``. The retriever's
query tokenizer *does* split camel case, so ``model`` and ``admin`` could never
match a symbol written that way -- an asymmetry that silently loses recall on
every camel-cased codebase. This module supplies the missing token filter: it
splits identifiers the same way the query side does, so the index can store the
sub-tokens alongside the original spelling.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Set

# ``HTTPServer`` -> ``HTTP Server`` (acronym run followed by a capitalised word)
_ACRONYM_BOUNDARY = re.compile(r"([A-Z]+)([A-Z][a-z])")
# ``getUser`` -> ``get User``
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
# ``utf8Codec`` -> ``utf 8 Codec`` so digit-suffixed names stay reachable
_DIGIT_BOUNDARY = re.compile(r"([A-Za-z])([0-9])")
_DIGIT_TRAILING_BOUNDARY = re.compile(r"([0-9])([A-Za-z])")

# Identifiers only: prose is already tokenised correctly by unicode61.
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

# Sub-tokens shorter than this are noise (``a``, ``of``) and blow up the index.
_MIN_SUBTOKEN_LENGTH = 3

# Very common code particles that would match nearly every document.
_SUBTOKEN_STOPWORDS = frozenset(
    {
        "get", "set", "the", "and", "for", "not", "new", "add", "def", "cls",
        "self", "this", "str", "int", "obj", "val", "var", "tmp", "arg", "args",
        "kwargs", "return", "class", "true", "false", "none", "null",
    }
)


def split_identifier(identifier: str) -> List[str]:
    """Split one identifier into its lowercase sub-tokens.

    ``ModelAdmin`` -> ``['model', 'admin']``; ``HTTPServerError`` ->
    ``['http', 'server', 'error']``; ``output_transaction`` ->
    ``['output', 'transaction']``. Returns an empty list when the identifier
    has no internal structure, so callers can cheaply skip simple names.
    """
    text = str(identifier or "")
    if not text:
        return []
    text = _ACRONYM_BOUNDARY.sub(r"\1 \2", text)
    text = _CAMEL_BOUNDARY.sub(r"\1 \2", text)
    text = _DIGIT_BOUNDARY.sub(r"\1 \2", text)
    text = _DIGIT_TRAILING_BOUNDARY.sub(r"\1 \2", text)
    parts = [part.lower() for part in text.replace("_", " ").split()]
    if len(parts) < 2:
        return []
    return parts


def _is_compound(identifier: str) -> bool:
    """Report whether FTS5 would store this identifier as one opaque token.

    unicode61 already splits on underscores, so only camel case, acronym runs
    and digit boundaries need help from this filter.
    """
    return bool(
        _CAMEL_BOUNDARY.search(identifier)
        or _ACRONYM_BOUNDARY.search(identifier)
        or _DIGIT_BOUNDARY.search(identifier)
    )


def subword_terms(text: str, *, limit: int = 512) -> List[str]:
    """Collect the distinct sub-tokens hidden inside a document's identifiers.

    Only compound identifiers contribute, and each sub-token is emitted once
    per document rather than once per occurrence: the goal is to make the term
    *reachable*, while leaving the original spellings to carry term frequency.
    That keeps index growth proportional to a file's distinct vocabulary
    instead of its length.
    """
    if not text:
        return []
    collected: List[str] = []
    seen: Set[str] = set()
    for identifier in _IDENTIFIER_PATTERN.findall(text):
        if not _is_compound(identifier):
            continue
        for part in split_identifier(identifier):
            if (
                len(part) < _MIN_SUBTOKEN_LENGTH
                or part in _SUBTOKEN_STOPWORDS
                or part in seen
            ):
                continue
            seen.add(part)
            collected.append(part)
            if len(collected) >= limit:
                return collected
    return collected


def subword_expansion(*values: str, limit: int = 512) -> str:
    """Render :func:`subword_terms` for one or more fields as indexable text."""
    joined = "\n".join(str(value or "") for value in values if value)
    terms = subword_terms(joined, limit=limit)
    return " ".join(terms)


def expand_identifier_text(text: str) -> str:
    """Return ``text`` followed by its sub-token expansion.

    Used for short fields (symbol names) where inlining the expansion keeps the
    original spelling adjacent to its parts.
    """
    expansion = subword_expansion(text)
    if not expansion:
        return str(text or "")
    return f"{text} {expansion}"


def unique_terms(terms: Iterable[str]) -> List[str]:
    """Order-preserving de-duplication helper for token lists."""
    seen: Set[str] = set()
    result: List[str] = []
    for term in terms:
        token = str(term or "").strip().lower()
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result
