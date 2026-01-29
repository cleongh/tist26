% =============================================================================
%
%    SIMPLE NARRATIVE RULES - Works with Basic Extracted Facts
%    ==========================================================
%
%    This file defines violation rules that work with the simplified facts
%    extracted by run_narrative_experiment.py's _structure_chapter() method.
%
%    EXPECTED INPUT FACTS:
%    - character(id).
%    - location_entity(id).
%    - object(id).
%    - event(id).
%    - event_type(id, type).
%    - agent(id, character).
%    - patient(id, target).
%    - location(id, place).
%
%    Events are numbered sequentially within a chapter (e1, e2, e3, ...)
%    so we can infer ordering from the event IDs.
%
%    VIOLATION OUTPUT FORMAT:
%    violation(category, type, event_or_entity, detail).
%
% =============================================================================

% =============================================================================
% PART 1: BASIC COHERENCE CHECKS
% =============================================================================

% --- Agent must be a known character ---
% If an event has an agent that's not declared as a character, flag it
violation(coherence, unknown_agent, E, A) :-
    event(E),
    agent(E, A),
    not character(A),
    A != unknown.

% --- Location must be known ---
% If an event happens at an undeclared location
violation(coherence, unknown_location, E, L) :-
    event(E),
    location(E, L),
    not location_entity(L),
    L != unknown.

% --- Patient should exist ---
% If an event acts on an unknown entity
violation(coherence, unknown_patient, E, P) :-
    event(E),
    patient(E, P),
    not character(P),
    not object(P),
    P != unknown.

% =============================================================================
% PART 2: LOCATION CONSISTENCY (Within Same Chapter)
% =============================================================================

% --- Extract event numbers for ordering ---
% Events are named like e1, e2, e3... or e0_1, e1_2 etc.
% We'll use string ordering as a proxy for temporal ordering

% Two events by the same agent at different locations in close succession
% This is a potential ubiquity issue (need very fast travel)
% Note: This is a weak signal since chapters can span time

% Track where each character is at each event
character_at(C, L, E) :-
    event(E),
    agent(E, C),
    location(E, L),
    L != unknown.

% Find cases where same character is at different locations in same chapter
% (This doesn't necessarily mean an error - they could have traveled)
% We flag it as a "check" not a definite violation
possible_location_change(C, L1, L2, E1, E2) :-
    character_at(C, L1, E1),
    character_at(C, L2, E2),
    L1 != L2,
    E1 != E2.

% =============================================================================
% PART 3: CAUSALITY CHECKS
% =============================================================================

% --- Dead characters shouldn't act ---
% If a character dies and then performs actions later
has_death_event(C) :-
    event(E),
    event_type(E, die),
    agent(E, C).

has_death_event(C) :-
    event(E),
    event_type(E, death),
    agent(E, C).

has_death_event(C) :-
    event(E),
    event_type(E, kill),
    patient(E, C).

has_death_event(C) :-
    event(E),
    event_type(E, murder),
    patient(E, C).

% Note: Without timestamps, we can't definitively say actions occur AFTER death
% This would require event ordering information

% --- Objects should be introduced before use ---
% Track if object is used as patient or instrument
object_used(O, E) :-
    event(E),
    patient(E, O),
    object(O).

% =============================================================================
% PART 4: CROSS-CHAPTER CONSISTENCY (Accumulated Facts)
% =============================================================================

% These rules work when facts from multiple chapters are accumulated

% --- Character consistency across chapters ---
% A character that appears should maintain consistent properties

% --- Resurrection detection ---
% If character died in earlier chapter but appears acting later
% Note: This requires facts to include chapter numbers

% =============================================================================
% PART 5: EVENT TYPE SPECIFIC RULES
% =============================================================================

% --- Movement events should have different start/end locations ---
% (When we have that information)

% --- Communication events need two characters ---
violation(coherence, solo_communication, E, Type) :-
    event(E),
    event_type(E, Type),
    is_communication_type(Type),
    agent(E, A),
    not has_second_party(E).

is_communication_type(talk).
is_communication_type(speak).
is_communication_type(conversation).
is_communication_type(dialogue).
is_communication_type(discuss).

has_second_party(E) :- patient(E, _).

% =============================================================================
% PART 6: SELF-REFERENTIAL VIOLATIONS
% =============================================================================

% --- Character can't be both agent and patient of same event (usually) ---
violation(coherence, self_action, E, C) :-
    event(E),
    agent(E, C),
    patient(E, C),
    not is_reflexive_action(E).

% Some actions are naturally reflexive
is_reflexive_action(E) :- event_type(E, think).
is_reflexive_action(E) :- event_type(E, sleep).
is_reflexive_action(E) :- event_type(E, wake).
is_reflexive_action(E) :- event_type(E, rest).
is_reflexive_action(E) :- event_type(E, hide).
is_reflexive_action(E) :- event_type(E, move).
is_reflexive_action(E) :- event_type(E, walk).
is_reflexive_action(E) :- event_type(E, run).

% =============================================================================
% OUTPUT CONTROL
% =============================================================================

#show violation/4.
#show possible_location_change/5.
