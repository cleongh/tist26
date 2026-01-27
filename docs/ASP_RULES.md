# Answer Set Programming (ASP) Rules Reference

## Introduction to ASP

Answer Set Programming (ASP) is a form of declarative programming oriented towards difficult combinatorial search problems. It uses a logic-based language to describe **what** constitutes a solution rather than **how** to compute it.

### Key Concepts

1. **Atoms**: Basic propositions like `character(hansel)` or `alive(witch)`
2. **Facts**: Unconditionally true atoms ending with `.`
3. **Rules**: Conditional statements `head :- body.` (head is true if body is true)
4. **Constraints**: Rules without head `:- body.` (body must not be all true)
5. **Negation as Failure**: `not X` means X cannot be proven true

### ASP Semantics

```prolog
% Fact: Always true
character(hansel).

% Rule: head is true if body is true
mortal(X) :- human(X).

% Constraint: This combination must not occur
:- married(X,Y), sibling(X,Y).

% Negation: X is innocent if not proven guilty
innocent(X) :- suspect(X), not guilty(X).
```

---

## base.lp: Complete Rule Reference

The `rules/base.lp` file contains the core reasoning rules for narrative consistency checking. This section documents each rule in detail.

### 1. Temporal Reasoning

#### Time Point Extraction

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% TIME POINT EXTRACTION
% 
% Purpose: Identify all time points mentioned in the narrative
% 
% We extract time points from:
%   1. Event intervals: time(Event, Start, End)
%   2. Fluent intervals: holds(Fluent, Start, End)
%   3. Explicit ordering: time_order(T1, T2)
% ═══════════════════════════════════════════════════════════════════════════════

% Time points come from event start/end times
time_point(T) :- time(_, T, _).
time_point(T) :- time(_, _, T).

% Time points come from fluent intervals
time_point(T) :- holds(_, T, _).
time_point(T) :- holds(_, _, T).

% Time points come from ordering relations
time_point(T) :- time_order(T, _).
time_point(T) :- time_order(_, T).
```

**Explanation:**
- These rules ensure we have a complete set of all time points in the story
- A time point can appear as the start of an event, end of an event, start of a fluent, end of a fluent, or in an ordering relation
- This allows us to reason about all moments in the narrative

#### Temporal Ordering

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% TEMPORAL ORDERING (before/2)
% 
% Purpose: Establish which time points precede which others
% 
% The before/2 relation is TRANSITIVE:
%   If T1 is before T2, and T2 is before T3, then T1 is before T3
% 
% This allows us to chain temporal relationships through the narrative.
% ═══════════════════════════════════════════════════════════════════════════════

% Direct ordering from facts
before(T1, T2) :- time_order(T1, T2).

% Transitive closure: if T1 < T2 and T2 < T3, then T1 < T3
before(T1, T3) :- before(T1, T2), before(T2, T3).
```

**Explanation:**
- `time_order(t1, t2)` means t1 immediately precedes t2
- `before(T1, T2)` means T1 is at some point earlier than T2
- Transitivity allows reasoning across the entire timeline

#### Event Temporal Relations

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% EVENT TEMPORAL RELATIONS
% 
% Purpose: Define relationships between events based on their time intervals
% 
% We use Allen's Interval Algebra relations (simplified):
%   - precedes: E1 ends before E2 starts
%   - meets: E1 ends exactly when E2 starts
%   - overlaps: E1 and E2 share some time points
% ═══════════════════════════════════════════════════════════════════════════════

% Event E1 precedes E2: E1 ends before E2 starts
precedes(E1, E2) :- 
    event(E1), event(E2), E1 != E2,
    time(E1, _, End1),
    time(E2, Start2, _),
    before(End1, Start2).

% Event E1 meets E2: E1 ends exactly when E2 starts
meets(E1, E2) :- 
    event(E1), event(E2), E1 != E2,
    time(E1, _, End1),
    time(E2, End1, _).

