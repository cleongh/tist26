% =============================================================================
%
%    GENERAL NARRATIVE CONSISTENCY RULES (Domain-Independent)
%    =========================================================
%
%    This module contains abstract, domain-independent rules for detecting
%    narrative inconsistencies across FIVE key categories:
%
%    1. CAUSALITY - Chekhov's gun, causal chains, unexplained events
%    2. COHERENCE - Semantic correctness, logical consistency  
%    3. TEMPORAL  - Time intervals, durations, ordering violations
%    4. LOCATION  - Spatial constraints, distances, ubiquity
%    5. EMOTIONAL - Character motivations, relationships, behavior
%
%    This file works with domain-specific facts (generated per story set)
%    and outputs structured violations for academic analysis.
%
%    VIOLATION OUTPUT FORMAT:
%    violation(Category, Type, EventID, Detail, Description).
%    - Category: causality | coherence | temporal | location | emotional
%    - Type: Specific violation subtype
%    - EventID: Primary event ID that triggered the violation
%    - Detail: Additional context (event/entity ID or "none")
%    - Description: Human-readable explanation
%
% =============================================================================

% =============================================================================
% CATEGORY 1: CAUSALITY
% =============================================================================
% 
% Causality violations detect problems in causal chains:
% - Chekhov's gun: introduced elements never used
% - Uncaused events: significant events without proper causes
% - Broken causal chains: effects without causes
% - Actions without preconditions
%
% =============================================================================

% ----- Time Infrastructure (needed for all categories) -----

time_point(T) :- time(_,T,_).
time_point(T) :- time(_,_,T).
time_point(T) :- holds(_,T,_).
time_point(T) :- holds(_,_,T).

before(T1,T2) :- time_order(T1,T2).
before(T1,T3) :- before(T1,T2), before(T2,T3).

% ----- Entity Tracking -----

introduced(X) :- character(X).
introduced(X) :- object(X).

used(X) :- agent(_, X).
used(X) :- patient(_, X).
used(X) :- instrument(_, X).
used(X) :- mentioned_in_event(X, _).  % Domain-specific predicate

% ----- Role Extraction Helper -----

role_arg(E, agent, A) :- agent(E, A).
role_arg(E, patient, P) :- patient(E, P).
role_arg(E, instrument, I) :- instrument(E, I).

% ----- CAUSALITY VIOLATION 1: Chekhov's Gun -----
% "If you show a gun in Act 1, it must fire by Act 3"
% Objects introduced but never meaningfully used

violation(causality, chekhovs_gun, X, none, Desc) :-
    object(X),
    introduced(X),
    not used(X),
    not decorative(X),                % Exemption for setting/background objects
    object_name(X, Name),
    Desc = @format("Object '~s' introduced but never used (Chekhov's gun violation)", [Name]).

% ----- CAUSALITY VIOLATION 2: Uncaused Significant Event -----
% Major plot events should have causes

caused(E) :- causes_event(_, E).      % Domain: some event causes this
caused(E) :- initial_event(E).        % Domain: marked as story opening
caused(E) :- event_type(E, natural).  % Natural phenomena don't need causes

violation(causality, uncaused_event, E, none, Desc) :-
    event(E),
    significant_event(E),             % Domain: marked as plot-significant
    not caused(E),
    event_description(E, EDesc),
    Desc = @format("Significant event '~s' lacks causal explanation", [EDesc]).

% ----- CAUSALITY VIOLATION 3: Effect Without Cause -----
% If a fluent becomes true, something must have caused it

fluent_caused(fluent(Prop, Entity), T) :-
    event(E),
    event_type(E, Type),
    causes_fluent(Type, pos, Prop, Role),  % Domain: event type causes fluent
    role_arg(E, Role, Entity),
    time(E, _, T).

violation(causality, effect_without_cause, F, T, Desc) :-
    holds(F, T, _),
    not fluent_caused(F, T),
    not initial_fluent(F),            % Domain: fluent true at story start
    fluent_description(F, FDesc),
    Desc = @format("State '~s' becomes true without causal explanation", [FDesc]).

% ----- CAUSALITY VIOLATION 4: Missing Precondition -----
% Actions that require preconditions

