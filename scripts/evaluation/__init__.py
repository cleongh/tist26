"""
Evaluation module for the Narrative Logic Engine.

Contains tools for analyzing experiment results, detectability classification,
evidence checklists, and reporting. These utilities do NOT affect runtime logic.
"""

from .detectability import (
    DetectabilityStatus,
    ImplantedError,
    DetectabilityResult,
    classify_detectability,
    classify_all_chapters,
    get_detectability_summary,
    format_detectability_report,
)

from .evidence_checklist import (
    PredicateType,
    EvidenceRequirement,
    ErrorCategoryChecklist,
    ChecklistItem,
    ChecklistEvaluation,
    ERROR_CATEGORY_CHECKLISTS,
    check_predicate_presence,
    evaluate_checklist,
    get_checklist_for_category,
    get_all_categories,
    format_checklist_evaluation,
)

__all__ = [
    # Detectability
    "DetectabilityStatus",
    "ImplantedError",
    "DetectabilityResult",
    "classify_detectability",
    "classify_all_chapters",
    "get_detectability_summary",
    "format_detectability_report",
    # Evidence Checklist
    "PredicateType",
    "EvidenceRequirement",
    "ErrorCategoryChecklist",
    "ChecklistItem",
    "ChecklistEvaluation",
    "ERROR_CATEGORY_CHECKLISTS",
    "check_predicate_presence",
    "evaluate_checklist",
    "get_checklist_for_category",
    "get_all_categories",
    "format_checklist_evaluation",
]