% Events overlap: they share at least one time point, or their intervals intersect
% Two intervals [S1,E1] and [S2,E2] overlap if NOT (E1 < S2 OR E2 < S1)
overlap(E1, E2) :- 
    event(E1), event(E2), E1 != E2,
    time(E1, S1, E1_end),
    time(E2, S2, E2_end),
    not before(E1_end, S2),
    not before(E2_end, S1).
```

**Explanation:**
- These relations help detect temporal conflicts
- Two events overlap if neither ends before the other starts
- This is crucial for detecting impossible simultaneity

---

### 2. Fluent Reasoning

#### Fluent State at Time Point

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% FLUENT STATE AT TIME POINT (holds_at/2)
% 
% Purpose: Determine if a fluent holds at a specific time point
% 
% A fluent F holds at time T if there exists an interval [Start, End] where:
%   1. holds(F, Start, End) is true
%   2. T is within the interval (Start <= T <= End)
% 
% We check this by ensuring T is not before Start and End is not before T.
% ═══════════════════════════════════════════════════════════════════════════════

% Fluent holds at T if T falls within its validity interval
holds_at(F, T) :- 
    holds(F, Start, End),
    time_point(T),
    not before(T, Start),    % T >= Start
    not before(End, T).      % T <= End (or End >= T)
```

**Explanation:**
- This is the core of fluent reasoning
- We can query if something is true at any point in time
- For example, `holds_at(alive(witch), t5)` checks if the witch is alive at t5

#### Frame Axiom (Persistence)

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% FRAME AXIOM (Persistence/Inertia)
% 
% Purpose: Things stay the same unless something changes them
% 
% This is a fundamental principle in temporal reasoning:
%   "If a fluent is true at time T and nothing changes it, it remains true"
% 
% However, in our system, fluents have explicit intervals, so the frame axiom
% is implicit in the holds/3 representation. Changes are explicit events.
% ═══════════════════════════════════════════════════════════════════════════════

% Note: Frame axiom is handled by explicit fluent intervals in our representation.
% The LLM should specify when fluents start and end.
% If more sophisticated frame axiom reasoning is needed, we could add:
%
% holds_at(F, T2) :- 
%     holds_at(F, T1), 
%     before(T1, T2),
%     not terminated(F, T1, T2).
%
% terminated(F, T1, T2) :-
%     causes(E, F, _, _),
%     time(E, ET, _),
%     before(T1, ET), before(ET, T2).
```

**Explanation:**
- In many AI systems, we need to reason about persistence
- Our approach uses explicit intervals instead
- This simplifies reasoning but requires the LLM to track all state changes

---

### 3. Spatial Reasoning

#### Location During Events

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% LOCATION DURING EVENTS
% 
% Purpose: Track where entities are during events
% 
% An entity is at a location during an event if:
%   1. The event has that location, OR
%   2. The entity has an at(Entity, Location) fluent during the event
% ═══════════════════════════════════════════════════════════════════════════════

% Entity is at event's location if they're the agent
at_during(Entity, Loc, E) :- 
    agent(E, Entity),
    location(E, Loc).

% Entity is at location during event if fluent says so
at_during(Entity, Loc, E) :-
    event(E),
    time(E, Start, End),
    holds_at(at(Entity, Loc), Start).
```

**Explanation:**
- We need to know where everyone is to detect spatial violations
- The agent of an event is at the event's location
- We also consider explicit location fluents

#### Ubiquity Violation (No Bilocation)

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% UBIQUITY VIOLATION (No Bilocation)
% 
% Purpose: Detect when a character is in two places at once
% 
% This is a fundamental physical constraint:
%   A person cannot be in two different locations simultaneously
% 
% We detect this when two overlapping events show the same character
% at different locations.
% ═══════════════════════════════════════════════════════════════════════════════

