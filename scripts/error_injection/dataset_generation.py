"""
Command-line pipeline that selects text chunks and injects narrative errors.

For every story, selects a fixed number of text chunks and injects an equal
share of each :class:`ErrorType` category into that story's chunks, so errors
are spread evenly across both stories and categories. Organizing the results
into output folders is a later, separate step and is out of scope for this
module.
"""

import argparse
import logging
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import text_selection
from .dataset_storage import ChunkLocationError, store_dataset
from .error_injection import DeepSeekAPIError, ErrorInjectionRequest, ErrorType, inject_error
from .telegram_notifier import (
    TelegramNotificationError,
    build_end_message,
    build_failure_message,
    build_start_message,
    send_telegram_message,
)
from .text_selection import TextChunk

logger = logging.getLogger(__name__)

# HTTP statuses that indicate an account-level problem (bad key, no balance,
# access denied) rather than a per-chunk issue; retrying other chunks would
# just fail the same way, so these abort the whole run instead of being skipped.
_FATAL_HTTP_STATUS_CODES = {401, 402, 403}


@dataclass(frozen=True)
class InjectedChunk:
    """A text chunk after a narrative error has been injected into it."""

    story: str
    chapter: str
    error_type: ErrorType
    original_text: str
    modified_text: str
    previous: str
    follows: str


def _build_category_assignments(total_errors: int) -> list[ErrorType]:
    """Build a shuffled list assigning each error slot an equal-share category."""
    error_types = list(ErrorType)
    errors_per_category = total_errors // len(error_types)
    assignments = [
        error_type for error_type in error_types for _ in range(errors_per_category)
    ]
    random.shuffle(assignments)
    return assignments


def _group_chunks_by_story(chunks: list[TextChunk]) -> dict[str, list[TextChunk]]:
    """Group chunks by their story name."""
    grouped: dict[str, list[TextChunk]] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.story, []).append(chunk)
    return grouped


def _build_category_count_lines(injected_chunks: list[InjectedChunk]) -> list[str]:
    """Build one '<story>: <category>=<count>, ...' summary line per story."""
    counts_by_story: dict[str, Counter] = {}
    for chunk in injected_chunks:
        counts_by_story.setdefault(chunk.story, Counter())[chunk.error_type] += 1

    lines = []
    for story_name, counts in sorted(counts_by_story.items()):
        breakdown = ", ".join(f"{error_type.value}={counts[error_type]}" for error_type in ErrorType)
        lines.append(f"{story_name}: {breakdown}")
    return lines


def _log_category_counts(injected_chunks: list[InjectedChunk]) -> None:
    """Log the per-category error count for each story."""
    for line in _build_category_count_lines(injected_chunks):
        logger.info("%s", line)


