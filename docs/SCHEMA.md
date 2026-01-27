# JSON Schema Reference for Narrative Structuring

## Overview

This document provides a comprehensive reference for the JSON schema used by the narrative consistency checker to represent structured stories. The LLM converts raw narrative text into this format, which is then converted to ASP facts for logical reasoning.

## Complete Schema Definition

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Narrative Structure",
  "description": "A structured representation of a narrative for consistency checking",
  "type": "object",
  "properties": {
    "entities": {
      "type": "object",
      "description": "All named entities in the story",
      "properties": {
        "characters": {
          "type": "array",
          "description": "People, animals, or anthropomorphized beings that can perform actions",
          "items": {
            "type": "object",
            "properties": {
              "id": {
                "type": "string",
                "description": "Unique identifier (lowercase, snake_case)",
                "pattern": "^[a-z][a-z0-9_]*$",
                "examples": ["hansel", "gretel", "witch", "old_man"]
              },
              "name": {
                "type": "string",
                "description": "Display name as it appears in the story",
                "examples": ["Hansel", "Gretel", "The Witch"]
              },
              "description": {
                "type": "string",
                "description": "Brief characterization",
                "examples": ["A young boy who is clever and resourceful"]
              }
            },
            "required": ["id", "name"]
          }
        },
        "objects": {
          "type": "array",
          "description": "Physical items that can be manipulated",
          "items": {
            "type": "object",
            "properties": {
              "id": {
                "type": "string",
                "description": "Unique identifier",
                "pattern": "^[a-z][a-z0-9_]*$",
                "examples": ["bread", "pebbles", "cage"]
              },
              "type": {
                "type": "string",
                "description": "Category or kind of object",
                "examples": ["food", "stones", "container"]
              },
              "description": {
                "type": "string",
                "description": "Physical description",
                "examples": ["A loaf of crusty bread"]
              }
            },
            "required": ["id", "type"]
          }
        },
        "locations": {
          "type": "array",
          "description": "Places where events occur",
          "items": {
            "type": "object",
            "properties": {
              "id": {
                "type": "string",
                "description": "Unique identifier",
                "pattern": "^[a-z][a-z0-9_]*$",
                "examples": ["cottage", "forest", "gingerbread_house"]
              },
              "description": {
                "type": "string",
                "description": "Description of the place",
                "examples": ["A small cottage at the edge of the forest"]
              }
            },
            "required": ["id"]
          }
        }
      }
    },
    "events": {
      "type": "array",
      "description": "Discrete actions or state changes in chronological order",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "Unique event identifier",
            "pattern": "^e[0-9]+$",
            "examples": ["e1", "e2", "e15"]
          },
          "type": {
            "type": "string",
            "description": "Action verb or event type",
            "enum": [
              "move", "go", "travel", "walk", "run",
              "take", "grab", "pick_up", "acquire",
              "drop", "put", "place", "release",
              "eat", "consume", "drink",
              "give", "hand", "offer",
              "say", "tell", "speak", "ask", "shout",
              "see", "look", "observe", "notice",
              "hear", "listen",
              "open", "close", "lock", "unlock",
              "enter", "exit", "leave",
              "sleep", "wake", "rest",
              "die", "kill", "attack", "fight",
              "build", "create", "make", "destroy",
              "push", "pull", "throw", "catch"
            ]
          },
          "agent": {
            "oneOf": [
              {
                "type": "string",
                "description": "Single character performing the action"
              },
              {
                "type": "array",
                "description": "Multiple characters performing together",
                "items": { "type": "string" }
              }
            ],
            "examples": ["hansel", ["hansel", "gretel"]]
          },
          "patient": {
            "oneOf": [
              {
                "type": "string",
                "description": "Single object/character being acted upon"
              },
              {
                "type": "array",
                "description": "Multiple objects/characters",
                "items": { "type": "string" }
              }
            ],
            "examples": ["bread", ["bread", "cheese"]]
          },
          "location": {
            "type": "string",
            "description": "Where the event takes place",
            "examples": ["forest", "cottage"]
          },
          "destination": {
            "type": "string",
            "description": "End location for movement events",
            "examples": ["gingerbread_house"]
          },
          "source": {
            "type": "string",
            "description": "Start location for movement events",
            "examples": ["cottage"]
          },
          "recipient": {
            "type": "string",
            "description": "Who receives something (for give/tell events)",
            "examples": ["gretel"]
          },
          "instrument": {
            "type": "string",
            "description": "Tool or means used",
            "examples": ["axe", "key"]
          },
          "time_start": {
            "type": "string",
            "description": "Start of event time interval",
            "pattern": "^t[0-9]+$",
            "examples": ["t1", "t5"]
          },
          "time_end": {
            "type": "string",
            "description": "End of event time interval",
            "pattern": "^t[0-9]+$",
            "examples": ["t1", "t6"]
          },
          "description": {
            "type": "string",
            "description": "Natural language description of what happens"
          }
        },
        "required": ["id", "type", "time_start", "time_end"]
      }
    },
    "time_order": {
      "type": "array",
      "description": "Explicit temporal ordering between time points",
      "items": {
        "type": "array",
        "items": { "type": "string" },
        "minItems": 2,
        "maxItems": 2
      },
      "examples": [
        [["t1", "t2"], ["t2", "t3"], ["t3", "t4"]]
      ]
    },
    "fluents": {
      "type": "array",
      "description": "Time-varying properties that can change",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "Property name",
            "examples": ["at", "has", "alive", "open", "locked"]
          },
          "args": {
            "type": "array",
            "description": "Arguments to the fluent",
            "items": { "type": "string" },
            "examples": [["hansel", "cottage"], ["gretel", "bread"]]
          },
          "value": {
            "type": ["boolean", "string"],
            "description": "Current value of the fluent",
            "examples": [true, false, "happy"]
          },
          "start": {
            "type": "string",
            "description": "When this fluent starts holding",
            "pattern": "^t[0-9]+$"
          },
          "end": {
            "type": "string",
            "description": "When this fluent stops holding",
            "pattern": "^t[0-9]+$"
          }
        },
        "required": ["name", "args", "value", "start", "end"]
      }
    },
    "traits": {
      "type": "array",
      "description": "Permanent character properties",
      "items": {
        "type": "object",
        "properties": {
          "character": {
            "type": "string",
            "description": "Which character has this trait"
          },
          "trait": {
            "type": "string",
            "description": "The trait name",
            "enum": [
              "claustrophobic", "acrophobic", "aquaphobic",
              "blind", "deaf", "mute",
              "vegetarian", "allergic_to_nuts",
              "brave", "cowardly", "clever", "foolish"
            ]
          },
          "description": {
            "type": "string",
            "description": "How this trait manifests"
          }
        },
        "required": ["character", "trait"]
      }
    },
    "rules": {
      "type": "array",
      "description": "Story-specific cause-effect relationships",
      "items": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": ["precondition", "causes"],
            "description": "Whether this is a requirement or an effect"
          },
          "event_type": {
            "type": "string",
            "description": "Type of event this rule applies to"
          },
          "fluent": {
            "type": "string",
            "description": "Fluent involved in the rule"
          },
          "args": {
            "type": "array",
            "items": { "type": "string" }
          },
          "value": {
            "type": ["boolean", "string"]
          },
          "negated": {
            "type": "boolean",
            "description": "Whether this is a negative requirement"
          }
        },
        "required": ["type", "event_type", "fluent"]
      }
    }
  },
  "required": ["entities", "events"]
}
```

## Field Reference

### Entity Fields

#### Characters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique identifier (lowercase, snake_case) |
| `name` | string | ✅ | Display name as in story |
| `description` | string | ❌ | Brief characterization |

**ASP Mapping:**
```prolog
character(id).
```

#### Objects

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique identifier |
| `type` | string | ✅ | Category (food, tool, container, etc.) |
| `description` | string | ❌ | Physical description |

**ASP Mapping:**
```prolog
object(id).
type(id).  % The type becomes a fact
```

#### Locations

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique identifier |
| `description` | string | ❌ | Place description |

**ASP Mapping:**
```prolog
location(id).
```

### Event Fields

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `id` | string | ✅ | Unique event ID (e1, e2, ...) | `"e5"` |
| `type` | string | ✅ | Action verb | `"eat"`, `"move"` |
| `agent` | string/array | ❌ | Who performs action | `"hansel"` or `["hansel", "gretel"]` |
| `patient` | string/array | ❌ | What is acted upon | `"bread"` |
| `location` | string | ❌ | Where it happens | `"forest"` |
| `destination` | string | ❌ | End location (for move) | `"cottage"` |
| `source` | string | ❌ | Start location | `"forest"` |
| `recipient` | string | ❌ | Who receives (give/tell) | `"gretel"` |
| `instrument` | string | ❌ | Tool used | `"axe"` |
| `time_start` | string | ✅ | Start time point | `"t1"` |
| `time_end` | string | ✅ | End time point | `"t1"` |
| `description` | string | ❌ | What happens | `"Hansel eats bread"` |

**ASP Mapping:**
```prolog
event(e5).
event_type(e5, eat).
agent(e5, hansel).
patient(e5, bread).
location(e5, forest).
time(e5, t1, t2).
```

### Fluent Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Property name (at, has, alive, etc.) |
| `args` | array | ✅ | Arguments to fluent |
| `value` | bool/string | ✅ | Current value |
| `start` | string | ✅ | Start time point |
| `end` | string | ✅ | End time point |

**Common Fluents:**

| Fluent | Args | Meaning |
|--------|------|---------|
| `at(X, L)` | [entity, location] | X is at location L |
| `has(X, O)` | [character, object] | X possesses O |
| `alive(X)` | [character] | X is alive |
| `open(O)` | [object] | O is open |
| `locked(O)` | [object] | O is locked |
| `lit(L)` | [location] | L is illuminated |
| `hungry(X)` | [character] | X is hungry |
| `knows(X, F)` | [char, fact] | X knows fact F |

**ASP Mapping:**
```prolog
holds(at(hansel, forest), t1, t5).
holds(has(gretel, bread), t3, t7).
holds(alive(witch), t1, t10).
```

### Trait Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `character` | string | ✅ | Who has the trait |
| `trait` | string | ✅ | Trait name |
| `description` | string | ❌ | How it manifests |

**Recognized Traits:**

| Category | Traits |
|----------|--------|
| Phobias | `claustrophobic`, `acrophobic`, `aquaphobic` |
| Disabilities | `blind`, `deaf`, `mute` |
| Dietary | `vegetarian`, `allergic_to_nuts` |
| Personality | `brave`, `cowardly`, `clever`, `foolish` |

**ASP Mapping:**
```prolog
trait(hansel, clever).
trait(gretel, brave).
```

### Rule Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✅ | `"precondition"` or `"causes"` |
| `event_type` | string | ✅ | Event type this applies to |
| `fluent` | string | ✅ | Fluent involved |
| `args` | array | ❌ | Fluent arguments |
| `value` | any | ❌ | Expected/caused value |
| `negated` | bool | ❌ | Negative requirement |

**ASP Mapping:**
```prolog
% Precondition: to unlock, must have key
precondition(unlock, Door, has(Agent, key), true) :-
    event_type(E, unlock), patient(E, Door), agent(E, Agent).

