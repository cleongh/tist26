% =============================================================================
%
%    GENERAL NARRATIVE RULES v3 - Enhanced Error Categories
%    =======================================================
%
%    This module contains domain-independent rules for detecting narrative
%    inconsistencies, organized into 5 error categories:
%
%    1. CAUSALITY - Chekhov's gun, unexplained effects, missing causes
%    2. COHERENCE - Semantic correctness, logical consistency
%    3. TEMPORAL  - Time intervals, durations, ordering violations
%    4. LOCATION  - Spatial constraints, distances, ubiquity
%    5. EMOTIONAL - Character motivations, relationships, behavior
%
%    VIOLATION OUTPUT FORMAT:
%    violation(category, violation_type, primary_event, detail, context).
%
%    Where:
%    - category: one of {causality, coherence, temporal, location, emotional}
%    - violation_type: specific subtype (e.g., chekhov_gun, ubiquity)
%    - primary_event: the event or entity causing the violation
%    - detail: additional context (another event, entity, or value)
%    - context: human-readable context string
%
%    USAGE:
%    $ clingo rules/general_narrative.lp rules/domain_<story>.lp facts.lp
%
% =============================================================================


% =============================================================================
% SECTION 1: TEMPORAL REASONING (Category: temporal)
% =============================================================================
%
% Temporal reasoning detects:
% - Circular time ordering (paradoxes)
% - Events with negative duration (ending before starting)
% - Explicit ordering constraint violations
% - Impossible simultaneity
%
% =============================================================================

% ----- Time Point Collection -----
% Gather all time points from the story for reasoning.

time_point(T) :- time(_,T,_).      % Event start times
time_point(T) :- time(_,_,T).      % Event end times
time_point(T) :- holds(_,T,_).     % Fluent interval starts
time_point(T) :- holds(_,_,T).     % Fluent interval ends

% ----- Temporal Ordering (Transitive Closure) -----

before(T1,T2) :- time_order(T1,T2).                    % Direct ordering
before(T1,T3) :- before(T1,T2), before(T2,T3).        % Transitive closure

% ----- Same Time Detection -----

same_time(T1, T2) :- time_point(T1), time_point(T2), T1 = T2.

% ----- Event Temporal Relations -----

% OVERLAP: Two events happen at overlapping times
overlap(E1,E2) :-
    event(E1), event(E2),
    time(E1,S1,End1),
    time(E2,S2,End2),
    not before(End1,S2),
    not before(End2,S1),
    E1 != E2.

% PRECEDES: E1 finishes strictly before E2 starts
precedes(E1,E2) :-
    event(E1), event(E2),
    time(E1,_,End1),
    time(E2,S2,_),
    before(End1,S2).

% MEETS: E1 ends exactly when E2 starts
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
violation(temporal, circular_time, T1, T2, "Time paradox: T1 both precedes and follows T2") :-
    before(T1, T2),
    before(T2, T1).

% VIOLATION: Event ends before it starts (negative duration)
violation(temporal, negative_duration, E, E, "Event has negative duration") :-
    event(E),
    time(E, Start, End),
    before(End, Start).

% VIOLATION: Explicit temporal constraint violated
violation(temporal, explicit_order_violated, E1, E2, "Story states E1 should precede E2 but timeline shows otherwise") :-
    must_precede(E1, E2),
    not precedes(E1, E2).

% VIOLATION: Same event happening at different times without explanation
% Note: This rule requires actual_duration/3 to be defined in domain module
% violation(temporal, impossible_duration, E, MinDur, "Event duration exceeds stated time interval") :-
%     event(E),
%     time(E, Start, End),
%     min_duration(E, MinDur),
%     actual_duration(Start, End, ActualDur),
%     ActualDur < MinDur.


% =============================================================================
% SECTION 2: LOCATION/SPATIAL REASONING (Category: location)
% =============================================================================
%
% Spatial reasoning detects:
% - Ubiquity: being in two places at once
% - Impossible travel: moving between distant locations instantly
% - Proximity violations: interacting with things too far away
%
% =============================================================================

% ----- Location Tracking -----

at_during(Entity, Loc, E) :- 
    event(E), 
    agent(E, Entity),
    location(E, Loc).

at_during(Entity, Loc, E) :-
    event(E),
    patient(E, Entity),
    location(E, Loc),
    character(Entity).

% ----- LOCATION VIOLATIONS -----

% VIOLATION: Ubiquity - same character in two places at same time
violation(location, ubiquity, E1, E2, "Character is in two places simultaneously") :-
    event(E1), event(E2),
    agent(E1, A), agent(E2, A),
    location(E1, L1), location(E2, L2),
    L1 != L2,
    overlap(E1, E2),
    E1 < E2.

