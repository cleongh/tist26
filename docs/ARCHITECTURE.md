# Architecture Overview: Narrative Consistency Checker

## High-Level System Design

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           NARRATIVE CONSISTENCY CHECKER                              │
│                                                                                     │
│  A Hybrid LLM + Logic Programming System for Story Analysis                         │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                    ┌──────────────┐
                                    │  story.txt   │
                                    │   (Input)    │
                                    └──────┬───────┘
                                           │
                         ┌─────────────────┴─────────────────┐
                         │                                   │
                         ▼                                   ▼
              ┌─────────────────────┐             ┌─────────────────────┐
              │   DIRECT LLM LINT   │             │   LOGIC-BASED LINT  │
              │   (Pattern-based)   │             │   (Formal reasoning)│
              └──────────┬──────────┘             └──────────┬──────────┘
                         │                                   │
                         │                    ┌──────────────┼──────────────┐
                         │                    │              │              │
                         │                    ▼              ▼              ▼
                         │           ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
                         │           │    LLM      │ │  json_to_   │ │   Clingo    │
                         │           │ Structurer  │ │   asp.py    │ │  Reasoner   │
                         │           │  (→ JSON)   │ │  (→ ASP)    │ │ (→ Results) │
                         │           └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
                         │                  │              │              │
                         │                  └──────────────┴──────────────┘
                         │                                   │
                         │                                   ▼
                         │                        ┌─────────────────────┐
                         │                        │  LLM Interpreter    │
                         │                        │ (Violations → Text) │
                         │                        └──────────┬──────────┘
                         │                                   │
                         └───────────────┬───────────────────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │   Combined Report   │
                              │   + output.json     │
                              └─────────────────────┘
```

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               DATA FLOW                                          │
└──────────────────────────────────────────────────────────────────────────────────┘

1. INPUT PROCESSING
   ─────────────────

   story.txt                    Natural language narrative
       │
       ▼
   story_lint.py                Main orchestrator, reads story
       │
       ├─────────────────────────────────────────┐
       │                                         │
       ▼                                         ▼

2. PARALLEL ANALYSIS PATHS
   ─────────────────────────

   PATH A: LLM Direct Lint              PATH B: Logic-Based Lint
   ─────────────────────────            ──────────────────────────

   LLM_LINT_PROMPT                      llm_structurer.py
   + story.txt                          + structure_prompt.txt
       │                                + story.txt
       │                                    │
       ▼                                    ▼
   call_*_json()                        call_*() LLM API
   (OpenAI/Gemini/Guidance)                 │
       │                                    ▼
       ▼                                Structured JSON
   {                                    {
     "error_count": 2,                    "entities": {...},
     "errors": [...]                      "events": [...],
   }                                      "traits": [...]
                                        }
                                            │
                                            ▼
                                        json_to_asp.py
                                            │
                                            ▼
                                        ASP Facts (facts.lp)
                                        ─────────────────────
                                        character(hansel).
                                        event(e1).
                                        event_type(e1, eat).
                                        patient(e1, bread).
                                        time(e1, t1, t1).
                                            │
                                            ▼
                                        Clingo Solver
                                        + rules/base.lp
                                            │
                                            ▼
                                        Raw Violations
                                        ─────────────────
                                        violation(non_edible, e5)
                                        violation(dead_agent, e12)
                                            │
                                            ▼
                                        LLM Interpreter
                                            │
                                            ▼
                                        {
                                          "error_count": 2,
                                          "errors": [
                                            {"id": "...", "description": "..."}
                                          ]
                                        }

3. OUTPUT GENERATION
   ─────────────────

       ├──────────────────────────────────────┤
       │                                      │
       ▼                                      ▼
   stdout (JSON)                        output.json
   Current results only                 Full history with
                                        prompts, responses,
                                        ASP facts, config
```

## Component Details

### 1. story_lint.py (Main Orchestrator)

**Responsibility**: Command-line interface, configuration, orchestration

```
┌─────────────────────────────────────────────────────────────────┐
│                        story_lint.py                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CONFIGURATION                                                  │
│  ─────────────                                                  │
│  • Parse command-line arguments                                 │
│  • Load environment variables (.env)                            │
│  • Resolve model IDs (auto-detect from API)                     │
│  • Validate API keys                                            │
│                                                                 │
│  LLM API ABSTRACTION                                            │
│  ────────────────────                                           │
│  • call_openai_json(): OpenAI-compatible APIs                   │
│  • call_gemini_json(): Google Gemini API                        │
│  • call_guidance_json(): Constrained generation                 │
│                                                                 │
│  LINTING PIPELINES                                              │
│  ─────────────────                                              │
│  • llm_lint(): Direct LLM analysis                              │
│  • logic_lint(): Full logic pipeline                            │
│                                                                 │
│  OUTPUT MANAGEMENT                                              │
│  ─────────────────                                              │
│  • Write results to stdout                                      │
│  • Append to output.json with full details                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2. llm_structurer.py (Semantic Parser)

**Responsibility**: Convert narrative text to structured JSON via LLM

```
┌─────────────────────────────────────────────────────────────────┐
│                      llm_structurer.py                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PROMPT HANDLING                                                │
│  ───────────────                                                │
│  • Load template from prompts/structure_prompt.txt              │
│  • Replace {{STORY}} with actual story text                     │
│                                                                 │
│  LLM BACKENDS                                                   │
│  ────────────                                                   │
│  • call_openai(): OpenAI-compatible chat completion             │
│  • call_gemini(): Google Gemini generateContent                 │
│  • call_guidance(): Constrained JSON generation                 │
│                                                                 │
│  JSON EXTRACTION                                                │
│  ───────────────                                                │
│  • extract_json(): Find JSON in LLM output                      │
│  • strip_think(): Remove <think> reasoning blocks               │
│  • basic_validate(): Add defaults for missing fields            │
│                                                                 │
│  PUBLIC API                                                     │
│  ──────────                                                     │
│  structure_story(story_text, **options) -> dict                 │
│    - return_details=True: Include prompts and raw responses     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3. json_to_asp.py (Logic Encoder)

