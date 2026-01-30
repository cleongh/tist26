% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - COHERENCE (v2.0)
%    =============================================
%
%    Default world assumptions for semantic/logical correctness.
%    These rules can be overridden by story-specific rules.
%
%    Per LOGIC_DESIGN.md Section 3.1:
%        Universal Rules are priority layer 3 (lowest priority).
%
%    VERSION 2.0: Uses time-indexed fluents, rule registration
%
%    COHERENCE VIOLATIONS:
%        - Self-referential impossibilities
%        - Contradictory states
%        - Solo communication (talking to no one)
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(coherence_impossible_self_action, universal, "Character cannot be both agent and patient of non-reflexive action").
rule(coherence_contradictory_state, universal, "Character cannot be in contradictory states").
rule(coherence_solo_communication, universal, "Communication requires a recipient").

% =============================================================================
% SELF-REFERENTIAL IMPOSSIBILITIES
% =============================================================================

% Reflexive action types (agent can be own patient)
is_reflexive_action(E) :- event_type(E, think).
is_reflexive_action(E) :- event_type(E, sleep).
is_reflexive_action(E) :- event_type(E, wake).
is_reflexive_action(E) :- event_type(E, rest).
is_reflexive_action(E) :- event_type(E, hide).
is_reflexive_action(E) :- event_type(E, move).
is_reflexive_action(E) :- event_type(E, walk).
is_reflexive_action(E) :- event_type(E, run).
is_reflexive_action(E) :- event_type(E, dress).
is_reflexive_action(E) :- event_type(E, wash).
is_reflexive_action(E) :- event_type(E, travel).
is_reflexive_action(E) :- event_type(E, escape).
is_reflexive_action(E) :- event_type(E, leave).
is_reflexive_action(E) :- event_type(E, arrive).
is_reflexive_action(E) :- event_type(E, get_up).
is_reflexive_action(E) :- event_type(E, practice).
is_reflexive_action(E) :- event_type(E, discover).
is_reflexive_action(E) :- event_type(E, transform).
is_reflexive_action(E) :- event_type(E, break).
is_reflexive_action(E) :- event_type(E, loss).
is_reflexive_action(E) :- event_type(E, read).
is_reflexive_action(E) :- event_type(E, cry).
is_reflexive_action(E) :- event_type(E, bow).
is_reflexive_action(E) :- event_type(E, sing).
is_reflexive_action(E) :- event_type(E, die).
is_reflexive_action(E) :- event_type(E, dies).
is_reflexive_action(E) :- event_type(E, died).
is_reflexive_action(E) :- event_type(E, death).
is_reflexive_action(E) :- event_type(E, faint).
is_reflexive_action(E) :- event_type(E, collapse).
is_reflexive_action(E) :- event_type(E, fall).
is_reflexive_action(E) :- event_type(E, stumble).

% VIOLATION: Self as both agent and patient (non-reflexive action)
violation(coherence, impossible_self_action, E, C) :-
    rule_active(coherence_impossible_self_action),
    event(E),
    agent(E, C),
    patient(E, C),
    not is_reflexive_action(E).

% =============================================================================
% CONTRADICTORY STATES (Time-Indexed)
% =============================================================================

% Contradictory state pairs
are_contradictory_states(alive, dead).
are_contradictory_states(dead, alive).
are_contradictory_states(asleep, awake).
are_contradictory_states(awake, asleep).
are_contradictory_states(present, absent).
are_contradictory_states(absent, present).
are_contradictory_states(visible, invisible).
are_contradictory_states(invisible, visible).

% VIOLATION: Character in contradictory states at same time
% Uses time-indexed holds/2 from core.lp
violation(coherence, contradictory_state, C, pair(S1, S2)) :-
    rule_active(coherence_contradictory_state),
    character(C),
    holds(state(C, S1), T),
    holds(state(C, S2), T),
    S1 != S2,
    are_contradictory_states(S1, S2).

% Backward compatibility: also check atemporal character_state
violation(coherence, contradictory_state, C, pair(S1, S2)) :-
    rule_active(coherence_contradictory_state),
    character_state(C, S1),
    character_state(C, S2),
    S1 != S2,
    are_contradictory_states(S1, S2).

% =============================================================================
% COMMUNICATION VIOLATIONS
% =============================================================================

% Communication types (require two parties)
is_communication_type(talk).
is_communication_type(speak).
is_communication_type(conversation).
is_communication_type(dialogue).
is_communication_type(discuss).
is_communication_type(argue).
is_communication_type(negotiate).
is_communication_type(chat).

% Has second party
has_second_party(E) :- patient(E, _).

% Internal thoughts (don't need second party)
is_internal_thought(E) :- event_type(E, think).
is_internal_thought(E) :- event_type(E, ponder).
is_internal_thought(E) :- event_type(E, reflect).
is_internal_thought(E) :- event_type(E, realize).
is_internal_thought(E) :- event_type(E, wonder).
is_internal_thought(E) :- event_type(E, remember).
is_internal_thought(E) :- event_type(E, monologue).

% Public speeches (don't need specific patient)
is_public_speech(E) :- event_type(E, announce).
is_public_speech(E) :- event_type(E, speech).
is_public_speech(E) :- event_type(E, proclaim).
is_public_speech(E) :- event_type(E, declare).

% VIOLATION: Communication without recipient
violation(coherence, solo_communication, E, Type) :-
    rule_active(coherence_solo_communication),
    event(E),
    event_type(E, Type),
    is_communication_type(Type),
    agent(E, _),
    not has_second_party(E),
    not is_internal_thought(E),
    not is_public_speech(E).
