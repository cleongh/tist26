% =============================================================================
%
%    GENERAL ABSTRACT NARRATIVE RULES - Domain-Independent Module
%    =============================================================
%
%    This module contains abstract, domain-independent rules for detecting
%    narrative inconsistencies. It is designed to work with domain-specific
%    facts generated per experiment.
%
%    ERROR CATEGORIES (as specified in requirements):
%    ================================================
%
%    1. CAUSALITY - Every element must be properly caused (Chekhov's gun).
%       Any event should be told because it's needed for causality.
%
%    2. COHERENCE - Semantic correctness. Things should make logical sense
%       (no dead characters acting, no eating inedible objects, etc.)
%
%    3. TEMPORAL - Time ordering must be possible. If exact times aren't
%       explicitly given or specifically inconsistent, assume correctness.
%
%    4. LOCATION - Spatial constraints must be respected. Can't grab something
%       from a table if you're in a different house.
%
%    5. EMOTIONAL - Character behavior must reflect their emotions and
%       relationships. Character A should be kind to B if A loves B.
%
%    VIOLATION OUTPUT FORMAT:
%    violation(Category, ViolationType, PrimaryEntity, SecondaryEntity, Description)
%    - Category: causality | coherence | temporal | location | emotional
%    - ViolationType: Specific subtype of the violation
%    - PrimaryEntity: Main event/entity involved
%    - SecondaryEntity: Related entity (or "none")
%    - Description: Human-readable explanation
%
%    USAGE:
%    $ clingo rules/general_abstract.lp rules/domain_specific.lp facts.lp
%
%    Author: Narrative Evaluation Research Project
%    Date: January 2026
%
% =============================================================================


% =============================================================================
% SECTION 0: TIME AND FLUENT INFRASTRUCTURE
% =============================================================================
% 
% Fundamental temporal reasoning infrastructure needed by all categories.
%
% =============================================================================

% Collect all time points from events and fluents
time_point(T) :- time(_, T, _).      % Event start times
time_point(T) :- time(_, _, T).      % Event end times
time_point(T) :- holds(_, T, _).     % Fluent interval starts
time_point(T) :- holds(_, _, T).     % Fluent interval ends

% Temporal ordering (transitive closure)
before(T1, T2) :- time_order(T1, T2).
before(T1, T3) :- before(T1, T2), before(T2, T3).

% Same time detection
same_time(T1, T2) :- time_point(T1), time_point(T2), T1 = T2.

% Event temporal relations
overlap(E1, E2) :-
    event(E1), event(E2),
    time(E1, S1, End1),
    time(E2, S2, End2),
    not before(End1, S2),
    not before(End2, S1),
    E1 != E2.

precedes(E1, E2) :-
    event(E1), event(E2),
    time(E1, _, End1),
    time(E2, S2, _),
    before(End1, S2).

meets(E1, E2) :-
    event(E1), event(E2),
    time(E1, _, T),
    time(E2, T, _),
    E1 != E2.

concurrent(E1, E2) :- overlap(E1, E2).
concurrent(E1, E2) :- overlap(E2, E1).

% Fluent reasoning - what holds at a given time
holds_at(F, T) :-
    holds(F, Start, End),
    time_point(T),
    not before(T, Start),
    not before(End, T).

% Role extraction helpers
role_arg(E, agent, A) :- agent(E, A).
role_arg(E, patient, P) :- patient(E, P).
role_arg(E, instrument, I) :- instrument(E, I).


% =============================================================================
% SECTION 1: CAUSALITY VIOLATIONS
% =============================================================================
%
% Causality: Every element of the story that is not trivially true must be
% properly caused, and any event should be told because it's needed for
% causality (Chekhov's gun principle).
%
% =============================================================================

% Track what entities are introduced and used
introduced(X) :- character(X).
introduced(X) :- object(X).

used(X) :- agent(_, X).
used(X) :- patient(_, X).
used(X) :- instrument(_, X).
used(X) :- mentioned_in_event(X, _).

% ----- CAUSALITY VIOLATION 1: Chekhov's Gun -----
% Objects introduced but never meaningfully used in the plot
% "If you show a gun in Act 1, it must fire by Act 3"

violation(causality, chekhovs_gun, X, none, Desc) :-
    object(X),
    introduced(X),
    not used(X),
    not decorative(X),
    object_name(X, Name),
    Desc = @format("Object '%s' introduced but never used (Chekhov's gun violation)", (Name)).

% ----- CAUSALITY VIOLATION 2: Uncaused Significant Event -----
% Major plot events should have causes

caused(E) :- causes(_, E).
caused(E) :- initial_event(E).
caused(E) :- event_type(E, natural).

violation(causality, uncaused_event, E, none, Desc) :-
    event(E),
    significant_event(E),
    not caused(E),
    event_description(E, EDesc),
    Desc = @format("Significant event '%s' lacks causal explanation", (EDesc)).

% ----- CAUSALITY VIOLATION 3: Effect Without Cause -----
% If a fluent becomes true, something must have caused it

fluent_caused(fluent(Prop, Entity), T) :-
    event(E),
    event_type(E, Type),
    causes_fluent(Type, pos, Prop, Role),
    role_arg(E, Role, Entity),
    time(E, _, T).

violation(causality, effect_without_cause, F, T, Desc) :-
    holds(F, T, _),
    not fluent_caused(F, T),
    not initial_fluent(F),
    fluent_description(F, FDesc),
    Desc = @format("State '%s' becomes true without causal explanation", (FDesc)).

% ----- CAUSALITY VIOLATION 4: Missing Precondition -----
% Actions that require preconditions

violation(causality, missing_precondition, E, Pred, Desc) :-
    event(E),
    event_type(E, Type),
    requires_precondition(Type, pos, Pred, Role),
    role_arg(E, Role, Arg),
    time(E, Start, _),
    not holds_at(fluent(Pred, Arg), Start),
    event_description(E, EDesc),
    Desc = @format("Event '%s' missing required precondition '%s'", (EDesc, Pred)).


% =============================================================================
% SECTION 2: COHERENCE VIOLATIONS (Semantic/Logical Consistency)
% =============================================================================
%
% Coherence: Things should have semantic correctness - no logical
% impossibilities like dead characters acting or eating inedible objects.
%
% =============================================================================

% ----- Life/Death Tracking -----

dead_after(C, T) :- event(E), event_type(E, die), agent(E, C), time(E, _, T).
dead_after(C, T) :- event(E), event_type(E, kill), patient(E, C), time(E, _, T).
dead_after(C, T) :- event(E), event_type(E, murder), patient(E, C), time(E, _, T).
dead_after(C, T2) :- dead_after(C, T1), before(T1, T2).

% COHERENCE VIOLATION 1: Dead Agent Acting
violation(coherence, dead_agent, E, C, Desc) :-
    event(E),
    agent(E, C),
    character(C),
    time(E, Tstart, _),
    dead_after(C, Tdeath),
    before(Tdeath, Tstart),
    character_name(C, CName),
    event_description(E, EDesc),
    Desc = @format("Dead character '%s' performs action: %s", (CName, EDesc)).

% ----- Edibility Rules -----

non_edible(X) :- rock(X).
non_edible(X) :- stone(X).
non_edible(X) :- metal(X).
non_edible(X) :- glass(X).
non_edible(X) :- plastic(X).
non_edible(X) :- wood(X).
non_edible(X) :- paper(X).
non_edible(X) :- building(X).
non_edible(X) :- furniture(X).
non_edible(X) :- clothing(X).
non_edible(X) :- weapon(X).
non_edible(X) :- poison(X).
non_edible(X) :- inedible(X).

edible(X) :- food(X).
edible(X) :- fruit(X).
edible(X) :- vegetable(X).
edible(X) :- meat(X).
edible(X) :- bread(X).
edible(X) :- candy(X).

% COHERENCE VIOLATION 2: Eating Non-Edible Objects
violation(coherence, non_edible, E, X, Desc) :-
    event(E),
    event_type(E, eat),
    patient(E, X),
    non_edible(X),
    object_name(X, OName),
    event_description(E, EDesc),
    Desc = @format("Eating non-edible object '%s': %s", (OName, EDesc)).

% ----- Physical Capability Requirements -----

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
requires_speech(say).
requires_speech(tell).

requires_mobility(walk).
requires_mobility(run).
requires_mobility(jump).
requires_mobility(climb).
requires_mobility(dance).

% COHERENCE VIOLATION 3: Physical Impossibility
violation(coherence, physical_impossibility, E, blind, Desc) :-
    trait(A, blind),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_sight(Type),
    character_name(A, AName),
    Desc = @format("Blind character '%s' performs sight-requiring action: %s", (AName, Type)).

violation(coherence, physical_impossibility, E, deaf, Desc) :-
    trait(A, deaf),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_hearing(Type),
    character_name(A, AName),
    Desc = @format("Deaf character '%s' performs hearing-requiring action: %s", (AName, Type)).

violation(coherence, physical_impossibility, E, mute, Desc) :-
    trait(A, mute),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_speech(Type),
    character_name(A, AName),
    Desc = @format("Mute character '%s' performs speech-requiring action: %s", (AName, Type)).

violation(coherence, physical_impossibility, E, paralyzed, Desc) :-
    trait(A, paralyzed),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_mobility(Type),
    character_name(A, AName),
    Desc = @format("Paralyzed character '%s' performs mobility-requiring action: %s", (AName, Type)).

% COHERENCE VIOLATION 4: Focus Overlap
% Can't do two attention-demanding tasks simultaneously
violation(coherence, focus_overlap, E1, E2, Desc) :-
    event(E1), event(E2),
    requires_focus(E1),
    requires_focus(E2),
    agent(E1, A), agent(E2, A),
    overlap(E1, E2),
    E1 < E2,
    character_name(A, AName),
    event_description(E1, E1Desc),
    event_description(E2, E2Desc),
    Desc = @format("Character '%s' simultaneously: %s and %s", (AName, E1Desc, E2Desc)).


% =============================================================================
% SECTION 3: TEMPORAL VIOLATIONS
% =============================================================================
%
% Temporal: Things must be possible in the given intervals. If exact times
% aren't explicitly given or specifically inconsistent, assume correctness.
% Only flag clear violations.
%
% =============================================================================

% TEMPORAL VIOLATION 1: Circular Time (Paradox)
violation(temporal, circular_time, T1, T2, Desc) :-
    before(T1, T2),
    before(T2, T1),
    Desc = @format("Time paradox: %s both precedes and follows %s", (T1, T2)).

% TEMPORAL VIOLATION 2: Negative Duration
% Event ends before it starts
violation(temporal, negative_duration, E, none, Desc) :-
    event(E),
    time(E, Start, End),
    before(End, Start),
    event_description(E, EDesc),
    Desc = @format("Event '%s' ends before it starts", (EDesc)).

% TEMPORAL VIOLATION 3: Explicit Order Violated
% Story explicitly states E1 before E2, but timeline shows otherwise
violation(temporal, order_violated, E1, E2, Desc) :-
    must_precede(E1, E2),
    not precedes(E1, E2),
    event_description(E1, E1Desc),
    event_description(E2, E2Desc),
    Desc = @format("Temporal constraint violated: '%s' must precede '%s'", (E1Desc, E2Desc)).

% TEMPORAL VIOLATION 4: Impossible Duration
% Event duration is clearly unrealistic for the action type
violation(temporal, impossible_duration, E, none, Desc) :-
    event(E),
    event_type(E, Type),
    time(E, Start, End),
    duration_constraint(Type, MinDur, MaxDur),
    time_duration(Start, End, Duration),
    Duration < MinDur,
    event_description(E, EDesc),
    Desc = @format("Event '%s' duration too short for action type", (EDesc)).


% =============================================================================
% SECTION 4: LOCATION VIOLATIONS
% =============================================================================
%
% Location: Locations and distances must be correct. You can grab something
% from a table if you're in the same room, but not if you're in a different
% house.
%
% =============================================================================

% Track where entities are during events
at_during(Entity, Loc, E) :-
    event(E),
    agent(E, Entity),
    location(E, Loc).

at_during(Entity, Loc, E) :-
    event(E),
    patient(E, Entity),
    location(E, Loc),
    character(Entity).

% LOCATION VIOLATION 1: Ubiquity (Same character in two places at once)
violation(location, ubiquity, E1, E2, Desc) :-
    event(E1), event(E2),
    agent(E1, A), agent(E2, A),
    location(E1, L1), location(E2, L2),
    L1 != L2,
    overlap(E1, E2),
    E1 < E2,
    character_name(A, AName),
    location_name(L1, L1Name),
    location_name(L2, L2Name),
    Desc = @format("Character '%s' simultaneously at '%s' and '%s'", (AName, L1Name, L2Name)).

% LOCATION VIOLATION 2: Impossible Travel
% Moving between distant locations with no travel time
violation(location, impossible_travel, E1, E2, Desc) :-
    event(E1), event(E2),
    agent(E1, A), agent(E2, A),
    location(E1, L1), location(E2, L2),
    L1 != L2,
    meets(E1, E2),
    distant(L1, L2),
    not is_travel_event(E1),
    not is_travel_event(E2),
    not allows_teleportation(A),
    character_name(A, AName),
    location_name(L1, L1Name),
    location_name(L2, L2Name),
    Desc = @format("Character '%s' instantly moves from '%s' to '%s'", (AName, L1Name, L2Name)).

% Travel event types
is_travel_event(E) :- event_type(E, walk).
is_travel_event(E) :- event_type(E, run).
is_travel_event(E) :- event_type(E, travel).
is_travel_event(E) :- event_type(E, journey).
is_travel_event(E) :- event_type(E, fly).
is_travel_event(E) :- event_type(E, ride).
is_travel_event(E) :- event_type(E, drive).
is_travel_event(E) :- event_type(E, teleport).
is_travel_event(E) :- event_type(E, apparate).

% LOCATION VIOLATION 3: Proximity Required
% Interacting with something too far away
violation(location, proximity_required, E, Patient, Desc) :-
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    location(E, AgentLoc),
    object_location(Patient, PatientLoc, E),
    AgentLoc != PatientLoc,
    requires_proximity(E),
    not allows_remote(E),
    character_name(Agent, AName),
    object_name(Patient, PName),
    location_name(AgentLoc, ALName),
    location_name(PatientLoc, PLName),
    Desc = @format("Character '%s' at '%s' interacts with '%s' at '%s'", (AName, ALName, PName, PLName)).

% Physical interaction actions require proximity by default
requires_proximity(E) :- event_type(E, grab).
requires_proximity(E) :- event_type(E, take).
requires_proximity(E) :- event_type(E, touch).
requires_proximity(E) :- event_type(E, push).
requires_proximity(E) :- event_type(E, hit).
requires_proximity(E) :- event_type(E, kick).


% =============================================================================
% SECTION 5: EMOTIONAL VIOLATIONS
% =============================================================================
%
% Emotional: Characters must behave in a way that reflects their current
% emotions and their relations and feelings with other characters.
% E.g., character A should be kind to character B if A loves B.
%
% =============================================================================

% Action classifications
harmful_action(kill).
harmful_action(murder).
harmful_action(attack).
harmful_action(hurt).
harmful_action(harm).
harmful_action(betray).
harmful_action(abandon).
harmful_action(steal_from).
harmful_action(deceive).
harmful_action(lie_to).
harmful_action(threaten).
harmful_action(insult).

helpful_action(help).
helpful_action(save).
helpful_action(rescue).
helpful_action(protect).
helpful_action(give).
helpful_action(heal).
helpful_action(comfort).
helpful_action(support).
helpful_action(assist).

approach_action(approach).
approach_action(confront).
approach_action(visit).
approach_action(meet).
approach_action(seek).

% EMOTIONAL VIOLATION 1: Harming Loved One
% Character harms someone they love without justification
violation(emotional, harm_loved, E, B, Desc) :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    harmful_action(Type),
    loves(A, B),
    not justified_harm(E),
    character_name(A, AName),
    character_name(B, BName),
    Desc = @format("Character '%s' (who loves '%s') performs harmful action: %s", (AName, BName, Type)).

% EMOTIONAL VIOLATION 2: Helping Enemy
% Character helps someone they hate without strategic reason
violation(emotional, help_enemy, E, B, Desc) :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    helpful_action(Type),
    hates(A, B),
    not strategic_help(E),
    character_name(A, AName),
    character_name(B, BName),
    Desc = @format("Character '%s' (who hates '%s') performs helpful action: %s", (AName, BName, Type)).

% EMOTIONAL VIOLATION 3: Approaching Feared Entity
% Character approaches something they fear without necessity
violation(emotional, approach_feared, E, B, Desc) :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    approach_action(Type),
    fears(A, B),
    not forced_approach(E),
    character_name(A, AName),
    entity_name(B, BName),
    Desc = @format("Character '%s' (who fears '%s') approaches without necessity", (AName, BName)).

% EMOTIONAL VIOLATION 4: Trusting Untrustworthy
% Character trusts someone they distrust
violation(emotional, misplaced_trust, E, B, Desc) :-
    event(E),
    agent(E, A),
    patient(E, B),
    involves_trust(E),
    distrusts(A, B),
    not trust_restored(A, B, E),
    character_name(A, AName),
    character_name(B, BName),
    event_description(E, EDesc),
    Desc = @format("Character '%s' trusts untrustworthy '%s': %s", (AName, BName, EDesc)).

% EMOTIONAL VIOLATION 5: Emotional State Mismatch
% Action contradicts current emotional state
violation(emotional, state_action_mismatch, E, State, Desc) :-
    event(E),
    agent(E, A),
    time(E, T, _),
    emotional_state(A, State, T),
    event_type(E, Type),
    contradicts_emotion(State, Type),
    character_name(A, AName),
    Desc = @format("Character '%s' in state '%s' performs contradictory action: %s", (AName, State, Type)).

% Emotion-action contradictions
contradicts_emotion(happy, mourn).
contradicts_emotion(happy, weep).
contradicts_emotion(happy, grieve).
contradicts_emotion(sad, celebrate).
contradicts_emotion(sad, laugh).
contradicts_emotion(sad, rejoice).
contradicts_emotion(calm, panic).
contradicts_emotion(calm, rage).
contradicts_emotion(angry, forgive).
contradicts_emotion(terrified, relax).


% =============================================================================
% SECTION 6: DEFAULT HELPERS AND FALLBACKS
% =============================================================================
%
% Default rules to ensure the program runs even with incomplete domain facts.
%
% =============================================================================

% Default naming if not provided
character_name(X, X) :- character(X), not has_explicit_char_name(X).
object_name(X, X) :- object(X), not has_explicit_obj_name(X).
location_name(X, X) :- location(X), not has_explicit_loc_name(X).
entity_name(X, Name) :- character_name(X, Name).
entity_name(X, Name) :- object_name(X, Name).
entity_name(X, Name) :- location_name(X, Name).

% Default event description
event_description(E, Desc) :- 
    event(E), 
    event_type(E, T),
    agent(E, A),
    character_name(A, AName),
    Desc = @format("%s performs %s", (AName, T)).

event_description(E, E) :- event(E), not event_type(E, _).

% Default fluent description - requires fluent to be grounded through holds
fluent_description(fluent(P, E), Desc) :-
    holds(fluent(P, E), _, _),
    entity_name(E, EName),
    Desc = @format("%s(%s)", (P, EName)).

% Fallback: if no entity_name available, use fluent as its own description  
fluent_description(F, F) :- holds(F, _, _), F = fluent(P, E), not entity_name(E, _).


% =============================================================================
% OUTPUT CONFIGURATION
% =============================================================================

% Show 5-argument violations (category, type, primary, secondary, description)
#show violation/5.

% For backwards compatibility
#show violation/2.
#show violation/3.
#show violation/4.


% =============================================================================
%
%    END OF GENERAL ABSTRACT RULES MODULE
%
%    DOMAIN-SPECIFIC PREDICATES EXPECTED FROM domain_specific.lp:
%    ------------------------------------------------------------
%    
%    BASIC ENTITIES:
%    - character(C), object(O), location(L)
%    - event(E), event_type(E, Type)
%    - agent(E, A), patient(E, P), instrument(E, I)
%    - time(E, Start, End), time_order(T1, T2)
%    - location(E, L) - event location
%    
%    NAMING:
%    - character_name(C, Name), object_name(O, Name), location_name(L, Name)
%    - event_description(E, Desc), fluent_description(F, Desc)
%    - has_explicit_char_name(X), has_explicit_obj_name(X), has_explicit_loc_name(X)
%    
%    CAUSALITY:
%    - decorative(X) - object is decorative (Chekhov exception)
%    - significant_event(E) - event is plot-significant
%    - initial_event(E), initial_fluent(F)
%    - causes(E1, E2) - event causation
%    - causes_fluent(Type, Pol, Prop, Role)
%    - requires_precondition(Type, Pol, Prop, Role)
%    
%    COHERENCE:
%    - trait(C, Trait), requires_focus(E)
%    - Material types: rock(X), metal(X), food(X), etc.
%    
%    TEMPORAL:
%    - must_precede(E1, E2)
%    - duration_constraint(Type, Min, Max)
%    - time_duration(T1, T2, Duration)
%    
%    LOCATION:
%    - distant(L1, L2), adjacent(L1, L2)
%    - object_location(O, L, E)
%    - allows_remote(E), allows_teleportation(C)
%    
%    EMOTIONAL:
%    - loves(A, B), hates(A, B), fears(A, B), trusts(A, B), distrusts(A, B)
%    - justified_harm(E), strategic_help(E), forced_approach(E)
%    - trust_restored(A, B, E)
%    - emotional_state(C, State, T)
%    - involves_trust(E)
%
% =============================================================================
