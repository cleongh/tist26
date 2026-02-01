% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - TEMPORAL (v3.0 - Phase One Refactor)
%    ==================================================================
%
%    Default world assumptions for time ordering and duration.
%    These rules can be overridden by story-specific rules.
%
%    Per LOGIC_DESIGN.md Section 3.3:
%        LINEAR TIME: Time is discrete, monotonic, and strictly ordered.
%        NO BRANCHING: No flashbacks, flashforwards, or alternate histories.
%
%    VERSION 3.0 CHANGES (Phase One):
%        - Temporal violations only fire on EXPLICIT contradictions
%        - Introduced explicit_state vs assumed_state distinction
%        - Presence is NOT assumed continuous unless explicitly stated
%        - Time travel requires explicit contradictory state assertions
%        - Ordering violations require must_precede AND evidence of reversal
%        - All violations include triggering events, times, and entities
%
%    DESIGN PRINCIPLE:
%        Time is linear, but evidence is PARTIAL.
%        Missing information is NOT a violation.
%        Only explicit contradictions trigger errors.
%
%    TEMPORAL VIOLATIONS:
%        - Explicit ordering reversal (must_precede violated)
%        - Explicit causal reversal (effect precedes cause)
%        - Explicit state contradiction (same entity, contradictory states, overlapping times)
%        - Simultaneous contradictory actions (same agent, incompatible actions)
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(temporal_ordering_violation, universal, "Events must respect explicit must_precede ordering").
rule(temporal_causal_violation, universal, "Effects cannot precede their explicitly linked causes").
rule(temporal_state_contradiction, universal, "Same entity cannot have contradictory explicit states at same time").
rule(temporal_simultaneous_contradiction, universal, "Same agent cannot do contradictory actions at once").

% =============================================================================
% TIME ORDERING (Uses core.lp time management)
% =============================================================================

% Derive time ordering from event_time (uses time/1 from core.lp)
time_order(E1, E2) :-
    event(E1),
    event(E2),
    E1 != E2,
    event_time(E1, T1),
    event_time(E2, T2),
    before(T1, T2).

% Also support explicit event_order
time_order(E1, E2) :-
    event_order(E1, N1),
    event_order(E2, N2),
    N1 < N2.

% Events happen at their specified time
happens_at(E, T) :- event_time(E, T).

% Immediately follows
immediately_follows(E1, E2) :-
    event(E1),
    event(E2),
    event_time(E1, T1),
    event_time(E2, T2),
    next_time(T1, T2).


% =============================================================================
% PART A: EXPLICIT STATE vs ASSUMED STATE (Phase One - Core Distinction)
% =============================================================================
%
% DESIGN PRINCIPLE:
%     Temporal violations must only derive from EXPLICIT_STATE.
%     Assumed states (inferred from persistence/defaults) cannot cause violations.
%
% explicit_state(Entity, State, Time, SourceEvent)
%     - State explicitly asserted by an event
%     - Includes the event that caused this state (for provenance)
%
% assumed_state(Entity, State, Time)
%     - State inferred from frame axioms or defaults
%     - Never triggers temporal violations
%
% =============================================================================

% --- Explicit State Assertions ---
% A state is EXPLICIT if it was directly caused by an event.

% Explicit presence: event explicitly places entity at location
explicit_state(Entity, at(Location), T, E) :-
    event(E),
    event_time(E, T),
    is_movement_event(E),
    agent(E, Entity),
    event_location(E, Location),
    Location != unknown.

% Explicit presence from event location for non-movement events
% (character is at location because event happens there)
explicit_state(Entity, at(Location), T, E) :-
    event(E),
    event_time(E, T),
    agent(E, Entity),
    event_location(E, Location),
    Location != unknown.

% Explicit alive/dead state from death events
explicit_state(Entity, dead, T, E) :-
    event(E),
    event_time(E, T),
    is_death_event(E),
    dies_in_event(E, Entity).

% Explicit alive state - characters are alive if no death event
explicit_state(Entity, alive, T, none) :-
    character(Entity),
    time(T),
    not has_explicit_death(Entity, T).

% Helper: entity has explicit death at or before time T
has_explicit_death(Entity, T) :-
    explicit_state(Entity, dead, T2, _),
    T2 <= T.

% Explicit relationship states
explicit_state(relationship(C1, C2), Type, T, E) :-
    event(E),
    event_time(E, T),
    initiates(E, relationship(C1, C2, Type)).

