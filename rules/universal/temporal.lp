% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - TEMPORAL (v2.0)
%    ============================================
%
%    Default world assumptions for time ordering and duration.
%    These rules can be overridden by story-specific rules.
%
%    Per LOGIC_DESIGN.md Section 3.3:
%        LINEAR TIME: Time is discrete, monotonic, and strictly ordered.
%        NO BRANCHING: No flashbacks, flashforwards, or alternate histories.
%
%    VERSION 2.0: Uses time/1 from core.lp, rule registration
%
%    TEMPORAL VIOLATIONS:
%        - Events in impossible order
%        - Duration impossibilities
%        - Simultaneous contradictory actions
%        - Time travel (unless story-specific)
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(temporal_ordering_violation, universal, "Events must respect explicit ordering").
rule(temporal_duration_too_fast, universal, "Actions cannot complete faster than minimum duration").
rule(temporal_duration_too_slow, universal, "Actions cannot take longer than maximum duration").
rule(temporal_simultaneous_contradiction, universal, "Same agent cannot do contradictory actions at once").
rule(temporal_causal_violation, universal, "Effects cannot precede their causes").

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
% MUST-PRECEDE VIOLATIONS
% =============================================================================

% Events can have explicit ordering requirements
% must_precede(E1, E2) means E1 must happen before E2

% VIOLATION: Event that should precede doesn't
violation(temporal, ordering_violation, E2, E1) :-
    rule_active(temporal_ordering_violation),
    must_precede(E1, E2),
    event_time(E1, T1),
    event_time(E2, T2),
    not before(T1, T2).

% Fallback using event_order
violation(temporal, ordering_violation, E2, E1) :-
    rule_active(temporal_ordering_violation),
    must_precede(E1, E2),
    event_order(E1, N1),
    event_order(E2, N2),
    N1 >= N2.

% =============================================================================
% CAUSAL ORDERING
% =============================================================================

% Causes must precede effects
causes(E1, E2) :- causal_link(E1, E2).

% VIOLATION: Effect precedes cause
violation(temporal, causal_violation, E2, E1) :-
    rule_active(temporal_causal_violation),
    causes(E1, E2),
    event_time(E1, T1),
    event_time(E2, T2),
    before(T2, T1).  % E2 before E1, but E1 causes E2

% =============================================================================
% DURATION CONSTRAINTS
% =============================================================================

% Some actions have minimum/maximum durations
% action_min_duration(Type, MinTime).
% action_max_duration(Type, MaxTime).

% Event duration (if start/end times available)
event_duration(E, D) :-
    event(E),
    event_start(E, Start),
    event_end(E, End),
    D = End - Start.

% VIOLATION: Action completed too quickly
violation(temporal, duration_too_fast, E, pair(Type, Duration)) :-
    rule_active(temporal_duration_too_fast),
    event(E),
    event_type(E, Type),
    event_duration(E, Duration),
    action_min_duration(Type, Min),
    Duration < Min.

% VIOLATION: Action took too long
violation(temporal, duration_too_slow, E, pair(Type, Duration)) :-
    rule_active(temporal_duration_too_slow),
    event(E),
    event_type(E, Type),
    event_duration(E, Duration),
    action_max_duration(Type, Max),
    Duration > Max.

% =============================================================================
% SIMULTANEOUS ACTION CONSTRAINTS (Time-Indexed)
% =============================================================================

% Some actions cannot happen simultaneously by same agent
cannot_simultaneous(sleep, run).
cannot_simultaneous(run, sleep).
cannot_simultaneous(eat, talk).
cannot_simultaneous(talk, eat).
cannot_simultaneous(die, any_action).

% VIOLATION: Simultaneous contradictory actions at same time point
violation(temporal, simultaneous_contradiction, E1, pair(T, pair(T1, T2))) :-
    rule_active(temporal_simultaneous_contradiction),
    event(E1),
    event(E2),
    E1 < E2,  % Avoid duplicates
    event_time(E1, T),
    event_time(E2, T),
    agent(E1, C),
    agent(E2, C),
    event_type(E1, T1),
    event_type(E2, T2),
    cannot_simultaneous(T1, T2).

% VIOLATION: Overlapping interval contradictions
violation(temporal, simultaneous_contradiction, E1, pair(E2, pair(T1, T2))) :-
    rule_active(temporal_simultaneous_contradiction),
    event(E1),
    event(E2),
    E1 < E2,
    agent(E1, C),
    agent(E2, C),
    event_type(E1, T1),
    event_type(E2, T2),
    cannot_simultaneous(T1, T2),
    event_start(E1, S1),
    event_end(E1, End1),
    event_start(E2, S2),
    event_end(E2, End2),
    S1 < End2,
    S2 < End1.  % Overlapping intervals

% =============================================================================
% TIME TRAVEL DETECTION
% =============================================================================

% Detect potential time travel (for flagging, not always a violation)
potential_time_travel(C, T1, T2) :-
    character(C),
    present(C, L1, T1),
    present(C, L2, T2),
    before(T2, T1),  % Character appears at earlier time after later time
    L1 != L2.

% Only a violation if time travel not allowed in story
violation(temporal, time_travel, none, triple(C, T1, T2)) :-
    rule_active(temporal_no_time_travel),
    potential_time_travel(C, T1, T2).

% Story can disable time travel violations
rule(temporal_no_time_travel, universal, "Characters cannot travel backwards in time").

% =============================================================================
% NARRATIVE SEQUENCE HELPERS
% =============================================================================

% First and last events
first_event(E) :-
    event(E),
    event_time(E, T),
    initial_time(T).

last_event(E) :-
    event(E),
    event_time(E, T),
    max_time(T).

% Consecutive events
consecutive_events(E1, E2) :-
    event(E1),
    event(E2),
    event_time(E1, T1),
    event_time(E2, T2),
    next_time(T1, T2).
