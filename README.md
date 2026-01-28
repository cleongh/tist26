# 📖 Narrative Consistency Checker

A hybrid AI system that combines **Large Language Model (LLM) analysis** with **Answer Set Programming (ASP) logic reasoning** to detect inconsistencies, errors, and logical violations in narrative texts.

## 📚 Documentation

For comprehensive documentation, see the [docs/](docs/) folder:

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow diagrams, component details |
| [SCHEMA.md](docs/SCHEMA.md) | Complete JSON schema reference for structured stories |
| [ASP_RULES.md](docs/ASP_RULES.md) | Answer Set Programming rules explained in detail |
| [LLM_INTEGRATION.md](docs/LLM_INTEGRATION.md) | LLM backend configuration and usage |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | Python module API documentation |
| [EXAMPLES.md](docs/EXAMPLES.md) | Worked examples and tutorials |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions |

## 🎯 Overview

This tool performs "story linting" - analyzing narrative texts for:

- **Temporal conflicts**: Events happening in impossible orders, dead characters acting, etc.
- **Spatial impossibilities**: Characters being in two places at once
- **Causality errors**: Effects without proper causes, missing preconditions
- **World-knowledge violations**: Eating inedible objects, physical impossibilities
- **Character trait conflicts**: Claustrophobic characters entering enclosed spaces, blind characters reading

The system uses a two-phase approach:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NARRATIVE CONSISTENCY CHECKER                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Story Text ──► LLM Structurer ──► JSON ──► ASP Facts ──► Clingo ──► Violations
│       │              │                          │              │           │
│       │              ▼                          ▼              │           │
│       │     (Semantic Parsing)         (Logic Encoding)        │           │
│       │                                                        │           │
│       └──────────────────► LLM Direct Lint ────────────────────┘           │
│                           (Pattern Matching)                               │
│                                                                             │
│   Both paths contribute to final error report                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Hybrid?

| Approach | Strengths | Weaknesses |
|----------|-----------|------------|
| **LLM-only** | Good at subtle/contextual issues, flexible | Can hallucinate, inconsistent, no formal guarantees |
| **Logic-only** | Sound, complete, explainable | Requires formal encoding, misses nuance |
| **Hybrid** | Best of both: formal reasoning + contextual understanding | More complex setup |

## 🚀 Quick Start

### Prerequisites

```bash
# Python 3.10+ required
python --version  # Should be 3.10 or higher

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```bash
# Using a local LLM server (e.g., llamafile, ollama)
python scripts/story_lint.py story.txt

# Using Gemini API
source .env  # Load GEMINI_API_KEY
python scripts/story_lint.py \
  --llm-backend gemini \
  --llm-model gemini-2.5-flash \
  --llm-api-key "$GEMINI_API_KEY" \
  --llm-base-url "https://generativelanguage.googleapis.com/v1beta" \
  --struct-backend gemini \
  --struct-model gemini-2.5-flash \
  --struct-api-key "$GEMINI_API_KEY" \
  --struct-base-url "https://generativelanguage.googleapis.com/v1beta" \
  story.txt

# Using OpenAI API
export OPENAI_API_KEY="your-key"
python scripts/story_lint.py \
  --llm-backend openai \
  --llm-model gpt-4o \
  --llm-base-url "https://api.openai.com/v1" \
  --struct-backend openai \
  --struct-model gpt-4o \
  --struct-base-url "https://api.openai.com/v1" \
  story.txt
```

## 📁 Project Structure

```
codigo/
├── README.md                    # This file - comprehensive documentation
├── requirements.txt             # Python dependencies
├── story.txt                    # Sample story for testing (Hansel & Gretel)
├── output.json                  # Execution history with all details
│
├── scripts/                     # Main Python modules
│   ├── story_lint.py           # Main orchestrator (CLI entry point)
│   ├── llm_structurer.py       # LLM-based story→JSON conversion
│   ├── json_to_asp.py          # JSON→ASP facts converter
│   └── run_reasoner.py         # Legacy standalone reasoner (deprecated)
│
├── prompts/                     # LLM prompt templates
│   └── structure_prompt.txt    # Prompt for semantic parsing
│
├── rules/                       # ASP reasoning rules
│   └── base.lp                 # Core narrative consistency rules
│
└── examples/                    # Example files
    ├── story.txt               # Example story
    └── story.json              # Example structured output