% VIOLATION: Interaction requires proximity
violation(location, proximity_required, E, Patient, "Character cannot interact with entity at different location") :-
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    location(E, Loc),
    at_during(Patient, PatientLoc, E),
    Loc != PatientLoc,
    not allows_remote_interaction(E).

% VIOLATION: Instant teleportation between distant locations
violation(location, impossible_travel, E1, E2, "Character moves between distant locations with no travel time") :-
    event(E1), event(E2),
    agent(E1, A), agent(E2, A),
    location(E1, L1), location(E2, L2),
    L1 != L2,
    meets(E1, E2),
    distant(L1, L2),
    not is_travel_event(E1),
    not is_travel_event(E2).

% Helper: Check if event is a travel/movement event
is_travel_event(E) :- event_type(E, walk).
is_travel_event(E) :- event_type(E, run).
is_travel_event(E) :- event_type(E, travel).
is_travel_event(E) :- event_type(E, journey).
is_travel_event(E) :- event_type(E, fly).
is_travel_event(E) :- event_type(E, ride).
is_travel_event(E) :- event_type(E, sail).
is_travel_event(E) :- event_type(E, drive).
is_travel_event(E) :- event_type(E, teleport).
is_travel_event(E) :- event_type(E, transport).
is_travel_event(E) :- event_type(E, arrive).
is_travel_event(E) :- event_type(E, leave).
is_travel_event(E) :- event_type(E, move).

% ----- Location Connectivity Reasoning -----

% Transitive connectivity: if A connects to B and B connects to C, A can reach C
reachable(L1, L2) :- connected(L1, L2).
reachable(L1, L3) :- reachable(L1, L2), connected(L2, L3), L1 != L3.

% Containment implies connectivity
connected(L1, L2) :- contains(L1, L2).
connected(L2, L1) :- contains(L1, L2).

% VIOLATION: Movement between unconnected locations (spatial impossibility)
% Only trigger if we have connectivity info for at least one of the locations
violation(location, unreachable_location, E1, E2, "Character moves to location not connected to previous location") :-
    event(E1), event(E2),
    agent(E1, A), agent(E2, A),
    location(E1, L1), location(E2, L2),
    L1 != L2,
    time_order(E1, E2),
    not reachable(L1, L2),
    has_connectivity_info(L1),
    not is_travel_event(E1),
    not is_travel_event(E2).

% Helper: Check if a location has any connectivity information defined
has_connectivity_info(L) :- connected(L, _).
has_connectivity_info(L) :- connected(_, L).
has_connectivity_info(L) :- contains(L, _).
has_connectivity_info(L) :- contains(_, L).


% =============================================================================
% SECTION 3: CAUSALITY REASONING (Category: causality)
% =============================================================================
%
% Causality violations include:
% - Chekhov's gun: introduced elements never used
% - Uncaused events: significant events without explanation
% - Effect without cause: state changes without triggering events
% - Missing preconditions: actions without required conditions
%
% =============================================================================

% ----- Track What's Introduced and Used -----

introduced(X) :- character(X).
introduced(X) :- object(X).
introduced(X) :- mentioned_object(X).

used(X) :- agent(_, X).
used(X) :- patient(_, X).
used(X) :- instrument(_, X).

caused(E) :- causes(_, E).
caused(E) :- initial_event(E).
caused(E) :- event_type(E, natural).
caused(E) :- background_event(E).

% ----- CAUSALITY VIOLATIONS -----

% VIOLATION: Chekhov's gun - prominently introduced object never used
violation(causality, chekhov_gun, X, X, "Prominently introduced object is never used in the story") :-
    object(X),
    prominently_introduced(X),
    not used(X),
    not decorative(X).

% VIOLATION: Uncaused significant event
violation(causality, uncaused_event, E, E, "Significant event occurs without explanation or cause") :-
    event(E),
    significant_event(E),
    not caused(E).

% VIOLATION: Effect without cause - fluent becomes true without cause
violation(causality, effect_without_cause, F, T, "State change occurs without any triggering event") :-
    holds(F, T, _),
    not fluent_caused(F, T),
    not initial_state(F).

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
violation(causality, precondition_missing, E, Pred, "Action requires condition that is not satisfied") :-
    event(E),
    requires(E, pos, Pred, Role),
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
% SECTION 4: BASIC COHERENCE (Category: coherence)
% =============================================================================
%
% Coherence violations are semantic/logical errors:
% - Dead agent: character acts after death
% - Non-edible food: eating inedible objects
% - Physical impossibility: actions incompatible with traits
% - Focus overlap: multiple attention-requiring tasks
%
% =============================================================================

% ----- Life/Death Tracking -----

dead_after(C, T) :- event(E), event_type(E, die), agent(E, C), time(E, _, T).
dead_after(C, T) :- event(E), event_type(E, kill), patient(E, C), time(E, _, T).
dead_after(C, T) :- event(E), event_type(E, murder), patient(E, C), time(E, _, T).

