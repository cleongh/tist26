% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - CAUSALITY (v2.0)
%    =============================================
%
%    Default world assumptions for cause-and-effect relationships.
%    These rules can be overridden by story-specific rules.
%
%    Per LOGIC_DESIGN.md Section 3.1:
%        Universal Rules are priority layer 3 (lowest priority).
%        They apply unless overridden by learned or story rules.
%
%    VERSION 2.0: Uses time-indexed fluents from core.lp
%
%    CAUSALITY VIOLATIONS:
%        - Dead characters cannot act
%        - Cannot interact with dead characters
%        - Cannot give what you don't have
%        - Effects require causes
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(causality_dead_character_acting, universal, "Dead characters cannot perform actions").
rule(causality_interacting_with_dead, universal, "Cannot interact with dead characters").
rule(causality_give_without_having, universal, "Cannot give items you don't possess").
rule(causality_effect_without_cause, universal, "Reactions require triggering events").

% =============================================================================
% DEAD CHARACTER VIOLATIONS (Time-Indexed)
% =============================================================================

% Death event types are defined in core.lp (is_death_event/1)

% VIOLATION: Dead character performing action
% Uses time-indexed alive/2 from core.lp fluent system
violation(causality, dead_character_acting, E, C) :-
    rule_active(causality_dead_character_acting),
    event(E),
    event_time(E, T),
    agent(E, C),
    not alive(C, T),
    not is_death_event(E),
    not is_ghost(C),
    not is_undead(C).

% Backward compatibility: also check atemporal is_dead
violation(causality, dead_character_acting, E, C) :-
    rule_active(causality_dead_character_acting),
    event(E),
    agent(E, C),
    is_dead(C),
    not is_death_event(E),
    not is_ghost(C),
    not is_undead(C),
    not event_time(E, _).  % Only if no time-indexed version

% VIOLATION: Interacting with dead character  
% Cannot have a dead character as patient of interaction
violation(causality, interacting_with_dead, E, C) :-
    rule_active(causality_interacting_with_dead),
    event(E),
    event_time(E, T),
    patient(E, C),
    not alive(C, T),
    event_type(E, Type),
    is_interaction_type(Type),
    not is_death_event(E).

% Interaction types (require living/present participant)
is_interaction_type(talk).
is_interaction_type(speak).
is_interaction_type(greet).
is_interaction_type(hug).
is_interaction_type(kiss).
is_interaction_type(fight).
is_interaction_type(attack).
is_interaction_type(help).
is_interaction_type(save).

% =============================================================================
% GHOST/UNDEAD EXCEPTIONS
% =============================================================================

% Characters can be marked as ghosts/undead to exempt from death rules
% These predicates are set by story-specific rules
% is_ghost(C)   - Character is a ghost (can act while "dead")
% is_undead(C)  - Character is undead (can act while "dead")

% Ghosts are a story exception to dead_character_acting
story_exception(dead_character_acting, C) :- is_ghost(C).
story_exception(dead_character_acting, C) :- is_undead(C).

% =============================================================================
% POSSESSION VIOLATIONS (Time-Indexed)
% =============================================================================

% VIOLATION: Giving what you don't have
% Uses time-indexed carries/3 from core.lp
violation(causality, give_without_having, E, Item) :-
    rule_active(causality_give_without_having),
    event(E),
    event_type(E, give),
    event_time(E, T),
    agent(E, Giver),
    patient(E, Item),
    item(Item),
    not carries(Giver, Item, T).

% =============================================================================
% CAUSE-EFFECT VIOLATIONS
% =============================================================================

% Reaction types (require a triggering event)
is_reaction_type(react).
is_reaction_type(respond).
is_reaction_type(retaliate).
is_reaction_type(revenge).
is_reaction_type(counter).

% Has a triggering event (has a patient/target)
has_triggering_event(E) :- patient(E, _).

% VIOLATION: Reaction without cause
violation(causality, effect_without_cause, E, reaction) :-
    rule_active(causality_effect_without_cause),
    event(E),
    event_type(E, Type),
    is_reaction_type(Type),
    not has_triggering_event(E).

% =============================================================================
% UNINTRODUCED CHARACTER (Informational)
% =============================================================================

% Track when characters are first introduced (using time-indexed events)
first_introduced(C, T) :-
    event(E),
    event_time(E, T),
    agent(E, C),
    character(C),
    not earlier_appearance(C, T).

first_introduced(C, T) :-
    event(E),
    event_time(E, T),
    patient(E, C),
    character(C),
    not earlier_appearance(C, T).

earlier_appearance(C, T2) :-
    event(E1),
    event_time(E1, T1),
    agent(E1, C),
    T1 < T2.

earlier_appearance(C, T2) :-
    event(E1),
    event_time(E1, T1),
    patient(E1, C),
    T1 < T2.

% Note: Unintroduced character violations are informational only
% in many stories, characters can appear without formal introduction
