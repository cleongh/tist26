#!/usr/bin/env python3
"""
Merge Experiment Extractions

Combines step2_extractions.jsonl (and the sibling debug_logs/*.jsonl files)
from multiple separate experiment runs into a single output experiment
directory, without needing to re-run extraction.

This is intended for cases where a single extraction run couldn't be
completed in one pass (e.g. ran out of API credits partway through) and had
to be split into multiple runs under different --experiment-name values.
Each such run overwrites step2_extractions.jsonl at startup (see
run_step2_engine in scripts/experiment/runners.py), so partial runs must be
merged after the fact rather than concatenated by re-running with the same
experiment name.

Usage:
    python scripts/merge_experiment_extractions.py --experiment-names exp1 exp2 exp3 --output-name merged_exp
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.state.config import EXPERIMENTS_DIR

# JSONL files where each line is an independent per-chapter record; safe to
# concatenate across experiment directories. Relative to the experiment dir.
MERGEABLE_JSONL_FILES = [
    "step2_extractions.jsonl",
    "debug_logs/step2_events_log.jsonl",
    "debug_logs/step2_alias_conflicts.jsonl",
    "debug_logs/step2_item_stats.jsonl",
    "debug_logs/step2_extraction_diagnostics.jsonl",
]

# Key fields used to detect duplicate chapter records in step2_extractions.jsonl
# (e.g. if the same story/variant/chapter was accidentally extracted in two
# of the merged runs).
DEDUPE_KEY_FIELDS = ("story", "variant", "chapter")


def load_jsonl(path: Path) -> List[Dict]:
    """Load a JSONL file into a list of dicts, skipping malformed lines."""
    records = []
    if not path.exists():
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  WARNING: skipping malformed line {line_num} in {path}: {e}")
    return records


def write_jsonl(path: Path, records: List[Dict]) -> None:
    """Write a list of dicts to a JSONL file, one JSON object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_key(record: Dict) -> Tuple:
    """Build the dedupe key for a step2_extractions.jsonl record."""
    return tuple(record.get(field) for field in DEDUPE_KEY_FIELDS)


def merge_jsonl_file(
    relative_path: str,
    source_dirs: List[Path],
    output_dir: Path,
    dedupe: bool,
) -> None:
    """Merge one relative JSONL file across all source experiment dirs."""
    merged: List[Dict] = []
    seen_keys: Dict[Tuple, str] = {}  # key -> source dir name (for dedupe warnings)
    total_before_dedupe = 0

    for source_dir in source_dirs:
        source_path = source_dir / relative_path
        records = load_jsonl(source_path)
        total_before_dedupe += len(records)

        if not dedupe:
            merged.extend(records)
            continue

        for record in records:
            key = record_key(record)
            if key in seen_keys:
                print(
                    f"  WARNING: duplicate record {key} in {relative_path} "
                    f"(already seen from '{seen_keys[key]}', now also in "
                    f"'{source_dir.name}') — keeping the first occurrence"
                )
                continue
            seen_keys[key] = source_dir.name
            merged.append(record)

    output_path = output_dir / relative_path
    write_jsonl(output_path, merged)

    dropped = total_before_dedupe - len(merged)
    suffix = f" ({dropped} duplicate(s) dropped)" if dropped else ""
    print(f"  {relative_path}: {len(merged)} records written{suffix}")


def merge_experiments(
    experiment_names: List[str],
    output_name: str,
    dedupe: bool,
    overwrite: bool,
) -> Path:
    """Merge multiple experiment directories into one output directory."""
    source_dirs = []
    for name in experiment_names:
        source_dir = EXPERIMENTS_DIR / name
        if not source_dir.exists():
            raise ValueError(f"Experiment directory not found: {source_dir}")
        if not (source_dir / "step2_extractions.jsonl").exists():
            raise ValueError(
                f"No step2_extractions.jsonl found in {source_dir} — "
                f"is this a step-2 engine experiment?"
            )
        source_dirs.append(source_dir)

    output_dir = EXPERIMENTS_DIR / output_name
    if output_dir.exists():
        if not overwrite:
            raise ValueError(
                f"Output directory already exists: {output_dir} "
                f"(pass --overwrite to replace it)"
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    print(f"Merging {len(source_dirs)} experiment(s) into: {output_dir}")
    for source_dir in source_dirs:
        print(f"  - {source_dir}")
    print()

    for relative_path in MERGEABLE_JSONL_FILES:
        merge_jsonl_file(relative_path, source_dirs, output_dir, dedupe)

    return output_dir


def main():
    parser = argparse.ArgumentParser(
        description="Merge step2_extractions.jsonl (and sibling debug logs) from "
                    "multiple partial experiment runs into a single experiment directory"
    )
    parser.add_argument(
        "--experiment-names",
        type=str,
        nargs="+",
        required=True,
        help="Names of the experiment directories (under experiments/) to merge, in order",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        required=True,
        help="Name of the merged output experiment directory (under experiments/)",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable duplicate (story, variant, chapter) detection/dropping in step2_extractions.jsonl",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output directory if it already exists",
    )

    args = parser.parse_args()

    try:
        output_dir = merge_experiments(
            args.experiment_names,
            args.output_name,
            dedupe=not args.no_dedupe,
            overwrite=args.overwrite,
        )
        print(f"\nMerge complete: {output_dir}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
