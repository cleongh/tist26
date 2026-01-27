% =============================================================================
%
%    GENERAL NARRATIVE CONSISTENCY RULES (Domain-Independent)
%    =========================================================
%
%    This module contains abstract, domain-independent rules for detecting
%    narrative inconsistencies. It is designed to work with ANY story and
%    does NOT contain story-specific facts or domain knowledge.
%
%    ARCHITECTURE:
%    - This file: general.lp (domain-independent rules)
%    - Domain file: domain_<story>.lp (story-specific facts and rules)
%    - Facts file: facts.lp (extracted from story via LLM)
%
%    ERROR CATEGORIES (5 types):
%    1. CAUSALITY - Chekhov's gun, unexplained effects, missing causes
%    2. COHERENCE - Semantic correctness, logical consistency
%    3. TEMPORAL  - Time intervals, durations, ordering violations
%    4. LOCATION  - Spatial constraints, distances, ubiquity
%    5. EMOTIONAL - Character motivations, relationships, behavior
%
%    VIOLATION OUTPUT FORMAT:
%    violation(category, type, event, detail).
%    - category: causality | coherence | temporal | location | emotional
%    - type: specific violation subtype
%    - event: event ID that triggered the violation
%    - detail: additional context (often another event or entity)
%
% =============================================================================

% =============================================================================
% PART 1: TEMPORAL REASONING (Category: temporal)
% =============================================================================
%
% Temporal reasoning detects violations in time intervals, ordering, and
% duration constraints. Examples:
% - Events happening in impossible order
% - Overlapping events that can't occur simultaneously
% - Duration violations (too long or too short for the action)
%
% =============================================================================

% ----- Time Point Collection -----
% Collect all time points mentioned in the story for reasoning.

time_point(T) :- time(_,T,_).      % Start times of events
time_point(T) :- time(_,_,T).      % End times of events
time_point(T) :- holds(_,T,_).     % Start times of fluent intervals
time_point(T) :- holds(_,_,T).     % End times of fluent intervals

% ----- Temporal Ordering (Transitive Closure) -----
% before(T1, T2) means T1 is strictly before T2 in the timeline.

before(T1,T2) :- time_order(T1,T2).                    % Direct ordering
before(T1,T3) :- before(T1,T2), before(T2,T3).        % Transitive closure

% ----- Same Time Detection -----
% Two time points are the same if neither comes before the other
same_time(T1, T2) :- time_point(T1), time_point(T2), T1 = T2.

% ----- Event Temporal Relations -----

% OVERLAP: Two events happen at overlapping times
overlap(E1,E2) :-
    event(E1), event(E2),
    time(E1,S1,End1),
    time(E2,S2,End2),
    not before(End1,S2),            % E1 doesn't end before E2 starts
    not before(End2,S1),            % E2 doesn't end before E1 starts
    E1 != E2.

% PRECEDES: E1 finishes strictly before E2 starts
precedes(E1,E2) :-
    event(E1), event(E2),
    time(E1,_,End1),
    time(E2,S2,_),
    before(End1,S2).

% MEETS: E1 ends exactly when E2 starts (no gap, no overlap)
meets(E1,E2) :-
    event(E1), event(E2),
    time(E1,_,T),
    time(E2,T,_),
    E1 != E2.

% CONCURRENT: Symmetric overlap
concurrent(E1,E2) :- overlap(E1,E2).
concurrent(E1,E2) :- overlap(E2,E1).

% ----- TEMPORAL VIOLATIONS -----

% VIOLATION: Circular time ordering (temporal paradox)
% If T1 < T2 < T1, we have a contradiction
violation(temporal, circular_time, T1, T2) :-
    before(T1, T2),
    before(T2, T1).

% VIOLATION: Event ends before it starts
violation(temporal, negative_duration, E, E) :-
    event(E),
    time(E, Start, End),
    before(End, Start).

% VIOLATION: Explicit temporal constraint violated
% If story says "E1 happens before E2" but our timeline shows otherwise
violation(temporal, explicit_order_violated, E1, E2) :-
    must_precede(E1, E2),           % Explicit constraint from story
    not precedes(E1, E2).           % But E1 doesn't precede E2