violation(ubiquity, E1, E2) :-
    overlap(E1, E2),                    % Events happen at the same time
    at_during(Entity, Loc1, E1),        % Entity at Loc1 during E1
    at_during(Entity, Loc2, E2),        % Entity at Loc2 during E2
    Loc1 != Loc2,                       % Different locations
    character(Entity).                   % Must be a character
```

**Explanation:**
- This catches impossible situations like "Hansel was in the forest while Hansel was at the cottage"
- Only applies to characters (objects can be duplicated)
- Requires events to overlap temporally

---

### 4. World Knowledge

#### Edibility

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% WORLD KNOWLEDGE: EDIBILITY
% 
% Purpose: Define what can and cannot be eaten
% 
% Default assumptions:
%   - Food-type objects are edible
%   - Rocks, stones, pebbles are not edible
%   - Glass, metal are not edible
%   
% This allows detecting violations like "Hansel ate a rock"
% ═══════════════════════════════════════════════════════════════════════════════

% Objects of type "food" are edible
edible(O) :- object(O), food(O).

% Specific edible items (common foods)
edible(O) :- object(O), bread(O).
edible(O) :- object(O), cheese(O).
edible(O) :- object(O), apple(O).
edible(O) :- object(O), meat(O).
edible(O) :- object(O), fruit(O).
edible(O) :- object(O), vegetable(O).
edible(O) :- object(O), cake(O).
edible(O) :- object(O), candy(O).
edible(O) :- object(O), gingerbread(O).

% Non-edible materials
not_edible(O) :- object(O), rock(O).
not_edible(O) :- object(O), stone(O).
not_edible(O) :- object(O), stones(O).
not_edible(O) :- object(O), pebble(O).
not_edible(O) :- object(O), pebbles(O).
not_edible(O) :- object(O), glass(O).
not_edible(O) :- object(O), metal(O).
not_edible(O) :- object(O), wood(O).
not_edible(O) :- object(O), poison(O).
```

**Explanation:**
- Common-sense world knowledge encoded as rules
- Prevents nonsensical actions from going undetected
- Can be extended with domain-specific knowledge

#### Non-Edible Food Violation

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% NON-EDIBLE FOOD VIOLATION
% 
% Purpose: Detect attempts to eat non-edible objects
% 
% If an eat event has a patient that is known to be non-edible,
% this is a violation.
% ═══════════════════════════════════════════════════════════════════════════════

violation(non_edible_food, E) :-
    event(E),
    event_type(E, eat),
    patient(E, P),
    not_edible(P).
```

**Explanation:**
- Simple rule that flags eating non-food items
- Works with the edibility world knowledge above
- Example: "Gretel ate the pebbles" → violation

---

### 5. Life and Death

#### Living State Tracking

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% LIVING STATE TRACKING
% 
% Purpose: Track whether characters are alive or dead
% 
% Key principles:
%   1. Characters start alive (unless stated otherwise)
%   2. Die events cause death
%   3. Dead characters cannot perform actions
% ═══════════════════════════════════════════════════════════════════════════════

% A character is dead at time T if they died at or before T
dead_at(C, T) :-
    event(E),
    event_type(E, die),
    agent(E, C),
    time(E, _, DeathTime),
    time_point(T),
    not before(T, DeathTime).  % T >= DeathTime

% Alternative: check for explicit alive fluent being false
dead_at(C, T) :-
    holds_at(alive(C), T),
    holds(alive(C), _, End),
    before(End, T).
```

**Explanation:**
- Death is irreversible in typical narratives
- We track when characters die
- This enables checking that dead characters don't act

#### Dead Agent Violation

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% DEAD AGENT VIOLATION
% 
% Purpose: Detect when dead characters perform actions
% 
% A fundamental narrative consistency rule:
%   Dead characters cannot be agents of events (except supernatural contexts)
% ═══════════════════════════════════════════════════════════════════════════════