violation(causality, missing_precondition, E, Pred, Desc) :-
    event(E),
    event_type(E, Type),
    requires_precondition(Type, pos, Pred, Role),  % Domain: action requires condition
    role_arg(E, Role, Arg),
    time(E, Start, _),
    not holds_at(fluent(Pred, Arg), Start),
    event_description(E, EDesc),
    Desc = @format("Event '~s' missing required precondition '~s'", [EDesc, Pred]).

% ----- Fluent Reasoning Infrastructure -----

holds_at(F, T) :- 
    holds(F, Start, End),
    time_point(T),
    not before(T, Start),
    not before(End, T).

holds_at(fluent(Pred, Arg), End) :-
    event(E), event_type(E, Type),
    causes_fluent(Type, pos, Pred, Role),
    role_arg(E, Role, Arg),
    time(E, _, End).

holds_at_negated(fluent(Pred, Arg), T) :- 
    event(E), event_type(E, Type),
    causes_fluent(Type, neg, Pred, Role),
    role_arg(E, Role, Arg),
    time(E, _, T).

% Frame axiom: fluents persist unless negated
holds_at(F, T2) :- 
    holds_at(F, T1),
    before(T1, T2),
    time_point(T2),
    not holds_at_negated(F, T2).


% =============================================================================
% CATEGORY 2: COHERENCE (Semantic/Logical Consistency)
% =============================================================================
%
% Coherence violations are semantic errors that break world consistency:
% - Dead agents acting
% - Eating inedible objects
% - Physical impossibilities (blind reading, etc.)
% - Contradictory states
%
% =============================================================================

% ----- Life/Death Tracking -----

dead_after(C, T) :- event(E), event_type(E, die), agent(E, C), time(E, _, T).
dead_after(C, T) :- event(E), event_type(E, kill), patient(E, C), time(E, _, T).
dead_after(C, T) :- event(E), event_type(E, murder), patient(E, C), time(E, _, T).

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
    Desc = @format("Dead character '~s' performs action: ~s", [CName, EDesc]).

% ----- Edibility Rules -----

% Objects that are definitively not edible
non_edible(X) :- rock(X).
non_edible(X) :- stone(X).
non_edible(X) :- pebble(X).
non_edible(X) :- metal(X).
non_edible(X) :- glass(X).
non_edible(X) :- plastic(X).
non_edible(X) :- wood(X).
non_edible(X) :- paper(X).
non_edible(X) :- building(X).
non_edible(X) :- furniture(X).
non_edible(X) :- clothing(X).
non_edible(X) :- tool(X).
non_edible(X) :- weapon(X).
non_edible(X) :- poison(X).
non_edible(X) :- inedible(X).

% Objects that are edible
edible(X) :- food(X).
edible(X) :- fruit(X).
edible(X) :- vegetable(X).
edible(X) :- meat(X).
edible(X) :- bread(X).
edible(X) :- candy(X).
edible(X) :- cake(X).
edible(X) :- gingerbread(X).
edible(X) :- crumbs(X).

% Default: objects not explicitly non-edible might be edible
edible(X) :- object(X), not non_edible(X), not explicitly_inedible(X).

% COHERENCE VIOLATION 2: Eating Non-Edible Objects
violation(coherence, non_edible, E, X, Desc) :-
    event(E),
    event_type(E, eat),
    patient(E, X),
    non_edible(X),
    object_name(X, OName),
    event_description(E, EDesc),
    Desc = @format("Eating non-edible object '~s': ~s", [OName, EDesc]).

% ----- Physical Limitations -----

% Actions requiring physical capabilities
requires_sight(read).
requires_sight(see).
requires_sight(watch).
requires_sight(observe).
requires_sight(look).
requires_sight(aim).
requires_sight(write).  % Normally requires sight

requires_hearing(hear).
requires_hearing(listen).
requires_hearing(eavesdrop).

requires_speech(speak).
requires_speech(shout).
requires_speech(sing).
requires_speech(call).
requires_speech(yell).
requires_speech(scream).
requires_speech(say).
requires_speech(tell).

requires_mobility(walk).
requires_mobility(run).
requires_mobility(jump).
requires_mobility(climb).
requires_mobility(dance).