**Responsibility**: Convert structured JSON to ASP facts

```
┌─────────────────────────────────────────────────────────────────┐
│                        json_to_asp.py                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  SYMBOL HANDLING                                                │
│  ───────────────                                                │
│  • sanitize_symbol(): Convert to valid ASP atom                 │
│    - Lowercase, alphanumeric + underscore only                  │
│    - Handle arrays by joining with __                           │
│                                                                 │
│  FACT GENERATION                                                │
│  ───────────────                                                │
│  • emit_fact(): Create "functor(args)." string                  │
│                                                                 │
│  CONVERSION SECTIONS                                            │
│  ───────────────────                                            │
│  • Characters → character(id).                                  │
│  • Objects → object(id). type(id).                              │
│  • Locations → location(id).                                    │
│  • Events → event(id). event_type(id,type). agent(id,who). ...  │
│  • Time ordering → time_order(t1,t2).                           │
│  • Fluents → holds(fluent(...),start,end).                      │
│  • Traits → trait(character,trait).                             │
│  • Rules → precondition(...). causes(...).                      │
│                                                                 │
│  PUBLIC API                                                     │
│  ──────────                                                     │
│  json_to_asp(data, include_candidates=False) -> str             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4. rules/base.lp (Logic Rules)

**Responsibility**: Define consistency rules in ASP

```
┌─────────────────────────────────────────────────────────────────┐
│                         rules/base.lp                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TEMPORAL REASONING                                             │
│  ─────────────────                                              │
│  • before/2: Transitive temporal ordering                       │
│  • overlap/2: Events with intersecting intervals                │
│  • precedes/2, meets/2: Event sequence relations                │
│                                                                 │
│  FLUENT REASONING                                               │
│  ────────────────                                               │
│  • holds_at/2: Fluent value at time point                       │
│  • Frame axiom: Fluents persist unless changed                  │
│  • causes/4: Event effects                                      │
│  • precondition/4: Event requirements                           │
│                                                                 │
│  SPATIAL REASONING                                              │
│  ─────────────────                                              │
│  • at_during/3: Entity location during event                    │
│  • Ubiquity check: No bilocation                                │
│                                                                 │
│  WORLD KNOWLEDGE                                                │
│  ───────────────                                                │
│  • Edibility defaults (rocks not edible, bread is)              │
│  • Living/dead state tracking                                   │
│                                                                 │
│  TRAIT CONSTRAINTS                                              │
│  ─────────────────                                              │
│  • Phobias: claustrophobia, acrophobia, aquaphobia              │
│  • Physical: blind, deaf, mute limitations                      │
│                                                                 │
│  VIOLATION DETECTION                                            │
│  ───────────────────                                            │
│  • violation(Type, Event): Something is inconsistent            │
│  • violation(Type, E1, E2): Two events conflict                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Violation Types Reference

| Violation | Arguments | Description |
|-----------|-----------|-------------|
| `ubiquity` | E1, E2 | Character in two places at once |
| `focus_overlap` | E1, E2 | Two focus-requiring tasks simultaneously |
| `non_edible_food` | E | Eating something non-edible |
| `dead_agent` | E | Dead character performing action |
| `claustrophobia` | E | Claustrophobic entering enclosed space |
| `acrophobia` | E | Acrophobic at height |
| `aquaphobia` | E | Aquaphobic in/near water |
| `physical_impossibility` | E | Action impossible due to disability |
| `precondition_not_met` | E, Pred | Required condition not satisfied |
| `precondition_violated` | E, Pred | Forbidden condition is true |

## File Dependencies

```
                         story_lint.py
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
    llm_structurer.py   json_to_asp.py   rules/base.lp
              │               │
              ▼               │
prompts/structure_prompt.txt  │
                              │
              ┌───────────────┘
              ▼
    [Clingo solver - external]
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Core Language | Python 3.10+ | Main implementation |
| Logic Solver | Clingo (Python API) | ASP reasoning |
| LLM APIs | OpenAI, Gemini, Guidance | Natural language processing |
| Data Format | JSON | Intermediate representation |
| Config | .env files | API keys and settings |

## Extension Points

1. **New Violation Types**: Add rules to `rules/base.lp`
2. **New LLM Backends**: Add `call_*` functions to `story_lint.py`
3. **New Entity Types**: Extend `json_to_asp.py` conversion
4. **New Traits**: Add trait-specific rules to `base.lp`
5. **Custom Prompts**: Create new templates in `prompts/`