```

## 🔧 Configuration

### Command-Line Arguments

The `story_lint.py` script accepts many configuration options:

#### Mode Selection
```bash
--mode {llm,logic,both}   # Which lint modes to run (default: both)
                          # - llm: LLM-only direct analysis
                          # - logic: ASP logic reasoning only
                          # - both: Run both and combine results
```

#### LLM Configuration (for direct linting)
```bash
--llm-model MODEL         # Model name/ID (default: auto - auto-detect)
--llm-base-url URL        # API endpoint (default: http://localhost:8080/v1)
--llm-api-key KEY         # API key (or set LLM_API_KEY env var)
--llm-backend {openai,guidance,gemini}  # API format (default: openai)
--llm-no-auth             # Skip Authorization header (for local servers)
--llm-temperature FLOAT   # Sampling temperature (default: 0.0)
--llm-timeout SECONDS     # Request timeout (default: 600)
--llm-max-tokens INT      # Max output tokens (default: 2048)
--llm-retries INT         # Retry count on failure (default: 3)
--llm-backoff SECONDS     # Initial backoff between retries (default: 5)
--llm-thinking-budget INT # Gemini thinking budget (default: 0)
```

#### Structurer Configuration (for JSON conversion)
```bash
--struct-model MODEL      # Model for structuring (default: auto)
--struct-base-url URL     # API endpoint for structurer
--struct-api-key KEY      # API key for structurer
--struct-backend {openai,guidance,gemini}  # API format
--struct-no-auth          # Skip auth for structurer
--struct-timeout SECONDS  # Timeout (default: 600)
--struct-max-tokens INT   # Max tokens (default: 8192)
--struct-retries INT      # Retries (default: 5)
--struct-backoff SECONDS  # Backoff (default: 30)
--struct-thinking-budget INT  # Gemini thinking budget (default: 0)
```

#### Other Options
```bash
--include-candidates      # Include candidate_rules in ASP facts
--mock                    # Use examples/story.json instead of LLM
--mock-llm                # Skip LLM lint, return mock response
--no-interpret            # Skip LLM interpretation of violations
```

### Environment Variables

Create a `.env` file for sensitive configuration:

```bash
# .env file
GEMINI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key
LLM_BASE_URL=http://localhost:8080/v1
LLM_API_KEY=local
```

Load with: `source .env`

## 📊 Output Format

Results are written to both stdout and appended to `output.json`:

### Stdout (Current Run)
```json
{
  "llm_lint": {
    "error_count": 0,
    "errors": [],
    "details": { ... }
  },
  "logic_lint": {
    "error_count": 1,
    "errors": [
      {
        "id": "non_edible_food_e14",
        "description": "Character tried to eat a non-edible object."
      }
    ],
    "raw_violations": ["violation(non_edible_food, e14)"],
    "details": { ... }
  },
  "total_errors": 1
}
```

### output.json (Full History)

The `output.json` file contains complete execution history with all details for debugging and analysis:

```json
[
  {
    "command": "python scripts/story_lint.py story.txt",
    "start_time": "2026-01-16T12:00:00",
    "end_time": "2026-01-16T12:00:30",
    "duration_seconds": 30.5,
    "config": {
      "mode": "both",
      "llm": { "model": "gemini-2.5-flash", ... },
      "structurer": { "model": "gemini-2.5-flash", ... }
    },
    "story_path": "story.txt",
    "story": "Once upon a time...",
    "result": {
      "llm_lint": {
        "error_count": 0,
        "errors": [],
        "details": {
          "prompt": "You are a narrative linting assistant...",
          "raw_response": "{\"error_count\": 0, ...}",
          "model": "gemini-2.5-flash",
          "backend": "gemini"
        }
      },
      "logic_lint": {
        "error_count": 0,
        "errors": [],
        "details": {
          "structurer": {
            "prompt": "SYSTEM: You are a semantic parser...",
            "raw_response": "{\"entities\": {...}, ...}",
            "parsed": { ... },
            "model": "gemini-2.5-flash"
          },
          "asp_facts": "character(hansel).\ncharacter(gretel).\n...",
          "asp_rules": "% NARRATIVE CONSISTENCY CHECKER...\n..."
        }
      }
    }
  }
]
```

---

## 🧠 How It Works

### Phase 1: Story Structuring (LLM → JSON)

The LLM converts free-form narrative text into structured JSON:

**Input (story.txt):**
```
Once upon a time there was a poor woodcutter who lived with his two children,
Hansel and Gretel. The mother died, and the father took a new wife...
```

**Output (structured JSON):**
```json
{
  "entities": {
    "characters": [
      {"id": "woodcutter"},
      {"id": "hansel"},
      {"id": "gretel"},
      {"id": "stepmother"},
      {"id": "witch"}
    ],
    "objects": [
      {"id": "pebbles", "type": "white pebbles"},
      {"id": "bread", "type": "bread"},
      {"id": "cottage", "type": "cottage"}
    ],
    "locations": [
      {"id": "home"},
      {"id": "forest"},
      {"id": "witch_house"}
    ]
  },
  "events": [
    {
      "id": "e1",
      "type": "die",
      "agent": "mother",
      "time": {"start": "t1"}
    },
    {
      "id": "e2",
      "type": "abandon",
      "agent": "woodcutter",
      "patient": ["hansel", "gretel"],
      "location": "forest",
      "time": {"start": "t2"}
    }
  ],
  "traits": [
    {"character": "stepmother", "trait": "cruel"},
    {"character": "witch", "trait": "evil"}
  ]
}
```

### Phase 2: JSON to ASP Facts

The structured JSON is converted to ASP (Answer Set Programming) facts:

```prolog
% Characters
character(woodcutter).
character(hansel).
character(gretel).
character(stepmother).
character(witch).