% COHERENCE VIOLATION 3: Physical Impossibility (Blind/Deaf/Mute)
violation(coherence, physical_impossibility, E, blind, Desc) :-
    trait(A, blind),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_sight(Type),
    character_name(A, AName),
    Desc = @format("Blind character '~s' performs sight-requiring action: ~s", [AName, Type]).

violation(coherence, physical_impossibility, E, deaf, Desc) :-
    trait(A, deaf),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_hearing(Type),
    character_name(A, AName),
    Desc = @format("Deaf character '~s' performs hearing-requiring action: ~s", [AName, Type]).

violation(coherence, physical_impossibility, E, mute, Desc) :-
    trait(A, mute),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_speech(Type),
    character_name(A, AName),
    Desc = @format("Mute character '~s' performs speech-requiring action: ~s", [AName, Type]).

violation(coherence, physical_impossibility, E, paralyzed, Desc) :-
    trait(A, paralyzed),
    event(E), agent(E, A),
    event_type(E, Type),
    requires_mobility(Type),
    character_name(A, AName),
    Desc = @format("Paralyzed character '~s' performs mobility-requiring action: ~s", [AName, Type]).

% ----- Focus/Attention Constraints -----

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
    Desc = @format("Character '~s' simultaneously: ~s and ~s", [AName, E1Desc, E2Desc]).


% =============================================================================
% CATEGORY 3: TEMPORAL (Time Ordering and Intervals)
% =============================================================================
%
% Temporal violations detect problems in time structure:
% - Circular time orderings (paradoxes)
% - Negative durations (end before start)
% - Violated explicit temporal constraints
% - Impossible durations
%
% =============================================================================

% ----- Event Temporal Relations -----

overlap(E1,E2) :-
    event(E1), event(E2),
    time(E1,S1,End1),
    time(E2,S2,End2),
    not before(End1,S2),
    not before(End2,S1),
    E1 != E2.

precedes(E1,E2) :-
    event(E1), event(E2),
    time(E1,_,End1),
    time(E2,S2,_),
    before(End1,S2).

meets(E1,E2) :-
    event(E1), event(E2),
    time(E1,_,T),
    time(E2,T,_),
    E1 != E2.

concurrent(E1,E2) :- overlap(E1,E2).
concurrent(E1,E2) :- overlap(E2,E1).

% TEMPORAL VIOLATION 1: Circular Time
% T1 < T2 and T2 < T1 is impossible
violation(temporal, circular_time, T1, T2, Desc) :-
    before(T1, T2),
    before(T2, T1),
    Desc = @format("Circular time ordering: ~s < ~s < ~s", [T1, T2, T1]).

% TEMPORAL VIOLATION 2: Negative Duration
% Event ends before it starts
violation(temporal, negative_duration, E, none, Desc) :-
    event(E),
    time(E, Start, End),
    before(End, Start),
    event_description(E, EDesc),
    Desc = @format("Event '~s' ends before it starts", [EDesc]).

% TEMPORAL VIOLATION 3: Explicit Order Violated
% Story explicitly states E1 before E2, but timeline shows otherwise
violation(temporal, order_violated, E1, E2, Desc) :-
    must_precede(E1, E2),           % Domain: explicit temporal constraint
    not precedes(E1, E2),
    event_description(E1, E1Desc),
    event_description(E2, E2Desc),
    Desc = @format("Temporal constraint violated: '~s' must precede '~s'", [E1Desc, E2Desc]).

% TEMPORAL VIOLATION 4: Impossible Duration
% Event duration is unrealistic for the action type
violation(temporal, impossible_duration, E, Duration, Desc) :-
    event(E),
    event_type(E, Type),
    time(E, Start, End),
    duration_constraint(Type, MinDur, MaxDur),  % Domain: realistic durations
    time_duration(Start, End, Duration),
    (Duration < MinDur ; Duration > MaxDur),
    event_description(E, EDesc),
    Desc = @format("Event '~s' has unrealistic duration: ~d (expected ~d-~d)", 
                   [EDesc, Duration, MinDur, MaxDur]).


% =============================================================================
% CATEGORY 4: LOCATION (Spatial Constraints)
% =============================================================================
%
% Location violations detect spatial impossibilities:
% - Ubiquity: being in two places at once
% - Impossible travel: instant teleportation
% - Proximity violations: interacting at distance
% - Out-of-reach actions
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

