"""
Configuration and constants for the narrative experiment.
"""

import os
import sys
from pathlib import Path

# =============================================================================
# PATHS AND CONFIGURATION
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.parent.resolve()  # scripts/
REPO_ROOT = SCRIPT_DIR.parent
SOURCE_ORIGINAL_BOOKS = REPO_ROOT / "original_books"
SOURCE_MODIFIED_BOOKS = REPO_ROOT / "modified_books"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
RULES_DIR = REPO_ROOT / "rules"
ERRORS_CHECKLIST_DIR = REPO_ROOT / "errors_checklist"

# Add script dir and repo root to path for imports
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))  # For engine module imports

# =============================================================================
# API CONFIGURATION
# =============================================================================
# Set these environment variables before running:
#   export GEMINI_API_KEY="your-gemini-api-key"
#   export OPENAI_API_KEY="your-openai-api-key"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Default models for each API provider
DEFAULT_MODELS = {
    "local": "auto",
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o",
}

# API mode: "local" | "gemini" | "openai"
API_MODE = "local"

# =============================================================================
# CHARACTER ID NORMALIZATION (DEPRECATED)
# =============================================================================
# 
# DEPRECATED: This hardcoded alias system is being phased out.
# 
# Use engine.alias_resolver.AliasResolver instead, which:
#   - Discovers aliases dynamically during LLM extraction
#   - Handles any story (not just Harry Potter)
#   - Supports alias promotion and conflict detection
#   - Integrates with the extraction pipeline
#
# This legacy mapping is kept for backward compatibility with scripts
# Stories to process
STORIES = [
    "Harry Potter",
    "The Hunger Games",
    "The Lord of the Rings",
    "Twilight",
    "Goosebumps",
]

# Error categories
ERROR_CATEGORIES = ["causality", "coherence", "temporal", "location", "emotional"]

# Required fields for structured chapter JSON
REQUIRED_STRUCTURE_FIELDS = {
    "entities": dict,
    "events": list,
}

REQUIRED_ENTITY_FIELDS = {
    "characters": list,
    "locations": list,
}