violation(dead_agent, E) :-
    event(E),
    agent(E, A),
    time(E, Start, _),
    dead_at(A, Start),
    character(A).
```

**Explanation:**
- If someone dies at t5, they can't do anything at t6 or later
- This catches zombie-like inconsistencies
- Example: "The witch died. Then the witch spoke." → violation

---

### 6. Trait Constraints

#### Phobias

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% TRAIT: CLAUSTROPHOBIA
% 
% Purpose: Characters with claustrophobia cannot enter enclosed spaces
% 
% Claustrophobia = fear of confined spaces
% 
% Violations occur when a claustrophobic character:
%   - Enters a cave, tunnel, closet, cage, etc.
%   - Is in a confined space
% ═══════════════════════════════════════════════════════════════════════════════

% Enclosed/confined locations
enclosed(L) :- cave(L).
enclosed(L) :- tunnel(L).
enclosed(L) :- closet(L).
enclosed(L) :- cage(L).
enclosed(L) :- basement(L).
enclosed(L) :- bunker(L).
enclosed(L) :- elevator(L).

% Claustrophobia violation
violation(claustrophobia, E) :-
    trait(C, claustrophobic),
    event(E),
    agent(E, C),
    event_type(E, enter),
    destination(E, L),
    enclosed(L).

violation(claustrophobia, E) :-
    trait(C, claustrophobic),
    event(E),
    agent(E, C),
    location(E, L),
    enclosed(L).
```

**Explanation:**
- Character traits constrain their possible actions
- A claustrophobic character would not willingly enter confined spaces
- This makes the narrative psychologically consistent

#### Acrophobia (Fear of Heights)

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% TRAIT: ACROPHOBIA
% 
% Purpose: Characters with acrophobia avoid heights
% ═══════════════════════════════════════════════════════════════════════════════

high_place(L) :- cliff(L).
high_place(L) :- tower(L).
high_place(L) :- rooftop(L).
high_place(L) :- mountain(L).
high_place(L) :- bridge(L).
high_place(L) :- balcony(L).

violation(acrophobia, E) :-
    trait(C, acrophobic),
    event(E),
    agent(E, C),
    location(E, L),
    high_place(L).
```

#### Aquaphobia (Fear of Water)

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% TRAIT: AQUAPHOBIA
% 
% Purpose: Characters with aquaphobia avoid water
% ═══════════════════════════════════════════════════════════════════════════════

water_location(L) :- lake(L).
water_location(L) :- river(L).
water_location(L) :- sea(L).
water_location(L) :- ocean(L).
water_location(L) :- pool(L).
water_location(L) :- beach(L).

violation(aquaphobia, E) :-
    trait(C, aquaphobic),
    event(E),
    agent(E, C),
    location(E, L),
    water_location(L).
```

#### Physical Disabilities

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% TRAIT: PHYSICAL DISABILITIES
% 
% Purpose: Ensure actions are consistent with physical capabilities
% ═══════════════════════════════════════════════════════════════════════════════

% Blind characters cannot see
violation(physical_impossibility, E) :-
    trait(C, blind),
    event(E),
    agent(E, C),
    event_type(E, Type),
    member(Type, (see; look; read; observe; watch)).

% Deaf characters cannot hear
violation(physical_impossibility, E) :-
    trait(C, deaf),
    event(E),
    agent(E, C),
    event_type(E, Type),
    member(Type, (hear; listen)).

% Mute characters cannot speak
violation(physical_impossibility, E) :-
    trait(C, mute),
    event(E),
    agent(E, C),
    event_type(E, Type),
    member(Type, (say; speak; shout; sing; yell)).