% LOCATION VIOLATION 1: Ubiquity
% Same character in two different places at the same time
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
    Desc = @format("Character '~s' simultaneously at '~s' and '~s'", [AName, L1Name, L2Name]).

% LOCATION VIOLATION 2: Impossible Travel
% Moving between distant locations with insufficient time
violation(location, impossible_travel, E1, E2, Desc) :-
    event(E1), event(E2),
    agent(E1, A), agent(E2, A),
    location(E1, L1), location(E2, L2),
    L1 != L2,
    precedes(E1, E2),
    time(E1, _, End1),
    time(E2, Start2, _),
    time_duration(End1, Start2, TravelTime),
    distant(L1, L2, MinDistance),     % Domain: location distances
    required_travel_time(MinDistance, MinTime),  % Domain: travel time calculation
    TravelTime < MinTime,
    character_name(A, AName),
    location_name(L1, L1Name),
    location_name(L2, L2Name),
    Desc = @format("Character '~s' travels from '~s' to '~s' in ~d time (requires ~d)", 
                   [AName, L1Name, L2Name, TravelTime, MinTime]).

% LOCATION VIOLATION 3: Proximity Required
% Interacting with something that's too far away
violation(location, proximity_required, E, Patient, Desc) :-
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    location(E, AgentLoc),
    object_location(Patient, PatientLoc, E),  % Domain: object locations
    AgentLoc != PatientLoc,
    requires_proximity(E),                    % Domain: action needs proximity
    not allows_remote(E),                     % Domain: unless explicitly remote
    character_name(Agent, AName),
    object_name(Patient, PName),
    location_name(AgentLoc, ALName),
    location_name(PatientLoc, PLName),
    Desc = @format("Character '~s' at '~s' interacts with '~s' at '~s'", 
                   [AName, ALName, PName, PLName]).

% Helper: Check if event is travel
is_travel_event(E) :- event_type(E, walk).
is_travel_event(E) :- event_type(E, run).
is_travel_event(E) :- event_type(E, travel).
is_travel_event(E) :- event_type(E, journey).
is_travel_event(E) :- event_type(E, fly).
is_travel_event(E) :- event_type(E, ride).
is_travel_event(E) :- event_type(E, drive).


% =============================================================================
% CATEGORY 5: EMOTIONAL (Character Motivations & Relationships)
% =============================================================================
%
% Emotional violations detect character behavior inconsistencies:
% - Harming loved ones without justification
% - Helping enemies without motivation
% - Approaching feared entities
% - Emotional state contradicting actions
%
% =============================================================================

% ----- Action Classifications -----

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
    loves(A, B),                      % Domain: relationship
    not justified_harm(E),            % Domain: unless justified
    character_name(A, AName),
    character_name(B, BName),
    Desc = @format("Character '~s' (who loves '~s') performs harmful action: ~s", 
                   [AName, BName, Type]).

% EMOTIONAL VIOLATION 2: Helping Enemy
% Character helps someone they hate without strategic reason
violation(emotional, help_enemy, E, B, Desc) :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    helpful_action(Type),
    hates(A, B),                      % Domain: relationship
    not strategic_help(E),            % Domain: unless strategic
    character_name(A, AName),
    character_name(B, BName),
    Desc = @format("Character '~s' (who hates '~s') performs helpful action: ~s", 
                   [AName, BName, Type]).

% EMOTIONAL VIOLATION 3: Approaching Feared Entity
% Character approaches someone/something they fear without necessity
violation(emotional, approach_feared, E, B, Desc) :-
    event(E),
    agent(E, A),
    patient(E, B),
    event_type(E, Type),
    approach_action(Type),
    fears(A, B),                      % Domain: relationship
    not forced_approach(E),           % Domain: unless forced/necessary
    character_name(A, AName),
    entity_name(B, BName),
    Desc = @format("Character '~s' (who fears '~s') approaches without necessity: ~s", 
                   [AName, BName, Type]).

