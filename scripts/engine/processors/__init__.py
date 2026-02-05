"""
Processors module for Clingo-based logic execution.
"""

from .clingo_runner import ClingoRunner, ClingoExecutionResult

__all__ = [
    "ClingoRunner",
    "ClingoExecutionResult",
]
