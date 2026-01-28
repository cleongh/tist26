# Narrative Experiment Implementation Summary

**Date:** 28 January 2026  
**Version:** 2.0 - Chapter-by-Chapter Processing  
**Purpose:** Comprehensive experiment comparing LLM-based vs Logic-based narrative evaluation

---

## Overview

This document summarizes the implementation of a two-step research experiment framework for comparing two approaches to narrative consistency checking:

1. **Step 1: Pure LLM-based Evaluation** - Using large language models to directly identify narrative errors
2. **Step 2: Logic-based Evaluation** - Using ILASP to learn rules + Clingo to detect violations

**CRITICAL DESIGN: Each chapter is processed SEPARATELY - stories are NEVER consolidated into a single prompt.**

---

## Experiment Design

### Two-Step Process

```
┌─────────────────────────────────────────────────────────────┐
│                       STEP 1: LLM-Only                       │
├─────────────────────────────────────────────────────────────┤
│  For each story:                                             │
│    For each variant (original, modified):                    │
│      For each chapter file (000.txt, 001.txt, ...):         │
│        → Send chapter to LLM                                 │
│        → Collect errors                                      │
│        → Record timing                                       │
│                                                              │
│  Output: step1_llm_results.json                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
            (External: Restart LLM server if needed)
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    STEP 2: Logic-Based                       │
├─────────────────────────────────────────────────────────────┤
│  For each story:                                             │
│    Reset ILASP/Clingo state (clean start)                   │
│    For each variant (original, modified):                    │
│      For each chapter file (000.txt, 001.txt, ...):         │
│        → Structure chapter with LLM → JSON                   │
│        → Convert JSON to ASP facts                           │
│        → Learn rules with ILASP (incremental)               │
│        → Check violations with Clingo                        │
│        → Record errors and timing                            │
│                                                              │
│  Output: step2_logic_results.json                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                       SUMMARIZE                              │
├─────────────────────────────────────────────────────────────┤
│  Compare results from Step 1 and Step 2                     │
│  Generate per-story and per-category breakdowns             │
│                                                              │
│  Output: experiment_summary.json                             │
└─────────────────────────────────────────────────────────────┘
```

### Chapter-by-Chapter Processing (NOT Story Consolidation)

**CONFIRMED: Each chapter file is processed independently.**

```
source_original_books/Harry Potter/
    ├── 000.txt  →  Sent to LLM/Logic independently
    ├── 001.txt  →  Sent to LLM/Logic independently
    ├── 002.txt  →  Sent to LLM/Logic independently
    └── ...      →  Each processed separately
```

For Step 2 (Logic), the evaluator accumulates facts across chapters within the same story, enabling incremental learning with ILASP.

---

## Files

### 1. `scripts/run_narrative_experiment.py` (~750 lines)

The main experiment orchestrator implementing the two-step design.

#### Data Classes

- `ChapterError` - Error detected in a specific chapter (category, type, description, fragment)
- `ChapterResult` - Complete result for one chapter (story, variant, chapter_file, errors, timing)
- `StepResults` - Aggregated results for one step (chapters_processed, total_errors, results list)

#### Key Classes

**`LLMClient`**
- Simple HTTP client for LLM interaction
- Sends individual chapters for evaluation
- Parses JSON error responses
- Temperature: 0.0 for deterministic output

**`LogicEvaluator`**
- Per-story state management (reset between stories)
- LLM structuring: Chapter text → JSON (entities, events, relationships)
- ASP conversion: JSON → logic facts
- ILASP learning: Incremental rule learning from accumulated facts
- Clingo checking: Find violations using learned rules

#### Key Functions

**`run_step1_llm(experiment_dir, stories, llm_url)`**
- Processes all chapters with LLM-only approach
- Saves results to `step1_llm_results.json`

**`run_step2_logic(experiment_dir, stories, llm_url)`**
- Processes all chapters with logic-based approach
- Resets state between stories
- Saves results to `step2_logic_results.json`

**`generate_summary(experiment_dir)`**
- Loads both step results
- Generates comparison metrics
- Saves to `experiment_summary.json`

