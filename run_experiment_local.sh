#!/bin/bash
#
# Narrative Logic Engine - Full Experiment Runner (Local Llamafile)
# ==================================================================
#
# This script runs the complete narrative experiment pipeline using a local
# llamafile server for LLM inference.
#
# Prerequisites:
#   1. Download and run a llamafile:
#      # Example with Mistral-7B:
#      wget https://huggingface.co/Mozilla/Mistral-7B-Instruct-v0.2-llamafile/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.llamafile
#      chmod +x mistral-7b-instruct-v0.2.Q4_K_M.llamafile
#      ./mistral-7b-instruct-v0.2.Q4_K_M.llamafile --server --host 0.0.0.0 --port 8080
#
#   2. Install Python dependencies:
#      pip install -r requirements.txt
#
# Usage:
#   ./run_experiment_local.sh [experiment_name] [options]
#
# Options:
#   --llm-url URL                 LLM server URL (default: http://localhost:8080/v1)
#   --stories "Story1" "Story2"   Process specific stories (default: all)
#   --max-chapters N              Limit chapters per story (default: all)
#   --skip-step1                  Skip Step 1 (LLM-only evaluation)
#   --skip-step2                  Skip Step 2 (Logic evaluation)
#   --quick                       Quick test: 3 chapters only
#   --disable-timeouts            Disable all timeouts (for slow models)
#
# Examples:
#   ./run_experiment_local.sh my_experiment
#   ./run_experiment_local.sh test_run --quick
#   ./run_experiment_local.sh hp_only --stories "Harry Potter" --max-chapters 5
#   ./run_experiment_local.sh slow_model --disable-timeouts
#

set -e  # Exit on error

# =============================================================================
# CONFIGURATION
# =============================================================================

# Default values
EXPERIMENT_NAME="${1:-local_experiment_$(date +%Y%m%d_%H%M%S)}"
LLM_URL="http://localhost:8080/v1"
MAX_CHAPTERS=""
STORIES=""
SKIP_STEP1=false
SKIP_STEP2=false
LLM_TIMEOUT="600"
ILASP_TIMEOUT="120"
DISABLE_TIMEOUTS=false

# Parse arguments
shift || true  # Shift past experiment name if provided
while [[ $# -gt 0 ]]; do
    case $1 in
        --llm-url)
            LLM_URL="$2"
            shift 2
            ;;
        --max-chapters)
            MAX_CHAPTERS="$2"
            shift 2
            ;;
        --stories)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                STORIES="$STORIES $1"
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
        --disable-timeouts)
            DISABLE_TIMEOUTS=true
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

# Get script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if LLM server is running
echo "Checking LLM server at $LLM_URL..."
if ! curl -s --connect-timeout 5 "$LLM_URL/models" > /dev/null 2>&1; then
    echo ""
    echo "WARNING: LLM server not responding at $LLM_URL"
    echo ""
    echo "Make sure your llamafile server is running:"
    echo "  ./your-model.llamafile --server --host 0.0.0.0 --port 8080"
    echo ""
    echo "Or use a different URL:"
    echo "  ./run_experiment_local.sh exp_name --llm-url http://localhost:1234/v1"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "LLM server is available"
fi

# =============================================================================
# BUILD COMMAND OPTIONS
# =============================================================================

CMD_OPTS="--api-mode local --llm-url $LLM_URL"

if [[ "$DISABLE_TIMEOUTS" == "true" ]]; then
    CMD_OPTS="$CMD_OPTS --disable-timeouts"
else
    CMD_OPTS="$CMD_OPTS --llm-timeout $LLM_TIMEOUT --ilasp-timeout $ILASP_TIMEOUT"
fi

if [[ -n "$MAX_CHAPTERS" ]]; then
    CMD_OPTS="$CMD_OPTS --max-chapters $MAX_CHAPTERS"
fi

if [[ -n "$STORIES" ]]; then
    CMD_OPTS="$CMD_OPTS --stories$STORIES"
fi

# =============================================================================
# RUN EXPERIMENT
# =============================================================================

echo ""
echo "============================================================"
echo "  NARRATIVE LOGIC ENGINE - LOCAL LLAMAFILE EXPERIMENT"
echo "============================================================"
echo ""
echo "  Experiment:    $EXPERIMENT_NAME"
echo "  LLM Server:    $LLM_URL"
echo "  Max Chapters:  ${MAX_CHAPTERS:-all}"
echo "  Stories:       ${STORIES:-all}"
if [[ "$DISABLE_TIMEOUTS" == "true" ]]; then
    echo "  Timeouts:      DISABLED"
else
    echo "  LLM Timeout:   ${LLM_TIMEOUT}s"
    echo "  ILASP Timeout: ${ILASP_TIMEOUT}s"
fi
echo ""
echo "============================================================"
echo ""

START_TIME=$(date +%s)

# Step 1: LLM-only evaluation
if [[ "$SKIP_STEP1" == "false" ]]; then
    echo ""
    echo "[STEP 1] LLM-Only Evaluation"
    echo "------------------------------------------------------------"
    python3 scripts/run_narrative_experiment_refactored.py \
        --experiment-name "$EXPERIMENT_NAME" \
        --step 1 \
        $CMD_OPTS
    echo ""
    echo "[STEP 1] Complete"
    echo ""
fi

# Step 2: Logic-based evaluation with engine
if [[ "$SKIP_STEP2" == "false" ]]; then
    echo ""
    echo "[STEP 2] Logic-Based Evaluation (Engine Mode)"
    echo "------------------------------------------------------------"
    python3 scripts/run_narrative_experiment_refactored.py \
        --experiment-name "$EXPERIMENT_NAME" \
        --step 2 \
        --engine \
        --split-extraction \
        $CMD_OPTS
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
