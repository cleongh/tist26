#!/bin/bash
#
# Narrative Logic Engine - Full Experiment Runner (OpenAI API)
# =============================================================
#
# This script runs the complete narrative experiment pipeline using OpenAI API.
#
# Prerequisites:
#   1. Set your OpenAI API key:
#      export OPENAI_API_KEY="your-api-key"
#
#   2. Install Python dependencies:
#      pip install -r requirements.txt
#
# Usage:
#   ./run_experiment_openai.sh [experiment_name] [options]
#
# Options:
#   --stories "Story1" "Story2"   Process specific stories (default: all)
#   --max-chapters N              Limit chapters per story (default: all)
#   --model MODEL                 OpenAI model (default: gpt-4o)
#   --api-delay SECONDS           Delay between API calls (default: 0.5)
#   --skip-step1                  Skip Step 1 (LLM-only evaluation)
#   --skip-step2                  Skip Step 2 (Logic evaluation)
#   --quick                       Quick test: 3 chapters only
#
# Examples:
#   ./run_experiment_openai.sh my_experiment
#   ./run_experiment_openai.sh test_run --quick
#   ./run_experiment_openai.sh hp_only --stories "Harry Potter" --max-chapters 5
#

set -e  # Exit on error

# =============================================================================
# CONFIGURATION
# =============================================================================

# Default values
EXPERIMENT_NAME="${1:-openai_experiment_$(date +%Y%m%d_%H%M%S)}"
MODEL="gpt-4o"
API_DELAY="0.5"
MAX_CHAPTERS=""
STORIES=()  # Use array to preserve story names with spaces
SKIP_STEP1=false
SKIP_STEP2=false
LLM_TIMEOUT="300"
ILASP_TIMEOUT="60"
USE_SPLIT_EXTRACTION=true

# Parse arguments
shift || true  # Shift past experiment name if provided
while [[ $# -gt 0 ]]; do
    case $1 in
        --model)
            MODEL="$2"
            shift 2
            ;;
        --api-delay)
            API_DELAY="$2"
            shift 2
            ;;
        --max-chapters)
            MAX_CHAPTERS="$2"
            shift 2
            ;;
        --stories)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                STORIES+=("$1")  # Append to array, preserving spaces
                shift
            done
            ;;
        --skip-step1)
            SKIP_STEP1=true
            shift
            ;;
        --skip-step2)
            SKIP_STEP2=true
            shift
            ;;
        --quick)
            MAX_CHAPTERS="3"
            shift
            ;;
        --llm-timeout)
            LLM_TIMEOUT="$2"
            shift 2
            ;;
        --ilasp-timeout)
            ILASP_TIMEOUT="$2"
            shift 2
            ;;
        --no-split)
            USE_SPLIT_EXTRACTION=false
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# =============================================================================
# VALIDATION
# =============================================================================

# Check for OpenAI API key
if [[ -z "${OPENAI_API_KEY}" ]]; then
    echo "ERROR: OPENAI_API_KEY environment variable not set"
    echo ""
    echo "Set it with:"
    echo "  export OPENAI_API_KEY='your-api-key'"
    echo ""
    exit 1
fi

# Get script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check Python dependencies
echo "Checking Python dependencies..."
python3 -c "import openai" 2>/dev/null || {
    echo "ERROR: openai package not installed"
    echo "Install with: pip install openai"
    exit 1
}

# =============================================================================
# BUILD COMMAND OPTIONS
# =============================================================================

CMD_OPTS="--api-mode openai --api-model $MODEL --api-delay $API_DELAY"
CMD_OPTS="$CMD_OPTS --llm-timeout $LLM_TIMEOUT --ilasp-timeout $ILASP_TIMEOUT"

if [[ -n "$MAX_CHAPTERS" ]]; then
    CMD_OPTS="$CMD_OPTS --max-chapters $MAX_CHAPTERS"
fi

# STORIES is handled separately as an array to preserve spaces in names

# =============================================================================
# RUN EXPERIMENT
# =============================================================================

echo ""
echo "============================================================"
echo "  NARRATIVE LOGIC ENGINE - OPENAI EXPERIMENT"
echo "============================================================"
echo ""
echo "  Experiment:   $EXPERIMENT_NAME"
echo "  Model:        $MODEL"
echo "  API Delay:    ${API_DELAY}s"
echo "  Max Chapters: ${MAX_CHAPTERS:-all}"
echo "  Stories:      ${STORIES[*]:-all}"
echo "  Split Extract: $USE_SPLIT_EXTRACTION"
echo "  LLM Timeout:  ${LLM_TIMEOUT}s"
echo "  ILASP Timeout: ${ILASP_TIMEOUT}s"
echo ""
echo "============================================================"
echo ""

START_TIME=$(date +%s)

# Step 1: LLM-only evaluation
if [[ "$SKIP_STEP1" == "false" ]]; then
    echo ""
    echo "[STEP 1] LLM-Only Evaluation"
    echo "------------------------------------------------------------"
    # Build command with proper array expansion for stories
    if [[ ${#STORIES[@]} -gt 0 ]]; then
        python3 scripts/run_narrative_experiment_refactored.py \
            --experiment-name "$EXPERIMENT_NAME" \
            --step 1 \
            $CMD_OPTS \
            --stories "${STORIES[@]}"
    else
        python3 scripts/run_narrative_experiment_refactored.py \
            --experiment-name "$EXPERIMENT_NAME" \
            --step 1 \
            $CMD_OPTS
    fi
    echo ""
    echo "[STEP 1] Complete"
    echo ""
fi

# Step 2: Logic-based evaluation with engine
if [[ "$SKIP_STEP2" == "false" ]]; then
    echo ""
    echo "[STEP 2] Logic-Based Evaluation (Engine Mode)"
    echo "------------------------------------------------------------"
    
    STEP2_OPTS="--engine"
    if [[ "$USE_SPLIT_EXTRACTION" == "true" ]]; then
        STEP2_OPTS="$STEP2_OPTS --split-extraction"
    fi
    
    # Build command with proper array expansion for stories
    if [[ ${#STORIES[@]} -gt 0 ]]; then
        python3 scripts/run_narrative_experiment_refactored.py \
            --experiment-name "$EXPERIMENT_NAME" \
            --step 2 \
            $STEP2_OPTS \
            $CMD_OPTS \
            --stories "${STORIES[@]}"
    else
        python3 scripts/run_narrative_experiment_refactored.py \
            --experiment-name "$EXPERIMENT_NAME" \
            --step 2 \
            $STEP2_OPTS \
            $CMD_OPTS
    fi
    echo ""
    echo "[STEP 2] Complete"
    echo ""
fi

# Generate summary
echo ""
echo "[SUMMARY] Generating Experiment Summary"
echo "------------------------------------------------------------"
python3 scripts/run_narrative_experiment_refactored.py \
    --experiment-name "$EXPERIMENT_NAME" \
    --summarize

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "============================================================"
echo "  EXPERIMENT COMPLETE"
echo "============================================================"
echo ""
echo "  Duration:     $((DURATION / 60))m $((DURATION % 60))s"
echo "  Results:      experiments/$EXPERIMENT_NAME/"
echo ""
echo "  Key files:"
echo "    - step1_llm_results.json    (LLM-only errors)"
echo "    - step2_logic_results.json  (Logic-based errors)"
echo "    - experiment_summary.json   (Comparison)"
echo "    - full_console_log.txt      (Complete log)"
echo ""
echo "============================================================"
