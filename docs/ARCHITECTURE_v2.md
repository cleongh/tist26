# Narrative Evaluation System - Restructured Architecture

## Overview

The narrative evaluation system has been restructured to analyze stories across **five error categories**:

1. **CAUSALITY** - Chekhov's gun, cause-effect violations, unexplained events
2. **COHERENCE** - Semantic/logical consistency, physical impossibility, state violations
3. **TEMPORAL** - Time ordering, duration, interval overlap violations  
4. **LOCATION** - Spatial constraints, ubiquity, impossible travel
5. **EMOTIONAL** - Character relationships, motivations, behavior consistency

## Architecture

```
                    ┌─────────────────┐
                    │   story.txt     │
                    └────────┬────────┘
                             │
            ┌────────────────┴────────────────┐
            │                                 │
            ▼                                 ▼
    ┌───────────────┐                ┌────────────────┐
    │  LLM Direct   │                │ LLM Structurer │
    │    Linting    │                │  (→ JSON)      │
    │ (5 categories)│                └───────┬────────┘
    └───────┬───────┘                        │
            │                                ▼
            │                        ┌───────────────┐
            │                        │ json_to_asp   │
            │                        │  (→ ASP)      │
            │                        └───────┬───────┘
            │                                │
            │                        ┌───────┴───────┐
            │                        │               │
            │                        ▼               ▼
            │                 ┌──────────┐   ┌──────────────┐
            │                 │ general  │   │   domain     │
            │                 │   .lp    │   │ module.lp    │
            │                 └────┬─────┘   └──────┬───────┘
            │                      │                │
            │                      └───────┬────────┘
            │                              │
            │                              ▼
            │                      ┌───────────────┐
            │                      │    Clingo     │
            │                      │  (Reasoner)   │
            │                      └───────┬───────┘
            │                              │
            └───────────────┬──────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   Combined    │
                    │    Report     │
                    │ (5 categories)│
                    └───────────────┘
```

## Files Created/Modified

### ASP Rules (rules/)

- **`general.lp`** - NEW: Domain-independent rules for all 5 categories
  - Temporal reasoning (overlap, precedes, meets)
  - Location/spatial reasoning (ubiquity, proximity)
  - Causality reasoning (Chekhov's gun, uncaused events)
  - Coherence reasoning (dead agent, non-edible food, physical limitations)
  - Emotional reasoning (harm loved, help enemy, emotion mismatch)

- **`base.lp`** - Previous merged rules (kept for backward compatibility)

### Python Scripts (scripts/)

- **`domain_generator.py`** - NEW: Generates domain-specific ASP rules
  - Extracts character relationships from stories
  - Builds location distance graph
  - Tracks emotional states
  - Generates experiment-specific rules

- **`experiment_runner.py`** - NEW: Comprehensive experiment orchestrator
  - Two-phase workflow: structure all stories first, then lint
  - Generates domain module from all stories
  - Runs both LLM and Logic linting
  - Produces detailed reports by category

- **`story_lint.py`** - Existing (unchanged)
- **`json_to_asp.py`** - Existing (unchanged)
- **`llm_structurer.py`** - Existing (unchanged)

### Prompts (prompts/)

- **`lint_prompt_v2.txt`** - NEW: 5-category LLM linting prompt
  - Structured output with category, type, description, story_fragment
  - Severity levels (low/medium/high)
  - Summary by category

- **`structure_prompt_v2.txt`** - NEW: Enhanced structuring prompt
  - Extracts relationships (loves, hates, fears, trusts)
  - Extracts emotional_states with causes
  - Builds location_graph with distances
  - Extracts causal_chains

### Test Stories (experiments/test_stories/)

Five stories with intentional errors across all categories:

1. **01_impossible_knight.txt** - Blind knight reads; ubiquity; harm loved; dead agent; Chekhov's gun
2. **02_broken_timeline.txt** - Temporal paradoxes; dead agent; duration violations; Chekhov's gun
3. **03_emotional_paradox.txt** - Harm loved; help enemy; emotion-action mismatch; approach feared
4. **04_spatial_nightmare.txt** - Ubiquity; impossible reach; instant teleportation; containment
5. **05_causality_disaster.txt** - Chekhov's gun (multiple); uncaused events; missing causes

## Error Category Details

### 1. CAUSALITY
- `chekhov_gun` - Significant object introduced but never used
- `uncaused_event` - Event happens without cause
- `effect_without_cause` - State change with no triggering event
- `precondition_missing` - Action without required precondition

### 2. COHERENCE
- `dead_agent` - Character acts after death
- `non_edible_food` - Eating inedible objects
- `physical_impossibility` - Blind reading, deaf hearing, mute speaking
- `focus_overlap` - Two attention-requiring tasks simultaneously

### 3. TEMPORAL
- `circular_time` - Time paradox (T1 < T2 < T1)
- `negative_duration` - Event ends before it starts
- `explicit_order_violated` - Stated sequence not honored

### 4. LOCATION
- `ubiquity` - Same character in two places simultaneously
- `proximity_required` - Interacting with distant objects
- `impossible_travel` - Instant travel between distant locations

### 5. EMOTIONAL
- `harm_loved` - Hurting someone loved without justification
- `help_enemy` - Helping someone hated without motivation
- `approach_feared` - Approaching feared entity without necessity
- `misplaced_trust` - Trusting proven untrustworthy character
- `state_action_mismatch` - Happy character mourning, sad celebrating

## Running Experiments

### Using experiment_runner.py

```bash
python3 scripts/experiment_runner.py \
    --name "my_experiment" \
    --stories-dir experiments/test_stories \
    --output-dir experiments \
    --llm-base-url "http://localhost:8080/v1" \
    --llm-timeout 1800 \
    --llm-model "auto"
```

### Output Structure

```
experiment_<name>-<start>-<end>-<uuid>/
├── config.json           # Experiment configuration
├── stories/              # Input stories as text files
├── llm_results/          # LLM lint JSON per story
├── logic_results/        # Logic lint JSON per story
├── structured_json/      # Structured story JSON
├── asp_facts/            # Generated ASP facts
├── domain_module.lp      # Generated domain-specific rules
├── logs/                 # Timestamped execution logs
├── report.md             # Comprehensive markdown report
└── summary.json          # Machine-readable summary
```

## Two-Module ASP Architecture

### General Module (rules/general.lp)
- Domain-independent rules
- Works with any story
- Defines violation predicates for all 5 categories
- Hooks for domain-specific predicates

### Domain Module (generated per experiment)
- Story-specific facts
- Character relationships (loves, hates, fears, trusts)
- Location distances (distant/2)
- Emotional states over time
- Custom causal rules

## Violation Output Format

New 4-argument format:
```prolog
violation(category, type, event, detail).
```

Examples:
```prolog
violation(location, ubiquity, e1, e2).
violation(coherence, dead_agent, e5, john).
violation(causality, chekhov_gun, sword, sword).
violation(emotional, harm_loved, e3, mary).
```

## Future Work

1. Extend domain generator to extract more relationships automatically
2. Add confidence levels to violations
3. Implement violation explanation via LLM
4. Add cross-story consistency checking
5. Implement incremental domain learning
