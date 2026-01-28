# ILASP Integration for Incremental Narrative Consistency Checking

## Overview

This document describes the ILASP (Inductive Learning of Answer Set Programs) integration for incremental narrative consistency checking. The system processes stories chapter by chapter, learning narrative rules as it goes, and detecting inconsistencies based on what it has learned.

## Key Principle: Complete Isolation

**Each experiment runs in TOTAL ISOLATION.** There is no data sharing between experiments.

```
Experiment 1: original_books/Harry Potter/
    → Start FRESH llamafile LLM server
    → Fresh ILASP/Clingo state  
    → Processes chapters 000.txt, 001.txt, ...
    → Kill LLM server (clear all state)
    → Reports: 0 errors (consistent story)

Experiment 2: modified_books/Harry Potter/
    → Start NEW FRESH llamafile LLM server
    → Fresh ILASP/Clingo state
    → Knows NOTHING from the original experiment
    → Processes chapters, finds INTERNAL inconsistencies
    → Kill LLM server
    → Reports: N errors (based on self-contradictions)
```

The modified story experiment detects errors based on **internal inconsistencies within itself**, not by comparing to the original.

## Local LLM Server

The system uses local llamafile models for text structuring. Available models:

| Model | File | Size | Context |
|-------|------|------|---------|
| `mistral-7b` | Mistral-7B-Instruct-v0.3.Q5_1.llamafile | 5.4 GB | 8192 |
| `gemma-3-12b` | google_gemma-3-12b-it-Q4_K_M.llamafile | 7.1 GB | 8192 |
| `deepseek-r1-7b` | DeepSeek-R1-Distill-Qwen-7B-Q8_0.llamafile | 7.8 GB | 4096 |

Models are located in: `/home/mrcorner/Workspace/models/`

### LLM Server Management

```bash
# List available models
python scripts/llm_server.py list

# Start server manually
python scripts/llm_server.py start --model mistral-7b

# Check status
python scripts/llm_server.py status

# Stop server
python scripts/llm_server.py stop

# Test server
python scripts/llm_server.py test "Hello, world!"
```

Note: When using `incremental_linter.py`, the LLM server is **automatically started and stopped** for each experiment.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     EXPERIMENT (ISOLATED)                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────┐                                          │
│  │ LlamafileServer     │ ← Started fresh, killed after experiment │
│  │ (mistral-7b, etc)   │                                          │
│  └─────────┬───────────┘                                          │
│            │                                                      │
│  ┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐  │
│  │ Chapter.txt │ → │ LLM Server       │ → │ Structured JSON │  │
│  └─────────────┘    │ Structure text   │    └────────┬────────┘  │
│                     └──────────────────┘             │           │
│                                                      ▼           │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    ILASP LEARNER (Fresh)                    │ │
│  │                                                             │ │
│  │   ┌─────────────────────┐    ┌────────────────────────┐    │ │
│  │   │ StoryKnowledge      │    │ Violation Checking     │    │ │
│  │   │ • Characters        │ ←→ │ • Dead agent check     │    │ │
│  │   │ • Locations         │    │ • Ubiquity check       │    │ │
│  │   │ • Objects           │    │ • Ownership check      │    │ │
│  │   │ • Relationships     │    │ • Trait check          │    │ │
│  │   │ • Events history    │    │ • Clingo integration   │    │ │
│  │   │ • Learned rules     │    └────────────────────────┘    │ │
│  │   └─────────────────────┘                                   │ │
│  │                                                             │ │
│  │   ┌─────────────────────┐                                   │ │
│  │   │ ILASP Learning      │                                   │ │
│  │   │ (or heuristics)     │                                   │ │
│  │   └─────────────────────┘                                   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

## Workflow

### Chapter 1 (First Chapter)
1. LLM structures the text → entities, events, relationships
2. Extract and store in knowledge base
3. Learn initial frame axioms (what persists)
4. **No checking** - nothing to check against yet