% Cause: eating bread makes it gone
causes(eat, Bread, has(Agent, Bread), false) :-
    event_type(E, eat), patient(E, Bread), agent(E, Agent).
```

## Example Complete JSON

```json
{
  "entities": {
    "characters": [
      {"id": "hansel", "name": "Hansel", "description": "Clever young boy"},
      {"id": "gretel", "name": "Gretel", "description": "Brave young girl"},
      {"id": "witch", "name": "The Witch", "description": "Evil old woman"}
    ],
    "objects": [
      {"id": "bread", "type": "food", "description": "A loaf of bread"},
      {"id": "pebbles", "type": "stones", "description": "White pebbles"},
      {"id": "cage", "type": "container", "description": "Iron cage"}
    ],
    "locations": [
      {"id": "cottage", "description": "Family home"},
      {"id": "forest", "description": "Dark forest"},
      {"id": "gingerbread_house", "description": "House made of candy"}
    ]
  },
  "events": [
    {
      "id": "e1",
      "type": "take",
      "agent": "hansel",
      "patient": "pebbles",
      "location": "cottage",
      "time_start": "t1",
      "time_end": "t1",
      "description": "Hansel collects white pebbles"
    },
    {
      "id": "e2",
      "type": "move",
      "agent": ["hansel", "gretel"],
      "source": "cottage",
      "destination": "forest",
      "time_start": "t2",
      "time_end": "t3",
      "description": "The children walk into the forest"
    },
    {
      "id": "e3",
      "type": "drop",
      "agent": "hansel",
      "patient": "pebbles",
      "location": "forest",
      "time_start": "t3",
      "time_end": "t3",
      "description": "Hansel drops pebbles to mark the path"
    }
  ],
  "time_order": [
    ["t1", "t2"],
    ["t2", "t3"]
  ],
  "fluents": [
    {
      "name": "at",
      "args": ["hansel", "cottage"],
      "value": true,
      "start": "t1",
      "end": "t2"
    },
    {
      "name": "has",
      "args": ["hansel", "pebbles"],
      "value": true,
      "start": "t1",
      "end": "t3"
    },
    {
      "name": "alive",
      "args": ["witch"],
      "value": true,
      "start": "t1",
      "end": "t10"
    }
  ],
  "traits": [
    {"character": "hansel", "trait": "clever"},
    {"character": "gretel", "trait": "brave"}
  ],
  "rules": [
    {
      "type": "precondition",
      "event_type": "drop",
      "fluent": "has",
      "args": ["agent", "patient"],
      "value": true
    },
    {
      "type": "causes",
      "event_type": "drop",
      "fluent": "has",
      "args": ["agent", "patient"],
      "value": false
    }
  ]
}
```

## Validation Rules

1. **ID Uniqueness**: All IDs must be unique within their category
2. **ID Format**: Must be lowercase, start with letter, contain only `[a-z0-9_]`
3. **Time Point Format**: Must match `t[0-9]+`
4. **Event ID Format**: Must match `e[0-9]+`
5. **References**: All references (agent, patient, location) must exist in entities
6. **Time Ordering**: Events must have `time_start <= time_end`
7. **Fluent Intervals**: Fluent `start` must precede `end` in time_order

## Common Patterns

### Movement Events
```json
{
  "id": "e5",
  "type": "move",
  "agent": "character_id",
  "source": "from_location",
  "destination": "to_location",
  "time_start": "t5",
  "time_end": "t6"
}
```

### Transfer Events (Give/Take)
```json
{
  "id": "e6",
  "type": "give",
  "agent": "giver",
  "patient": "object_id",
  "recipient": "receiver",
  "location": "where",
  "time_start": "t6",
  "time_end": "t6"
}
```

### Communication Events
```json
{
  "id": "e7",
  "type": "tell",
  "agent": "speaker",
  "recipient": "listener",
  "location": "where",
  "time_start": "t7",
  "time_end": "t7",
  "description": "What was said"
}
```

### Death Events
```json
{
  "id": "e10",
  "type": "die",
  "agent": "character_who_dies",
  "location": "where",
  "time_start": "t10",
  "time_end": "t10"
}
```

This causes the `alive(character)` fluent to become false.
