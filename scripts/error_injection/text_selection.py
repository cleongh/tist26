"""
Random text chunk selection from narrative book datasets.

Selects a single full sentence (at least a minimum word count) from chapter
files, each accompanied by up to four sentences of preceding and following
context. Chunks at the very start or end of a chapter may have empty context
on that side, which callers can use to detect chapter boundaries.
"""

import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolved relative to this file: scripts/error_injection/ -> scripts/ -> project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ORIGINAL_BOOKS_DIR = (
    _PROJECT_ROOT.parent / "narrative_coherence_datasets" / "original_books"
)

_CORE_MIN_WORDS = 5
_CONTEXT_SENTENCES = 4

# Heuristic sentence boundary: .!? followed by whitespace and an uppercase letter.
# May misfire on abbreviations such as Mr., Mrs., Dr. — acceptable for chunk selection.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"])")


@dataclass(frozen=True)
class TextChunk:
    story: str     # story name, e.g. "Harry Potter"
    chapter: str   # "<story>/<chapter_file>", e.g. "Harry Potter/003.txt"
    text: str      # the single selected sentence (at least _CORE_MIN_WORDS words)
    previous: str  # up to four sentences before the chunk; empty at chapter start
    follows: str   # up to four sentences after the chunk; empty at chapter end


def resolve_books_dir(books_dir: Path | None = None) -> Path:
    """Return `books_dir` if given, otherwise the default original_books location."""
    return books_dir if books_dir is not None else _ORIGINAL_BOOKS_DIR


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_BOUNDARY.split(text.strip())
    return [s.strip() for s in parts if s.strip()]


def _word_count(sentence: str) -> int:
    return len(sentence.split())