### Chapter 2+ (Subsequent Chapters)
1. LLM structures the text
2. **CHECK** new facts against accumulated knowledge:
   - Dead agent violations (dead character acting)
   - Ubiquity violations (character in two places)
   - Ownership violations (using object you don't have)
   - Trait violations (blind character seeing)
   - Clingo-based complex checks
3. **If violation found** → Report error
4. **Update** knowledge base with new information
5. **Learn** new rules via ILASP (or heuristics)

## Usage

### Single Story Experiment

```bash
# Using local llamafile (default)
python scripts/incremental_linter.py run-story original_books/Goosebumps/

# Specify model
python scripts/incremental_linter.py run-story original_books/Goosebumps/ --llm-model gemma-3-12b
```

### All Stories in Directory

```bash
python scripts/incremental_linter.py run-all original_books/
```

### Compare Original vs Modified

```bash
python scripts/incremental_linter.py compare \
    original_books/Goosebumps/ \
    modified_books/Goosebumps/
```

### Programmatic Usage

```python
from scripts.incremental_linter import run_story_experiment, compare_experiments

# Single experiment with local llamafile
result = run_story_experiment(
    story_dir="original_books/Goosebumps/",
    llm_model="mistral-7b",    # or gemma-3-12b, deepseek-r1-7b
    llm_provider="local",       # uses llamafile
    verbose=True,
)

print(f"Violations found: {result['total_violations']}")

# Compare experiments
comparison = compare_experiments(
    original_dir="original_books/Goosebumps/",
    modified_dir="modified_books/Goosebumps/",
    llm_model="mistral-7b",
)

print(f"Detection success: {comparison['detection_success']}")
```

## File Structure

```
scripts/
├── ilasp_learner.py         # Core learning module
│   ├── StoryKnowledge       # Accumulated knowledge class
│   └── ILASPLearner         # Incremental learner class
├── incremental_linter.py    # Main CLI
│   ├── IncrementalLinter    # Orchestrator class
│   └── CLI commands         # run-story, run-all, compare
├── llm_server.py            # Llamafile server manager
│   ├── LlamafileServer      # Server start/stop/chat
│   └── fresh_llm_server     # Context manager for isolation
└── llm_structurer.py        # LLM text structuring (existing)

rules/
├── ilasp_mode_declarations.las  # ILASP hypothesis space
├── general_narrative.lp         # Clingo rules
└── base.lp                      # Base rules

experiment_results/              # Output directory
└── {experiment_id}.json         # Results files
```

## Violation Categories

The system detects 5 categories of violations:

| Category   | Examples                                    |
|------------|---------------------------------------------|
| Causality  | Effect without cause, broken causal chain   |
| Coherence  | Dead agent acting, trait conflicts          |
| Temporal   | Time paradoxes, wrong event order           |
| Location   | Ubiquity, impossible travel                 |
| Emotional  | Sudden mood swings without trigger          |

## ILASP Configuration

### Mode Declarations

The file `rules/ilasp_mode_declarations.las` defines what ILASP can learn:

- **Frame axioms**: What persists (alive, location, ownership)
- **Causal rules**: What causes what
- **Violation patterns**: What constitutes an error

### Fallback Mode

If ILASP is not installed, the system falls back to heuristic rule learning:

```python
# Heuristic rules learned automatically
stays_dead(C) :- dead(C).
cannot_act(C) :- dead(C).
```

## Installation

### Python Dependencies

```bash
pip install -r requirements.txt
```

### ILASP (Optional)

ILASP must be installed separately from: https://doc.ilasp.com/installation.html

After installation, ensure the `ILASP` binary is in your PATH.

The system works without ILASP using built-in heuristics.

## Output Format

Results are saved as JSON:

```json
{
  "experiment_id": "original_books_Goosebumps_20250101_120000",
  "story_dir": "/path/to/original_books/Goosebumps",
  "start_time": "2025-01-01T12:00:00",
  "end_time": "2025-01-01T12:05:00",
  "chapters": [
    {
      "chapter_num": 1,
      "file": "001.txt",
      "violations": [],
      "entities_found": 5,
      "events_found": 12
    },
    {
      "chapter_num": 2,
      "file": "002.txt",
      "violations": [
        {
          "category": "coherence",
          "type": "dead_agent",
          "event": "e15",
          "detail": "Character 'bob' died in chapter 1",
          "description": "Character 'bob' performs action 'speak' but died in chapter 1",
          "chapter": 2,
          "severity": "high"
        }
      ],
      "entities_found": 3,
      "events_found": 8
    }
  ],
  "total_violations": 1,
  "violations_by_category": {
    "coherence": 1
  }
}
```

## How Detection Works

The key insight is that **modified stories contain internal inconsistencies**:

1. **Original story**: Alice dies in chapter 5. No actions by Alice after chapter 5. → Consistent
2. **Modified story**: Alice dies in chapter 5. Alice speaks in chapter 7. → **INTERNAL INCONSISTENCY**

The system doesn't need to know the "correct" version. It detects that the modified story **contradicts itself**.

## Extending the System

### Adding New Violation Checks

Add to `ILASPLearner._check_chapter()`:

```python
def _check_custom_violation(self, structured_json, chapter_num):
    violations = []
    # Your logic here
    return violations
```

### Adding New Entity Types

Extend `StoryKnowledge.__init__()` and `_extract_entities()`.

### Adding New Learned Rules

Extend `rules/ilasp_mode_declarations.las` with new `#modeh` and `#modeb` declarations.