def generate_injected_chunks(
    errors_per_story: int,
    books_dir: Path | None = None,
    api_key: str | None = None,
) -> list[InjectedChunk]:
    """
    Select text chunks and inject narrative errors into every story.

    Each story contributes exactly ``errors_per_story`` chunks, and within
    each story that count is split evenly across every :class:`ErrorType`
    category. The overall total is ``errors_per_story * number_of_stories``.

    Args:
        errors_per_story: Number of errors to introduce per story. Must be a
            positive multiple of the number of error categories (currently 5).
        books_dir: Optional override for the ``original_books`` directory.
            Defaults to the dataset location resolved by :mod:`text_selection`.
        api_key: Optional DeepSeek API key override. Defaults to the
            DEEPSEEK_API_KEY environment variable.

    Returns:
        A list of :class:`InjectedChunk`, one per successfully injected error.
        Chunks whose API call fails are skipped and logged as warnings.

    Raises:
        ValueError: If ``errors_per_story`` is not a positive multiple of the
            number of error categories.
        RuntimeError: If any story yields fewer usable chunks than
            ``errors_per_story``.
    """
    num_categories = len(ErrorType)
    if errors_per_story < 1 or errors_per_story % num_categories != 0:
        raise ValueError(
            f"errors_per_story must be a positive multiple of {num_categories} "
            f"(one per error category), got {errors_per_story}"
        )

    story_names = text_selection.list_story_names(books_dir)
    if not story_names:
        raise RuntimeError("No story directories found; cannot select text chunks.")

    chunks_by_story = _group_chunks_by_story(
        text_selection.selectChunks(errors_per_story, books_dir=books_dir)
    )

    total_chunks = errors_per_story * len(story_names)
    processed_count = 0

    injected_chunks: list[InjectedChunk] = []
    for story_name in story_names:
        story_chunks = chunks_by_story.get(story_name, [])
        if len(story_chunks) < errors_per_story:
            raise RuntimeError(
                f"Story '{story_name}' only yielded {len(story_chunks)} usable "
                f"chunks, need {errors_per_story}."
            )

        category_assignments = _build_category_assignments(errors_per_story)
        for chunk, error_type in zip(story_chunks, category_assignments):
            remaining = total_chunks - processed_count
            percent_complete = (processed_count / total_chunks) * 100
            logger.info(
                "Requesting '%s' error injection (%d chars) for %s chapter %s, "
                "%d/%d chunks remaining, %.0f%% complete",
                error_type.value,
                len(chunk.text),
                chunk.story,
                Path(chunk.chapter).stem,
                remaining,
                total_chunks,
                percent_complete,
            )
            # logger.info("Original text: %s", chunk.text)
            processed_count += 1

            request = ErrorInjectionRequest(
                text=chunk.text,
                error_type=error_type,
                previous=chunk.previous,
                follows=chunk.follows,
            )
            try:
                modified_text = inject_error(request, api_key=api_key)
            except DeepSeekAPIError as exc:
                if exc.status_code in _FATAL_HTTP_STATUS_CODES:
                    raise RuntimeError(
                        f"Aborting: DeepSeek API call failed with a non-retryable "
                        f"error (HTTP {exc.status_code}): {exc}"
                    ) from exc
                logger.warning(
                    "Skipping chunk from '%s' (%s): %s", chunk.chapter, error_type.value, exc
                )
                continue

            # logger.info("Response: %s", modified_text)

            injected_chunks.append(
                InjectedChunk(
                    story=chunk.story,
                    chapter=chunk.chapter,
                    error_type=error_type,
                    original_text=chunk.text,
                    modified_text=modified_text,
                    previous=chunk.previous,
                    follows=chunk.follows,
                )
            )

    _log_category_counts(injected_chunks)
    target_total = errors_per_story * len(story_names)
    if len(injected_chunks) < target_total:
        logger.error(
            "Only %d/%d requested errors were successfully injected; %d chunk(s) "
            "permanently failed (see 'Skipping chunk' warnings above for details).",
            len(injected_chunks),
            target_total,
            target_total - len(injected_chunks),
        )
    else:
        logger.info("Total errors injected: %d (target: %d)", len(injected_chunks), target_total)
    return injected_chunks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select text chunks and inject narrative errors into them."
    )
    parser.add_argument(
        "errors_per_story",
        type=int,
        help=(
            "Number of errors to inject per story; must be a multiple of the "
            "number of error categories (5). Total errors = this value "
            "multiplied by the number of stories."
        ),
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
        num_stories = len(text_selection.list_story_names(args.books_dir))

        try:
            send_telegram_message(build_start_message(num_stories, args.errors_per_story))
        except TelegramNotificationError as exc:
            logger.warning("Could not send Telegram start notification: %s", exc)

        injected_chunks = generate_injected_chunks(args.errors_per_story, books_dir=args.books_dir)
        logger.info("Successfully injected %d errors", len(injected_chunks))

        modified_books_dir = store_dataset(
            args.errors_per_story, injected_chunks, books_dir=args.books_dir
        )
        logger.info("Modified books stored in '%s'", modified_books_dir)

        summary_lines = _build_category_count_lines(injected_chunks)
        try:
            send_telegram_message(build_end_message(num_stories, args.errors_per_story, summary_lines))
        except TelegramNotificationError as exc:
            logger.warning("Could not send Telegram end notification: %s", exc)

    except (ValueError, RuntimeError, FileNotFoundError, FileExistsError, OSError, ChunkLocationError) as exc:
        logger.error("%s", exc)
        try:
            send_telegram_message(build_failure_message(str(exc)))
        except TelegramNotificationError as telegram_exc:
            logger.warning("Could not send Telegram failure notification: %s", telegram_exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
