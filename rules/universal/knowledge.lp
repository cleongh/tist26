% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - KNOWLEDGE (v1.0)
%    =============================================
%
%    ERROR CATEGORY: COHERENCE (knowledge-related)
%    ----------------------------------------------
%    Tracks knowledge acquisition and temporal knowledge state.
%    
%    Per LOGIC_DESIGN.md Section 3.1:
%        Universal Rules are priority layer 3 (lowest priority).
%        They apply unless overridden by learned or story rules.
%
%    FACTS CONSUMED:
%        - learned(Entity, Fact, Time): Entity learns Fact at Time
%        - learn_event(EventID): Marks an event as a knowledge acquisition event
%        - knowledge_source(EventID, SourceID): The source of the knowledge
%
%    FACTS PRODUCED:
%        - knows(Entity, Fact, Time): Entity knows Fact at time T >= learned time
%
%    KNOWLEDGE PROPERTIES:
%        - Monotonic: Once known, stays known unless explicitly contradicted
%        - Entity-scoped: Knowledge is private to the learning entity
%        - Evidence-based: No inference without explicit learn event
%
% =============================================================================

% --- Rule Registration ---
rule(knowledge_monotonic, universal, "Knowledge persists once acquired").
rule(knowledge_no_inference, universal, "Knowledge requires explicit learn events").

% =============================================================================
% PART A: TIME DOMAIN
% =============================================================================
% Ensure all learned times are valid time points
time(T) :- learned(_, _, T).

% =============================================================================
% PART B: KNOWLEDGE DERIVATION (MONOTONIC)
% =============================================================================

% An entity knows a fact at the exact time they learned it
knows(Entity, Fact, T) :-
    rule_active(knowledge_monotonic),
    learned(Entity, Fact, T),
    character(Entity).

% Knowledge persists: if entity knew fact at T, they still know it at T+1
% This implements monotonic knowledge (once known, stays known)
knows(Entity, Fact, T2) :-
    rule_active(knowledge_monotonic),
    knows(Entity, Fact, T1),
    T2 > T1,
    time(T2),
    character(Entity),
    % Guard against infinite grounding
    T2 - T1 <= 100.

% =============================================================================
% PART C: HELPER PREDICATES
% =============================================================================

% Identify characters who have learned something
has_knowledge(Entity) :-
    learned(Entity, _, _),
    character(Entity).

% Check if entity knew a fact before a specific time
knew_before(Entity, Fact, T) :-
    learned(Entity, Fact, LearnTime),
    time(T),
    LearnTime < T,
    character(Entity).

% First time an entity learned a specific fact
first_learned(Entity, Fact, T) :-
    learned(Entity, Fact, T),
    character(Entity),
    not knew_before(Entity, Fact, T).

% =============================================================================
% PART D: KNOWLEDGE SOURCE TRACKING
% =============================================================================

% Track who/what provided knowledge
informed_by(Entity, Fact, Source) :-
    learn_event(E),
    agent(E, Entity),
    event_type(E, learn),
    knowledge_source(E, Source),
    learned(Entity, Fact, _).

% =============================================================================
% PART E: QUERY HELPERS
% =============================================================================

% Query: Does entity know fact at current time?
% Usage: knows_now(Entity, Fact) where current_time(T) is the latest time
knows_now(Entity, Fact) :-
    knows(Entity, Fact, T),
    current_time(T).

% Define current time as the maximum time point
current_time(T) :-
    time(T),
    not exists_later_time(T).

exists_later_time(T) :-
    time(T),
    time(T2),
    T2 > T.

% =============================================================================
% PART F: NEGATIVE KNOWLEDGE CONSTRAINTS
% =============================================================================

% These rules ensure proper knowledge semantics but do not produce violations.
% Knowledge violations (e.g., acting on unknown information) would go here
% if needed in the future.

% Placeholder for future: violation when character acts on knowledge they don't have
% violation(coherence, acting_without_knowledge, E, C) :-
%     rule_active(knowledge_no_inference),
%     event(E),
%     requires_knowledge(E, Fact),
%     agent(E, C),
%     event_time(E, T),
%     not knows(C, Fact, T).

% =============================================================================
% PART G: COMPATIBILITY WITH EC FRAMEWORK
% =============================================================================

% Export knows/3 as a fluent for EC framework integration if needed
% holds(knows(Entity, Fact), T) :- knows(Entity, Fact, T).

