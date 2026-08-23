% =============================================================================
%
%    NARRATIVE LOGIC ENGINE - CORE DEFINITIONS (v2.0)
%    =================================================
%
%    This file contains core ASP definitions shared by all rule layers.
%    Per LOGIC_DESIGN.md, this is the foundation of the Logic Knowledge Graph.
%
%    VERSION 2.0 CHANGES (Phase 2 Refactor):
%        - Time-indexed facts with explicit timestep progression
%        - Fluent/holds framework for state transitions
%        - Logic Knowledge Graph (LKG) implementation
%        - Global constraints (non-ubiquity, linear time)
%        - Layered rule precedence mechanism
%
%    Rule Layer Hierarchy (Priority Order):
%        1. rules/story/*.lp - Story-specific overrides (highest priority)
%        2. rules/learned/*.lp - ILASP-learned rules
%        3. rules/universal/*.lp - Default world assumptions
%        4. rules/core.lp (this file) - Base definitions (always loaded)
%
% =============================================================================


% =============================================================================
% PART 1: TIME MANAGEMENT (Step 2.1)
% =============================================================================
%
% Per LOGIC_DESIGN.md Section 3.3:
%     - Linear time: discrete, monotonic, strictly ordered
%     - No branching timelines
%
% Time is represented as discrete timesteps T = 0, 1, 2, ...
% The engine provides: max_time(N) to define the time horizon
% =============================================================================

% Generate time points spanning this chapter's own event range.
% NOTE: event ids/times come from a global, ever-increasing counter that is
% never reset per chapter (StateManager.next_event_id), so bounding this to
% 0..max_time would regenerate a time/1 domain (and everything joining on it,
% e.g. before/2 below) that grows without bound as the story progresses even
% though each chapter's own facts only span a handful of new event times.
time(TMin..TMax) :- min_time(TMin), max_time(TMax).

min_time(MinT) :- MinT = #min { T : event_time(_, T) }.

% Default max_time if not provided (from event times)
max_time(MaxT) :- MaxT = #max { T : event_time(_, T) }, MaxT >= 0.

% Fallback: if no events, time 0 exists
time(0) :- not max_time(_).

% Time ordering predicates
before(T1, T2) :- time(T1), time(T2), T1 < T2.
after(T1, T2) :- before(T2, T1).
next_time(T, T+1) :- time(T), time(T+1).

% Initial time (T=0 is the initial state before any events)
initial_time(0).


% =============================================================================
% PART 2: ENTITY TYPES - LOGIC KNOWLEDGE GRAPH (Step 2.2)
% =============================================================================
%
% Per LOGIC_DESIGN.md Section 3.2:
%     Entities (Nodes): character(X), location(X), item(X)
%
% Entities are the nodes in the Logic Knowledge Graph.
% =============================================================================

% Entity type hierarchy
entity(X) :- character(X).
entity(X) :- location(X).
entity(X) :- item(X).

% Backward compatibility aliases
location_entity(X) :- location(X).
object(X) :- item(X).

% Auto-introduce entities from events
character(C) :- agent(_, C), C != unknown.
character(C) :- patient(_, C), not item(C), C != unknown.
location(L) :- event_location(_, L), L != unknown.


% =============================================================================
% PART 2.5: CHARACTER ALIAS RESOLUTION
% =============================================================================
%
% Per LOGIC_DESIGN.md:
%     "Python must not encode story logic"
%     Alias resolution happens in ASP, not Python.
%
% Alias facts are injected by Python as: alias(AliasID, CanonicalID).
% Examples:
%     alias(harry_potter, harry).
%     alias(uncle_vernon, vernon_dursley).
%
% All downstream predicates should use canonical IDs.
% =============================================================================

% --- Canonical ID Resolution ---
% If X is an alias, resolve to canonical; otherwise, X is its own canonical
canonical(X, C) :- alias(X, C).
canonical(X, X) :- entity(X), not alias(X, _).

% Transitive alias resolution (for chains like "potter" -> "harry_potter" -> "harry")
canonical(X, C) :- alias(X, Y), canonical(Y, C), X != Y.

% --- Entity Normalization ---
% Derive canonical character set (no duplicates from aliases)
character_canonical(C) :- character(X), canonical(X, C).
location_canonical(L) :- location(X), canonical(X, L).
item_canonical(I) :- item(X), canonical(X, I).

% --- Predicate Normalization Helpers ---
% These allow queries to work with canonical IDs even when facts use aliases.

% Normalize presence: present_normalized(Canonical, Location, Time)
present_normalized(C_Canon, L, T) :- 
    present(E, L, T), 
    canonical(E, C_Canon).

% Normalize carries: carries_normalized(CharCanon, ItemCanon, Time)
carries_normalized(C_Canon, I_Canon, T) :- 
    carries(C, I, T), 
    canonical(C, C_Canon),
    canonical(I, I_Canon).

% Normalize relationship: relationship_normalized(C1_Canon, C2_Canon, Type, Time)
relationship_normalized(C1_Canon, C2_Canon, Type, T) :- 
    holds(relationship(C1, C2, Type), T),
    canonical(C1, C1_Canon),
    canonical(C2, C2_Canon).

% Normalize traits
trait_normalized(E_Canon, Trait) :- 
    trait(E, Trait), 
    canonical(E, E_Canon).


% =============================================================================
% PART 3: FLUENTS AND STATE (Step 2.1 - State Transitions)
% =============================================================================
%
% Per LOGIC_DESIGN.md Section 4:
%     Events are STATE TRANSITIONS, not static facts.
%     Each event occurs at a specific timestep.
%     Events modify the LKG by changing fluent values.
%
% Fluents are properties that can change over time.
% We use holds(Fluent, T) to represent that Fluent is true at time T.
% =============================================================================

% --- Fluent Types ---
% Fluents represent time-varying properties:
%   present(Entity, Location)   - Entity is at Location
%   carries(Character, Item)    - Character has Item
%   alive(Character)            - Character is alive
%   relationship(C1, C2, Type)  - Relationship between characters

% --- Initial State (T=0) ---
% Initial fluents are provided as: initially(Fluent).
% They become true at T=0.
holds(Fluent, 0) :- initially(Fluent).

% --- Frame Axioms (Persistence) ---
% Fluents persist to the next timestep unless explicitly changed.
% This is the "law of inertia" for the narrative world.
holds(Fluent, T+1) :- 
    holds(Fluent, T), 
    time(T), 
    time(T+1),
    not terminated(Fluent, T),
    not abnormal(Fluent, T).

% --- Effect Axioms (Changes) ---
% Events cause fluent changes via initiates/terminates predicates.
% initiates(E, Fluent) - Event E makes Fluent true
% terminates(E, Fluent) - Event E makes Fluent false

holds(Fluent, T+1) :- 
    event_time(E, T),
    initiates(E, Fluent),
    time(T+1).

terminated(Fluent, T) :- 
    event_time(E, T),
    terminates(E, Fluent).

% Abnormal blocks persistence (for special cases)
% abnormal(Fluent, T) can be defined by story rules


% =============================================================================
% PART 3.5: EXPLICIT vs ASSUMED STATE FRAMEWORK (Phase One Refactor)
% =============================================================================
%
% Per LOGIC_DESIGN.md Phase One:
%     Temporal violations must only derive from EXPLICIT STATE.
%     Assumed states (from persistence/defaults) cannot cause violations.
%
% This distinction prevents false positives from:
%     - Implicit scene changes
%     - Missing location information
%     - Assumed persistence between events
%
% The explicit_state and assumed_state predicates are DEFINED IN temporal.lp
% but we provide core helpers here.
% =============================================================================

% --- Explicit State Interval ---
% For states with known start and end times (from events with intervals)
explicit_state_interval(Entity, State, T_start, T_end, E) :-
    event(E),
    event_start(E, T_start),
    event_end(E, T_end),
    T_start < T_end,
    initiates_state(E, Entity, State).

% --- State Initiation Helpers ---
% These connect events to the states they create

% Movement initiates location state
initiates_state(E, C, at(L)) :-
    event(E),
    is_movement_event(E),
    agent(E, C),
    event_location(E, L),
    L != unknown.

% Death initiates dead state
initiates_state(E, C, dead) :-
    event(E),
    is_death_event(E),
    dies_in_event(E, C).

% Possession initiates carries state
initiates_state(E, C, carries(I)) :-
    event(E),
    is_take_event(E),
    agent(E, C),
    patient(E, I),
    item(I).

% --- State Termination Helpers ---
% Movement terminates previous location state
terminates_state(E, C, at(OldL)) :-
    event(E),
    is_movement_event(E),
    agent(E, C),
    event_time(E, T),
    explicit_state(C, at(OldL), T_prev, _),
    T_prev < T,
    event_location(E, NewL),
    OldL != NewL.

% Drop terminates carries state
terminates_state(E, C, carries(I)) :-
    event(E),
    is_give_event(E),
    agent(E, C),
    patient(E, I).

% --- Helpers for Provenance ---
% Track which event caused which state change

state_changed_by(Entity, State, positive, T, E) :-
    event(E),
    event_time(E, T),
    initiates_state(E, Entity, State).

state_changed_by(Entity, State, negative, T, E) :-
    event(E),
    event_time(E, T),
    terminates_state(E, Entity, State).


% =============================================================================
% PART 4: TIME-INDEXED RELATIONS (Step 2.2 - LKG Relations)
% =============================================================================
%
% Per LOGIC_DESIGN.md Section 3.2:
%     Relations (Edges/Predicates) - Time-Indexed:
%         relationship(C1, C2, Type, T)
%         present(Entity, Location, T)
%         carries(Character, Item, T)
%         connected(L1, L2) - timeless
%         trait(Entity, Trait) - timeless
%
% These are derived from holds/2 for convenience.
% =============================================================================

% --- Presence Relation ---
% present(Entity, Location, T) - Entity is at Location at time T
present(E, L, T) :- holds(present(E, L), T).

% Initialize presence from initially/1
initially(present(E, L)) :- initial_location(E, L).

% --- Possession Relation ---
% carries(Character, Item, T) - Character has Item at time T
carries(C, I, T) :- holds(carries(C, I), T).

% Initialize possession from initially/1
initially(carries(C, I)) :- initial_carries(C, I).

% --- Relationship Relation ---
% relationship(C1, C2, Type, T) - Relationship exists at time T
relationship(C1, C2, Type, T) :- holds(relationship(C1, C2, Type), T).

% Initialize relationships from initially/1
initially(relationship(C1, C2, Type)) :- initial_relationship(C1, C2, Type).

% --- Alive Status ---
% alive(C, T) - Character is alive at time T
alive(C, T) :- holds(alive(C), T).

% Characters are alive initially unless marked dead
initially(alive(C)) :- character(C), not initially_dead(C).

% =============================================================================
% INVARIANT FIX: Characters are ALIVE by default
% =============================================================================
%
% PROBLEM: The fluent inertia framework (holds/initially) requires consecutive
% time steps (T, T+1, T+2...) for state to propagate. Additionally, when
% event_time/2 facts are not generated, the time-indexed alive(C, T) cannot
% be derived, causing `not alive(C, T)` to be true and dead_character_acting
% to fire globally.
%
% FIX: Assert both time-indexed and atemporal alive defaults.
%
% This restores the invariant:
%   "Characters are ALIVE by default unless explicitly marked dead."
%
% =============================================================================

% TIME-INDEXED: Alive at any event time unless died in an earlier event
alive(C, T) :- 
    character(C), 
    event_time(_, T),
    not died_before(C, T).

% Character died before time T if there's a death event at an earlier time
died_before(C, T) :- 
    dies_in_event(E, C), 
    event_time(E, T_death),
    event_time(_, T),
    T_death < T.

% ATEMPORAL: Characters are alive unless explicitly marked dead
% This handles cases where event_time/2 is not available
alive(C) :- character(C), not explicitly_dead(C).

% Explicitly dead: character state is "dead" or died in an event (atemporal)
explicitly_dead(C) :- is_dead_explicit(C).
explicitly_dead(C) :- dies_in_event(_, C).

% is_dead_explicit/1 is asserted by asp_converter when character state = "dead"
% (via the existing is_dead(C) fact emission)

% Death tracking (convenience predicate)
% Only mark as dead if NOT atemporally alive (fixes the invariant)
is_dead(C, T) :- character(C), time(T), not alive(C, T), not alive(C).
is_dead(C) :- explicitly_dead(C).


% =============================================================================
% PART 5: DERIVED RELATIONS (Step 2.2)
% =============================================================================
%
% Per LOGIC_DESIGN.md Section 3.2:
%     Item presence via carrying:
%     If a character carries an item and is present in a location,
%     the item is present in that location.
% =============================================================================

% Item is present where its carrier is
item_present(Item, Loc, T) :-
    carries(Char, Item, T),
    present(Char, Loc, T).

% Alternative: item present directly (dropped/placed items)
item_present(Item, Loc, T) :- holds(item_at(Item, Loc), T).


% =============================================================================
% PART 5.5: LOCATION CONTAINMENT (Phase Two - Evidence-Based Presence)
% =============================================================================
%
% Locations can have containment relationships:
%     contains(Parent, Child) - Child is inside Parent
%
% Examples:
%     contains(house, kitchen).
%     contains(house, hallway).
%     contains(diagon_alley, ollivanders).
%
% Phase Two Changes:
%     - Presence is EVIDENCE-BASED, not continuous
%     - Characters can "disappear" from tracking without contradiction
%     - Movement within containment chain is always allowed
%     - Non-ubiquity only fires on EXPLICIT presence (see location.lp)
%
% The detailed containment logic is now in rules/universal/location.lp
% This section provides backward-compatible helpers.
% =============================================================================

% --- Presence Propagation (Backward Compatibility) ---
% Presence in a sub-location implies presence in its container.
% NOTE: This is now a DERIVED presence, not an explicit one.
% For violation detection, use explicit_presence from location.lp
present_in_container(E, Parent, T) :-
    present(E, Child, T),
    contains(Parent, Child).

% Transitive containment (now also defined in location.lp)
contains_transitive(Parent, Child) :- contains(Parent, Child).
contains_transitive(Ancestor, Child) :- 
    contains(Ancestor, Intermediate),
    contains_transitive(Intermediate, Child).

% --- Container-based Connectivity ---
% Locations within the same container are implicitly connected.
same_container(L1, L2) :-
    contains(Parent, L1),
    contains(Parent, L2),
    L1 != L2.

% A location and its container are connected
same_container(Child, Parent) :- contains(Parent, Child).
same_container(Parent, Child) :- contains(Parent, Child).

% Container connectivity is symmetric
same_container(L2, L1) :- same_container(L1, L2).

% --- Helper: Check if travel is within same container ---
% Used to suppress time_travel and impossible_travel violations
travel_within_container(L1, L2) :- same_container(L1, L2).
travel_within_container(L1, L2) :- contains_transitive(L1, L2).
travel_within_container(L1, L2) :- contains_transitive(L2, L1).


% =============================================================================
% PART 6: EVENT EFFECTS (Step 2.1 - State Transitions)
% =============================================================================
%
% Per LOGIC_DESIGN.md Section 4:
%     Events modify the LKG by:
%         - Changing presence
%         - Adding/removing relationships
%         - Modifying carried items
%         - Introducing or overriding rules
%
% Each event type has associated initiates/terminates effects.
% =============================================================================

% --- Movement Events ---
% Moving to a location initiates presence there, terminates old presence
initiates(E, present(C, L)) :- 
    event(E), 
    is_movement_event(E),
    agent(E, C),
    event_location(E, L),
    L != unknown.

terminates(E, present(C, OldL)) :- 
    event(E),
    is_movement_event(E),
    agent(E, C),
    event_time(E, T),
    present(C, OldL, T),
    event_location(E, NewL),
    OldL != NewL.

% --- Refined Movement Event Types (Phase 3) ---
% These provide more precise semantics for spatial reasoning:
%   enter  - entering a container/building/room (implies presence inside)
%   exit   - exiting a container/building/room (terminates presence inside)
%   travel - movement between distant/unconnected locations
%   arrive - generic arrival at a location (legacy, mapped to enter where possible)
%   leave  - generic departure (legacy, mapped to exit where possible)

is_movement_event(E) :- event_type(E, travel).
is_movement_event(E) :- event_type(E, move).
is_movement_event(E) :- event_type(E, go).
is_movement_event(E) :- event_type(E, walk).
is_movement_event(E) :- event_type(E, run).
is_movement_event(E) :- event_type(E, enter).
is_movement_event(E) :- event_type(E, exit).
is_movement_event(E) :- event_type(E, leave).
is_movement_event(E) :- event_type(E, arrive).
is_movement_event(E) :- event_type(E, depart).
is_movement_event(E) :- event_type(E, fly).
is_movement_event(E) :- event_type(E, apparate).
is_movement_event(E) :- event_type(E, teleport).

% Refined movement type classification
is_enter_event(E) :- event_type(E, enter).
is_enter_event(E) :- event_type(E, arrive).  % Legacy mapping
is_exit_event(E) :- event_type(E, exit).
is_exit_event(E) :- event_type(E, leave).    % Legacy mapping
is_exit_event(E) :- event_type(E, depart).   % Legacy mapping
is_travel_event(E) :- event_type(E, travel).
is_travel_event(E) :- event_type(E, fly).
is_travel_event(E) :- event_type(E, apparate).
is_travel_event(E) :- event_type(E, teleport).

% --- Implicit Leave Events (from MovementContinuityGuard) ---
% These are derived events inserted when a character appears at a new location
% without explicit movement. They bridge gaps in the narrative extraction.
is_movement_event(E) :- event_type(E, implicit_leave).
is_exit_event(E) :- event_type(E, implicit_leave).

% Implicit transitions provide context about derived movement
% implicit_transition(Agent, FromLoc, ToLoc, AfterEvent, BeforeEvent)
% This fact is purely informational for debugging/auditing.

% --- Death Events ---
% Death terminates alive status
terminates(E, alive(C)) :- 
    event(E),
    is_death_event(E),
    dies_in_event(E, C).

% Who dies in a death event
dies_in_event(E, C) :- event(E), is_death_event(E), patient(E, C).
dies_in_event(E, C) :- event(E), event_type(E, die), agent(E, C).
dies_in_event(E, C) :- event(E), event_type(E, dies), agent(E, C).
dies_in_event(E, C) :- event(E), event_type(E, death), agent(E, C).

is_death_event(E) :- event_type(E, die).
is_death_event(E) :- event_type(E, dies).
is_death_event(E) :- event_type(E, died).
is_death_event(E) :- event_type(E, death).
is_death_event(E) :- event_type(E, kill).
is_death_event(E) :- event_type(E, killed).
is_death_event(E) :- event_type(E, murder).
is_death_event(E) :- event_type(E, execute).

% --- Possession Events ---
% Taking initiates carrying
initiates(E, carries(C, I)) :-
    event(E),
    is_take_event(E),
    agent(E, C),
    patient(E, I),
    item(I).

is_take_event(E) :- event_type(E, take).
is_take_event(E) :- event_type(E, pick_up).
is_take_event(E) :- event_type(E, grab).
is_take_event(E) :- event_type(E, receive).
is_take_event(E) :- event_type(E, get).

% Giving/dropping terminates carrying
terminates(E, carries(C, I)) :-
    event(E),
    is_give_event(E),
    agent(E, C),
    patient(E, I),
    item(I).

is_give_event(E) :- event_type(E, give).
is_give_event(E) :- event_type(E, drop).
is_give_event(E) :- event_type(E, put_down).
is_give_event(E) :- event_type(E, lose).
is_give_event(E) :- event_type(E, hand_over).

% Receiving initiates carrying for recipient
initiates(E, carries(Recipient, I)) :-
    event(E),
    is_give_event(E),
    patient(E, I),
    item(I),
    recipient(E, Recipient).

% --- Relationship Events ---
% Some events modify relationships
initiates(E, relationship(C1, C2, Type)) :-
    event(E),
    creates_relationship(E, C1, C2, Type).

terminates(E, relationship(C1, C2, OldType)) :-
    event(E),
    changes_relationship(E, C1, C2, _, OldType).


% =============================================================================
% PART 6.5: CHARACTER STATES (Phase 3 - Explicit State Modeling)
% =============================================================================
%
% Per Phase 3 requirements:
%     - Track explicit character states: seated, lying, standing, asleep, awake
%     - States persist until changed by an event
%     - Contradictions arise only when states truly conflict
%
% State fluents:
%     posture(C, seated)   - Character is seated
%     posture(C, lying)    - Character is lying down
%     posture(C, standing) - Character is standing (default)
%     consciousness(C, asleep) - Character is asleep
%     consciousness(C, awake)  - Character is awake (default)
%
% =============================================================================

% --- Posture States ---
% Postures: seated, lying, standing (mutually exclusive)

% Sitting initiates seated posture, terminates other postures
initiates(E, posture(C, seated)) :-
    event(E),
    is_sit_event(E),
    agent(E, C).

terminates(E, posture(C, standing)) :-
    event(E),
    is_sit_event(E),
    agent(E, C).

terminates(E, posture(C, lying)) :-
    event(E),
    is_sit_event(E),
    agent(E, C).

is_sit_event(E) :- event_type(E, sit).
is_sit_event(E) :- event_type(E, sit_down).
is_sit_event(E) :- event_type(E, seat).

% Standing initiates standing posture, terminates other postures
initiates(E, posture(C, standing)) :-
    event(E),
    is_stand_event(E),
    agent(E, C).

terminates(E, posture(C, seated)) :-
    event(E),
    is_stand_event(E),
    agent(E, C).

terminates(E, posture(C, lying)) :-
    event(E),
    is_stand_event(E),
    agent(E, C).

is_stand_event(E) :- event_type(E, stand).
is_stand_event(E) :- event_type(E, stand_up).
is_stand_event(E) :- event_type(E, get_up).
is_stand_event(E) :- event_type(E, rise).

% Lying down initiates lying posture, terminates other postures
initiates(E, posture(C, lying)) :-
    event(E),
    is_lie_down_event(E),
    agent(E, C).

terminates(E, posture(C, standing)) :-
    event(E),
    is_lie_down_event(E),
    agent(E, C).

terminates(E, posture(C, seated)) :-
    event(E),
    is_lie_down_event(E),
    agent(E, C).

is_lie_down_event(E) :- event_type(E, lie_down).
is_lie_down_event(E) :- event_type(E, lie).
is_lie_down_event(E) :- event_type(E, recline).
is_lie_down_event(E) :- event_type(E, collapse).
is_lie_down_event(E) :- event_type(E, fall).
is_lie_down_event(E) :- event_type(E, faint).

% --- Consciousness States ---
% Consciousness: asleep, awake (mutually exclusive)

% Sleeping initiates asleep state, terminates awake
initiates(E, consciousness(C, asleep)) :-
    event(E),
    is_sleep_event(E),
    agent(E, C).

terminates(E, consciousness(C, awake)) :-
    event(E),
    is_sleep_event(E),
    agent(E, C).

is_sleep_event(E) :- event_type(E, sleep).
is_sleep_event(E) :- event_type(E, fall_asleep).
is_sleep_event(E) :- event_type(E, doze).
is_sleep_event(E) :- event_type(E, nap).
is_sleep_event(E) :- event_type(E, faint).
is_sleep_event(E) :- event_type(E, pass_out).

% Waking up initiates awake state, terminates asleep
initiates(E, consciousness(C, awake)) :-
    event(E),
    is_wake_event(E),
    agent(E, C).

terminates(E, consciousness(C, asleep)) :-
    event(E),
    is_wake_event(E),
    agent(E, C).

is_wake_event(E) :- event_type(E, wake_up).
is_wake_event(E) :- event_type(E, wake).
is_wake_event(E) :- event_type(E, awaken).
is_wake_event(E) :- event_type(E, rouse).

% --- State Convenience Predicates ---
% Derive readable state predicates from holds/2

posture(C, Posture, T) :- holds(posture(C, Posture), T).
consciousness(C, State, T) :- holds(consciousness(C, State), T).

% Atemporal shortcuts (latest state)
is_seated(C) :- posture(C, seated, T), not posture_changed_after(C, T).
is_lying(C) :- posture(C, lying, T), not posture_changed_after(C, T).
is_standing(C) :- posture(C, standing, T), not posture_changed_after(C, T).
is_asleep(C) :- consciousness(C, asleep, T), not consciousness_changed_after(C, T).
is_awake(C) :- consciousness(C, awake, T), not consciousness_changed_after(C, T).

posture_changed_after(C, T) :-
    posture(C, _, T),
    posture(C, _, T2),
    T2 > T.

consciousness_changed_after(C, T) :-
    consciousness(C, _, T),
    consciousness(C, _, T2),
    T2 > T.

% --- Default Initial States ---
% Characters default to standing and awake unless specified otherwise
initially(posture(C, standing)) :- 
    character(C), 
    not initially_seated(C),
    not initially_lying(C).

initially(consciousness(C, awake)) :- 
    character(C), 
    not initially_asleep(C).

% --- State Conflict Detection ---
% Conflicting postures at the same time
violation(coherence, posture_conflict, C, pair(P1, P2)) :-
    character(C),
    posture(C, P1, T),
    posture(C, P2, T),
    P1 != P2.

% Conflicting consciousness at the same time
violation(coherence, consciousness_conflict, C, pair(S1, S2)) :-
    character(C),
    consciousness(C, S1, T),
    consciousness(C, S2, T),
    S1 != S2.

% --- State-Action Constraints ---
% Certain actions require specific states

% DISABLED: action_while_asleep generates too many false positives
% Sleeping character cannot perform most actions
% violation(coherence, action_while_asleep, E, C) :-
%     event(E),
%     agent(E, C),
%     event_time(E, T),
%     consciousness(C, asleep, T),
%     not is_wake_event(E),
%     not is_sleep_related_event(E),
%     not is_passive_event(E).

is_sleep_related_event(E) :- event_type(E, dream).
is_sleep_related_event(E) :- event_type(E, nightmare).
is_sleep_related_event(E) :- event_type(E, snore).

% Passive events can happen to sleeping characters
% An event is passive if it has no agent (patient-only events)
is_passive_event(E) :- event(E), not has_agent(E).
is_passive_event(E) :- event_type(E, receive).
is_passive_event(E) :- event_type(E, hear).  % Might hear in sleep

% Helper: check if event has an agent
has_agent(E) :- agent(E, _).


% =============================================================================
% PART 7: GLOBAL CONSTRAINTS (Step 2.3)
% =============================================================================
%
% Per LOGIC_DESIGN.md Section 3.3:
%     - NON-UBIQUITY: Entity cannot be in multiple locations at same time
%     - LINEAR TIME: Discrete, monotonic, strictly ordered
%     - Items follow characters unless explicitly dropped
%
% Constraints can be hard (integrity constraints) or soft (violations).
% =============================================================================

% --- NON-UBIQUITY CONSTRAINT ---
% An entity cannot be present in more than one location at the same time.
% This is a SOFT constraint (detected as violation, not rejected).
%
% Phase Two Changes:
%     - This rule now only fires for BACKWARD COMPATIBILITY with present/3
%     - The PRIMARY ubiquity check is in location.lp using explicit_presence
%     - The explicit_ubiquity violation requires two EXPLICIT presence facts
%     - This rule uses frame-axiom presence, so it may fire on persisted presence
%
% EXCEPTION: Being in a sub-location AND its container is NOT ubiquity.
% e.g., present(harry, kitchen, T) and present_in_container(harry, house, T)
% are consistent because kitchen ⊂ house.
%
% NOTE: For new code, prefer the explicit_ubiquity rule in location.lp which
%       only fires on explicit presence assertions (no false positives from persistence).

violation(location, ubiquity, E, pair(L1, L2)) :-
    entity(E),
    present(E, L1, T),
    present(E, L2, T),
    L1 != L2,
    L1 != unknown,
    L2 != unknown,
    not ubiquity_allowed(E),
    not containment_explains_presence(E, L1, L2, T),
    not same_container(L1, L2).  % Phase Two: same-container locations are coherent

% Containment explains apparent ubiquity
% If L1 contains L2 (or vice versa), presence in both is coherent (not a violation)
containment_explains_presence(E, L1, L2, T) :-
    present(E, L1, T),
    present(E, L2, T),
    contains(L1, L2).

containment_explains_presence(E, L1, L2, T) :-
    present(E, L1, T),
    present(E, L2, T),
    contains(L2, L1).

% Transitive containment also explains apparent ubiquity
containment_explains_presence(E, L1, L2, T) :-
    present(E, L1, T),
    present(E, L2, T),
    contains_transitive(L1, L2).

containment_explains_presence(E, L1, L2, T) :-
    present(E, L1, T),
    present(E, L2, T),
    contains_transitive(L2, L1).

% Story rules can allow ubiquity for specific entities (e.g., teleportation)
% ubiquity_allowed(Entity) :- ...

% --- HARD CONSTRAINT VERSION (uncomment to reject invalid models) ---
% :- present(E, L1, T), present(E, L2, T), L1 != L2, L1 != unknown, L2 != unknown, not ubiquity_allowed(E).

% --- ITEM FOLLOWS CARRIER ---
% Items carried by a character are present where the character is.
% (Already implemented via item_present/3 derived relation)

% Violation: Item in two places (carried AND elsewhere)
violation(location, item_ubiquity, I, pair(L1, L2)) :-
    item(I),
    item_present(I, L1, T),
    item_present(I, L2, T),
    L1 != L2,
    L1 != unknown,
    L2 != unknown.

% --- LINEAR TIME VALIDATION ---
% Time must progress monotonically (enforced by time/1 generation).
% Events must have valid times.
violation(temporal, invalid_event_time, E, T) :-
    event_time(E, T),
    not time(T).


% =============================================================================
% PART 8: LAYERED RULE PRECEDENCE (Step 2.4)
% =============================================================================
%
% Per LOGIC_DESIGN.md Section 3.1:
%     1. Story-Specific Rules (highest priority) - override all others
%     2. Learned Rules - inferred via ILASP
%     3. Universal Rules (lowest priority) - default assumptions
%
% Contradicted rules are DEACTIVATED but RETAINED for auditing.
% =============================================================================

% --- Rule Layer Definitions ---
% rule_layer(RuleID, Layer) - Assigns a rule to a layer
% Layer values: story (3), learned (2), universal (1)
rule_priority(story, 3).
rule_priority(learned, 2).
rule_priority(universal, 1).

% --- Rule Metadata ---
% rule(RuleID, Layer, Description) - Rule registration
% Rules register themselves via this predicate

% --- Override Mechanism ---
% override(OverridingRule, OverriddenRule) - Explicit override declaration
% Story rules can override universal rules.

% A rule is active if not overridden by a higher-priority rule
rule_active(RuleID) :- 
    rule(RuleID, Layer, _),
    not rule_overridden(RuleID).

rule_overridden(RuleID) :- 
    override(OverridingRule, RuleID),
    rule(OverridingRule, OverridingLayer, _),
    rule(RuleID, OverriddenLayer, _),
    rule_priority(OverridingLayer, P1),
    rule_priority(OverriddenLayer, P2),
    P1 > P2.

% --- Violation Suppression via Overrides ---
% story_override(ViolationType) suppresses that violation type
suppressed(Category, Type, E, D) :-
    violation(Category, Type, E, D),
    story_override(Type).

% story_exception(ViolationType, Entity) allows specific exceptions
suppressed(Category, Type, E, Entity) :-
    violation(Category, Type, E, Entity),
    story_exception(Type, Entity).

% --- Conflict Tracking (for auditing) ---
% Track when rules conflict for final analysis
rule_conflict(OverridingRule, OverriddenRule, Reason) :-
    override(OverridingRule, OverriddenRule),
    rule_active(OverridingRule),
    Reason = override.

% --- Deactivation Audit Trail ---
% deactivated_rule(RuleID, ByRule, AtTime) - Track deactivations
deactivated_rule(RuleID, ByRule, T) :-
    override(ByRule, RuleID),
    rule_active(ByRule),
    event_time(_, T).  % At any event time


% =============================================================================
% PART 9: BACKWARD COMPATIBILITY
% =============================================================================
%
% These predicates maintain compatibility with existing rule files
% that use the old (non-time-indexed) format.
% =============================================================================

% Old-style event location (event_location vs location/2)
event_location(E, L) :- location(E, L).

% Old-style character_at derived from presence
character_at(C, L, E) :- 
    event(E),
    agent(E, C),
    event_location(E, L).

% Old-style is_dead (atemporal) - already defined above

% Old-style relationship (atemporal, uses latest)
relationship(C1, C2, Type) :- 
    relationship(C1, C2, Type, T),
    not relationship_changed_after(C1, C2, T).

relationship_changed_after(C1, C2, T) :-
    relationship(C1, C2, _, T),
    relationship(C1, C2, _, T2),
    T2 > T.

% Old-style carries (atemporal)
carries(C, I) :- carries(C, I, _).

% Event ordering from event_order facts
time_order(E1, E2) :-
    event_order(E1, N1),
    event_order(E2, N2),
    N1 < N2.


% =============================================================================
% PART 10: OUTPUT AND DEBUGGING
% =============================================================================

% Show violations in answer set (unsuppressed only)
% NOTE: emotional.lp/temporal.lp's evidence-gated relationship/ordering/causal
% rules produce violation/3 (category, type, single compound detail term),
% which was previously never declared here -- Clingo silently drops any
% predicate arity that isn't shown, so those rules were being solved but
% discarded before ever reaching Python. Declaring both arities used by the
% loaded rule set restores them without changing any rule's own logic.
#show violation/3.
#show violation/4.

% Show suppressed violations separately (for analysis)
#show suppressed/4.

% Show rule conflicts (for auditing)
#show rule_conflict/3.

% Debugging helpers (uncomment as needed)
% #show holds/2.
% #show present/3.
% #show carries/3.
% #show alive/2.
% #show initiates/2.
% #show terminates/2.
% #show entity/1.
% #show rule_active/1.
% #show rule_overridden/1.
