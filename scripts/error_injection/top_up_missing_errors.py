"""
Fills in errors missing from a previous dataset_generation.py run.

Compares each story's actual per-category counts in an existing
``dataset_modifications.csv`` against the ``errors_per_story`` target,
selects fresh sentences (skipping any already recorded in the CSV) to cover
the shortfall, injects the missing errors via the DeepSeek API, splices them
into the already-modified books, and appends the new rows to the CSV.

Unlike a full dataset_generation.py run, this only calls the API for the
handful of chunks that are actually missing.
"""

import argparse
import csv
import logging
from collections import Counter
from pathlib import Path

from . import text_selection
from .dataset_generation import InjectedChunk
from .dataset_storage import (
    DATASET_CSV_NAME,
    ChunkLocationError,
    append_to_dataset_csv,
    apply_injected_chunks,
    modified_books_dir_name,
    normalize_whitespace,
)
from .error_injection import DeepSeekAPIError, ErrorInjectionRequest, ErrorType, inject_error
from .text_selection import TextChunk

logger = logging.getLogger(__name__)

# How many extra candidate sentences to try per missing error, in case some
# can't be spliced in (e.g. their context overlaps an edit from the original run).
_CANDIDATE_ATTEMPTS_PER_MISSING = 5


def _read_existing_rows(csv_path: Path) -> list[dict[str, str]]:
    """Read the existing dataset CSV rows.

    Raises:
        FileNotFoundError: If `csv_path` does not exist.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _compute_shortfall(
    existing_rows: list[dict[str, str]],
    story_names: list[str],
    errors_per_story: int,
) -> tuple[dict[str, dict[ErrorType, int]], dict[str, set[str]]]:
    """
    Determine how many errors are missing per (story, category).

    Returns:
        A tuple of:
        - missing_by_story: story -> {error_type: missing_count}, only for
          categories that are short of the target.
        - used_texts_by_story: story -> set of already-used original sentences
          (whitespace-normalized), used to avoid re-selecting them.
    """
    target_per_category = errors_per_story // len(ErrorType)

    counts: Counter[tuple[str, str]] = Counter()
    used_texts_by_story: dict[str, set[str]] = {}
    for row in existing_rows:
        counts[(row["story"], row["error_type"])] += 1
        used_texts_by_story.setdefault(row["story"], set()).add(row["original_text"])

    missing_by_story: dict[str, dict[ErrorType, int]] = {}
    for story_name in story_names:
        for error_type in ErrorType:
            missing = target_per_category - counts[(story_name, error_type.value)]
            if missing > 0:
                missing_by_story.setdefault(story_name, {})[error_type] = missing

    return missing_by_story, used_texts_by_story


def _inject_and_splice_replacement(
    chunk: TextChunk,
    error_type: ErrorType,
    modified_books_dir: Path,
    api_key: str | None,
) -> InjectedChunk | None:
    """
    Inject an error into `chunk` and splice the result into its chapter file.

    Returns:
        The applied :class:`InjectedChunk`, or None if the API call failed or
        the result could not be located in the already-modified chapter file
        (e.g. its context overlaps an edit from the original run).
    """
    request = ErrorInjectionRequest(
        text=chunk.text,
        error_type=error_type,
        previous=chunk.previous,
        follows=chunk.follows,
    )
    try:
        modified_text = inject_error(request, api_key=api_key)
    except DeepSeekAPIError as exc:
        logger.warning(
            "Skipping top-up candidate from '%s' (%s): %s", chunk.chapter, error_type.value, exc
        )
        return None

    injected_chunk = InjectedChunk(
        story=chunk.story,
        chapter=chunk.chapter,
        error_type=error_type,
        original_text=chunk.text,
        modified_text=modified_text,
        previous=chunk.previous,
        follows=chunk.follows,
    )
    try:
        apply_injected_chunks([injected_chunk], modified_books_dir)
    except ChunkLocationError as exc:
        logger.warning(
            "Could not splice replacement from '%s' (%s); trying a different sentence: %s",
            chunk.chapter,
            error_type.value,
            exc,
        )
        return None
    return injected_chunk


def top_up_missing_errors(
    errors_per_story: int,
    books_dir: Path | None = None,
    api_key: str | None = None,
) -> list[InjectedChunk]:
    """
    Fill in any errors missing from a previous run, without redoing the whole run.

    Args:
        errors_per_story: The errors-per-story value of the run to top up
            (identifies the existing ``modified_books_ai_<value>`` folder).
        books_dir: Optional override for the ``original_books`` directory.
        api_key: Optional DeepSeek API key override. Defaults to the
            DEEPSEEK_API_KEY environment variable.

    Returns:
        The list of newly injected chunks that were successfully applied
        and appended to the CSV. Empty if nothing was missing.

    Raises:
        FileNotFoundError: If the modified-books folder or its CSV don't exist.
    """
    modified_books_dir = text_selection.resolve_books_dir(books_dir).parent / modified_books_dir_name(
        errors_per_story
    )
    csv_path = modified_books_dir / DATASET_CSV_NAME

    existing_rows = _read_existing_rows(csv_path)
    story_names = text_selection.list_story_names(books_dir)
    missing_by_story, used_texts_by_story = _compute_shortfall(
        existing_rows, story_names, errors_per_story
    )

    if not missing_by_story:
        logger.info("No missing errors found for '%s'; nothing to top up.", modified_books_dir)
        return []

    new_chunks: list[InjectedChunk] = []
    for story_name, missing_by_category in missing_by_story.items():
        excluded_texts = used_texts_by_story.get(story_name, set())
        for error_type, missing_count in missing_by_category.items():
            logger.info(
                "Topping up %d '%s' error(s) for story '%s'",
                missing_count,
                error_type.value,
                story_name,
            )

            remaining = missing_count
            max_attempts = missing_count * _CANDIDATE_ATTEMPTS_PER_MISSING
            attempts = 0

            while remaining > 0 and attempts < max_attempts:
                candidates = text_selection.select_chunks_for_story(
                    story_name, remaining, books_dir=books_dir, excluded_texts=excluded_texts
                )
                if not candidates:
                    break  # no more usable sentences left in this story

                for chunk in candidates:
                    attempts += 1
                    excluded_texts.add(normalize_whitespace(chunk.text))

                    applied = _inject_and_splice_replacement(
                        chunk, error_type, modified_books_dir, api_key
                    )
                    if applied is not None:
                        new_chunks.append(applied)
                        remaining -= 1

                    if remaining <= 0 or attempts >= max_attempts:
                        break

            if remaining > 0:
                logger.warning(
                    "Still missing %d '%s' error(s) for story '%s' after %d attempt(s)",
                    remaining,
                    error_type.value,
                    story_name,
                    attempts,
                )

    if not new_chunks:
        logger.info("No replacement chunks were successfully injected.")
        return []

    append_to_dataset_csv(new_chunks, modified_books_dir)
    logger.info(
        "Topped up %d error(s) in '%s'",
        len(new_chunks),
        modified_books_dir,
    )
    return new_chunks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill in errors missing from a previous dataset_generation.py run."
    )
    parser.add_argument(
        "errors_per_story",
        type=int,
        help="The errors_per_story value of the run to top up (identifies modified_books_ai_<value>).",
    )
    parser.add_argument(
        "--books-dir",
        type=Path,
        default=None,
        help=(
            "Override for the original_books directory (default: resolved "
            "relative to the project root)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()

    try:
        top_up_missing_errors(args.errors_per_story, books_dir=args.books_dir)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