% Explicit possession states
explicit_state(carries(Char), Item, T, E) :-
    event(E),
    event_time(E, T),
    initiates(E, carries(Char, Item)).

% --- Assumed State (Persistence) ---
% Assumed states are inferred, never trigger violations.

% Assumed presence: persisted from earlier explicit state
assumed_state(Entity, at(Location), T) :-
    explicit_state(Entity, at(Location), T_earlier, _),
    time(T),
    T_earlier < T,
    not has_later_explicit_location(Entity, T_earlier, T).

% Helper: entity has an explicit location change after T1 but at or before T2
has_later_explicit_location(Entity, T_earlier, T) :-
    explicit_state(Entity, at(_), T_change, _),
    T_earlier < T_change,
    T_change <= T.

% Assumed alive: persisted from alive state
assumed_state(Entity, alive, T) :-
    character(Entity),
    time(T),
    not has_explicit_death(Entity, T).

% --- State Query Helpers ---
% These helpers check for any state (explicit or assumed)

has_explicit_state(Entity, State, T) :-
    explicit_state(Entity, State, T, _).

has_any_state(Entity, State, T) :-
    explicit_state(Entity, State, T, _).

has_any_state(Entity, State, T) :-
    assumed_state(Entity, State, T).


% =============================================================================
% PART B: MUST-PRECEDE VIOLATIONS (Explicit Only)
% =============================================================================
%
% Ordering violations require:
%     1. An explicit must_precede(E1, E2) constraint
%     2. Evidence that E2 happened at or before E1's time
%
% =============================================================================

% Events can have explicit ordering requirements
% must_precede(E1, E2) means E1 must happen before E2

% VIOLATION: Event that should precede actually follows
% Requires explicit must_precede AND explicit time evidence showing reversal
violation(temporal, ordering_violation, violation_info(E2, expected_after, E1, at_times, T2, T1)) :-
    rule_active(temporal_ordering_violation),
    must_precede(E1, E2),
    event(E1),
    event(E2),
    event_time(E1, T1),
    event_time(E2, T2),
    not before(T1, T2).  % E1 is not before E2

% Alternative using event_order (if event_time not available)
violation(temporal, ordering_violation, violation_info(E2, expected_after, E1, order, N2, N1)) :-
    rule_active(temporal_ordering_violation),
    must_precede(E1, E2),
    event(E1),
    event(E2),
    event_order(E1, N1),
    event_order(E2, N2),
    not event_time(E1, _),  % Only use event_order if no event_time
    N1 >= N2.

% =============================================================================
% PART C: CAUSAL ORDERING (Explicit Only)
% =============================================================================
%
% Causal violations require EXPLICIT causal_link between events.
% Only fires when the linked effect precedes its linked cause.
%
% =============================================================================

% Causes must precede effects (derived from explicit causal_link)
causes(E1, E2) :- causal_link(E1, E2).

% VIOLATION: Effect precedes cause (with full context)
violation(temporal, causal_violation, violation_info(effect, E2, at, T2, precedes_cause, E1, at, T1)) :-
    rule_active(temporal_causal_violation),
    causes(E1, E2),
    event(E1),
    event(E2),
    event_time(E1, T1),
    event_time(E2, T2),
    before(T2, T1).  % E2 is before E1, but E1 causes E2


% =============================================================================
% PART D: EXPLICIT STATE CONTRADICTION (Phase One Core)
% =============================================================================
%
% State contradiction violations ONLY fire when:
%     1. Two EXPLICIT states are asserted for the same entity
%     2. The states are contradictory (defined by contradictory_states/2)
%     3. The times overlap or are the same
%
% CRITICAL: Assumed states (persistence) NEVER trigger these violations.
%
% =============================================================================

% --- Contradictory State Pairs ---
% Only these pairs can trigger temporal_state_contradiction

contradictory_states(alive, dead).
contradictory_states(dead, alive).
contradictory_states(at(L1), at(L2)) :- L1 != L2, L1 != unknown, L2 != unknown.

% Visibility
contradictory_states(visible, invisible).
contradictory_states(invisible, visible).

% Consciousness
contradictory_states(asleep, awake).
contradictory_states(awake, asleep).
contradictory_states(conscious, unconscious).
contradictory_states(unconscious, conscious).

% Posture (if modeled as explicit states)
contradictory_states(standing, lying).
contradictory_states(lying, standing).
contradictory_states(standing, sitting).
contradictory_states(sitting, standing).
contradictory_states(lying, sitting).
contradictory_states(sitting, lying).

