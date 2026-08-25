"""
Copies the original books dataset and writes injected errors into it.

Given a list of ``InjectedChunk`` objects (see :mod:`dataset_generation`),
this module creates a full copy of the original_books dataset, splices each
injected chunk's modified text into the matching chapter file (located via
its surrounding sentence context), and writes a CSV summary of every applied
modification.
"""

import csv
import dataclasses
import logging
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from . import text_selection

if TYPE_CHECKING:
    # Avoids a runtime circular import: dataset_generation imports this module
    # to store its results, so this module must not import it back at runtime.
    from .dataset_generation import InjectedChunk

logger = logging.getLogger(__name__)

DATASET_CSV_NAME = "dataset_modifications.csv"
CSV_FIELDNAMES = ["story", "chapter", "error_type", "original_text", "modified_text"]


class ChunkLocationError(RuntimeError):
    """Raised when a chunk's text cannot be located in its chapter file."""


def modified_books_dir_name(errors_per_story: int) -> str:
    """Return the folder name for a modified-books copy with this many errors per story."""
    return f"modified_books_ai_{errors_per_story}"


def _flexible_pattern(text: str) -> str:
    """Escape `text` for regex use, letting single spaces match any whitespace run.

    Chunk text is built by joining sentences with a single literal space, but
    the source file may separate them with a line-wrap or other whitespace.
    Each space-delimited token is escaped individually (rather than escaping
    the whole string first) because ``re.escape`` also escapes plain spaces,
    which would prevent a simple space-to-``\\s+`` substitution afterwards.
    """
    return r"\s+".join(re.escape(token) for token in text.split(" "))


def normalize_whitespace(text: str) -> str:
    """Collapse any run of whitespace (including embedded line-wraps) to a single space."""
    return re.sub(r"\s+", " ", text).strip()