### 2. `scripts/ilasp_task_generator.py` (~500 lines)

Advanced ILASP task generation (unchanged from previous version).

---

## Usage

```bash
# 1. Start llamafile server
./Mistral-7B-Instruct-v0.3.Q5_1.llamafile --server --nobrowser --port 8080

# 2. Activate conda environment with ILASP support
conda activate tist26
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"

# 3. Run Step 1: LLM-only evaluation
python scripts/run_narrative_experiment.py \
    --step 1 \
    --experiment-name "my_experiment"

# 4. (Optional) Restart LLM server if needed

# 5. Run Step 2: Logic-based evaluation
python scripts/run_narrative_experiment.py \
    --step 2 \
    --experiment-name "my_experiment"

# 6. Generate comparison summary
python scripts/run_narrative_experiment.py \
    --summarize \
    --experiment-name "my_experiment"
```

### Command-Line Options

| Option | Description |
|--------|-------------|
| `--step 1` | Run Step 1 (LLM-only evaluation) |
| `--step 2` | Run Step 2 (Logic-based evaluation) |
| `--summarize` | Generate comparison summary |
| `--experiment-name NAME` | Name for experiment directory |
| `--llm-url URL` | LLM server URL (default: http://localhost:8080/v1) |
| `--stories S1 S2 ...` | Specific stories to process |

---

## Output Structure

```
experiments/
└── <experiment_name>/
    ├── step1_llm_results.json    # LLM-only evaluation results
    ├── step2_logic_results.json  # Logic-based evaluation results
    └── experiment_summary.json   # Comparison summary
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
          "description": "Character acts after being killed",
          "story_fragment": "..."
        }
      ],
      "duration_seconds": 12.5,
      "success": true
    }
  ]
}
```

### experiment_summary.json

```json
{
  "experiment_name": "my_experiment",
  "generated_at": "2026-01-28T20:00:00",
  "step1_llm": {
    "approach": "LLM-only",
    "chapters_processed": 125,
    "total_errors": 47
  },
  "step2_logic": {
    "approach": "Logic (ILASP + Clingo)",
    "chapters_processed": 125,
    "total_errors": 32
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

## Error Categories

| Category | Description |
|----------|-------------|
| **Causality** | Chekhov's gun violations, unexplained effects, missing causes |
| **Coherence** | Logical impossibilities (dead acting, trait violations) |
| **Temporal** | Time paradoxes, impossible sequences, duration violations |
| **Location** | Ubiquity errors, impossible travel, spatial contradictions |
| **Emotional** | Motivation mismatches, relationship contradictions |

---

## Key Design Decisions

### 1. Chapter-by-Chapter (NOT Consolidation)

Stories are **never** merged into a single prompt. Each `.txt` file is processed as a separate evaluation unit. This:
- Avoids context window limits
- Provides granular error attribution
- Matches how humans read stories (chapter by chapter)

### 2. Incremental Learning in Step 2

Within a single story (same variant), the logic evaluator:
- Accumulates ASP facts from previous chapters
- Runs ILASP to learn rules from accumulated knowledge
- Uses learned rules + new facts for Clingo checking

State is **reset** when switching to a new story or variant.

### 3. External Server Restart

The server restart between Step 1 and Step 2 is **external** (not scripted). This allows:
- Using different LLM configurations
- Manual verification before Step 2
- Flexibility in experiment workflow

### 4. Temperature 0

Both steps use temperature=0 for deterministic, reproducible results.

---

## Dependencies

Required in conda environment `tist26`:
- Python 3.10 (required for ILASP)
- clingo 5.8.0
- ILASP 4.4.0 (with LD_LIBRARY_PATH set)

---

## Notes

1. **CPU Mode Performance**: Each chapter takes ~30-60 seconds on CPU-only llamafile.

2. **Story Isolation**: Each story starts with clean ILASP/Clingo state - no cross-story knowledge transfer.

3. **Variant Independence**: Original and modified versions of the same story are processed independently.