% --- VIOLATION: Explicit State Contradiction ---
% Two explicit states for same entity at same time that contradict each other
violation(temporal, state_contradiction, 
          violation_info(Entity, has_contradictory_states, S1, from_event, E1, and, S2, from_event, E2, at_time, T)) :-
    rule_active(temporal_state_contradiction),
    explicit_state(Entity, S1, T, E1),
    explicit_state(Entity, S2, T, E2),
    E1 != E2,
    contradictory_states(S1, S2).

% --- VIOLATION: Overlapping Interval State Contradiction ---
% For states with intervals [T1_start, T1_end] and [T2_start, T2_end]
% Only if both are explicitly asserted and intervals overlap
violation(temporal, state_contradiction, 
          violation_info(Entity, has_overlapping_contradictory_states, S1, from, T1, to, T1_end, and, S2, from, T2)) :-
    rule_active(temporal_state_contradiction),
    explicit_state_interval(Entity, S1, T1, T1_end, E1),
    explicit_state(Entity, S2, T2, E2),
    E1 != E2,
    contradictory_states(S1, S2),
    T1 <= T2,
    T2 < T1_end.  % T2 falls within [T1, T1_end)


% =============================================================================
% PART E: SIMULTANEOUS ACTION CONSTRAINTS (Explicit Only)
% =============================================================================
%
% Simultaneous action violations require:
%     1. Two events with the same agent
%     2. Events happen at exactly the same time (explicit)
%     3. Event types are incompatible
%
% =============================================================================

% Incompatible simultaneous action pairs
cannot_simultaneous(sleep, run).
cannot_simultaneous(run, sleep).
cannot_simultaneous(sleep, walk).
cannot_simultaneous(walk, sleep).
cannot_simultaneous(sleep, fight).
cannot_simultaneous(fight, sleep).
cannot_simultaneous(die, run).
cannot_simultaneous(run, die).
cannot_simultaneous(die, walk).
cannot_simultaneous(walk, die).
cannot_simultaneous(die, fight).
cannot_simultaneous(fight, die).

% VIOLATION: Same agent, same time, incompatible actions
violation(temporal, simultaneous_contradiction, 
          violation_info(Agent, performs, Type1, in_event, E1, and, Type2, in_event, E2, at_time, T)) :-
    rule_active(temporal_simultaneous_contradiction),
    event(E1),
    event(E2),
    E1 < E2,  % Avoid duplicate violations
    event_time(E1, T),
    event_time(E2, T),  % Same explicit time
    agent(E1, Agent),
    agent(E2, Agent),  % Same agent
    event_type(E1, Type1),
    event_type(E2, Type2),
    cannot_simultaneous(Type1, Type2).

% VIOLATION: Overlapping intervals with incompatible actions
violation(temporal, simultaneous_contradiction, 
          violation_info(Agent, performs_overlapping, Type1, from, S1, to, End1, and, Type2, from, S2, to, End2)) :-
    rule_active(temporal_simultaneous_contradiction),
    event(E1),
    event(E2),
    E1 < E2,
    agent(E1, Agent),
    agent(E2, Agent),
    event_type(E1, Type1),
    event_type(E2, Type2),
    cannot_simultaneous(Type1, Type2),
    event_start(E1, S1),
    event_end(E1, End1),
    event_start(E2, S2),
    event_end(E2, End2),
    S1 < End2,
    S2 < End1.  % Intervals overlap

% =============================================================================
% PART F: TIME TRAVEL DETECTION (Phase One - Explicit Only)
% =============================================================================
%
% Time travel violations ONLY fire when:
%     1. Two EXPLICIT location states for the same character
%     2. The times are in reversed order (T2 < T1 in narrative sequence)
%     3. Both states are event-linked (not assumed persistence)
%
% CRITICAL:
%     - Implicit scene changes do NOT trigger time_travel
%     - Missing location information does NOT trigger time_travel
%     - Only explicit contradictory presence assertions trigger violations
%
% =============================================================================

% --- Rule Registration ---
rule(temporal_no_time_travel, universal, "Characters cannot travel backwards in time (explicit evidence only)").

% --- Explicit Presence Pairs ---
% Two explicit presence assertions that could indicate time travel
explicit_presence_pair(Character, Loc1, T1, E1, Loc2, T2, E2) :-
    explicit_state(Character, at(Loc1), T1, E1),
    explicit_state(Character, at(Loc2), T2, E2),
    E1 != E2,
    E1 != none,
    E2 != none,
    Loc1 != Loc2,
    T1 != T2.

