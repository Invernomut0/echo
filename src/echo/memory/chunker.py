"""Sentence-aware text chunker with sliding overlap for embedding pipelines.

Short texts (≤ CHUNK_MIN_LEN chars) are kept as a single chunk so the
overhead of splitting is never paid when it isn't needed.  Longer texts are
split at sentence boundaries into overlapping windows so that no detail is
compressed away into a single high-dimensional vector.

Public surface
--------------
chunk_text(text, ...) -> list[str]
    Split *text* into overlapping chunks.

chunk_ids(entry_id, n) -> list[str]
    Derive ChromaDB IDs for *n* chunks.  Single-chunk entries keep the bare
    ``entry_id`` for full backward-compatibility with existing ChromaDB data.

memory_id_from_chunk_id(chunk_id) -> str
    Recover the parent memory ID from any chunk ID (handles both old bare IDs
    and new ``{id}__chunk_{nn}`` IDs).
"""

from __future__ import annotations

import re

# ── Default parameters ────────────────────────────────────────────────────────

#: Texts at or below this length are stored as a single vector — no chunking.
CHUNK_MIN_LEN: int = 300

#: Target maximum *characters* per chunk (roughly ≈ 200–300 tokens for most
#: embedding models that cap at 512 tokens).
CHUNK_SIZE: int = 512

#: Characters of the previous chunk carried into the start of the next one.
#: Preserves sentence context across boundaries without large duplication.
CHUNK_OVERLAP: int = 64


# ── Public helpers ─────────────────────────────────────────────────────────────


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    min_len: int = CHUNK_MIN_LEN,
) -> list[str]:
    """Return a list of overlapping text chunks.

    Rules
    -----
    * ``len(text) <= min_len``  →  ``[text]`` (no overhead for short memories).
    * Otherwise split at sentence boundaries (``. ! ? \\n``) and aggregate into
      windows ≤ *chunk_size* chars.  Each new window starts with the last
      *overlap* characters of the previous window to preserve boundary context.

    The returned list is never empty (always ≥ 1 element).
    """
    text = text.strip()
    if not text:
        return [""]

    if len(text) <= min_len:
        return [text]

    sentences = _split_sentences(text)

    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        candidate = (current + " " + sentence).strip() if current else sentence

        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
                # Seed next window with the tail of the finished chunk.
                tail = current[-overlap:] if len(current) > overlap else current
                current = (tail + " " + sentence).strip()
            else:
                # Single sentence already exceeds chunk_size — hard character-split.
                for piece in _hard_split(sentence, chunk_size, overlap):
                    chunks.append(piece)
                current = ""

    if current:
        chunks.append(current)

    # Safety net — should never trigger, but keeps contract.
    return chunks if chunks else [text]


def chunk_ids(entry_id: str, n_chunks: int) -> list[str]:
    """Return ChromaDB IDs for *n_chunks* chunks of *entry_id*.

    A single-chunk entry keeps the bare ``entry_id`` so that existing
    ChromaDB data written before chunking was introduced remains valid.
    """
    if n_chunks == 1:
        return [entry_id]
    return [f"{entry_id}__chunk_{i:02d}" for i in range(n_chunks)]


def memory_id_from_chunk_id(chunk_id: str) -> str:
    """Return the parent memory ID for any ChromaDB entry ID.

    Examples::

        memory_id_from_chunk_id("abc-123")              == "abc-123"
        memory_id_from_chunk_id("abc-123__chunk_00")    == "abc-123"
        memory_id_from_chunk_id("abc-123__chunk_07")    == "abc-123"
    """
    idx = chunk_id.find("__chunk_")
    return chunk_id[:idx] if idx != -1 else chunk_id


# ── Internal helpers ──────────────────────────────────────────────────────────

# Split AFTER a sentence-terminating character followed by whitespace or a
# newline sequence.  Keeps the terminator attached to the preceding sentence.
_SENTENCE_SPLIT: re.Pattern[str] = re.compile(r"(?<=[.!?])\s+|\n+")


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def _hard_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Character-level fallback for single sentences that exceed *chunk_size*."""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        pieces.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return pieces
