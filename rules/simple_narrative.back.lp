% =============================================================================
%
%    SIMPLE NARRATIVE RULES - For ILASP Experiments
%    ===============================================
%
%    A simplified rule set for narrative consistency checking that works
%    with basic event/character facts without explicit time intervals.
%
%    ERROR CATEGORIES:
%    1. COHERENCE - Dead characters acting, logical impossibilities
%    2. CAUSALITY - Events without proper causes
%    3. TEMPORAL - Ordering violations (using before/2)
%    4. LOCATION - Character presence violations
%    5. EMOTIONAL - Relationship-behavior mismatches
%
% =============================================================================

% Show only violations
#show violation/5.

% =============================================================================
% SECTION 1: INFERRED STATES FROM EVENTS
% =============================================================================

% Infer death from death/die/kill events
% A character dies if they are the patient of a kill event
dies_in_event(C, E) :- event(E), event_type(E, kill), patient(E, C), character(C).
dies_in_event(C, E) :- event(E), event_type(E, murder), patient(E, C), character(C).
dies_in_event(C, E) :- event(E), event_type(E, death), patient(E, C), character(C).

% Also check if character is the agent of a 'die' event
dies_in_event(C, E) :- event(E), event_type(E, die), agent(E, C), character(C).
dies_in_event(C, E) :- event(E), event_type(E, death), agent(E, C), character(C).

% Character is dead after death event
dead_after(C, E) :- dies_in_event(C, E).

% Dead state propagates forward through event ordering
dead_at(C, E2) :- dead_after(C, E1), before(E1, E2).
dead_at(C, E2) :- dead_after(C, E1), E1 = E2.

% Character acts in event (as agent)
acts_in(C, E) :- event(E), agent(E, C).

% =============================================================================
% SECTION 2: COHERENCE VIOLATIONS
% =============================================================================

% COHERENCE: Dead agent acting
% A dead character cannot perform actions after dying
violation(coherence, dead_agent, E, C, "Dead character performs action after dying") :-
    event(E),
    agent(E, C),
    dead_at(C, E),
    not dies_in_event(C, E).  % Exclude the death event itself

% COHERENCE: Object in multiple places
violation(coherence, object_ubiquity, E1, O, "Object simultaneously in multiple locations") :-
    event(E1), event(E2),
    location(E1, L1), location(E2, L2),
    patient(E1, O), patient(E2, O),
    object(O),
    L1 != L2,
    not before(E1, E2),
    not before(E2, E1),
    E1 < E2.

% =============================================================================
% SECTION 3: LOCATION VIOLATIONS
% =============================================================================

% Track character locations based on events
at_location_after(C, L, E) :- event(E), agent(E, C), location(E, L).
at_location_after(C, L, E) :- event(E), patient(E, C), location(E, L).

% LOCATION: Character ubiquity (two places at once)
violation(location, character_ubiquity, E1, C, "Character in two locations simultaneously") :-
    event(E1), event(E2),
    agent(E1, C), agent(E2, C),
    location(E1, L1), location(E2, L2),
    character(C),
    L1 != L2,
    not before(E1, E2),
    not before(E2, E1),
    E1 < E2.

% =============================================================================
% SECTION 4: TEMPORAL VIOLATIONS  
% =============================================================================

% TEMPORAL: Circular causation (A before B and B before A)
violation(temporal, circular_ordering, E1, E2, "Circular temporal ordering detected") :-
    event(E1), event(E2),
    before(E1, E2),
    before(E2, E1).

% =============================================================================
% SECTION 5: CAUSALITY VIOLATIONS
% =============================================================================

% An action event requires a living agent
% (already covered by dead_agent coherence violation)

% Causality: Effect without cause for state changes
% If a character has an object but never acquired it
violation(causality, unexplained_possession, E, O, "Character uses object never acquired") :-
    event(E),
    event_type(E, use),
    patient(E, O),
    object(O),
    not owns(_, O).

% Track ownership
owns(C, O) :- event(E), event_type(E, take), agent(E, C), patient(E, O).
owns(C, O) :- event(E), event_type(E, grab), agent(E, C), patient(E, O).
owns(C, O) :- event(E), event_type(E, acquire), agent(E, C), patient(E, O).

% =============================================================================
% SECTION 6: EMOTIONAL VIOLATIONS
% =============================================================================

% EMOTIONAL: Hostile action toward loved one
violation(emotional, love_hate_conflict, E, C2, "Character acts hostile toward loved one") :-
    event(E),
    event_type(E, attack),
    agent(E, C1),
    patient(E, C2),
    loves(C1, C2).

violation(emotional, love_hate_conflict, E, C2, "Character acts hostile toward loved one") :-
    event(E),
    event_type(E, kill),
    agent(E, C1),
    patient(E, C2),
    loves(C1, C2).

% EMOTIONAL: Kind action toward enemy
violation(emotional, enemy_kindness, E, C2, "Character acts kind toward enemy") :-
    event(E),
    event_type(E, help),
    agent(E, C1),
    patient(E, C2),
    hates(C1, C2).

% Default empty relationships if not specified
loves(X, Y) :- relationship(X, Y, love).
loves(X, Y) :- relationship(X, Y, spouse).
hates(X, Y) :- relationship(X, Y, enemy).
hates(X, Y) :- relationship(X, Y, hate).

% =============================================================================
% SECTION 7: TRAIT-BASED VIOLATIONS  
% =============================================================================

% Visual actions
visual_action(see).
visual_action(look).
visual_action(observe).
visual_action(read).
visual_action(watch).

% Auditory actions
auditory_action(hear).
auditory_action(listen).

% Speech actions
speech_action(speak).
speech_action(say).
speech_action(tell).
speech_action(shout).
speech_action(sing).

% COHERENCE: Blind character seeing
violation(coherence, trait_violation, E, C, "Blind character performing visual action") :-
    event(E),
    agent(E, C),
    event_type(E, T),
    visual_action(T),
    trait(C, blind).

% COHERENCE: Deaf character hearing
violation(coherence, trait_violation, E, C, "Deaf character performing auditory action") :-
    event(E),
    agent(E, C),
    event_type(E, T),
    auditory_action(T),
    trait(C, deaf).

% COHERENCE: Mute character speaking
violation(coherence, trait_violation, E, C, "Mute character performing speech action") :-
    event(E),
    agent(E, C),
    event_type(E, T),
    speech_action(T),
    trait(C, mute).
