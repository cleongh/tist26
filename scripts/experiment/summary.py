"""
Summary generation for experiment results.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict

from ..state.config import ERROR_CATEGORIES
from ..state.logging import log
from .ground_truth import compare_with_ground_truth


def generate_summary(experiment_dir: Path) -> Dict:
    """Generate comparison summary from both steps."""
    log("=" * 60)
    log("Generating Experiment Summary")
    log("=" * 60)
    
    # Load step 1 results
    step1_file = experiment_dir / "step1_llm_results.json"
    step2_file = experiment_dir / "step2_logic_results.json"
    
    step1_data = {}
    step2_data = {}
    
    if step1_file.exists():
        with open(step1_file) as f:
            step1_data = json.load(f)
        log(f"Loaded Step 1 results: {step1_data.get('total_errors', 0)} errors")
    else:
        log("Step 1 results not found", "WARN")
    
    if step2_file.exists():
        with open(step2_file) as f:
            step2_data = json.load(f)
        log(f"Loaded Step 2 results: {step2_data.get('total_errors', 0)} errors")
    else:
        log("Step 2 results not found", "WARN")
    
    # Build summary
    summary = {
        "experiment_name": experiment_dir.name,
        "generated_at": datetime.now().isoformat(),
        "step1_llm": {
            "approach": "LLM-only",
            "chapters_processed": step1_data.get("chapters_processed", 0),
            "total_errors": step1_data.get("total_errors", 0),
            "timestamp": step1_data.get("timestamp", ""),
        },
        "step2_logic": {
            "approach": "Logic (ILASP + Clingo)",
            "chapters_processed": step2_data.get("chapters_processed", 0),
            "total_errors": step2_data.get("total_errors", 0),
            "timestamp": step2_data.get("timestamp", ""),
        },
        "comparison": {},
    }
    
    # Per-story breakdown
    stories_summary = {}
    
    for result in step1_data.get("results", []):
        key = f"{result['story_name']}_{result['variant']}"
        if key not in stories_summary:
            stories_summary[key] = {"story": result["story_name"], "variant": result["variant"], "llm_errors": 0, "logic_errors": 0}
        stories_summary[key]["llm_errors"] += result.get("error_count", 0)
    
    for result in step2_data.get("results", []):
        key = f"{result['story_name']}_{result['variant']}"
        if key not in stories_summary:
            stories_summary[key] = {"story": result["story_name"], "variant": result["variant"], "llm_errors": 0, "logic_errors": 0}
        stories_summary[key]["logic_errors"] += result.get("error_count", 0)
    
    summary["comparison"]["per_story"] = list(stories_summary.values())
    
    # Category breakdown
    llm_categories = {cat: 0 for cat in ERROR_CATEGORIES}
    logic_categories = {cat: 0 for cat in ERROR_CATEGORIES}
    
    for result in step1_data.get("results", []):
        for error in result.get("errors", []):
            cat = error.get("category", "unknown")
            if cat in llm_categories:
                llm_categories[cat] += 1
    
    for result in step2_data.get("results", []):
        for error in result.get("errors", []):
            cat = error.get("category", "unknown")
            if cat in logic_categories:
                logic_categories[cat] += 1
    
    summary["comparison"]["by_category"] = {
        "llm": llm_categories,
        "logic": logic_categories,
    }
    
    # Ground truth comparison
    ground_truth_results = {}
    stories_in_results = set()
    
    for result in step2_data.get("results", []):
        stories_in_results.add(result.get("story_name"))
    
    for story_name in stories_in_results:
        gt_comparison = compare_with_ground_truth(
            step2_data.get("results", []),
            story_name,
            variant="modified"
        )
        if "note" not in gt_comparison:
            ground_truth_results[story_name] = gt_comparison
    
    summary["ground_truth_comparison"] = ground_truth_results
    
    # Save summary
    output_file = experiment_dir / "experiment_summary.json"
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    log(f"\nSummary saved to: {output_file}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("EXPERIMENT SUMMARY")
    print("=" * 60)
    print(f"\nStep 1 (LLM-only):   {summary['step1_llm']['total_errors']} errors")
    print(f"Step 2 (Logic):      {summary['step2_logic']['total_errors']} errors")
    print("\nPer-story breakdown:")
    for s in summary["comparison"]["per_story"]:
        print(f"  {s['story']} ({s['variant']}): LLM={s['llm_errors']}, Logic={s['logic_errors']}")
    
    # Print ground truth comparison
    if ground_truth_results:
        print("\n" + "-" * 60)
        print("GROUND TRUTH COMPARISON (Modified Stories)")
        print("-" * 60)
        for story_name, gt in ground_truth_results.items():
            print(f"\n{story_name}:")
            print(f"  Chapters processed: {gt['chapters_processed']}")
            print(f"  Ground truth errors in range: {gt['ground_truth_errors_in_range']}")
            print(f"  Detected errors: {gt['total_detected_errors']}")
            print(f"  True positive chapters: {gt['true_positive_chapters']}")
            print(f"  False positive chapters: {gt['false_positive_chapters']}")
            print(f"  False negative chapters: {gt['false_negative_chapters']}")
            print(f"  Precision: {gt['precision']:.1%}")
            print(f"  Recall: {gt['recall']:.1%}")
            print(f"  F1 Score: {gt['f1_score']:.1%}")
            
            # Print details for missed detections
            missed = [d for d in gt['details'] if not d.get('match') and d.get('ground_truth_type')]
            if missed:
                print(f"  Missed errors:")
                for m in missed:
                    print(f"    - {m['chapter']}: {m['ground_truth_type']} - {m['ground_truth_description']}")
    
    return summary