% Objects with types
object(pebbles).
white_pebbles(pebbles).
object(bread).
bread(bread).
object(cottage).
cottage(cottage).

% Events
event(e1).
event_type(e1, die).
agent(e1, mother).
time(e1, t1, t1).

event(e2).
event_type(e2, abandon).
agent(e2, woodcutter).
patient(e2, hansel).
patient(e2, gretel).
location(e2, forest).
time(e2, t2, t1).

% Temporal ordering
time_order(t1, t2).
time_order(t2, t3).

% Character traits
trait(stepmother, cruel).
trait(witch, evil).
```

### Phase 3: ASP Reasoning (Clingo)

The ASP facts are combined with reasoning rules (`rules/base.lp`) and solved by Clingo:

```prolog
% Example rule: eating requires edible food
violation(non_edible_food, E) :-
    event(E),
    event_type(E, eat),
    patient(E, X),
    not edible(X).

% Example rule: dead characters cannot act
violation(dead_agent, E) :-
    event(E),
    agent(E, C),
    time(E, Tstart, _),
    dead_after(C, Tdeath),
    before(Tdeath, Tstart).
```

### Phase 4: Violation Interpretation

Raw violations like `violation(non_edible_food, e14)` are interpreted by the LLM into human-readable explanations:

```json
{
  "id": "non_edible_food_e14",
  "description": "The children tried to eat from the cottage walls, but cottages are not edible food items."
}
```

---

## 📜 ASP Rules Reference

The `rules/base.lp` file contains all the reasoning rules. Here's a detailed breakdown:

### Part 1: Temporal Reasoning

```prolog
% Collect all time points from events and fluents
time_point(T) :- time(_, T, _).
time_point(T) :- time(_, _, T).

% Transitive closure of time ordering
% If T1 < T2 and T2 < T3, then T1 < T3
before(T1, T2) :- time_order(T1, T2).
before(T1, T3) :- before(T1, T2), before(T2, T3).

% Events overlap if their intervals intersect
% E1: [S1, End1], E2: [S2, End2] overlap if
% NOT (End1 < S2) AND NOT (End2 < S1)
overlap(E1, E2) :-
    event(E1), event(E2),
    time(E1, S1, End1), time(E2, S2, End2),
    not before(End1, S2),
    not before(End2, S1),
    E1 != E2.
```

### Part 2: Fluent Reasoning

Fluents are time-varying properties (e.g., "the door is open", "Alice is alive"):

```prolog
% A fluent holds during its explicit interval
holds_at(F, T) :-
    holds(F, Start, End),
    time_point(T),
    not before(T, Start),
    not before(End, T).

% Events can cause fluents to become true or false
holds_at(fluent(Pred, Arg), End) :-
    event(E), event_type(E, Type),
    causes(Type, pos, Pred, Role),  % pos = positive effect
    role_arg(E, Role, Arg),
    time(E, _, End).