def _preview(text: str, limit: int = 150) -> str:
    """Return a single-line, length-limited preview of `text` for log messages."""
    normalized = normalize_whitespace(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "…"


def _build_locator_pattern(chunk: "InjectedChunk") -> re.Pattern[str]:
    """Build a regex locating `chunk.original_text`, anchored by its context.

    The original text itself is captured in group 1 so callers can splice in
    the replacement without disturbing the untouched surrounding text.
    """
    parts = []
    if chunk.previous:
        parts.append(_flexible_pattern(chunk.previous))
        parts.append(r"\s+")
    parts.append(f"({_flexible_pattern(chunk.original_text)})")
    if chunk.follows:
        parts.append(r"\s+")
        parts.append(_flexible_pattern(chunk.follows))
    return re.compile("".join(parts))


def _apply_chunk_to_content(content: str, chunk: "InjectedChunk") -> str | None:
    """Replace `chunk.original_text` in `content` with `chunk.modified_text`.

    Returns the updated content, or None if the chunk could not be located.
    """
    match = _build_locator_pattern(chunk).search(content)
    if match is None:
        return None
    return content[: match.start(1)] + chunk.modified_text + content[match.end(1):]


def _resolve_context(context_text: str, prior_chunks_in_file: list["InjectedChunk"]) -> str:
    """Return the text that now stands where `context_text` used to be.

    If an earlier chunk in the same file already replaced the sentences that
    `context_text` refers to, that chunk's ``original_text`` will no longer
    appear in the file verbatim. In that case, return the chunk's
    ``modified_text`` instead, since that is what is actually adjacent to the
    current chunk now. Returns `context_text` unchanged if no such overlap is found.
    """
    if not context_text:
        return context_text

    normalized_context = normalize_whitespace(context_text)
    for prior_chunk in prior_chunks_in_file:
        if normalized_context in normalize_whitespace(prior_chunk.original_text):
            return prior_chunk.modified_text
    return context_text


def _apply_chunk_with_fallback(
    content: str,
    chunk: "InjectedChunk",
    prior_chunks_in_file: list["InjectedChunk"],
    chapter_path: Path,
) -> str:
    """
    Locate and replace `chunk.original_text` in `content`, retrying with resolved context.

    If the chunk's ``previous``/``follows`` sentences were themselves swallowed
    by an earlier chunk's rewrite in the same file, retries using that
    chunk's ``modified_text`` as the context instead.

    Raises:
        ChunkLocationError: If the chunk cannot be located even after the retry.
    """
    updated_content = _apply_chunk_to_content(content, chunk)
    if updated_content is not None:
        return updated_content

    resolved_previous = _resolve_context(chunk.previous, prior_chunks_in_file)
    resolved_follows = _resolve_context(chunk.follows, prior_chunks_in_file)
    if resolved_previous != chunk.previous or resolved_follows != chunk.follows:
        resolved_chunk = dataclasses.replace(
            chunk, previous=resolved_previous, follows=resolved_follows
        )
        updated_content = _apply_chunk_to_content(content, resolved_chunk)
        if updated_content is not None:
            logger.info(
                "Located chunk in '%s' (%s) after resolving context overlapping "
                "with a previously applied injection",
                chapter_path,
                chunk.error_type.value,
            )
            return updated_content

    raise ChunkLocationError(
        f"Could not locate chunk text in '{chapter_path}' ({chunk.error_type.value}), "
        "even after resolving context against previously applied injections.\n"
        f"  previous: {_preview(chunk.previous)}\n"
        f"  original_text: {_preview(chunk.original_text)}\n"
        f"  follows: {_preview(chunk.follows)}"
    )


def copy_original_books(errors_per_story: int, books_dir: Path | None = None) -> Path:
    """
    Create a fresh copy of the original_books dataset for error injection.

    Returns:
        Path to the new ``modified_books_ai_<errors_per_story>`` directory.

    Raises:
        FileExistsError: If the destination directory already exists.
    """
    source_dir = text_selection.resolve_books_dir(books_dir)
    destination_dir = source_dir.parent / modified_books_dir_name(errors_per_story)

    try:
        shutil.copytree(source_dir, destination_dir)
    except FileExistsError as exc:
        raise FileExistsError(
            f"Destination directory already exists: {destination_dir}. "
            "Remove it or choose a different errors_per_story value."
        ) from exc

    logger.info("Copied '%s' to '%s'", source_dir, destination_dir)
    return destination_dir


def apply_injected_chunks(
    injected_chunks: list["InjectedChunk"], modified_books_dir: Path
) -> list["InjectedChunk"]:
    """
    Splice every injected chunk's modified text into its chapter file.

    If a chunk's ``previous``/``follows`` context was itself rewritten by an
    earlier chunk applied to the same file, the search retries using that
    chunk's modified text instead of the stale original context.

    Returns:
        The chunks that were successfully located and applied.

    Raises:
        ChunkLocationError: If a chunk cannot be located even after retrying
            with resolved context.
    """
    chunks_by_file: dict[Path, list["InjectedChunk"]] = {}
    for chunk in injected_chunks:
        chapter_path = modified_books_dir / chunk.chapter
        chunks_by_file.setdefault(chapter_path, []).append(chunk)

    applied_chunks: list["InjectedChunk"] = []
    for chapter_path, chunks in chunks_by_file.items():
        try:
            content = chapter_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.error("Could not read '%s': %s", chapter_path, exc)
            continue

        applied_in_file: list["InjectedChunk"] = []
        for chunk in chunks:
            content = _apply_chunk_with_fallback(content, chunk, applied_in_file, chapter_path)
            applied_in_file.append(chunk)

        try:
            chapter_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            logger.error("Could not write '%s': %s", chapter_path, exc)
            continue

        applied_chunks.extend(applied_in_file)

    return applied_chunks


def _write_csv_rows(writer: "csv.DictWriter[str]", injected_chunks: list["InjectedChunk"]) -> None:
    """Write one CSV row per injected chunk using the shared column format."""
    for chunk in injected_chunks:
        writer.writerow(
            {
                "story": chunk.story,
                "chapter": chunk.chapter,
                "error_type": chunk.error_type.value,
                "original_text": normalize_whitespace(chunk.original_text),
                "modified_text": normalize_whitespace(chunk.modified_text),
            }
        )


def write_dataset_csv(injected_chunks: list["InjectedChunk"], modified_books_dir: Path) -> Path:
    """Write a CSV summary (one row per applied injection) to the modified books folder."""
    csv_path = modified_books_dir / DATASET_CSV_NAME
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        _write_csv_rows(writer, injected_chunks)

    logger.info("Wrote %d modification(s) to '%s'", len(injected_chunks), csv_path)
    return csv_path


def append_to_dataset_csv(injected_chunks: list["InjectedChunk"], modified_books_dir: Path) -> Path:
    """Append rows for newly injected chunks to an existing (or new) dataset CSV."""
    csv_path = modified_books_dir / DATASET_CSV_NAME
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        _write_csv_rows(writer, injected_chunks)

    logger.info("Appended %d modification(s) to '%s'", len(injected_chunks), csv_path)
    return csv_path


def store_dataset(
    errors_per_story: int,
    injected_chunks: list["InjectedChunk"],
    books_dir: Path | None = None,
) -> Path:
    """
    Copy the original books, splice in the injected errors, and write the CSV summary.

    Returns:
        Path to the ``modified_books_ai_<errors_per_story>`` directory.
    """
    modified_books_dir = copy_original_books(errors_per_story, books_dir)
    applied_chunks = apply_injected_chunks(injected_chunks, modified_books_dir)
    write_dataset_csv(applied_chunks, modified_books_dir)
    return modified_books_dir