% --- Time Travel Detection (Informational) ---
% Detects potential time travel for analysis, NOT automatically a violation
potential_time_travel(Character, Loc1, T1, E1, Loc2, T2, E2) :-
    explicit_presence_pair(Character, Loc1, T1, E1, Loc2, T2, E2),
    before(T2, T1).  % Event E2 happens at earlier time T2, but is extracted after E1

% --- VIOLATION: Explicit Time Travel ---
% Only fires when:
%   1. We have two explicit presence events (not assumed)
%   2. The event that happens "later" in extraction has an earlier time index
%   3. The rule is active
%
% This catches: "Harry was in London at T=5, then was in Paris at T=3"
% This does NOT catch: implicit scene changes or missing locations
violation(temporal, time_travel, 
          violation_info(Character, at, Loc1, via_event, E1, at_time, T1, 
                        then_at, Loc2, via_event, E2, at_earlier_time, T2)) :-
    rule_active(temporal_no_time_travel),
    potential_time_travel(Character, Loc1, T1, E1, Loc2, T2, E2),
    not travel_within_container(Loc1, Loc2),  % Exclude same-building movement
    not is_teleport_event(E2).  % Exclude magical travel

% --- Helpers for Suppression ---
% These prevent false positives from legitimate narrative patterns

% Teleport/apparate events can "travel backwards" in narrative time
is_teleport_event(E) :- event_type(E, apparate).
is_teleport_event(E) :- event_type(E, teleport).
is_teleport_event(E) :- event_type(E, portal).
is_teleport_event(E) :- event_type(E, floo).
is_teleport_event(E) :- event_type(E, time_travel).  % Explicit time travel in story

% Flashback narration is indicated by story rule
allows_time_travel(Character) :- story_allows_flashback(Character).
allows_time_travel(Character) :- story_allows_time_travel(Character).

% Suppress violation if story explicitly allows time travel
% (violation rule already requires rule_active, story can deactivate rule)


% =============================================================================
% PART G: NARRATIVE SEQUENCE HELPERS
% =============================================================================

% First and last events (by time)
first_event(E) :-
    event(E),
    event_time(E, T),
    T = #min { T2 : event_time(_, T2) }.

last_event(E) :-
    event(E),
    event_time(E, T),
    T = #max { T2 : event_time(_, T2) }.

% Consecutive events in time
consecutive_events(E1, E2) :-
    event(E1),
    event(E2),
    event_time(E1, T1),
    event_time(E2, T2),
    next_time(T1, T2).

% Event ordering by extraction sequence (for debugging)
extracted_before(E1, E2) :-
    event_order(E1, N1),
    event_order(E2, N2),
    N1 < N2.


% =============================================================================
% PART H: DURATION CONSTRAINTS (Optional, Explicit Only)
% =============================================================================
%
% Duration constraints are OPTIONAL and only fire when:
%     1. Explicit duration bounds are defined for action types
%     2. Event has explicit start/end times
%
% =============================================================================

% Rule registration (optional rules, not always active)
rule(temporal_duration_too_fast, universal, "Actions cannot complete faster than minimum duration").
rule(temporal_duration_too_slow, universal, "Actions cannot take longer than maximum duration").

% Event duration (only if explicit start/end)
event_duration(E, D) :-
    event(E),
    event_start(E, Start),
    event_end(E, End),
    D = End - Start,
    D >= 0.

% VIOLATION: Action completed too quickly (if bounds defined)
violation(temporal, duration_too_fast, 
          violation_info(E, event_type, Type, duration, Duration, min_required, Min)) :-
    rule_active(temporal_duration_too_fast),
    event(E),
    event_type(E, Type),
    event_duration(E, Duration),
    action_min_duration(Type, Min),
    Duration < Min.

% VIOLATION: Action took too long (if bounds defined)  
violation(temporal, duration_too_slow,
          violation_info(E, event_type, Type, duration, Duration, max_allowed, Max)) :-
    rule_active(temporal_duration_too_slow),
    event(E),
    event_type(E, Type),
    event_duration(E, Duration),
    action_max_duration(Type, Max),
    Duration > Max.


% =============================================================================
% SHOW DIRECTIVES (for Clingo output)
% =============================================================================

#show violation/4.