% Fluent persistence (frame axiom): fluents persist unless negated
holds_at(F, T2) :-
    holds_at(F, T1),
    before(T1, T2),
    time_point(T2),
    not holds_at_negated(F, T2).
```

### Part 3: Spatial Reasoning

```prolog
% Ubiquity violation: same agent in two different places simultaneously
violation(ubiquity, E1, E2) :-
    event(E1), event(E2),
    agent(E1, A), agent(E2, A),       % Same agent
    location(E1, L1), location(E2, L2),
    L1 != L2,                          % Different locations
    overlap(E1, E2).                   % At the same time
```

### Part 4: Focus/Attention Constraints

```prolog
% An agent cannot do two focus-requiring tasks simultaneously
violation(focus_overlap, E1, E2) :-
    event(E1), event(E2),
    requires_focus(E1), requires_focus(E2),
    agent(E1, A), agent(E2, A),
    overlap(E1, E2),
    E1 < E2.  % Avoid duplicate violations
```

### Part 5: World Knowledge

```prolog
% Edibility rules
non_edible(X) :- rock(X).
non_edible(X) :- metal(X).
non_edible(X) :- cottage(X).  % Houses aren't food!
non_edible(X) :- pebbles(X).

edible(X) :- object(X), not non_edible(X).  % Default: objects are edible
edible(X) :- bread(X).  % Bread is always edible
edible(X) :- food(X).

% Violation: eating something non-edible
violation(non_edible_food, E) :-
    event(E),
    event_type(E, eat),
    patient(E, X),
    not edible(X).

% Death tracking
dead_after(C, T) :- event(E), event_type(E, die), agent(E, C), time(E, _, T).
dead_after(C, T) :- event(E), event_type(E, kill), patient(E, C), time(E, _, T).

% Dead characters can't act
violation(dead_agent, E) :-
    event(E),
    agent(E, C),
    time(E, Tstart, _),
    dead_after(C, Tdeath),
    before(Tdeath, Tstart).
```

### Part 6: Character Trait Constraints

```prolog
% Phobia violations
violation(claustrophobia, E) :-
    trait(A, claustrophobic),
    event(E), agent(E, A),
    event_type(E, enter),
    location(E, L),
    enclosed_space(L).

enclosed_space(elevator).
enclosed_space(closet).
enclosed_space(cave).

% Physical limitations
violation(physical_impossibility, E) :-
    trait(A, blind),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_sight(Type).

requires_sight(read).
requires_sight(watch).
requires_sight(see).
```

### Part 7: Possession Tracking

```prolog
% Track when agents acquire objects
has_after(Agent, Object, T) :-
    event(E), event_type(E, take),
    agent(E, Agent), patient(E, Object),
    time(E, _, T).
```

### Part 8: Preconditions and Effects

```prolog
% State change effects
causes(open, pos, open, patient).    % Opening makes things open
causes(close, neg, open, patient).   % Closing makes things not-open
causes(lock, pos, locked, patient).
causes(unlock, neg, locked, patient).

% Sleep/wake cycle
causes(sleep, pos, asleep, agent).
causes(wake, neg, asleep, agent).
precondition(wake, pos, asleep, agent).  % Must be asleep to wake
```

---

## 🔌 LLM Backend Support

### OpenAI-Compatible APIs (Default)

Works with any OpenAI-compatible API:
- OpenAI (gpt-4o, gpt-4-turbo, gpt-3.5-turbo)
- Llamafile (local)
- Ollama (local)
- vLLM (local)
- LM Studio (local)
- Together AI
- Anyscale

```bash
# Local llamafile
python scripts/story_lint.py --llm-base-url http://localhost:8080/v1 story.txt

# OpenAI
python scripts/story_lint.py \
  --llm-backend openai \
  --llm-model gpt-4o \
  --llm-base-url https://api.openai.com/v1 \
  --llm-api-key "$OPENAI_API_KEY" \
  story.txt
```

### Google Gemini

Native support for Gemini API with thinking budget:

```bash
python scripts/story_lint.py \
  --llm-backend gemini \
  --llm-model gemini-2.5-flash \
  --llm-base-url https://generativelanguage.googleapis.com/v1beta \
  --llm-api-key "$GEMINI_API_KEY" \
  --llm-thinking-budget 1024 \
  story.txt