% =============================================================================
% PART 2: LOCATION/SPATIAL REASONING (Category: location)
% =============================================================================
%
% Spatial reasoning detects violations in:
% - Ubiquity: being in two places at once
% - Reachability: moving between distant locations instantly
% - Proximity: interacting with things that are too far away
%
% =============================================================================

% ----- Location Tracking -----
% Track where entities are during events

at_during(Entity, Loc, E) :- 
    event(E), 
    agent(E, Entity),
    location(E, Loc).

at_during(Entity, Loc, E) :-
    event(E),
    patient(E, Entity),
    location(E, Loc),
    character(Entity).              % Only track characters, not objects

% ----- LOCATION VIOLATIONS -----

% VIOLATION: Ubiquity - same character in two places at same time
violation(location, ubiquity, E1, E2) :-
    event(E1), event(E2),
    agent(E1, A), agent(E2, A),     % Same agent
    location(E1, L1), location(E2, L2),
    L1 != L2,                       % Different locations
    overlap(E1, E2),                % Events overlap in time
    E1 < E2.                        % Avoid duplicates

% VIOLATION: Interaction requires proximity
% Can't interact with something if you're in a different location
violation(location, proximity_required, E, Patient) :-
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    location(E, Loc),
    at_during(Patient, PatientLoc, E),
    Loc != PatientLoc,
    not allows_remote_interaction(E).  % Unless action allows remote

% VIOLATION: Instant teleportation
% Moving between distant locations with no travel time
violation(location, impossible_travel, E1, E2) :-
    event(E1), event(E2),
    agent(E1, A), agent(E2, A),     % Same agent
    location(E1, L1), location(E2, L2),
    L1 != L2,                       % Different locations
    meets(E1, E2),                  % Events are adjacent in time
    distant(L1, L2),                % Locations are far apart
    not is_travel_event(E1),        % E1 is not a travel event
    not is_travel_event(E2).        % E2 is not a travel event

% Helper: Check if event is a travel/movement event
is_travel_event(E) :- event_type(E, walk).
is_travel_event(E) :- event_type(E, run).
is_travel_event(E) :- event_type(E, travel).
is_travel_event(E) :- event_type(E, journey).
is_travel_event(E) :- event_type(E, fly).
is_travel_event(E) :- event_type(E, ride).
is_travel_event(E) :- event_type(E, sail).


% =============================================================================
% PART 3: CAUSALITY REASONING (Category: causality)
% =============================================================================
%
% Causality violations include:
% - Chekhov's gun: introduced elements that are never used
% - Missing cause: effects without adequate causes
% - Unexplained: events that happen without explanation
%
% =============================================================================

% ----- Track What's Introduced and Used -----

% An entity is introduced if it appears in the story
introduced(X) :- character(X).
introduced(X) :- object(X).

% An entity is used if it participates in an event
used(X) :- agent(_, X).
used(X) :- patient(_, X).
used(X) :- instrument(_, X).

% An event is caused if it has a stated cause or is an initial event
caused(E) :- causes(_, E).         % Another event causes E
caused(E) :- initial_event(E).     % E is marked as initial (no cause needed)
caused(E) :- event_type(E, natural).  % Natural events don't need causes

% ----- CAUSALITY VIOLATIONS -----

% VIOLATION: Chekhov's gun - object introduced but never used
% "If you show a gun in Act 1, it must fire by Act 3"
violation(causality, chekhov_gun, X, X) :-
    object(X),
    introduced(X),
    not used(X),
    not decorative(X).              % Unless marked as decorative/setting

% VIOLATION: Uncaused significant event
% Major story events should have causes
violation(causality, uncaused_event, E, E) :-
    event(E),
    significant_event(E),           % Event is marked significant
    not caused(E).

% VIOLATION: Effect without cause
% If a fluent becomes true, there should be an event causing it
violation(causality, effect_without_cause, F, T) :-
    holds(F, T, _),                 % Fluent F holds starting at T
    not fluent_caused(F, T).        % But nothing caused it

% Helper: A fluent is caused if an event's effect establishes it
fluent_caused(fluent(Prop, Entity), T) :-
    event(E),
    event_type(E, Type),
    causes(Type, pos, Prop, Role),
    role_arg(E, Role, Entity),
    time(E, _, T).

