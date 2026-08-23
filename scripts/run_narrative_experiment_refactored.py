#!/usr/bin/env python3
"""
Narrative Experiment Runner

This script runs narrative evaluation experiments comparing LLM-only
evaluation against logic-based evaluation using ILASP and Clingo.

Usage:
    Step 1 (LLM-only):  python run_narrative_experiment.py --step 1 --experiment-name my_exp
    Step 2 (Logic):     python run_narrative_experiment.py --step 2 --experiment-name my_exp
    Debug mode:         python run_narrative_experiment.py --step 2 --api-mode debug --engine
    Summarize:          python run_narrative_experiment.py --summarize --experiment-name my_exp
"""

import argparse
import sys
import os

# Add parent directory to Python path to allow imports from scripts package
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Import configuration and logging
from scripts.state.config import (
    EXPERIMENTS_DIR,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    MOONSHOT_API_KEY,
    DASHSCOPE_API_KEY,
    STORIES,
)
from scripts.state.logging import log, set_console_log_file

# Import experiment runners
from scripts.experiment.runners import (
    run_step1_llm,
    run_step2_logic,
    run_step2_debug,
    run_step2_engine,
)
from scripts.experiment.summary import generate_summary


def main():
    parser = argparse.ArgumentParser(
        description="Run narrative evaluation experiment (chapter by chapter)"
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="narrative_experiment",
        help="Name for this experiment",
    )
    parser.add_argument(
        "--step",
        type=int,
        choices=[1, 2],
        help="Which step to run (1=LLM-only, 2=Logic)",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Generate summary from existing step results",
    )
    parser.add_argument(
        "--llm-url",
        type=str,
        default="http://localhost:8080/v1",
        help="LLM server URL (default: http://localhost:8080/v1)",
    )
    parser.add_argument(
        "--stories",
        type=str,
        nargs="+",
        default=None,
        help="Stories to process (default: all)",
    )
    parser.add_argument(
        "--variants",
        type=str,
        nargs="+",
        choices=["original", "modified"],
        default=None,
        help="Which variants to process, e.g. '--variants modified' to skip "
             "the original (unmodified) books (default: both)",
    )
    parser.add_argument(
        "--max-chapters",
        type=int,
        default=None,
        help="Maximum number of chapters to process (for testing)",
    )
    parser.add_argument(
        "--api-mode",
        type=str,
        choices=["local", "gemini", "openai", "claude", "kimi", "qwen", "debug"],
        default="local",
        help="API mode: 'local' for local LLM server, 'gemini' for Google Gemini, 'openai' for OpenAI, 'claude' for Anthropic Claude, 'kimi' for Moonshot Kimi, 'qwen' for Alibaba Model Studio Qwen, 'debug' for using existing extractions without LLM (default: local)",
    )
    parser.add_argument(
        "--api-model",
        type=str,
        default=None,
        help="Model to use (default: auto for local, gemini-2.0-flash for Gemini, gpt-4o for OpenAI, claude-sonnet-4-5-20250929 for Claude, kimi-k3 for Kimi, qwen3.7-flash for Qwen)",
    )
    parser.add_argument(
        "--api-delay",
        type=float,
        default=0.0,
        help="Delay in seconds between API calls (helps avoid rate limiting, default: 0)",
    )
    parser.add_argument(
        "--structured",
        action="store_true",
        help="Use Phase 4 structured output pipeline (no LLM interpretation of violations)",
    )
    parser.add_argument(
        "--engine",
        action="store_true",
        help="Use Phase 5 engine modules (StateManager, EventExecutor, etc.) with final analysis",
    )
    parser.add_argument(
        "--split-extraction",
        action="store_true",
        help="Use Phase 2 split extraction (four independent LLM calls for characters, items, relationships, events)",
    )
    parser.add_argument(
        "--llm-timeout",
        type=int,
        default=300,
        help="Timeout for LLM API calls in seconds (default: 300)",
    )
    parser.add_argument(
        "--ilasp-timeout",
        type=int,
        default=60,
        help="Timeout for ILASP learning in seconds (default: 60)",
    )
    parser.add_argument(
        "--disable-timeouts",
        action="store_true",
        help="Disable all timeouts (set to None)",
    )
    parser.add_argument(
        '--extraction-only',
        action='store_true',
        default=False,
        help='Only extract data from LLM, skip engine processing'
    )
    
    args = parser.parse_args()
    
    # Handle disable-timeouts flag
    if args.disable_timeouts:
        args.llm_timeout = None
        args.ilasp_timeout = None
    
    # Validate API keys if using cloud APIs
    if args.api_mode == "gemini" and not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY environment variable not set")
        print("Set it with: export GEMINI_API_KEY='your-api-key'")
        sys.exit(1)
    if args.api_mode == "openai" and not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY='your-api-key'")
        sys.exit(1)
    if args.api_mode == "claude" and not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        print("Set it with: export ANTHROPIC_API_KEY='your-api-key'")
        sys.exit(1)
    if args.api_mode == "kimi" and not MOONSHOT_API_KEY:
        print("ERROR: MOONSHOT_API_KEY environment variable not set")
        print("Set it with: export MOONSHOT_API_KEY='your-api-key'")
        sys.exit(1)
    if args.api_mode == "qwen" and not DASHSCOPE_API_KEY:
        print("ERROR: DASHSCOPE_API_KEY environment variable not set")
        print("Set it with: export DASHSCOPE_API_KEY='your-api-key'")
        sys.exit(1)
    
    # Create/find experiment directory
    experiment_dir = EXPERIMENTS_DIR / args.experiment_name
    experiment_dir.mkdir(parents=True, exist_ok=True)
    
    # Set up console logging to file
    console_log_file = experiment_dir / "full_console_log.txt"
    set_console_log_file(console_log_file)
    
    stories = args.stories if args.stories else STORIES
    max_chapters = args.max_chapters
    
    # Log API mode
    log(f"API Mode: {args.api_mode}", "INFO")
    if args.api_model:
        log(f"API Model: {args.api_model}", "INFO")
    if getattr(args, 'split_extraction', False):
        log("Extraction Mode: SPLIT (Phase 2 - four independent LLM calls)", "INFO")
    if args.disable_timeouts:
        log("Timeouts: DISABLED", "INFO")
    else:
        log(f"LLM Timeout: {args.llm_timeout}s, ILASP Timeout: {args.ilasp_timeout}s", "INFO")
    
    if args.summarize:
        generate_summary(experiment_dir)
    elif args.step == 1:
        run_step1_llm(experiment_dir, stories, args.llm_url, max_chapters, 
                      api_mode=args.api_mode, api_model=args.api_model, api_delay=args.api_delay)
    elif args.step == 2:
        # Debug mode: use existing extractions without LLM
        if args.api_mode == "debug":
            if not getattr(args, 'engine', False):
                print("WARNING: Debug mode requires --engine flag. Adding it automatically.")
            run_step2_debug(experiment_dir, stories)
        # Choose evaluation mode based on flags
        elif getattr(args, 'engine', False):
            # Phase 5: Use new engine modules
            run_step2_engine(experiment_dir, stories, args.llm_url, max_chapters,
                             api_mode=args.api_mode, api_model=args.api_model, api_delay=args.api_delay,
                             use_split_extraction=getattr(args, 'split_extraction', False),
                             llm_timeout=args.llm_timeout, extraction_only=args.extraction_only,
                             variants=args.variants)
        else:
            # Original or Phase 4 mode
            run_step2_logic(experiment_dir, stories, args.llm_url, max_chapters,
                            api_mode=args.api_mode, api_model=args.api_model, api_delay=args.api_delay,
                            structured=getattr(args, 'structured', False))
    else:
        print("Please specify --step 1, --step 2, or --summarize")
        print("\nUsage:")
        print("  Step 1 (LLM-only):  python run_narrative_experiment.py --step 1 --experiment-name my_exp")
        print("  Step 2 (Logic):     python run_narrative_experiment.py --step 2 --experiment-name my_exp")
        print("  Debug mode:         python run_narrative_experiment.py --step 2 --api-mode debug --experiment-name my_exp --engine")
        print("  Summarize:          python run_narrative_experiment.py --summarize --experiment-name my_exp")
        print("  Limit chapters:     python run_narrative_experiment.py --step 2 --max-chapters 5")
        print("\nAPI options:")
        print("  --api-mode gemini   Use Google Gemini API (requires GEMINI_API_KEY)")
        print("  --api-mode openai   Use OpenAI API (requires OPENAI_API_KEY)")
        print("  --api-mode claude   Use Anthropic Claude API (requires ANTHROPIC_API_KEY)")
        print("  --api-mode kimi     Use Moonshot Kimi API (requires MOONSHOT_API_KEY)")
        print("  --api-mode qwen     Use Alibaba Model Studio Qwen API (requires DASHSCOPE_API_KEY)")
        print("  --api-mode debug    Use existing extractions without LLM (requires --engine)")
        print("  --api-model MODEL   Specify model (e.g., gemini-2.0-flash, gpt-4o-mini, claude-sonnet-4-5-20250929)")
        print("\nPhase 2/4/5 options:")
        print("  --split-extraction  Use Phase 2 split extraction (four LLM calls)")
        print("  --structured        Use structured output only (no LLM interpretation)")
        print("  --engine            Use Phase 5 engine modules with final analysis")


if __name__ == "__main__":
    main()