```

### Guidance (Structured Generation)

Uses the `guidance` library for constrained JSON generation:

```bash
pip install guidance
python scripts/story_lint.py \
  --llm-backend guidance \
  --llm-model gpt-4o \
  story.txt
```

---

## 🧪 Testing & Development

### Mock Mode (No LLM Required)

Test the logic pipeline without LLM calls:

```bash
# Use pre-made structured JSON
python scripts/story_lint.py --mock story.txt

# Skip LLM lint entirely
python scripts/story_lint.py --mock --mock-llm story.txt
```

### VS Code Task

The project includes a VS Code task for quick testing:

```json
{
  "label": "Run story linter (.venv)",
  "type": "shell",
  "command": "${workspaceFolder}/.venv/bin/python",
  "args": [
    "${workspaceFolder}/scripts/story_lint.py",
    "${workspaceFolder}/story.txt"
  ]
}
```

Run with: `Ctrl+Shift+B` or Terminal → Run Task

### Debug Output

All modules log to stderr with prefixes for tracing:

```
[story_lint] Story lint starting.
[story_lint] Mode=both LLM=gemini-2.5-flash Struct=gemini-2.5-flash
[llm_structurer] Calling Gemini for story structuring.
[story_lint] Converting structured JSON -> ASP facts.
[story_lint] Running clingo reasoner.
[story_lint] Found 0 violations via clingo Python API.
```

---

## 📚 JSON Schema Reference

### Structured Story Schema

The LLM outputs JSON conforming to this schema:

```typescript
interface StructuredStory {
  schema_version: string;  // "1.0"
  
  entities: {
    characters: Array<{
      id: string;          // Unique identifier (e.g., "hansel")
    }>;
    objects: Array<{
      id: string;          // Unique identifier (e.g., "pebbles")
      type: string;        // Object type (e.g., "white pebbles")
    }>;
    locations: Array<{
      id: string;          // Unique identifier (e.g., "forest")
    }>;
  };
  
  events: Array<{
    id: string;            // Unique identifier (e.g., "e1")
    type: string;          // Event type (e.g., "die", "eat", "take")
    agent: string | string[];    // Who performs the action
    patient?: string | string[]; // Who/what receives the action
    location?: string;     // Where it happens
    time: {
      start: string;       // Start time point (e.g., "t1")
      end?: string;        // End time point (default: same as start)
    };
    requires_focus?: boolean;  // Does this need full attention?
  }>;
  
  fluents: Array<{
    id: string;            // Fluent predicate (e.g., "alive(hansel)")
    time: {
      start: string;       // When fluent becomes true
      end: string;         // When fluent becomes false
    };
  }>;
  
  traits: Array<{
    character: string;     // Character ID
    trait: string;         // Trait name (e.g., "cruel", "blind")
  }>;
  
  rules: Array<{
    id: string;            // Rule identifier
    type: "causal" | "precondition";
    head: string;          // Event/fluent affected
    body: string;          // Condition
  }>;
  
  constraints: Array<{
    id: string;            // Constraint identifier
    type: string;          // Constraint type (e.g., "ordering")
    description: string;   // Human-readable description
    body: string;          // Formal constraint
  }>;
  
  candidate_rules: Array<{
    id: string;            // Rule identifier
    type: string;          // Rule type
    rule: string;          // The proposed rule
    confidence: "high" | "low";
  }>;
}
```

---

## 🔍 Troubleshooting

### Common Issues

#### "clingo Python module not available"
```bash
pip install clingo
```

#### "Missing GEMINI_API_KEY"
```bash
export GEMINI_API_KEY="your-api-key"
# or create .env file and source it
```

#### ASP Parsing Errors
If you see errors like `syntax error, unexpected <IDENTIFIER>`:
- Check that object types don't contain spaces (the converter sanitizes them)
- Check `output.json` for the generated ASP facts to debug

#### LLM Returns Invalid JSON
- Increase `--llm-max-tokens` (default: 2048)
- Try a more capable model
- Check the `raw_response` in `output.json`

#### Timeout Errors
- Increase `--llm-timeout` (default: 600 seconds)
- Reduce story length
- Use a faster model

### Debug Mode

For detailed debugging, check `output.json` which contains:
- All prompts sent to LLMs
- Raw responses received
- Generated ASP facts
- Full configuration used

---

## 📄 License

[Specify your license here]

## 🤝 Contributing

[Contribution guidelines here]

## 📧 Contact

[Contact information here]