% Helper: Role extraction
role_arg(E, agent, A) :- agent(E, A).
role_arg(E, patient, P) :- patient(E, P).
role_arg(E, instrument, I) :- instrument(E, I).

% VIOLATION: Action without proper precondition
% E.g., "He read the letter" requires the letter to exist and be accessible
violation(causality, precondition_missing, E, Pred) :-
    event(E),
    requires(E, pos, Pred, Role),   % E requires Pred to be true
    role_arg(E, Role, Arg),
    time(E, Start, _),
    not holds_at(fluent(Pred, Arg), Start).

% ----- Fluent Reasoning -----

holds_at(F, T) :- 
    holds(F, Start, End),
    time_point(T),
    not before(T, Start),
    not before(End, T).

holds_at(fluent(Pred, Arg), End) :-
    event(E), event_type(E, Type),
    causes(Type, pos, Pred, Role),
    role_arg(E, Role, Arg),
    time(E, _, End).

% Frame axiom: fluents persist unless negated
holds_at(F, T2) :- 
    holds_at(F, T1),
    before(T1, T2),
    time_point(T2),
    not holds_at_negated(F, T2).

holds_at_negated(fluent(Pred, Arg), T) :- 
    event(E), event_type(E, Type),
    causes(Type, neg, Pred, Role),
    role_arg(E, Role, Arg),
    time(E, _, T).


% =============================================================================
% PART 4: BASIC COHERENCE (Category: coherence)
% =============================================================================
%
% Coherence violations are semantic/logical errors:
% - Dead agent: character acts after death
% - Non-edible food: eating inedible objects
% - Physical impossibility: blind character reads, etc.
%
% =============================================================================

% ----- Life/Death Tracking -----

dead_after(C, T) :- event(E), event_type(E, die), agent(E, C), time(E, _, T).
dead_after(C, T) :- event(E), event_type(E, kill), patient(E, C), time(E, _, T).

% VIOLATION: Dead character acting
violation(coherence, dead_agent, E, C) :-
    event(E),
    agent(E, C),
    time(E, Tstart, _),
    dead_after(C, Tdeath),
    before(Tdeath, Tstart).

% ----- Edibility -----

non_edible(X) :- rock(X).
non_edible(X) :- metal(X).
non_edible(X) :- poison(X).
non_edible(X) :- glass(X).
non_edible(X) :- plastic(X).
non_edible(X) :- building(X).
non_edible(X) :- furniture(X).
non_edible(X) :- inedible(X).

edible(X) :- object(X), not non_edible(X).
edible(X) :- food(X).
edible(X) :- fruit(X).
edible(X) :- vegetable(X).
edible(X) :- meat(X).
edible(X) :- bread(X).
edible(X) :- gingerbread(X).

% VIOLATION: Eating non-edible objects
violation(coherence, non_edible_food, E, X) :-
    event(E),
    event_type(E, eat),
    patient(E, X),
    not edible(X).

% ----- Physical Limitations -----

% Actions requiring sight
requires_sight(read).
requires_sight(see).
requires_sight(watch).
requires_sight(observe).
requires_sight(look).

% Actions requiring hearing
requires_hearing(hear).
requires_hearing(listen).
requires_hearing(eavesdrop).

% Actions requiring speech
requires_speech(speak).
requires_speech(shout).
requires_speech(sing).
requires_speech(call).
requires_speech(yell).
requires_speech(scream).

% VIOLATION: Blind character needs sight
violation(coherence, physical_impossibility, E, blind) :-
    trait(A, blind),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_sight(Type).

% VIOLATION: Deaf character needs hearing
violation(coherence, physical_impossibility, E, deaf) :-
    trait(A, deaf),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_hearing(Type).

% VIOLATION: Mute character needs speech
violation(coherence, physical_impossibility, E, mute) :-
    trait(A, mute),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_speech(Type).


% =============================================================================
% PART 5: EMOTIONAL RELATIONS (Category: emotional)
% =============================================================================
%
% Emotional violations occur when character behavior contradicts their
% established relationships and emotional states:
% - Acting against a loved one without justification
% - Helping an enemy without motivation
% - Emotional state inconsistent with actions
%
% =============================================================================

% ----- Relationship Types -----
% These are filled in by the domain module based on story extraction

