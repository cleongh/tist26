# API Reference

## Module: story_lint

Main orchestrator module for narrative consistency checking.

### Command Line Interface

```bash
python scripts/story_lint.py [OPTIONS] STORY_FILE
```

#### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `STORY_FILE` | path | ✅ | Path to the story text file |

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--backend` | string | `openai` | LLM backend: `openai`, `gemini`, `guidance` |
| `--model` | string | `auto` | Model identifier (or "auto" for auto-detection) |
| `--api-key` | string | env var | API key (overrides environment variable) |
| `--api-base` | string | env var | API base URL (for OpenAI-compatible backends) |
| `--rules` | path | `rules/base.lp` | Path to ASP rules file |
| `--prompt` | path | `prompts/structure_prompt.txt` | Path to structuring prompt |
| `--output` | path | `output.json` | Path to detailed output file |
| `--no-llm-lint` | flag | - | Skip direct LLM linting |
| `--no-logic-lint` | flag | - | Skip logic-based linting |
| `--verbose` | flag | - | Show detailed progress output |
| `--debug` | flag | - | Show debug information including ASP facts |

#### Examples

```bash
# Basic usage with Gemini
python scripts/story_lint.py story.txt --backend gemini

# Local LLM with verbose output
python scripts/story_lint.py story.txt --backend openai --api-base http://localhost:8080/v1 --verbose

# Only logic-based linting
python scripts/story_lint.py story.txt --backend gemini --no-llm-lint

# Custom rules and output
python scripts/story_lint.py story.txt --backend gemini \
    --rules my_rules.lp \
    --output results.json
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success, no errors found |
| 1 | Success, errors found in narrative |
| 2 | Configuration error (missing API key, etc.) |
| 3 | Runtime error (API failure, parsing error) |

---

## Module: llm_structurer

Converts narrative text to structured JSON using LLM.

### Functions

#### `structure_story(story_text, **kwargs) -> dict`

Main entry point for story structuring.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `story_text` | str | required | The narrative text to structure |
| `backend` | str | `"openai"` | LLM backend identifier |
| `model` | str | `"auto"` | Model identifier |
| `api_key` | str | env var | API key |
| `api_base` | str | env var | API base URL (OpenAI only) |
| `prompt_path` | str | `prompts/structure_prompt.txt` | Prompt template path |
| `temperature` | float | `0.3` | Generation temperature |
| `return_details` | bool | `False` | Include prompt and raw response |

**Returns:**

When `return_details=False`:
```python
{
    "entities": {
        "characters": [...],
        "objects": [...],
        "locations": [...]
    },
    "events": [...],
    "time_order": [...],
    "fluents": [...],
    "traits": [...],
    "rules": [...]
}
```

When `return_details=True`:
```python
{
    "structure": { ... },  # Same as above
    "prompt": "...",       # The prompt sent to LLM
    "raw_response": "...", # Raw LLM output
    "model": "...",        # Model ID used
    "backend": "..."       # Backend used
}
```

**Raises:**

| Exception | Condition |
|-----------|-----------|
| `ValueError` | Missing API key |
| `RuntimeError` | API call failed |
| `json.JSONDecodeError` | Failed to parse LLM output |

**Example:**

```python
from scripts.llm_structurer import structure_story

# Basic usage
result = structure_story(
    story_text="Once upon a time, Hansel and Gretel lived in a cottage.",
    backend="gemini",
    api_key="your-key"
)

# With full details
result = structure_story(
    story_text=open("story.txt").read(),
    backend="gemini",
    api_key="your-key",
    return_details=True
)

print(f"Model used: {result['model']}")
print(f"Characters: {result['structure']['entities']['characters']}")
```

---

#### `call_openai(prompt, model, api_base, api_key, temperature=0.3) -> str`

Make a call to an OpenAI-compatible API.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | str | The prompt text |
| `model` | str | Model identifier |
| `api_base` | str | API base URL |
| `api_key` | str | API key |
| `temperature` | float | Generation temperature |

**Returns:** Raw response text from the LLM.

---

#### `call_gemini(prompt, model, api_key, temperature=0.3) -> str`

Make a call to the Google Gemini API.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | str | The prompt text |
| `model` | str | Gemini model identifier |
| `api_key` | str | Gemini API key |
| `temperature` | float | Generation temperature |

**Returns:** Raw response text from the LLM.

---

#### `extract_json(text) -> dict`

Extract JSON object from LLM response text.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | str | Raw LLM response |

**Returns:** Parsed JSON as Python dict.