```

**Explanation:**
- Physical constraints must be respected
- A blind character cannot "see the witch approaching"
- A deaf character cannot "hear the scream"

---

### 7. Possession Tracking

#### Ownership Changes

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% POSSESSION TRACKING
% 
% Purpose: Track who has what objects throughout the narrative
% 
% Key events that change possession:
%   - take: Agent gains object
%   - drop: Agent loses object
%   - give: Object moves from agent to recipient
% ═══════════════════════════════════════════════════════════════════════════════

% Agent has object after taking it
has_after(Agent, Obj, T) :-
    event(E),
    event_type(E, take),
    agent(E, Agent),
    patient(E, Obj),
    time(E, _, T).

% Agent loses object after dropping it
loses_at(Agent, Obj, T) :-
    event(E),
    event_type(E, drop),
    agent(E, Agent),
    patient(E, Obj),
    time(E, _, T).

% Give transfers possession
has_after(Recipient, Obj, T) :-
    event(E),
    event_type(E, give),
    patient(E, Obj),
    recipient(E, Recipient),
    time(E, _, T).

loses_at(Agent, Obj, T) :-
    event(E),
    event_type(E, give),
    agent(E, Agent),
    patient(E, Obj),
    time(E, _, T).
```

#### Possession Violations

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% POSSESSION VIOLATIONS
% 
% Purpose: Detect using/giving/dropping objects not possessed
% ═══════════════════════════════════════════════════════════════════════════════

% Cannot drop what you don't have
violation(possession, E) :-
    event(E),
    event_type(E, drop),
    agent(E, A),
    patient(E, Obj),
    time(E, T, _),
    not holds_at(has(A, Obj), T).

% Cannot give what you don't have
violation(possession, E) :-
    event(E),
    event_type(E, give),
    agent(E, A),
    patient(E, Obj),
    time(E, T, _),
    not holds_at(has(A, Obj), T).

% Cannot use what you don't have
violation(possession, E) :-
    event(E),
    instrument(E, Obj),
    agent(E, A),
    time(E, T, _),
    not holds_at(has(A, Obj), T).
```

**Explanation:**
- You can't give away something you don't have
- You can't drop something you're not carrying
- This catches "impossible inventory" errors

---

### 8. Focus and Attention

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% FOCUS AND ATTENTION CONSTRAINTS
% 
% Purpose: Some activities require full attention and cannot be done simultaneously
% 
% A person cannot:
%   - Fight while sleeping
%   - Read two books at once
%   - Have two conversations simultaneously
% ═══════════════════════════════════════════════════════════════════════════════

% Actions requiring focus
requires_focus(fight).
requires_focus(read).
requires_focus(write).
requires_focus(build).
requires_focus(cook).
requires_focus(drive).
requires_focus(perform_surgery).

% Focus overlap violation
violation(focus_overlap, E1, E2) :-
    event(E1), event(E2), E1 < E2,  % Avoid duplicates
    overlap(E1, E2),
    agent(E1, A), agent(E2, A),     % Same agent
    event_type(E1, T1), event_type(E2, T2),
    requires_focus(T1),
    requires_focus(T2).
```

**Explanation:**
- Some tasks are mutually exclusive
- A character can't fight and read simultaneously
- This adds cognitive realism to the story

---

### 9. Preconditions and Effects

```prolog
% ═══════════════════════════════════════════════════════════════════════════════
% PRECONDITIONS AND EFFECTS (CAUSES)
% 
% Purpose: Define what must be true for an action and what changes after
% 
% precondition(EventType, EntityRole, Fluent, RequiredValue, Negated)
%   - EntityRole: agent, patient, location
%   - Negated: 0 = fluent must have value, 1 = fluent must NOT have value
% 
% causes(EventType, EntityRole, Fluent, NewValue)
%   - After event, fluent has new value
% ═══════════════════════════════════════════════════════════════════════════════

% Precondition violation
violation(precondition_not_met, E, Pred) :-
    event(E),
    event_type(E, Type),
    precondition(Type, Role, Fluent, Value, 0),  % Positive requirement
    get_entity(E, Role, Entity),
    ground_fluent(Fluent, Entity, GroundedFluent),
    time(E, T, _),
    not holds_at(GroundedFluent, T).

violation(precondition_violated, E, Pred) :-
    event(E),
    event_type(E, Type),
    precondition(Type, Role, Fluent, Value, 1),  % Negative requirement
    get_entity(E, Role, Entity),
    ground_fluent(Fluent, Entity, GroundedFluent),
    time(E, T, _),
    holds_at(GroundedFluent, T).

% Helper: get entity by role
get_entity(E, agent, X) :- agent(E, X).
get_entity(E, patient, X) :- patient(E, X).
get_entity(E, location, X) :- location(E, X).
```

