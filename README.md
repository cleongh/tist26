# Narrative Consistency Checker - Experiment Guide

A hybrid LLM + Logic Programming system for detecting narrative inconsistencies. This README documents how to set up the environment and run the complete two-step experiment comparing **LLM-based evaluation** vs **Logic-based evaluation** (using ILASP and Clingo).

---

## Table of Contents

1. [Overview](#overview)
2. [System Requirements](#system-requirements)
3. [Environment Setup](#environment-setup)
4. [Folder Structure](#folder-structure)
5. [LLM Server Setup](#llm-server-setup)
6. [Cloud API Setup (Optional)](#cloud-api-setup-optional)
7. [Running the Experiment](#running-the-experiment)
8. [Long-Running Execution](#long-running-execution)
9. [Output Structure](#output-structure)
10. [Interpreting Results](#interpreting-results)
11. [Troubleshooting](#troubleshooting)

---

## Overview

This experiment compares two approaches to narrative consistency checking:

| Step | Approach | Description |
|------|----------|-------------|
| **Step 1** | LLM-Only | Send each chapter directly to the LLM for error detection |
| **Step 2** | Logic-Based | Structure chapters with LLM → Learn rules with ILASP → Detect violations with Clingo |

**Key Design Principle:** Each chapter file is processed **separately**. Stories are never consolidated into a single prompt.

### Experiment Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     STEP 1: LLM-Only                        │
│  python run_narrative_experiment.py --step 1                │
├─────────────────────────────────────────────────────────────┤
│  For each story (Harry Potter, Hunger Games, etc.):         │
│    For each variant (original, modified):                   │
│      For each chapter (000.txt, 001.txt, ...):              │
│        → Send chapter text to LLM                           │
│        → Parse errors from JSON response                    │
│        → Record timing and results                          │
│                                                             │
│  Output: experiments/<name>/step1_llm_results.json          │
└─────────────────────────────────────────────────────────────┘
                            ↓
              (Optional: Restart LLM server)
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   STEP 2: Logic-Based                       │
│  python run_narrative_experiment.py --step 2                │
├─────────────────────────────────────────────────────────────┤
│  For each story:                                            │
│    Reset ILASP/Clingo state (clean start per story)         │
│    For each variant (original, modified):                   │
│      For each chapter (000.txt, 001.txt, ...):              │
│        → Structure chapter with LLM → JSON                  │
│        → Convert JSON to ASP facts                          │
│        → Learn rules with ILASP (incremental within story)  │
│        → Detect violations with Clingo                      │
│        → Record errors and timing                           │
│                                                             │
│  Output: experiments/<name>/step2_logic_results.json        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      SUMMARIZE                              │
│  python run_narrative_experiment.py --summarize             │
├─────────────────────────────────────────────────────────────┤
│  Load step1 and step2 results                               │
│  Generate comparison metrics                                │
│  Per-story and per-category breakdowns                      │
│                                                             │
│  Output: experiments/<name>/experiment_summary.json         │
└─────────────────────────────────────────────────────────────┘
```

---

## System Requirements

- **Operating System:** Linux (tested on Ubuntu 20.04+, Arch Linux)
- **Python:** 3.10 (required for ILASP compatibility)
- **GPU:** NVIDIA GPU recommended for LLM inference (optional, falls back to CPU)
- **RAM:** Minimum 16GB recommended
- **Disk:** ~10GB for models and experiment outputs
- **Tools:**
  - Conda or Miniconda
  - ILASP binary (for rule learning)
  - llamafile (for local LLM inference)

---

## Environment Setup

### Step 1: Create Conda Environment

```bash
conda create -n tist26 python=3.10 -y
conda activate tist26
```

### Step 2: Install Python Dependencies

```bash
pip install clingo requests openai
```

### Step 3: Verify Clingo Installation

```bash
python -c "import clingo; print(f'Clingo version: {clingo.__version__}')"
# Expected output: Clingo version: 5.8.0 (or similar)
```

### Step 4: Install ILASP

1. Download ILASP from: https://doc.ilasp.com/installation.html
2. Extract and place the `ILASP` binary in your PATH:

```bash
# Option A: System-wide
sudo mv ILASP /usr/local/bin/

# Option B: User local
mv ILASP ~/.local/bin/
export PATH="$HOME/.local/bin:$PATH"
```

3. **CRITICAL:** Set the library path (required before every session):

```bash
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
```

4. Verify ILASP installation:

```bash
ILASP --version
# Expected output: ILASP version 4.4.0 (or similar)
```

> **Note:** If ILASP fails with `libpython3.10.so.1.0: cannot open shared object file`, ensure the `LD_LIBRARY_PATH` is set correctly.

### Step 5: Download LLM Model (llamafile)

1. Download the Mistral-7B-Instruct llamafile:
   - **Model:** `Mistral-7B-Instruct-v0.3.Q5_1.llamafile`
   - **Source:** https://huggingface.co/Mozilla/Mistral-7B-Instruct-v0.3-llamafile

2. Place the llamafile in a known location:

```bash
mkdir -p ~/Workspace/models
mv Mistral-7B-Instruct-v0.3.Q5_1.llamafile ~/Workspace/models/
chmod +x ~/Workspace/models/Mistral-7B-Instruct-v0.3.Q5_1.llamafile
```

---

## Folder Structure

The experiment expects the following directory layout:

```
tist26/
├── source_original_books/    # Error-free reference narratives
│   ├── Harry Potter/
│   │   ├── 000.txt          # Chapter files (sequential)
│   │   ├── 001.txt
│   │   └── ...
│   ├── The Hunger Games/
│   ├── The Lord of the Rings/
│   ├── Twilight/
│   └── Goosebumps/
│
├── source_modified_books/    # Narratives with injected errors
│   ├── Harry Potter/
│   │   ├── 000.txt
│   │   ├── 001.txt
│   │   └── ...
│   ├── The Hunger Games/
│   ├── The Lord of the Rings/
│   ├── Twilight/
│   └── Goosebumps/
│
├── rules/                    # ASP rule files
│   ├── base.lp              # Core ASP rules
│   ├── general.lp           # Domain-independent rules
│   └── ilasp_mode_declarations.las  # ILASP hypothesis space
│
├── scripts/                  # Python scripts
│   ├── run_narrative_experiment.py  # Two-step experiment (LLM vs Logic)
│   ├── run_kfold_incremental.py     # K-fold cross-validation experiment
│   ├── ilasp_task_generator.py      # ILASP task generation
│   ├── story_lint.py                # Core linting logic
│   ├── llm_structurer.py            # Story to JSON structurer
│   └── json_to_asp.py               # JSON to ASP converter
│
├── experiments/              # Experiment outputs (auto-created)
│
└── docs/                     # Documentation
    ├── EXPERIMENT_CHANGES_SUMMARY.md
    └── ...
```

### Input Data Requirements

- Each story is a folder containing multiple `.txt` files
- Files must be named with zero-padded numbers: `000.txt`, `001.txt`, `002.txt`, etc.
- Files are processed in lexicographical order
- Each file represents one chapter and is processed **independently**
- `source_original_books/` contains error-free narratives (baseline)
- `source_modified_books/` contains narratives with injected errors

---

## LLM Server Setup

The experiment uses a local LLM via llamafile on port 8080.

### Start the LLM Server

Open a **dedicated terminal** (Terminal 1) and run:

```bash
cd ~/Workspace/models

# With GPU (NVIDIA) - Recommended
./Mistral-7B-Instruct-v0.3.Q5_1.llamafile \
    --server \
    --nobrowser \
    -ngl 9999 \
    --gpu nvidia

# Without GPU (CPU only) - Slower
./Mistral-7B-Instruct-v0.3.Q5_1.llamafile \
    --server \
    --nobrowser
```

**Parameters explained:**
| Parameter | Description |
|-----------|-------------|
| `--server` | Run in server mode (API endpoint) |
| `--nobrowser` | Don't open browser |
| `-ngl 9999` | Offload all layers to GPU |
| `--gpu nvidia` | Use NVIDIA GPU |

The server will listen on `http://localhost:8080`.

### Verify Server is Running

```bash
curl http://localhost:8080/v1/models
```

You should see a JSON response with model information.

> **Important:** Keep Terminal 1 open. The LLM server must remain running throughout the experiment.

---

## Cloud API Setup (Optional)

Instead of running a local LLM, you can use cloud APIs from Google (Gemini) or OpenAI.

### API Keys Configuration

Set your API keys as environment variables:

```bash
# For Google Gemini API
export GEMINI_API_KEY="your-gemini-api-key"

# For OpenAI API
export OPENAI_API_KEY="your-openai-api-key"
```

**To make these permanent**, add them to your shell profile:

```bash
# Add to ~/.bashrc or ~/.zshrc
echo 'export GEMINI_API_KEY="your-gemini-api-key"' >> ~/.bashrc
echo 'export OPENAI_API_KEY="your-openai-api-key"' >> ~/.bashrc
source ~/.bashrc
```

### Getting API Keys

| Provider | Get Key From | Free Tier |
|----------|--------------|-----------|
| **Google Gemini** | [Google AI Studio](https://aistudio.google.com/apikey) | ✅ Yes (generous limits) |
| **OpenAI** | [OpenAI Platform](https://platform.openai.com/api-keys) | ❌ No (pay-as-you-go) |

### Default Models

| API Mode | Default Model | Cost (Full Experiment) |
|----------|---------------|------------------------|
| `local` | auto (llamafile) | Free (electricity only) |
| `gemini` | gemini-2.0-flash | ~$0.67 |
| `openai` | gpt-4o | ~$17 |

### Usage Examples

```bash
# Use Gemini 2.0 Flash (recommended for quality/cost)
python scripts/run_narrative_experiment.py --step 2 \
    --experiment-name "hp_gemini" \
    --stories "Harry Potter" \
    --api-mode gemini

# Use a specific Gemini model
python scripts/run_narrative_experiment.py --step 2 \
    --experiment-name "hp_gemini_pro" \
    --api-mode gemini \
    --api-model "gemini-2.5-pro"

# Use OpenAI GPT-4o
python scripts/run_narrative_experiment.py --step 2 \
    --experiment-name "hp_openai" \
    --stories "Harry Potter" \
    --api-mode openai

# Use a cheaper OpenAI model
python scripts/run_narrative_experiment.py --step 2 \
    --experiment-name "hp_gpt5mini" \
    --api-mode openai \
    --api-model "gpt-5-mini"
```

### Cost Estimation

See [API_COST_ESTIMATION.md](API_COST_ESTIMATION.md) for detailed pricing breakdown.

| Model | Harry Potter Only | Full Experiment (704 ch) |
|-------|-------------------|--------------------------|
| Gemini 2.0 Flash | ~$0.11 | ~$0.67 |
| GPT-4o-mini | ~$0.16 | ~$1.00 |
| GPT-5.2 | ~$2.50 | ~$15.41 |

---

## Running the Experiment

There are **two experiment scripts** available:

| Script | Purpose | Best For |
|--------|---------|----------|
| `run_narrative_experiment.py` | Two-step comparison (LLM vs Logic) | Simple comparison, manual control |
| `run_kfold_incremental.py` | K-fold cross-validation with baseline filtering | Rigorous evaluation, false positive removal |

---

### Option A: Two-Step Experiment (`run_narrative_experiment.py`)

This is the simpler approach with explicit step-by-step control.

```bash
# Step 1: LLM-only evaluation
python scripts/run_narrative_experiment.py --step 1 --experiment-name "my_exp"

# Step 2: Logic-based evaluation
python scripts/run_narrative_experiment.py --step 2 --experiment-name "my_exp"

# Generate comparison summary
python scripts/run_narrative_experiment.py --summarize --experiment-name "my_exp"
```

---

### Option B: K-Fold Cross-Validation (`run_kfold_incremental.py`)

This is the more rigorous approach with automatic baseline filtering.

```bash
# Full k-fold experiment
python scripts/run_kfold_incremental.py \
    --model-name "mistral" \
    --base-url "http://localhost:8080/v1" \
    --k-values "1,2,3,4" \
    --timeout 900
```

**K-Fold Workflow:**
1. **Baseline Training**: Run on original books to collect false positive signatures
2. **Testing**: Run on modified books to detect errors
3. **Filtering**: Remove errors matching false positive signatures
4. **Cross-Validation**: Repeat with different train/test book splits

---

### Detailed Instructions

#### Terminal 2: Activate Environment

Open a new terminal (Terminal 2) and prepare the environment:

```bash
# Navigate to project
cd /home/mrcorner/Workspace/Repos/tist26

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tist26

# Set library path for ILASP (REQUIRED)
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"

# Verify setup
python -c "import clingo; print('clingo OK')"
ILASP --version
curl -s http://localhost:8080/v1/models | head -1
```

---

### Option A: Two-Step Experiment (Detailed)

#### Run Step 1: LLM-Only Evaluation

```bash
python scripts/run_narrative_experiment.py \
    --step 1 \
    --experiment-name "full_experiment"
```

This will:
- Process all 5 stories (both original and modified variants)
- Send each chapter to the LLM for error detection
- Save results to `experiments/full_experiment/step1_llm_results.json`

**Expected duration:** 2-4 hours (GPU) or 8-12 hours (CPU only)

#### (Optional) Restart LLM Server

If you want a fresh LLM state between steps, restart the llamafile server in Terminal 1.

#### Run Step 2: Logic-Based Evaluation

```bash
python scripts/run_narrative_experiment.py \
    --step 2 \
    --experiment-name "full_experiment"
```

This will:
- Process all stories with the logic-based approach
- Use LLM to structure each chapter into JSON
- Convert JSON to ASP facts
- Learn rules with ILASP (incrementally within each story)
- Detect violations with Clingo
- Save results to `experiments/full_experiment/step2_logic_results.json`

**Expected duration:** 3-6 hours (GPU) or 10-15 hours (CPU only)

#### Generate Comparison Summary

```bash
python scripts/run_narrative_experiment.py \
    --summarize \
    --experiment-name "full_experiment"
```

This will:
- Load results from both steps
- Generate per-story and per-category breakdowns
- Save summary to `experiments/full_experiment/experiment_summary.json`
- Print a summary table to the console

#### Command-Line Options (Two-Step)

| Option | Description | Default |
|--------|-------------|---------|
| `--step 1` | Run Step 1 (LLM-only evaluation) | - |
| `--step 2` | Run Step 2 (Logic-based evaluation) | - |
| `--summarize` | Generate comparison summary | - |
| `--experiment-name NAME` | Name for experiment directory | `narrative_experiment` |
| `--llm-url URL` | LLM server endpoint (for local mode) | `http://localhost:8080/v1` |
| `--stories S1 S2 ...` | Specific stories to process | All 5 stories |
| `--max-chapters N` | Limit number of chapters (for testing) | All chapters |
| `--api-mode MODE` | API backend: `local`, `gemini`, or `openai` | `local` |
| `--api-model MODEL` | Override default model for API | Auto-selected |

---

### Option B: K-Fold Cross-Validation (Detailed)

The k-fold experiment provides more rigorous evaluation with automatic false positive filtering.

#### Run Full K-Fold Experiment

```bash
python scripts/run_kfold_incremental.py \
    --model-name "mistral" \
    --base-url "http://localhost:8080/v1" \
    --k-values "1,2,3,4" \
    --timeout 900
```

**What it does:**
1. For each k-fold split:
   - Use some books for **baseline** (run on original versions to collect false positives)
   - Use remaining books for **testing** (run on modified versions)
   - Filter out errors matching baseline signatures
2. Compare LLM direct analysis vs ILASP incremental learning
3. Aggregate results across all folds

#### Command-Line Options (K-Fold)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--model-name` | Name for experiment folder (required) | - |
| `--base-url` | LLM server endpoint | `http://localhost:8080/v1` |
| `--k-values` | Comma-separated k-fold values | `1,2,3,4` |
| `--timeout` | Timeout per book in seconds | `900` |
| `--books` | Comma-separated book names | All 5 books |
| `--local-llm` | Local llamafile model name | None |

#### K-Fold Output Structure

```
experiments/incremental_<model>_<start>_<end>_<id>/
├── config.json           # Experiment configuration
├── log.txt               # Detailed execution log
├── results.json          # Complete results (all folds)
├── report.md             # Markdown report with analysis
└── results/
    ├── fold_1_k1.json    # Per-fold results
    ├── fold_1_k2.json
    └── ...
```

---

### Run on Specific Stories

```bash
# Two-step: Process only Harry Potter and Goosebumps
python scripts/run_narrative_experiment.py \
    --step 1 \
    --experiment-name "subset_test" \
    --stories "Harry Potter" "Goosebumps"

# K-fold: Same subset
python scripts/run_kfold_incremental.py \
    --model-name "subset" \
    --books "Harry Potter,Goosebumps" \
    --k-values "2"
```

### Quick Test Run

For a quick test with minimal configuration:

```bash
# Two-step quick test
python scripts/run_narrative_experiment.py \
    --step 1 \
    --experiment-name "quick_test" \
    --stories "Goosebumps"

python scripts/run_narrative_experiment.py \
    --step 2 \
    --experiment-name "quick_test" \
    --stories "Goosebumps"

python scripts/run_narrative_experiment.py \
    --summarize \
    --experiment-name "quick_test"

# K-fold quick test
python scripts/run_kfold_incremental.py \
    --model-name "test" \
    --books "Goosebumps" \
    --k-values "1" \
    --timeout 300
```

---

## Long-Running Execution

The full experiment can take **several hours** depending on:
- Number of stories and chapters
- LLM inference speed (GPU vs CPU)
- ILASP learning complexity

### Using tmux (Recommended)

```bash
# Create a new tmux session for the LLM server
tmux new -s llm_server
cd ~/Workspace/models
./Mistral-7B-Instruct-v0.3.Q5_1.llamafile --server --nobrowser -ngl 9999 --gpu nvidia
# Detach: Ctrl+B, then D

# Create a new tmux session for the experiment
tmux new -s experiment
conda activate tist26
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
cd /home/mrcorner/Workspace/Repos/tist26

# Run all steps
python scripts/run_narrative_experiment.py --step 1 --experiment-name "full_run"
python scripts/run_narrative_experiment.py --step 2 --experiment-name "full_run"
python scripts/run_narrative_experiment.py --summarize --experiment-name "full_run"

# Detach: Ctrl+B, then D
# Reattach later: tmux attach -t experiment
```

### Using screen

```bash
# Create a new screen session
screen -S experiment

# Run experiment commands...

# Detach: Ctrl+A, then D
# Reattach: screen -r experiment
```

### Using nohup

```bash
# Run Step 1 in background
nohup python scripts/run_narrative_experiment.py \
    --step 1 \
    --experiment-name "full_run" \
    > step1.log 2>&1 &

# Monitor progress
tail -f step1.log

# After Step 1 completes, run Step 2
nohup python scripts/run_narrative_experiment.py \
    --step 2 \
    --experiment-name "full_run" \
    > step2.log 2>&1 &
```

---

## Output Structure

All experiment outputs are saved to `experiments/`:

### Two-Step Experiment Output

```
experiments/<experiment-name>/
├── step1_llm_results.json      # LLM-only evaluation results
├── step2_logic_results.json    # Logic-based evaluation results
└── experiment_summary.json     # Comparison summary
```

### K-Fold Experiment Output

```
experiments/incremental_<model>_<start>_<end>_<id>/
├── config.json           # Experiment configuration
├── log.txt               # Detailed execution log
├── results.json          # Complete results (all folds, all books)
├── report.md             # Markdown report with analysis
└── results/
    ├── fold_1_k1.json    # Per-fold results
    ├── fold_1_k2.json
    └── ...
```

### step1_llm_results.json / step2_logic_results.json

```json
{
  "step": 1,
  "approach": "llm",
  "timestamp": "2026-01-28T19:30:00",
  "chapters_processed": 125,
  "total_errors": 47,
  "results": [
    {
      "story_name": "Harry Potter",
      "variant": "modified",
      "chapter_file": "003.txt",
      "chapter_number": 3,
      "error_count": 2,
      "errors": [
        {
          "chapter_file": "003.txt",
          "category": "coherence",
          "error_type": "dead_character_acting",
          "description": "Character performs action after being killed",
          "story_fragment": "The ghost of Dumbledore picked up his wand..."
        }
      ],
      "duration_seconds": 12.5,
      "success": true,
      "error_message": ""
    }
  ]
}
```

### experiment_summary.json

```json
{
  "experiment_name": "full_experiment",
  "generated_at": "2026-01-28T20:00:00",
  "step1_llm": {
    "approach": "LLM-only",
    "chapters_processed": 125,
    "total_errors": 47,
    "timestamp": "2026-01-28T18:00:00"
  },
  "step2_logic": {
    "approach": "Logic (ILASP + Clingo)",
    "chapters_processed": 125,
    "total_errors": 32,
    "timestamp": "2026-01-28T19:30:00"
  },
  "comparison": {
    "per_story": [
      {"story": "Harry Potter", "variant": "original", "llm_errors": 5, "logic_errors": 2},
      {"story": "Harry Potter", "variant": "modified", "llm_errors": 12, "logic_errors": 8}
    ],
    "by_category": {
      "llm": {"causality": 10, "coherence": 15, "temporal": 8, "location": 7, "emotional": 7},
      "logic": {"causality": 6, "coherence": 12, "temporal": 5, "location": 4, "emotional": 5}
    }
  }
}
```

---

## Interpreting Results

### Error Categories

| Category | Description | Examples |
|----------|-------------|----------|
| `causality` | Chekhov's gun violations, unexplained effects, missing causes | Introduced element never used, effect without cause |
| `coherence` | Logical impossibilities, trait violations | Dead character acting, blind character reading |
| `temporal` | Time paradoxes, impossible sequences | Events in wrong order, duration violations |
| `location` | Ubiquity, impossible travel | Character in two places, instant teleportation |
| `emotional` | Motivation mismatches, relationship contradictions | Harming loved ones without reason |

### Understanding the Comparison

- **Step 1 (LLM-only):** Direct natural language analysis. Good at catching semantic issues but may produce false positives.
- **Step 2 (Logic-based):** Formal verification with learned rules. More precise but limited to patterns ILASP can learn.

### Expected Patterns

- Modified stories should have more errors than original stories
- LLM-only may detect more errors overall (including false positives)
- Logic-based should have higher precision on detectable patterns
- Errors in `original` variants are likely false positives

---

## Troubleshooting

### LLM Server Issues

**Server not responding:**
```bash
# Check if server is running
curl http://localhost:8080/v1/models

# If not responding, check Terminal 1 for errors
# Restart the llamafile server if needed
```

**Out of memory:**
```bash
# Reduce GPU layers
./Mistral-7B-Instruct-v0.3.Q5_1.llamafile --server --nobrowser -ngl 20 --gpu nvidia

# Or use CPU only (slower but less memory)
./Mistral-7B-Instruct-v0.3.Q5_1.llamafile --server --nobrowser
```

### ILASP Issues

**ILASP not found:**
```bash
which ILASP
# If not found, add to PATH:
export PATH="$HOME/.local/bin:$PATH"
```

**libpython3.10.so error:**
```bash
# Must set LD_LIBRARY_PATH before running
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
```

### Python Import Errors

**Module not found:**
```bash
conda activate tist26
pip install clingo requests openai
```

### Experiment Issues

**Wrong source directories:**
Ensure stories are in `source_original_books/` and `source_modified_books/`, not `original_books/` or `modified_books/`.

**No chapters found:**
Verify chapter files are named with zero-padded numbers: `000.txt`, `001.txt`, etc.

**Timeout errors:**
LLM requests have a 180-second timeout. If running on CPU, this may not be enough. Consider using GPU or a faster model.

### Verify Full Installation

```bash
# Activate environment
conda activate tist26
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"

# Check all components
echo "=== Python Modules ==="
python -c "import clingo; print(f'clingo: {clingo.__version__}')"
python -c "import requests; print('requests: OK')"

echo "=== ILASP ==="
ILASP --version

echo "=== LLM Server ==="
curl -s http://localhost:8080/v1/models | python -c "import sys,json; print('LLM Server: OK' if json.load(sys.stdin) else 'ERROR')"

echo "=== Source Data ==="
ls source_original_books/
ls source_modified_books/
```

---

## Quick Start Checklist

```
[ ] 1. Create conda environment
      conda create -n tist26 python=3.10 -y
      conda activate tist26

[ ] 2. Install dependencies
      pip install clingo requests openai

[ ] 3. Download and install ILASP
      Place binary in PATH, verify with: ILASP --version

[ ] 4. Download Mistral-7B llamafile
      chmod +x Mistral-7B-Instruct-v0.3.Q5_1.llamafile

[ ] 5. Start LLM server (Terminal 1)
      ./Mistral-7B-Instruct-v0.3.Q5_1.llamafile --server --nobrowser -ngl 9999 --gpu nvidia

[ ] 6. Set LD_LIBRARY_PATH (Terminal 2)
      export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"

[ ] 7. Run experiment (choose one):

      # Option A: Two-step experiment
      python scripts/run_narrative_experiment.py --step 1 --experiment-name "test"
      python scripts/run_narrative_experiment.py --step 2 --experiment-name "test"
      python scripts/run_narrative_experiment.py --summarize --experiment-name "test"

      # Option B: K-fold experiment
      python scripts/run_kfold_incremental.py --model-name "test" --k-values "1"

[ ] 8. Check results
      cat experiments/test/experiment_summary.json
      # or
      cat experiments/incremental_test_*/report.md
```

---

## Citation

If you use this system in your research, please cite:

```bibtex
TBD
```

---

*Last updated: 28 January 2026*