% VIOLATION: Dead character acting
violation(coherence, dead_agent, E, C, "Character performs action after their death") :-
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
non_edible(X) :- weapon(X).
non_edible(X) :- tool(X), not edible_tool(X).

edible(X) :- object(X), not non_edible(X).
edible(X) :- food(X).
edible(X) :- fruit(X).
edible(X) :- vegetable(X).
edible(X) :- meat(X).
edible(X) :- bread(X).
edible(X) :- gingerbread(X).
edible(X) :- candy(X).
edible(X) :- drink(X).

% VIOLATION: Eating non-edible objects
violation(coherence, non_edible_food, E, X, "Character attempts to eat something inedible") :-
    event(E),
    event_type(E, eat),
    patient(E, X),
    not edible(X).

violation(coherence, non_edible_food, E, X, "Character attempts to consume something inedible") :-
    event(E),
    event_type(E, consume),
    patient(E, X),
    not edible(X).

% ----- Physical Limitations -----

requires_sight(read).
requires_sight(see).
requires_sight(watch).
requires_sight(observe).
requires_sight(look).
requires_sight(aim).
requires_sight(write).

requires_hearing(hear).
requires_hearing(listen).
requires_hearing(eavesdrop).

requires_speech(speak).
requires_speech(shout).
requires_speech(sing).
requires_speech(call).
requires_speech(yell).
requires_speech(scream).
requires_speech(whisper).

requires_mobility(walk).
requires_mobility(run).
requires_mobility(jump).
requires_mobility(climb).
requires_mobility(dance).

% VIOLATION: Blind character needs sight
violation(coherence, physical_impossibility, E, "blind", "Blind character performs action requiring sight") :-
    trait(A, blind),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_sight(Type).

% VIOLATION: Deaf character needs hearing
violation(coherence, physical_impossibility, E, "deaf", "Deaf character performs action requiring hearing") :-
    trait(A, deaf),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_hearing(Type).

% VIOLATION: Mute character needs speech
violation(coherence, physical_impossibility, E, "mute", "Mute character performs action requiring speech") :-
    trait(A, mute),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_speech(Type).

% VIOLATION: Paralyzed character needs mobility
violation(coherence, physical_impossibility, E, "paralyzed", "Paralyzed character performs action requiring mobility") :-
    trait(A, paralyzed),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_mobility(Type).

% VIOLATION: Focus overlap - can't do two attention-requiring tasks
violation(coherence, focus_overlap, E1, E2, "Character cannot perform two focus-requiring tasks simultaneously") :-
    event(E1), event(E2),
    requires_focus(E1),
    requires_focus(E2),
    agent(E1, A), agent(E2, A),
    overlap(E1, E2),
    E1 < E2.

% ----- Appearance/Physical State Coherence -----

% VIOLATION: Unusual appearance without explanation
% This detects when a character has an unusual appearance that might indicate an error
% (e.g., "pale green" face when they should be angry, not sick)

% Define color appearances that suggest sickness
sick_appearance(pale).
sick_appearance(green).
sick_appearance(pale_green).
sick_appearance(white).
sick_appearance(gray).
sick_appearance(grey).
sick_appearance(sickly).

% Define appearances that suggest injury
injured_appearance(bloody).
injured_appearance(bruised).
injured_appearance(scarred).
injured_appearance(wounded).
injured_appearance(burned).

% VIOLATION: Character has sick appearance but emotion is angry (not sick)
violation(coherence, appearance_emotion_mismatch, C, Appearance, "Character appearance suggests sickness but emotion is angry/happy") :-
    character(C),
    character_appearance(C, Appearance),
    sick_appearance(Appearance),
    character_emotion(C, angry).

violation(coherence, appearance_emotion_mismatch, C, Appearance, "Character appearance suggests sickness but emotion is happy") :-
    character(C),
    character_appearance(C, Appearance),
    sick_appearance(Appearance),
    character_emotion(C, happy).

% VIOLATION: Character has injured appearance but state is normal
violation(coherence, appearance_state_mismatch, C, Appearance, "Character appearance suggests injury but state is normal") :-
    character(C),
    character_appearance(C, Appearance),
    injured_appearance(Appearance),
    character_state(C, normal).


% =============================================================================
% SECTION 5: EMOTIONAL RELATIONS (Category: emotional)
% =============================================================================
%
% Emotional violations occur when character behavior contradicts their
% established relationships and emotional states:
% - Harming loved ones without justification
% - Helping enemies without strategic reason
% - Approaching feared entities voluntarily
% - Actions contradicting emotional state
%
% =============================================================================

% ----- Harmful/Helpful Action Types -----

harmful_action(kill).
harmful_action(attack).
harmful_action(hurt).
harmful_action(betray).
harmful_action(abandon).
harmful_action(steal_from).
harmful_action(deceive).
harmful_action(threaten).
harmful_action(insult).
harmful_action(reject).

