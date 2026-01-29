%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% ILASP Mode Declarations for Narrative Consistency Learning
%% ============================================================
%%
%% This file defines the hypothesis space for ILASP (Inductive Learning of
%% Answer Set Programs). It specifies what kinds of rules ILASP can learn.
%%
%% STRUCTURE:
%%   1. Type declarations (domain sorts)
%%   2. Mode declarations (what predicates can appear in hypotheses)
%%   3. Example weights and noise settings
%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%% === TYPE DECLARATIONS ===
%% Define the sorts (types) that constrain variables

#modeh(violation(causality, const(violation_type), var(event), const(detail), const(description))).
#modeh(violation(coherence, const(violation_type), var(event), const(detail), const(description))).
#modeh(violation(temporal, const(violation_type), var(event), const(detail), const(description))).
#modeh(violation(location, const(violation_type), var(event), const(detail), const(description))).
#modeh(violation(emotional, const(violation_type), var(event), const(detail), const(description))).

%% === FRAME AXIOMS ===
%% What persists unless explicitly changed

% Alive persists
#modeh(alive(var(character))).
#modeb(alive(var(character))).
#modeb(dead(var(character)), (negative)).  % Allow negated dead in body

% Dead persists (once dead, always dead)
#modeh(dead(var(character))).
#modeb(dead(var(character))).
#modeb(event_type(var(event), die)).
#modeb(event_type(var(event), kill)).
#modeb(agent(var(event), var(character))).
#modeb(patient(var(event), var(character))).

% Location persists
#modeh(at_location(var(character), var(location))).
#modeb(at_location(var(character), var(location))).
#modeb(at_location(var(character), var(location)), (negative)).  % Allow negated

% Ownership persists
#modeh(has(var(character), var(object))).
#modeb(has(var(character), var(object))).
#modeb(has(var(character), var(object)), (negative)).  % Allow negated

%% === ENTITY PREDICATES ===
%% Background knowledge about entities

#modeb(character(var(character))).
#modeb(object(var(object))).
#modeb(location_entity(var(location))).

%% === EVENT PREDICATES ===
%% What events can be referenced

#modeb(event(var(event))).
#modeb(event_type(var(event), const(event_type))).
#modeb(agent(var(event), var(character))).
#modeb(patient(var(event), var(character))).
#modeb(patient(var(event), var(object))).
#modeb(location(var(event), var(location))).
#modeb(before(var(event), var(event))).
#modeb(after(var(event), var(event))).

%% === RELATIONSHIP PREDICATES ===
%% Relationships between characters

#modeb(parent(var(character), var(character))).
#modeb(child(var(character), var(character))).
#modeb(sibling(var(character), var(character))).
#modeb(spouse(var(character), var(character))).
#modeb(friend(var(character), var(character))).
#modeb(enemy(var(character), var(character))).
#modeb(ally(var(character), var(character))).
#modeb(knows(var(character), var(character))).
#modeb(loves(var(character), var(character))).
#modeb(hates(var(character), var(character))).

%% === TRAIT PREDICATES ===
%% Character traits and capabilities

#modeb(trait(var(character), const(trait))).
#modeb(capable(var(character), const(action))).
#modeb(incapable(var(character), const(action))).

%% === STATE CHANGE PREDICATES ===
%% How events change state

#modeh(initiates(var(event), alive(var(character)))).
#modeh(terminates(var(event), alive(var(character)))).
#modeh(initiates(var(event), at_location(var(character), var(location)))).
#modeh(terminates(var(event), at_location(var(character), var(location)))).
#modeh(initiates(var(event), has(var(character), var(object)))).
#modeh(terminates(var(event), has(var(character), var(object)))).

%% === CAUSAL PREDICATES ===
%% What causes what

#modeb(causes(var(event), var(event))).
#modeb(precondition(var(event), const(fluent))).
#modeb(effect(var(event), const(fluent))).

%% === VIOLATION DETECTION ===
%% Rules for detecting violations

% Dead agent violation
#modeh(violation(coherence, dead_agent, var(event), var(detail), var(description))).
#modeb(dead(var(character))).
#modeb(agent(var(event), var(character))).

% Ubiquity violation (same person, two places, same time)
#modeh(violation(location, ubiquity, var(event), var(detail), var(description))).
#modeb(at_location(var(character), var(location1))).
#modeb(at_location(var(character), var(location2))).
#modeb(location1 != location2).

% Ownership violation
#modeh(violation(coherence, ownership, var(event), var(detail), var(description))).
#modeb(has(var(character1), var(object))).
#modeb(has(var(character2), var(object))).
#modeb(character1 != character2).

% Trait violation
#modeh(violation(coherence, trait_conflict, var(event), var(detail), var(description))).
#modeb(trait(var(character), const(trait))).
#modeb(event_type(var(event), const(action))).
#modeb(incompatible_trait_action(const(trait), const(action))).

%% === CONSTANTS ===
%% Define specific constant values

#constant(violation_type, dead_agent).
#constant(violation_type, ubiquity).
#constant(violation_type, ownership).
#constant(violation_type, trait_conflict).
#constant(violation_type, temporal_paradox).
#constant(violation_type, causality_break).
#constant(violation_type, emotional_shift).

#constant(event_type, die).
#constant(event_type, kill).
#constant(event_type, move).
#constant(event_type, take).
#constant(event_type, give).
#constant(event_type, drop).
#constant(event_type, speak).
#constant(event_type, see).
#constant(event_type, hear).
#constant(event_type, attack).
#constant(event_type, defend).
#constant(event_type, flee).
#constant(event_type, create).
#constant(event_type, destroy).

#constant(trait, blind).
#constant(trait, deaf).
#constant(trait, mute).
#constant(trait, paralyzed).
#constant(trait, immortal).
#constant(trait, mortal).
#constant(trait, magical).
#constant(trait, human).

%% === INCOMPATIBLE TRAIT-ACTION PAIRS ===
%% Background knowledge for trait violations

incompatible_trait_action(blind, see).
incompatible_trait_action(blind, look).
incompatible_trait_action(blind, observe).
incompatible_trait_action(blind, read).
incompatible_trait_action(blind, watch).
incompatible_trait_action(deaf, hear).
incompatible_trait_action(deaf, listen).
incompatible_trait_action(mute, speak).
incompatible_trait_action(mute, say).
incompatible_trait_action(mute, tell).
incompatible_trait_action(mute, shout).
incompatible_trait_action(mute, sing).
incompatible_trait_action(paralyzed, walk).
incompatible_trait_action(paralyzed, run).
incompatible_trait_action(paralyzed, move).
incompatible_trait_action(paralyzed, fight).
incompatible_trait_action(paralyzed, attack).

%% === BIAS SETTINGS ===
%% Control hypothesis space size
%% Note: These directives are handled via command-line options in ILASP4
%% --max-body-literals=5 (instead of #bias)
%% --max-variables=5 (instead of #maxv)
%% --noise=0.1 (instead of #noise_threshold)
