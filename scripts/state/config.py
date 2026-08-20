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

# Read-only dataset inputs; override to point at a shared/NAS location.
# NARRATIVE_DATA_ROOT is the common base; the three vars below can each be
# overridden independently for multi-variant datasets (e.g. modified_books_ai_15/).
DATA_ROOT = Path(os.environ.get("NARRATIVE_DATA_ROOT") or REPO_ROOT)

SOURCE_ORIGINAL_BOOKS = Path(
    os.environ.get("NARRATIVE_ORIGINAL_BOOKS") or DATA_ROOT / "original_books"
)
SOURCE_MODIFIED_BOOKS = Path(
    os.environ.get("NARRATIVE_MODIFIED_BOOKS") or DATA_ROOT / "modified_books"
)

# Multi-variant datasets ship ground truth nested inside the modified-books
# folder; fall back to a root-level errors_checklist for the legacy layout.
_variant_checklist = SOURCE_MODIFIED_BOOKS / "errors_checklist"
ERRORS_CHECKLIST_DIR = Path(
    os.environ.get("NARRATIVE_ERRORS_CHECKLIST")
    or (_variant_checklist if _variant_checklist.is_dir() else DATA_ROOT / "errors_checklist")
)

# Generated output always stays local to the machine running the experiment.
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
RULES_DIR = REPO_ROOT / "rules"

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
#   export ANTHROPIC_API_KEY="your-anthropic-api-key"
#   export MOONSHOT_API_KEY="your-moonshot-api-key"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MOONSHOT_API_KEY = os.environ.get("MOONSHOT_API_KEY", "")

# Default models for each API provider
DEFAULT_MODELS = {
    "local": "auto",
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o",
    "claude": "claude-sonnet-4-5-20250929",
    "kimi": "kimi-k3",
}

# OpenAI-compatible base URLs for providers reached through OpenAIAPIClient
PROVIDER_BASE_URLS = {
    "claude": "https://api.anthropic.com/v1/",
    "kimi": "https://api.moonshot.ai/v1",
}

# API mode: "local" | "gemini" | "openai" | "claude" | "kimi"
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
