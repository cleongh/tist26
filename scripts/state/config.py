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
# CHARACTER ID NORMALIZATION
# =============================================================================
# Map character aliases to canonical IDs to ensure consistency across chapters.
# Characters may be referred to differently (e.g., "uncle_vernon" vs "mr_dursley").
# This mapping ensures rules established for one ID apply to all aliases.

CHAR_ALIASES = {
    # Harry Potter character aliases
    'uncle_vernon': 'vernon_dursley',
    'vernon': 'vernon_dursley',
    'mr_dursley': 'vernon_dursley',
    'aunt_petunia': 'petunia_dursley',
    'petunia': 'petunia_dursley',
    'mrs_dursley': 'petunia_dursley',
    'dudley': 'dudley_dursley',
    'harry': 'harry_potter',
    'potter': 'harry_potter',
    'ron': 'ron_weasley',
    'hermione': 'hermione_granger',
    'dumbledore': 'albus_dumbledore',
    'professor_dumbledore': 'albus_dumbledore',
    'snape': 'severus_snape',
    'professor_snape': 'severus_snape',
    'mcgonagall': 'minerva_mcgonagall',
    'professor_mcgonagall': 'minerva_mcgonagall',
    'hagrid': 'rubeus_hagrid',
    'voldemort': 'lord_voldemort',
    'you_know_who': 'lord_voldemort',
    'he_who_must_not_be_named': 'lord_voldemort',
    'the_dark_lord': 'lord_voldemort',
    
    # Generic family relation aliases (less specific)
    'uncle': 'uncle',  # Keep as-is if no specific match
    'aunt': 'aunt',
    'mother': 'mother',
    'father': 'father',
}


def normalize_character_id(char_id: str) -> str:
    """
    Normalize a character ID to its canonical form.
    This ensures that 'uncle_vernon' and 'mr_dursley' both map to 'vernon_dursley'.
    """
    if not char_id:
        return char_id
    char_lower = char_id.lower().strip()
    return CHAR_ALIASES.get(char_lower, char_lower)


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
