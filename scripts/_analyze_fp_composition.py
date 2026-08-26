#!/usr/bin/env python3
"""Scratch analysis (not part of the pipeline): for a given experiment's
all_detected_errors.csv + errors_checklist/, compute per (category, type)
TP/FP counts using the same chapter+category-strict matching convention as
the runner's informational precision/recall report. Read-only, no ground
truth is ever fed back into detection logic -- this is purely for human
analysis to find a structural (not content-based) discard rule.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.kfold_experiment_runner_conflict_resolver import (
    load_ground_truth, match_error_category, STORY_SLUG_MAP,
)
from scripts.state.config import ERRORS_CHECKLIST_DIR

experiment_dir = Path(sys.argv[1])
errors_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else ERRORS_CHECKLIST_DIR

ground_truth = load_ground_truth(errors_dir)
gt_by_story_chapter = defaultdict(lambda: defaultdict(list))
for story, errs in ground_truth.items():
    for e in errs:
        gt_by_story_chapter[story][e.chapter_num].append(e.category)

csv_path = experiment_dir / "final_errors_count" / "all_detected_errors.csv"
rows = list(csv.DictReader(open(csv_path, encoding="utf-8"), delimiter=";"))

# Re-derive chapter number the same way GroundTruthError.chapter_num does
def chapter_num(chapter_str):
    m = re.match(r"(\d+)", chapter_str)
    return int(m.group(1)) if m else -1

stats = defaultdict(lambda: {"tp": 0, "fp": 0, "total": 0})
event_id_generic = defaultdict(lambda: {"tp": 0, "fp": 0})

for story in gt_by_story_chapter:
    gt_used = defaultdict(lambda: [False] * 0)

for row in rows:
    story = row["Story"]
    ch = chapter_num(row["Chapter"])
    cat = row["Category"]
    try:
        detail = json.loads(row["Description"])
    except Exception:
        detail = {}
    vtype = detail.get("type", "unknown")
    key = (cat, vtype)
    stats[key]["total"] += 1
    gt_types = gt_by_story_chapter.get(story, {}).get(ch, [])
    is_match = any(match_error_category(cat, gt) for gt in gt_types)
    if is_match:
        stats[key]["tp"] += 1
    else:
        stats[key]["fp"] += 1

    eid = str(detail.get("event_id", ""))
    generic = eid in ("chapter",) or not eid
    gkey = f"{cat}/{vtype}/generic_event_id={generic}"
    if is_match:
        event_id_generic[gkey]["tp"] += 1
    else:
        event_id_generic[gkey]["fp"] += 1

print(f"{'category/type':45s} {'total':>6s} {'tp*':>5s} {'fp*':>5s} {'prec*':>7s}")
print("(*chapter-level, category-strict overlap -- NOT true per-error matching, just diagnostic)")
for key, s in sorted(stats.items(), key=lambda kv: -kv[1]["total"]):
    prec = s["tp"] / s["total"] if s["total"] else 0
    print(f"{key[0]+'/'+key[1]:45s} {s['total']:6d} {s['tp']:5d} {s['fp']:5d} {prec:7.2%}")

print("\nBy generic event_id (event_id=='chapter' or empty) vs specific:")
for key, s in sorted(event_id_generic.items(), key=lambda kv: -(kv[1]["tp"]+kv[1]["fp"])):
    total = s["tp"] + s["fp"]
    prec = s["tp"] / total if total else 0
    print(f"{key:60s} total={total:5d} tp={s['tp']:5d} fp={s['fp']:5d} prec={prec:7.2%}")