% EMOTIONAL VIOLATION 4: Trusting Untrustworthy
% Character trusts someone shown to be untrustworthy
violation(emotional, misplaced_trust, E, B, Desc) :-
    event(E),
    agent(E, A),
    patient(E, B),
    involves_trust(E),                % Domain: action involves trust
    distrusts(A, B),                  % Domain: relationship
    not trust_restored(A, B, E),      % Domain: unless trust was restored
    character_name(A, AName),
    character_name(B, BName),
    event_description(E, EDesc),
    Desc = @format("Character '~s' trusts untrustworthy '~s': ~s", [AName, BName, EDesc]).

% EMOTIONAL VIOLATION 5: Emotional State Mismatch
% Action contradicts current emotional state
violation(emotional, state_mismatch, E, State, Desc) :-
    event(E),
    agent(E, A),
    time(E, T, _),
    emotional_state(A, State, T),     % Domain: character's emotional state
    event_type(E, Type),
    contradicts_emotion(State, Type), % Defined below
    character_name(A, AName),
    Desc = @format("Character '~s' in state '~s' performs contradictory action: ~s", 
                   [AName, State, Type]).

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
% DOMAIN INTERFACE
% =============================================================================
%
% These predicates are expected to be provided by the domain-specific module:
%
% BASIC ENTITIES:
% - character(C): C is a character
% - object(O): O is an object
% - location(L): L is a location
% - event(E): E is an event
% - event_type(E, Type): E is of action type Type
% - agent(E, A): A performs event E
% - patient(E, P): P is acted upon in event E
% - instrument(E, I): I is used in event E
% - time(E, Start, End): E occurs from Start to End
% - time_order(T1, T2): T1 is before T2
%
% NAMING:
% - character_name(C, Name): Character C has name Name
% - object_name(O, Name): Object O has name Name
% - location_name(L, Name): Location L has name Name
% - entity_name(E, Name): Generic entity naming
% - event_description(E, Desc): Human-readable event description
% - fluent_description(F, Desc): Human-readable fluent description
%
% CAUSALITY:
% - decorative(X): Object X is decorative (Chekhov's gun exception)
% - significant_event(E): Event E is plot-significant
% - initial_event(E): Event E is a story opening event
% - causes_event(E1, E2): Event E1 causes event E2
% - causes_fluent(Type, Polarity, Prop, Role): Event type causes fluent change
% - requires_precondition(Type, Polarity, Prop, Role): Event type requires precondition
% - initial_fluent(F): Fluent F is true at story start
%
% COHERENCE:
% - trait(C, Trait): Character C has trait Trait
% - requires_focus(E): Event E requires full attention
% - explicitly_inedible(X): Object X explicitly marked inedible
%
% TEMPORAL:
% - must_precede(E1, E2): E1 must happen before E2 (explicit constraint)
% - duration_constraint(Type, Min, Max): Event type has duration constraints
% - time_duration(T1, T2, Dur): Duration from T1 to T2 is Dur
%
% LOCATION:
% - location(E, L): Event E occurs at location L
% - distant(L1, L2, Distance): Locations are distant
% - object_location(O, L, E): Object O is at location L during event E
% - requires_proximity(E): Event E requires agent/patient proximity
% - allows_remote(E): Event E can occur remotely
% - required_travel_time(Distance, Time): Travel time for distance
%
% EMOTIONAL:
% - loves(A, B): Character A loves B
% - hates(A, B): Character A hates B
% - fears(A, B): Character A fears B
% - trusts(A, B): Character A trusts B
% - distrusts(A, B): Character A distrusts B
% - justified_harm(E): Harm in event E is justified
% - strategic_help(E): Help in event E is strategic
% - forced_approach(E): Approach in event E is forced
% - trust_restored(A, B, E): Trust between A and B was restored before E
% - emotional_state(A, State, T): Character A has emotional state at time T
% - involves_trust(E): Event E involves trust
%
% =============================================================================


% =============================================================================
% OUTPUT CONFIGURATION
% =============================================================================

% Show new 5-argument violations with detailed descriptions
#show violation/5.

% Backward compatibility with older formats
#show violation/2.
#show violation/3.
#show violation/4.


% =============================================================================
%
%    END OF GENERAL RULES MODULE
%
%    Usage:
%    $ clingo rules/general_v2.lp rules/domain_<story>.lp facts/<story>.lp
%
% =============================================================================