**Notes:**
- Handles `<think>` blocks from reasoning models
- Handles markdown code blocks (` ```json `)
- Falls back to regex extraction if needed

---

#### `strip_think(text) -> str`

Remove `<think>` reasoning blocks from text.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | str | Text potentially containing think blocks |

**Returns:** Text with think blocks removed.

---

#### `basic_validate(data) -> dict`

Add default values for missing required fields.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | dict | Parsed JSON structure |

**Returns:** Validated structure with defaults.

**Defaults applied:**
- `entities`: `{}`
- `entities.characters`: `[]`
- `entities.objects`: `[]`
- `entities.locations`: `[]`
- `events`: `[]`
- `time_order`: `[]`
- `fluents`: `[]`
- `traits`: `[]`
- `rules`: `[]`

---

## Module: json_to_asp

Converts structured JSON to Answer Set Programming (ASP) facts.

### Functions

#### `json_to_asp(data, include_candidates=False) -> str`

Convert structured story JSON to ASP facts.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | dict | required | Structured story JSON |
| `include_candidates` | bool | `False` | Include candidate violation facts |

**Returns:** String containing ASP facts, one per line.

**Example:**

```python
from scripts.json_to_asp import json_to_asp

data = {
    "entities": {
        "characters": [{"id": "hansel", "name": "Hansel"}],
        "objects": [{"id": "bread", "type": "food"}],
        "locations": [{"id": "forest"}]
    },
    "events": [
        {
            "id": "e1",
            "type": "eat",
            "agent": "hansel",
            "patient": "bread",
            "location": "forest",
            "time_start": "t1",
            "time_end": "t1"
        }
    ],
    "time_order": [["t1", "t2"]]
}

asp_facts = json_to_asp(data)
print(asp_facts)
# Output:
# character(hansel).
# object(bread).
# food(bread).
# location(forest).
# event(e1).
# event_type(e1, eat).
# agent(e1, hansel).
# patient(e1, bread).
# location(e1, forest).
# time(e1, t1, t1).
# time_order(t1, t2).
```

---

#### `sanitize_symbol(s) -> str`

Convert any string to a valid ASP atom.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `s` | str | Input string |

**Returns:** Valid ASP atom (lowercase, alphanumeric + underscore only).

**Transformation rules:**
1. Convert to lowercase
2. Replace spaces and hyphens with underscores
3. Remove all non-alphanumeric characters (except underscore)
4. Collapse multiple underscores
5. Strip leading/trailing underscores
6. Prefix with 'x' if starts with digit

**Examples:**

```python
from scripts.json_to_asp import sanitize_symbol

sanitize_symbol("Hansel")          # -> "hansel"
sanitize_symbol("white pebbles")   # -> "white_pebbles"
sanitize_symbol("the-witch")       # -> "the_witch"
sanitize_symbol("123abc")          # -> "x123abc"
sanitize_symbol("O'Brien")         # -> "obrien"
```

---

#### `emit_fact(functor, *args) -> str`

Generate an ASP fact string.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `functor` | str | Predicate name |
| `*args` | str | Arguments to the predicate |

**Returns:** ASP fact string ending with `.`

**Examples:**

```python
from scripts.json_to_asp import emit_fact

emit_fact("character", "hansel")
# -> "character(hansel)."

emit_fact("time", "e1", "t1", "t2")
# -> "time(e1, t1, t2)."

emit_fact("holds", "at(hansel, forest)", "t1", "t5")
# -> "holds(at(hansel, forest), t1, t5)."
```

---

### Generated Fact Types

The `json_to_asp` function generates the following fact types:

#### Entity Facts

| Fact | Source | Example |
|------|--------|---------|
| `character(ID).` | entities.characters | `character(hansel).` |
| `object(ID).` | entities.objects | `object(bread).` |
| `TYPE(ID).` | entities.objects.type | `food(bread).` |
| `location(ID).` | entities.locations | `location(forest).` |

#### Event Facts

| Fact | Source | Example |
|------|--------|---------|
| `event(ID).` | events[].id | `event(e1).` |
| `event_type(E, TYPE).` | events[].type | `event_type(e1, eat).` |
| `agent(E, A).` | events[].agent | `agent(e1, hansel).` |
| `patient(E, P).` | events[].patient | `patient(e1, bread).` |
| `location(E, L).` | events[].location | `location(e1, forest).` |
| `destination(E, D).` | events[].destination | `destination(e2, cottage).` |
| `source(E, S).` | events[].source | `source(e2, forest).` |
| `recipient(E, R).` | events[].recipient | `recipient(e3, gretel).` |
| `instrument(E, I).` | events[].instrument | `instrument(e4, axe).` |
| `time(E, S, End).` | events[].time_start/end | `time(e1, t1, t2).` |

#### Temporal Facts

| Fact | Source | Example |
|------|--------|---------|
| `time_order(T1, T2).` | time_order | `time_order(t1, t2).` |

#### Fluent Facts

| Fact | Source | Example |
|------|--------|---------|
| `holds(F, S, E).` | fluents | `holds(at(hansel, forest), t1, t5).` |

#### Trait Facts

| Fact | Source | Example |
|------|--------|---------|
| `trait(C, T).` | traits | `trait(hansel, clever).` |

#### Rule Facts

| Fact | Source | Example |
|------|--------|---------|
| `precondition(...)` | rules (type=precondition) | `precondition(unlock, door, has(agent, key), true, 0).` |
| `causes(...)` | rules (type=causes) | `causes(eat, food, has(agent, food), false).` |

---

## Module: run_reasoner

Direct interface to Clingo ASP solver.

### Functions

#### `run_clingo(facts, rules_path, timeout=30) -> list[str]`

Run Clingo solver on facts with rules.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `facts` | str | required | ASP facts as string |
| `rules_path` | str | required | Path to rules file |
| `timeout` | int | `30` | Solving timeout in seconds |

**Returns:** List of violation atoms as strings.

**Example:**

```python
from scripts.run_reasoner import run_clingo

facts = """
character(alice).
event(e1).
event(e2).
event_type(e1, die).
event_type(e2, walk).
agent(e1, alice).
agent(e2, alice).
time(e1, t1, t1).
time(e2, t2, t2).
time_order(t1, t2).
"""

violations = run_clingo(facts, "rules/base.lp")
# -> ['violation(dead_agent, e2)']
```

---

## Data Structures

### Structured Story JSON

```typescript
interface StructuredStory {
  entities: {
    characters: Character[];
    objects: StoryObject[];
    locations: Location[];
  };
  events: Event[];
  time_order: [string, string][];
  fluents: Fluent[];
  traits: Trait[];
  rules: Rule[];
}

interface Character {
  id: string;        // Required: unique identifier
  name: string;      // Required: display name
  description?: string;
}

interface StoryObject {
  id: string;        // Required: unique identifier
  type: string;      // Required: object category
  description?: string;
}

interface Location {
  id: string;        // Required: unique identifier
  description?: string;
}

interface Event {
  id: string;           // Required: e1, e2, etc.
  type: string;         // Required: action verb
  agent?: string | string[];
  patient?: string | string[];
  location?: string;
  destination?: string;
  source?: string;
  recipient?: string;
  instrument?: string;
  time_start: string;   // Required: t1, t2, etc.
  time_end: string;     // Required: t1, t2, etc.
  description?: string;
}

interface Fluent {
  name: string;      // Required: fluent predicate
  args: string[];    // Required: fluent arguments
  value: boolean | string;  // Required: fluent value
  start: string;     // Required: start time point
  end: string;       // Required: end time point
}

interface Trait {
  character: string;  // Required: character id
  trait: string;      // Required: trait name
  description?: string;
}

interface Rule {
  type: "precondition" | "causes";  // Required
  event_type: string;  // Required
  fluent: string;      // Required
  args?: string[];
  value?: boolean | string;
  negated?: boolean;
}
```

### Output JSON

```typescript
interface OutputRecord {
  timestamp: string;           // ISO 8601 timestamp
  story_file: string;          // Input file path
  backend: string;             // LLM backend used
  model: string;               // Model identifier
  
  llm_lint?: {
    prompt: string;
    raw_response: string;
    result: {
      error_count: number;
      errors: ErrorItem[];
    };
  };
  
  logic_lint?: {
    structuring: {
      prompt: string;
      raw_response: string;
      structure: StructuredStory;
    };
    asp: {
      facts: string;
      rules_file: string;
      violations: string[];
    };
    interpretation: {
      prompt: string;
      raw_response: string;
      result: {
        error_count: number;
        errors: ErrorItem[];
      };
    };
  };
  
  combined_result: {
    error_count: number;
    errors: ErrorItem[];
  };
}

interface ErrorItem {
  id: string;
  description: string;
  source?: "llm" | "logic";
}
```

---

## Environment Variables

| Variable | Description | Required For |
|----------|-------------|--------------|
| `OPENAI_API_KEY` | OpenAI/compatible API key | `--backend openai` |
| `OPENAI_API_BASE` | OpenAI-compatible API URL | `--backend openai` |
| `GEMINI_API_KEY` | Google Gemini API key | `--backend gemini` |

---

## Error Handling

### Exception Hierarchy

```
Exception
├── ValueError
│   ├── Missing API key
│   ├── Invalid backend
│   └── Invalid model
├── RuntimeError
│   ├── API call failed
│   ├── Clingo error
│   └── Timeout
├── json.JSONDecodeError
│   └── Failed to parse LLM output
└── FileNotFoundError
    ├── Story file not found
    ├── Rules file not found
    └── Prompt file not found
```

### Error Recovery

The system attempts to recover from common errors:

1. **JSON parsing failures**: Try multiple extraction patterns
2. **API timeouts**: No automatic retry (implement in calling code)
3. **Missing fields**: Add defaults via `basic_validate()`
4. **Invalid ASP syntax**: Sanitize all symbols before generation
