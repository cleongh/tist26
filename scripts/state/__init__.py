# state/ - Cross-chapter state, configuration, and data structures
# TODO: Future refactors may add persistence mechanisms

from .config import (
    SCRIPT_DIR,
    REPO_ROOT,
    SOURCE_ORIGINAL_BOOKS,
    SOURCE_MODIFIED_BOOKS,
    EXPERIMENTS_DIR,
    RULES_DIR,
    ERRORS_CHECKLIST_DIR,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    MOONSHOT_API_KEY,
    DASHSCOPE_API_KEY,
    DEFAULT_MODELS,
    PROVIDER_BASE_URLS,
    API_MODE,
    STORIES,
    ERROR_CATEGORIES,
    REQUIRED_STRUCTURE_FIELDS,
    REQUIRED_ENTITY_FIELDS,
)
from .logging import log, set_console_log_file, log_step_start, log_step_end, reset_logging
from .data_structures import ChapterError, ChapterResult, StepResults

__all__ = [
    # Config
    "SCRIPT_DIR",
    "REPO_ROOT",
    "SOURCE_ORIGINAL_BOOKS",
    "SOURCE_MODIFIED_BOOKS",
    "EXPERIMENTS_DIR",
    "RULES_DIR",
    "ERRORS_CHECKLIST_DIR",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "MOONSHOT_API_KEY",
    "DASHSCOPE_API_KEY",
    "DEFAULT_MODELS",
    "PROVIDER_BASE_URLS",
    "API_MODE",
    "STORIES",
    "ERROR_CATEGORIES",
    "REQUIRED_STRUCTURE_FIELDS",
    "REQUIRED_ENTITY_FIELDS",
    # Logging
    "log",
    "set_console_log_file",
    "log_step_start",
    "log_step_end",
    "reset_logging",
    # Data structures
    "ChapterError",
    "ChapterResult",
    "StepResults",
]