**Explanation:**
- This is the most flexible mechanism for custom rules
- Story-specific logic can be added through preconditions
- Example: "unlock requires has(agent, key)"

---

## Violation Summary

| Violation ID | Arguments | Meaning |
|--------------|-----------|---------|
| `ubiquity` | E1, E2 | Same character in two places at once |
| `focus_overlap` | E1, E2 | Same character doing two focus tasks |
| `non_edible_food` | E | Eating non-edible object |
| `dead_agent` | E | Dead character acting |
| `claustrophobia` | E | Claustrophobic in enclosed space |
| `acrophobia` | E | Acrophobic at height |
| `aquaphobia` | E | Aquaphobic near water |
| `physical_impossibility` | E | Action impossible due to disability |
| `possession` | E | Using/dropping object not possessed |
| `precondition_not_met` | E, Pred | Required condition not satisfied |
| `precondition_violated` | E, Pred | Forbidden condition is true |

---

## Extending the Rules

### Adding a New Violation Type

1. Define the condition that constitutes a violation
2. Add a rule that produces `violation(type_name, Event)` or `violation(type_name, E1, E2)`

Example: Adding a "talking to self in public" violation:

```prolog
% Public locations
public_place(L) :- market(L).
public_place(L) :- street(L).
public_place(L) :- plaza(L).

% Violation: talking to yourself in public (considered odd)
violation(talking_to_self_public, E) :-
    event(E),
    event_type(E, say),
    agent(E, A),
    recipient(E, A),  % Talking to self
    location(E, L),
    public_place(L).
```

### Adding World Knowledge

Add facts that categorize objects or locations:

```prolog
% New food category
spicy(O) :- chili(O).
spicy(O) :- pepper(O).
spicy(O) :- wasabi(O).

% New phobia
violation(spicy_food_aversion, E) :-
    trait(C, cant_eat_spicy),
    event(E),
    event_type(E, eat),
    agent(E, C),
    patient(E, Food),
    spicy(Food).
```

### Adding Trait Constraints

```prolog
% New trait: vegetarian
violation(dietary_violation, E) :-
    trait(C, vegetarian),
    event(E),
    event_type(E, eat),
    agent(E, C),
    patient(E, Food),
    meat(Food).

% New trait: pacifist
violation(pacifism_violation, E) :-
    trait(C, pacifist),
    event(E),
    event_type(E, Type),
    agent(E, C),
    member(Type, (fight; attack; kill; hit; punch)).
```

---

## Debugging ASP Rules

### Show All Derived Facts

Add `#show` directives:

```prolog
#show violation/2.
#show violation/3.
#show before/2.
#show holds_at/2.
```

### Trace Derivation

To understand why a violation was detected, temporarily add auxiliary predicates:

```prolog
% Debug: show why ubiquity triggered
debug_ubiquity(E1, E2, Entity, Loc1, Loc2) :-
    violation(ubiquity, E1, E2),
    at_during(Entity, Loc1, E1),
    at_during(Entity, Loc2, E2).

#show debug_ubiquity/5.
```

### Test Individual Rules

Create a minimal test file:

```prolog
% test_dead_agent.lp
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

% Should produce: violation(dead_agent, e2)
```

Run with:
```bash
clingo test_dead_agent.lp rules/base.lp
```
