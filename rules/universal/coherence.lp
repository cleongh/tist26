% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - COHERENCE (v2.2)
%    =============================================
%
%    ERROR CATEGORY: COHERENCE
%    -------------------------
%    Per docs/ILASP_INTEGRATION.md:
%        "Dead agent acting, trait conflicts"
%
%    All violations produced by this file are in the COHERENCE category.
%    Violations are structured as: violation(coherence, TYPE, EVENT, ENTITY)
%
%    Default world assumptions for semantic/logical correctness.
%    These rules can be overridden by story-specific rules.
%
%    Per LOGIC_DESIGN.md Section 3.1:
%        Universal Rules are priority layer 3 (lowest priority).
%
%    VERSION 2.0: Uses time-indexed fluents, rule registration
%    VERSION 2.1: Phase Four - Appearance violations moved to appearance.lp
%    VERSION 2.2: Added ERROR CATEGORY documentation for consistency audit
%
%    COHERENCE VIOLATIONS PRODUCED:
%        - impossible_self_action: Character cannot be both agent and patient
%        - contradictory_state: Character cannot be in contradictory states
%        - solo_communication: Communication requires a recipient
%        - (appearance violations now in appearance.lp)
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
%
% Phase Three Updates:
%     - Presence contradiction now uses present_in_scene vs explicitly_absent
%     - NOT inferred from location gaps
%     - See narrative_state.lp for presence_contradiction/2
%
% =============================================================================

% Contradictory state pairs
are_contradictory_states(alive, dead).
are_contradictory_states(dead, alive).
are_contradictory_states(asleep, awake).
are_contradictory_states(awake, asleep).
% Phase Three: present/absent now handled via presence_contradiction in narrative_state.lp
% are_contradictory_states(present, absent).  % DEPRECATED: use presence_contradiction
% are_contradictory_states(absent, present).  % DEPRECATED: use presence_contradiction
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

% Communication types (require two parties when patient is specified)
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

% =============================================================================
% SPEECH ACT vs DIALOGUE DISTINCTION
% =============================================================================
%
% SPEECH ACTS: Communication without a specific addressee
%   - Announcements, speeches, muttering, thinking aloud
%   - These are VALID even without a patient
%
% DIALOGUE: Communication directed at a specific person
%   - Requires patient to be present/reachable
%   - Violation if patient is absent
%
% =============================================================================

% Speech act: talk event without explicit patient (monologue, narration, etc.)
is_speech_act(E) :- event_type(E, talk), not has_second_party(E).
is_speech_act(E) :- event_type(E, speak), not has_second_party(E).

% Exempt event types (never require a patient)
is_exempt_speech(E) :- event_type(E, shout).
is_exempt_speech(E) :- event_type(E, mutter).
is_exempt_speech(E) :- event_type(E, whisper), not has_second_party(E).
is_exempt_speech(E) :- event_type(E, yell).
is_exempt_speech(E) :- event_type(E, cry).
is_exempt_speech(E) :- event_type(E, scream).
is_exempt_speech(E) :- event_type(E, sing).
is_exempt_speech(E) :- event_type(E, chant).
is_exempt_speech(E) :- event_type(E, greet), not has_second_party(E).  % General greeting
is_exempt_speech(E) :- event_type(E, farewell), not has_second_party(E).

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

% =============================================================================
% SOLO COMMUNICATION VIOLATION (REFINED)
% =============================================================================
%
% This violation now fires ONLY for DIALOGUE (talk with explicit patient)
% where the patient is not reachable/present.
%
% DOES NOT fire for:
%   - Speech acts (talk without patient)
%   - Internal thoughts
%   - Public speeches
%   - Exempt speech types (shout, mutter, etc.)
%
% =============================================================================

% VIOLATION: Dialogue with absent/unreachable patient
% Only fires when there IS a patient but they cannot hear the communication
violation(coherence, solo_communication, E, Type) :-
    rule_active(coherence_solo_communication),
    event(E),
    event_type(E, Type),
    is_communication_type(Type),
    agent(E, Agent),
    patient(E, Patient),          % Must have explicit patient (this is dialogue)
    Agent != Patient,             % Not self-talk
    not is_internal_thought(E),
    not is_public_speech(E),
    not is_speech_act(E),
    not is_exempt_speech(E),
    not same_location_possible(Agent, Patient, E).  % Patient not reachable

% Same location check: characters could plausibly be in same place
% This is a permissive check - defaults to true if location info is missing
same_location_possible(A, P, E) :-
    event(E),
    agent(E, A),
    patient(E, P),
    location(E, L),          % Event has a location
    character(P).            % Patient exists as character (assume co-located if no contrary evidence)

% If no location info, assume same location is possible (no violation)
same_location_possible(A, P, E) :-
    event(E),
    agent(E, A),
    patient(E, P),
    not location(E, _).      % No location specified, assume valid