def _load_chapter_sentences(path: Path) -> list[str] | None:
    """Return sentences from a chapter file, or None if none are usable."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None

    sentences = split_sentences(content)
    if not any(_word_count(s) >= _CORE_MIN_WORDS for s in sentences):
        logger.debug(
            "Skipping %s — no sentence with at least %d words",
            path.name,
            _CORE_MIN_WORDS,
        )
        return None
    return sentences


def _pick_chunk(
    sentences: list[str],
    story_name: str,
    chapter_name: str,
) -> tuple[TextChunk, tuple[int, int]] | None:
    """Pick one random single-sentence chunk (>= _CORE_MIN_WORDS words) with context.

    The chunk may sit at the very first or last sentence of the chapter, in
    which case ``previous`` or ``follows`` is an empty string, signaling a
    chapter boundary.

    Returns:
        The chunk, and the (previous_start, follows_end) sentence-index
        range it occupies, including its context buffer. Callers use this
        range to avoid picking another chunk that overlaps it. Returns None
        if no sentence meets the minimum word count.
    """
    qualifying_indices = [
        i for i, s in enumerate(sentences) if _word_count(s) >= _CORE_MIN_WORDS
    ]
    if not qualifying_indices:
        return None

    start_idx = random.choice(qualifying_indices)
    end_idx = start_idx + 1
    total_sentences = len(sentences)

    previous_start = max(0, start_idx - _CONTEXT_SENTENCES)
    follows_end = min(total_sentences, end_idx + _CONTEXT_SENTENCES)

    previous = " ".join(sentences[previous_start:start_idx])
    text = sentences[start_idx]
    follows = " ".join(sentences[end_idx:follows_end])

    chunk = TextChunk(
        story=story_name,
        chapter=f"{story_name}/{chapter_name}",
        text=text,
        previous=previous,
        follows=follows,
    )
    return chunk, (previous_start, follows_end)


def _range_indices(sentence_range: tuple[int, int]) -> set[int]:
    """Return the set of sentence indices covered by a (start, end) range."""
    return set(range(sentence_range[0], sentence_range[1]))


def _normalize_for_dedup(text: str) -> str:
    """Collapse whitespace so duplicate-sentence comparisons ignore line-wrap artifacts."""
    return " ".join(text.split())


def list_story_names(books_dir: Path | None = None) -> list[str]:
    """Return the sorted names of story directories under the books directory."""
    original_books_dir = resolve_books_dir(books_dir)
    if not original_books_dir.exists():
        raise FileNotFoundError(
            f"Original books directory not found: {original_books_dir}"
        )
    return sorted(p.name for p in original_books_dir.iterdir() if p.is_dir())


def select_chunks_for_story(
    story_name: str,
    num_chunks: int,
    books_dir: Path | None = None,
    excluded_texts: set[str] | None = None,
) -> list[TextChunk]:
    """
    Select random text chunks from a single named story.

    Args:
        story_name: The story directory name (e.g. "Goosebumps").
        num_chunks: Number of chunks to select (must be >= 1).
        books_dir: Optional override for the ``original_books`` directory.
        excluded_texts: Optional set of sentence texts to never select, e.g.
            sentences already used by a prior run (whitespace-insensitive).

    Returns:
        Up to ``num_chunks`` :class:`TextChunk` objects for that story.

    Raises:
        ValueError: If ``num_chunks`` is less than 1.
        FileNotFoundError: If the ``original_books`` directory or the story
            directory within it does not exist.
    """
    if num_chunks < 1:
        raise ValueError(f"num_chunks must be at least 1, got {num_chunks}")

    original_books_dir = resolve_books_dir(books_dir)
    if not original_books_dir.exists():
        raise FileNotFoundError(
            f"Original books directory not found: {original_books_dir}"
        )

    story_dir = original_books_dir / story_name
    if not story_dir.is_dir():
        raise FileNotFoundError(f"Story directory not found: {story_dir}")

    logger.info("Selecting %d chunk(s) from '%s'", num_chunks, story_name)
    return _select_chunks_for_story(story_dir, num_chunks, excluded_texts=excluded_texts)


def _select_chunks_for_story(
    story_dir: Path,
    num_chunks: int,
    excluded_texts: set[str] | None = None,
) -> list[TextChunk]:
    chapter_files = sorted(story_dir.glob("*.txt"))
    if not chapter_files:
        logger.warning("No chapter files found in %s", story_dir)
        return []

    valid_chapters: list[tuple[str, list[str]]] = []
    for chapter_path in chapter_files:
        sentences = _load_chapter_sentences(chapter_path)
        if sentences is not None:
            valid_chapters.append((chapter_path.name, sentences))

    if not valid_chapters:
        logger.warning("No usable chapters in story '%s'", story_dir.name)
        return []

    excluded_normalized = {_normalize_for_dedup(t) for t in (excluded_texts or ())}

    chunks: list[TextChunk] = []
    used_indices_by_chapter: dict[str, set[int]] = {}
    # Higher than num_chunks * 10 since rejected-overlap attempts consume attempts too.
    max_attempts = num_chunks * 20

    for _ in range(max_attempts):
        if len(chunks) >= num_chunks:
            break
        chapter_name, sentences = random.choice(valid_chapters)
        result = _pick_chunk(sentences, story_dir.name, chapter_name)
        if result is None:
            continue  # no sentence in this chapter meets the word-count minimum
        candidate, candidate_range = result

        if _normalize_for_dedup(candidate.text) in excluded_normalized:
            continue  # already used in a previous selection/run; try another sentence

        used_indices = used_indices_by_chapter.setdefault(chapter_name, set())
        candidate_indices = _range_indices(candidate_range)
        if candidate_indices & used_indices:
            continue  # a sentence here was already part of a previous selection; try again

        chunks.append(candidate)
        used_indices.update(candidate_indices)

    if len(chunks) < num_chunks:
        logger.warning(
            "Selected only %d/%d chunks for story '%s'",
            len(chunks),
            num_chunks,
            story_dir.name,
        )

    return chunks


def selectChunks(
    num_chunks: int,
    books_dir: Path | None = None,
    excluded_texts: set[str] | None = None,
) -> list[TextChunk]:
    """
    Select random text chunks from every story in the dataset.

    Iterates over all story directories under ``original_books`` and selects
    ``num_chunks`` chunks per story. Each chunk is a single sentence of at
    least ``_CORE_MIN_WORDS`` words, with up to four sentences of preceding
    and following context. Chunks at the very start or end of a chapter have
    an empty ``previous`` or ``follows`` value, respectively.

    Args:
        num_chunks: Number of chunks to select per story (must be >= 1).
        books_dir: Optional override for the ``original_books`` directory.
            Defaults to the dataset location resolved relative to the project.
        excluded_texts: Optional set of sentence texts to never select, e.g.
            sentences already used by a prior run (whitespace-insensitive).

    Returns:
        A flat list of :class:`TextChunk` objects across all stories.

    Raises:
        ValueError: If ``num_chunks`` is less than 1.
        FileNotFoundError: If the ``original_books`` directory does not exist.
    """
    if num_chunks < 1:
        raise ValueError(f"num_chunks must be at least 1, got {num_chunks}")

    original_books_dir = resolve_books_dir(books_dir)
    if not original_books_dir.exists():
        raise FileNotFoundError(
            f"Original books directory not found: {original_books_dir}"
        )

    story_dirs = sorted(p for p in original_books_dir.iterdir() if p.is_dir())
    if not story_dirs:
        logger.warning("No story directories found in %s", original_books_dir)
        return []

    all_chunks: list[TextChunk] = []
    for story_dir in story_dirs:
        logger.info("Selecting %d chunk(s) from '%s'", num_chunks, story_dir.name)
        all_chunks.extend(
            _select_chunks_for_story(story_dir, num_chunks, excluded_texts=excluded_texts)
        )

    return all_chunks


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    chunks = selectChunks(num_chunks=2)
    for chunk in chunks:
        print(f"\n=== {chunk.chapter} ===")
        print(f"[previous] {chunk.previous}")
        print(f"[text]     {chunk.text}")
        print(f"[follows]  {chunk.follows}")