helpful_action(help).
helpful_action(save).
helpful_action(protect).
helpful_action(give).
helpful_action(heal).
helpful_action(rescue).
helpful_action(comfort).
helpful_action(support).
helpful_action(defend).

approach_action(approach).
approach_action(confront).
approach_action(visit).
approach_action(meet).
approach_action(seek).
approach_action(follow).

% ----- EMOTIONAL VIOLATIONS -----

% VIOLATION: Harming loved one without justification
violation(emotional, harm_loved, E, B, "Character harms someone they love without justification") :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    harmful_action(Type),
    loves(A, B),
    not justified_harm(E).

% VIOLATION: Helping enemy without motivation
violation(emotional, help_enemy, E, B, "Character helps someone they hate without strategic reason") :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    helpful_action(Type),
    hates(A, B),
    not strategic_help(E).

% VIOLATION: Approaching feared entity without necessity
violation(emotional, approach_feared, E, B, "Character voluntarily approaches someone they fear") :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    approach_action(Type),
    fears(A, B),
    not forced_approach(E),
    not brave_moment(E).

% VIOLATION: Trusting someone who's been shown untrustworthy
violation(emotional, misplaced_trust, E, B, "Character trusts someone they distrust without earned redemption") :-
    event(E),
    agent(E, A),
    event_type(E, trust),
    patient(E, B),
    distrusts(A, B),
    not trust_earned(B, E).

% VIOLATION: Emotional state contradicts action
violation(emotional, state_action_mismatch, E, State, "Character's action contradicts their emotional state") :-
    event(E),
    agent(E, A),
    time(E, T, _),
    emotional_state(A, State, T),
    event_type(E, Type),
    contradicts_emotion(State, Type).

% Contradiction pairs (state, action)
contradicts_emotion(happy, mourn).
contradicts_emotion(happy, weep).
contradicts_emotion(happy, grieve).
contradicts_emotion(sad, celebrate).
contradicts_emotion(sad, laugh).
contradicts_emotion(sad, rejoice).
contradicts_emotion(calm, panic).
contradicts_emotion(calm, scream).
contradicts_emotion(angry, forgive).
contradicts_emotion(terrified, approach).
contradicts_emotion(grieving, celebrate).

% VIOLATION: Sudden emotional shift without trigger
violation(emotional, sudden_shift, A, State2, "Character shows sudden emotional change without trigger") :-
    emotional_state(A, State1, T1),
    emotional_state(A, State2, T2),
    before(T1, T2),
    opposite_emotions(State1, State2),
    not emotional_trigger_between(A, T1, T2).

% Opposite emotion pairs
opposite_emotions(happy, sad).
opposite_emotions(sad, happy).
opposite_emotions(loving, hateful).
opposite_emotions(hateful, loving).
opposite_emotions(calm, angry).
opposite_emotions(angry, calm).
opposite_emotions(trusting, suspicious).
opposite_emotions(suspicious, trusting).


% =============================================================================
% SECTION 6: DOMAIN HOOKS (To be filled by domain module)
% =============================================================================
%
% These predicates should be defined in the domain-specific module:
%
% Location/Distance:
%   - distant(L1, L2): Locations are far apart
%   - connected(L1, L2): Locations are directly connected
%
% Causality:
%   - decorative(X): Object is decorative (Chekhov's gun exception)
%   - significant_event(E): Event is significant (needs cause)
%   - initial_event(E): Event is initial (no cause needed)
%   - prominently_introduced(X): Object is prominently introduced
%   - initial_state(F): Fluent is part of initial state
%   - background_event(E): Event is background/setting
%
% Emotional:
%   - loves(A, B), hates(A, B), fears(A, B)
%   - trusts(A, B), distrusts(A, B)
%   - justified_harm(E): Harm is justified
%   - strategic_help(E): Help is strategic
%   - forced_approach(E): Approach is forced
%   - brave_moment(E): Character overcomes fear
%   - trust_earned(B, E): B earned trust before E
%   - emotional_state(A, State, T): A has State at T
%   - emotional_trigger_between(A, T1, T2): Trigger exists
%
% Physical:
%   - allows_remote_interaction(E): Event allows remote
%   - min_duration(E, D): Minimum duration for event
%
% =============================================================================


% =============================================================================
% OUTPUT CONFIGURATION
% =============================================================================

% Show all 5-argument violations (new enhanced format)
#show violation/5.

% Also support legacy formats for backward compatibility
#show violation/4.
#show violation/3.
#show violation/2.


% =============================================================================
%
%    END OF GENERAL NARRATIVE RULES v3
%
%    Usage:
%    $ clingo rules/general_narrative.lp rules/domain_<story>.lp facts.lp
%
% =============================================================================
