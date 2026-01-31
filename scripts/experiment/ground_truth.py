"""
Ground truth loading and comparison utilities.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List

from ..state.config import ERRORS_CHECKLIST_DIR


def load_ground_truth(story_name: str) -> List[Dict[str, Any]]:
    """
    Load ground truth errors from the errors_checklist CSV file for a story.
    Returns a list of dicts with: chunk, chapter, error_type, description, sentence
    """
    csv_mapping = {
        "Harry Potter": "harry_potter_errors.csv",
        "The Hunger Games": "hunger_games_errors.csv",
        "The Lord of the Rings": "the_lord_of_the_rings_errors.csv",
        "Twilight": "twilight_errors.csv",
        "Goosebumps": "goosebumps_errors.csv",
    }
    
    csv_file = csv_mapping.get(story_name)
    if not csv_file:
        return []
    
    csv_path = ERRORS_CHECKLIST_DIR / csv_file
    if not csv_path.exists():
        return []
    
    ground_truth = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ground_truth.append({
                "chunk": int(row.get("Chunk", 0)),
                "chapter": row.get("Chapter", ""),
                "error_type": row.get("Error Type", ""),
                "description": row.get("Error description", ""),
                "sentence": row.get("Error sentence", ""),
            })
    
    return ground_truth


def _map_error_type_to_category(error_type: str) -> str:
    """Map ground truth error types to our category system."""
    mapping = {
        "Basic Coherence": "coherence",
        "Emotional Relations": "emotional",
        "Location correctness": "location",
        "Temporal Order": "temporal",
        "Causality": "causality",
    }
    return mapping.get(error_type, "unknown")


def compare_with_ground_truth(
    results: List[Dict[str, Any]], 
    story_name: str,
    variant: str = "modified"
) -> Dict[str, Any]:
    """
    Compare detected errors against ground truth for a story.
    
    Returns a dict with:
    - total_ground_truth: Total errors in ground truth for processed chapters
    - total_detected: Total errors detected
    - true_positives: Errors correctly detected (matching chapter)
    - false_positives: Errors detected but not in ground truth
    - false_negatives: Errors in ground truth but not detected
    - precision, recall, f1: Metrics
    - details: Per-chapter breakdown
    """
    if variant != "modified":
        return {"note": "Ground truth comparison only applicable to modified variant"}
    
    ground_truth = load_ground_truth(story_name)
    if not ground_truth:
        return {"note": f"No ground truth found for {story_name}"}
    
    # Get chapters that were processed
    processed_chapters = set()
    detected_by_chapter = {}
    
    for result in results:
        if result.get("story_name") == story_name and result.get("variant") == variant:
            chapter = result.get("chapter_file", "")
            processed_chapters.add(chapter)
            if chapter not in detected_by_chapter:
                detected_by_chapter[chapter] = []
            detected_by_chapter[chapter].extend(result.get("errors", []))
    
    # Filter ground truth to only processed chapters
    gt_in_range = [gt for gt in ground_truth if gt["chapter"] in processed_chapters]
    gt_chapters = {gt["chapter"] for gt in gt_in_range}
    
    # Calculate metrics
    detected_chapters = {ch for ch, errors in detected_by_chapter.items() if errors}
    
    true_positive_chapters = gt_chapters & detected_chapters
    false_negative_chapters = gt_chapters - detected_chapters
    false_positive_chapters = detected_chapters - gt_chapters
    
    # Build detailed breakdown
    details = []
    for gt in gt_in_range:
        chapter = gt["chapter"]
        detected = detected_by_chapter.get(chapter, [])
        details.append({
            "chapter": chapter,
            "ground_truth_type": gt["error_type"],
            "ground_truth_category": _map_error_type_to_category(gt["error_type"]),
            "ground_truth_description": gt["description"][:100] + "..." if len(gt["description"]) > 100 else gt["description"],
            "detected_count": len(detected),
            "detected_categories": list(set(e.get("category", "unknown") for e in detected)),
            "match": chapter in true_positive_chapters,
        })
    
    # Add false positives
    for chapter in false_positive_chapters:
        detected = detected_by_chapter.get(chapter, [])
        details.append({
            "chapter": chapter,
            "ground_truth_type": None,
            "ground_truth_category": None,
            "ground_truth_description": None,
            "detected_count": len(detected),
            "detected_categories": list(set(e.get("category", "unknown") for e in detected)),
            "match": False,
            "false_positive": True,
        })
    
    details.sort(key=lambda x: x["chapter"])
    
    # Calculate precision, recall, F1
    tp = len(true_positive_chapters)
    fp = len(false_positive_chapters)
    fn = len(false_negative_chapters)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        "story": story_name,
        "chapters_processed": len(processed_chapters),
        "ground_truth_errors_in_range": len(gt_in_range),
        "total_detected_errors": sum(len(detected_by_chapter.get(ch, [])) for ch in processed_chapters),
        "chapters_with_gt_errors": len(gt_chapters),
        "chapters_with_detected_errors": len(detected_chapters),
        "true_positive_chapters": len(true_positive_chapters),
        "false_positive_chapters": len(false_positive_chapters),
        "false_negative_chapters": len(false_negative_chapters),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1_score": round(f1, 3),
        "details": details,
    }