% loves(A, B) - A loves B
% hates(A, B) - A hates B
% fears(A, B) - A fears B
% trusts(A, B) - A trusts B
% distrusts(A, B) - A distrusts B

% ----- Emotion-Inconsistent Actions -----

% Harmful actions
harmful_action(kill).
harmful_action(attack).
harmful_action(hurt).
harmful_action(betray).
harmful_action(abandon).
harmful_action(steal_from).
harmful_action(deceive).
harmful_action(threaten).

% Helpful actions
helpful_action(help).
helpful_action(save).
helpful_action(protect).
helpful_action(give).
helpful_action(heal).
helpful_action(rescue).
helpful_action(comfort).

% Fear-inducing actions (approaching feared entity)
approach_action(approach).
approach_action(confront).
approach_action(visit).
approach_action(meet).

% ----- EMOTIONAL VIOLATIONS -----

% VIOLATION: Harming loved one without justification
violation(emotional, harm_loved, E, B) :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    harmful_action(Type),
    loves(A, B),
    not justified_harm(E).          % Unless justified (e.g., mercy killing)

% VIOLATION: Helping enemy without motivation
violation(emotional, help_enemy, E, B) :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    helpful_action(Type),
    hates(A, B),
    not strategic_help(E).          % Unless strategic

% VIOLATION: Approaching feared entity without necessity
violation(emotional, approach_feared, E, B) :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    approach_action(Type),
    fears(A, B),
    not forced_approach(E).         % Unless forced

% VIOLATION: Trusting someone who's been shown untrustworthy
violation(emotional, misplaced_trust, E, B) :-
    event(E),
    agent(E, A),
    event_type(E, trust),
    patient(E, B),
    distrusts(A, B),
    not trust_earned(B, E).         % Unless they earned it back

% VIOLATION: Emotional state contradicts action
% E.g., "happy" character performs "mourn" action
violation(emotional, state_action_mismatch, E, State) :-
    event(E),
    agent(E, A),
    time(E, T, _),
    emotional_state(A, State, T),
    event_type(E, Type),
    contradicts_emotion(State, Type).

% Contradiction pairs (state, action)
contradicts_emotion(happy, mourn).
contradicts_emotion(happy, weep).
contradicts_emotion(sad, celebrate).
contradicts_emotion(sad, laugh).
contradicts_emotion(calm, panic).
contradicts_emotion(angry, forgive).  % Unless explicitly showing growth


% =============================================================================
% PART 6: FOCUS/ATTENTION CONSTRAINTS (Cross-category)
% =============================================================================

% VIOLATION: Focus overlap - can't do two attention-requiring tasks
violation(coherence, focus_overlap, E1, E2) :-
    event(E1), event(E2),
    requires_focus(E1),
    requires_focus(E2),
    agent(E1, A), agent(E2, A),
    overlap(E1, E2),
    E1 < E2.


% =============================================================================
% PART 7: DOMAIN HOOKS (To be filled by domain module)
% =============================================================================
%
% These predicates are expected to be defined in the domain-specific module:
%
% - distant(L1, L2): Locations L1 and L2 are far apart
% - decorative(X): Object X is decorative (Chekhov's gun exception)
% - significant_event(E): Event E is significant (needs cause)
% - initial_event(E): Event E is an initial/starting event
% - justified_harm(E): Harm in event E is justified
% - strategic_help(E): Help in event E is strategic
% - forced_approach(E): Approach in event E is forced
% - trust_earned(B, E): B earned trust before event E
% - emotional_state(A, State, T): Character A has emotional state at time T
% - allows_remote_interaction(E): Event E allows remote interaction
%
% The domain module also provides:
% - loves(A, B), hates(A, B), fears(A, B), trusts(A, B), distrusts(A, B)
% - causes(Type, Polarity, Property, Role)
% - precondition(Type, Polarity, Property, Role)
%
% =============================================================================


% =============================================================================
% OUTPUT CONFIGURATION
% =============================================================================

% Show all 4-argument violations (new format)
#show violation/4.

% Also support legacy 2 and 3-argument violations for backward compatibility
#show violation/2.
#show violation/3.


% =============================================================================
%
%    END OF GENERAL RULES MODULE
%
%    To use:
%    $ clingo rules/general.lp rules/domain_<story>.lp facts.lp
%
% =============================================================================
