# Narrative Logic Engine – Repository Design Document

## 1. Purpose & Vision

This repository implements a **Narrative Logic Engine** for story analysis, consistency checking, and rule learning. The engine is designed to reason symbolically about stories using **Answer Set Programming (ASP)** with **Clingo**, integrate **Inductive Logic Programming (ILASP)** for rule learning, and use **Python strictly as an orchestration layer**.

The system tracks characters, locations, items, traits, relationships, and events across a linear timeline, detecting logical inconsistencies while allowing stories to override real-world rules (e.g., ghosts, magic, impossible physics).

This is not a text-understanding system; it is a **logic-based world simulator and validator** driven by extracted facts.

---

## 2. Core Design Principles

* **Logic-first architecture**: ASP is the source of truth for world state and reasoning
* **Layered rule precedence**: story > learned > universal
* **Deterministic and explainable**: every conclusion must trace back to rules and events
* **Temporal reasoning**: all facts are time-indexed
* **Extensible rule learning**: new rules emerge via ILASP, not Python heuristics
* **LLM-agnostic core**: LLMs may assist extraction, but never reasoning

---

## 3. Conceptual Model

### 3.1 Rule Layers (Priority Order)

1. **Story-Specific Rules**
   Rules explicitly or implicitly introduced by the narrative. These override all others.

2. **Learned Rules**
   Rules inferred via ILASP based on repeated patterns or contradictions.

3. **Universal Rules**
   Default assumptions about the world (physics, social norms, etc.). These apply unless overridden.

Contradicted rules are **deactivated but retained** for auditing and final analysis.

---

### 3.2 Logic Knowledge Graph (LKG)

The story world is represented as a **logic-defined knowledge graph**.

#### Entities (Nodes)

* `character(X)`
* `location(X)`
* `item(X)`

#### Relations (Edges / Predicates)

* `relationship(Character1, Character2, Type, Time)`
* `present(Entity, Location, Time)`
* `carries(Character, Item, Time)`
* `connected(Location1, Location2)`
* `trait(Entity, Trait)`

#### Derived Relations

* **Item presence via carrying**:
  If a character carries an item and is present in a location, the item is present in that location.

---

### 3.3 Global Constraints

* **Non-ubiquity**:
  An entity cannot be present in more than one location at the same time.

* **Linear time**:
  Time is discrete, monotonic, and strictly ordered.

* **No branching timelines**:
  No flashbacks, flashforwards, or alternate histories.

---

## 4. Events & State Transitions

* Events are **state transitions**, not static facts
* Each event occurs at a specific timestep
* Events modify the LKG by:

  * Changing presence
  * Adding/removing relationships
  * Modifying carried items
  * Introducing or overriding rules

Events are evaluated **sequentially**, and each produces a new world state.

---

## 5. Story Evaluation Pipeline

### Step 1: Extraction

Input (from an external system, possibly LLM-assisted):

* Entities with traits
* Initial relationships
* Initial presence and carried items
* Ordered list of events

### Step 2: Sequential Evaluation

For each event:

* Apply state transition
* Recompute derived facts
* Enforce constraints
* Detect violations

### Step 3: Conflict Resolution

* If a story contradicts a universal rule:

  * Generate a **story-specific override rule**
  * Deactivate the universal rule
* Conflicts are logged with provenance

### Step 4: Rule Learning (ILASP)

* Observe repeated violations or exceptions
* Learn:

  * New rules
  * Conditional exceptions
* Learned rules are scoped to the story and versioned

### Step 5: Output

* Output is **structured JSON only**
* Each issue includes:

  * Violated rule
  * Entities involved
  * Event index / time
  * Severity (hard contradiction vs soft inconsistency)

---

## 6. Final Chapter Analysis

After the final chapter:

* Audit all active and deactivated rules
* Detect loose ends:

  * Unresolved items
  * Introduced but unused entities
  * Chekhov-style artifacts
* Detect long-range inconsistencies not visible at chapter scope

---

## 7. Repository Architecture

### 7.1 Python Layer (Orchestration Only)

Responsibilities:

* Load logic programs
* Manage timestep progression
* Inject extracted facts
* Invoke Clingo
* Integrate ILASP
* Produce JSON diagnostics

Suggested structure:

```
engine/
  state_manager.py        # World state snapshots & deltas
  event_executor.py       # Applies events per timestep
  rule_registry.py        # Rule loading, priorities, activation
  conflict_resolver.py    # Handles rule overrides & deactivation
  learning_adapter.py    # ILASP integration
```

Python **must not** encode story logic.

---

### 7.2 Logic Layer (ASP)

Responsibilities:

* World state representation
* Constraint enforcement
* Rule evaluation
* Derived fact inference

Suggested structure:

```
logic/
  universal_rules.lp     # Default world rules
  story_rules.lp         # Story-specific overrides
  learned_rules.lp       # ILASP output
  constraints.lp         # Global constraints
  events.lp              # Event-to-state transitions
```

ASP is the **single source of truth** for reasoning.

---

## 8. Anti-Goals (Hard No’s)

The system must NOT:

* Encode narrative logic in Python conditionals
* Use LLM reasoning inside the logic engine
* Delete overridden rules
* Produce natural language explanations
* Break determinism or grounding assumptions

---

## 9. Acceptance Criteria

The engine is correct if:

* Stories can override physical impossibilities
* Entities cannot exist in two locations simultaneously
* Items follow characters unless explicitly dropped
* Learned rules persist across chapters
* Final analysis detects unresolved narrative elements

---

## 10. Future Extensions (Out of Scope)

* Non-linear timelines
* Hypothetical or counterfactual reasoning
* Probabilistic rules
* Reader inference modeling

---

**This document is the authoritative specification for all refactors and future development.**
