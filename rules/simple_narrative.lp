% =============================================================================
%
%    NARRATIVE CONSISTENCY RULES
%    ============================
%
%    Version: Phase Three (Narrative State Separation)
%    
%    Phase Three Changes:
%    - Integrates with narrative_state.lp for three-tier state model:
%        alive(C, T) → present_in_scene(C, T) → physically_at(C, L, T)
%    - Communication violations check scene presence, not physical location
%    - Dead character violations use the canonical rules in narrative_state.lp
%    - Deprecated present/absent character_state pairs (use presence_contradiction)
%
%    Violation Categories (aligned with theoretical framework):
%
%    a) CAUSALITY: Every story element must be properly caused. Events need
%       causes, and introduced elements should have narrative purpose 
%       (Chekhov's gun principle).
%
%    b) COHERENCE: Semantic correctness - things must make logical sense.
%       An orange can't be blue, a character can't be in two places at once.
%
%    c) TEMPORAL: Events must respect time ordering. Actions must be possible
%       within given time intervals. Dead characters can't act later.
%
%    d) LOCATION: Spatial correctness - actions must be possible given 
%       character positions. Can't grab something from another room.
%
%    e) EMOTIONAL: Characters must behave according to their emotions,
%       relationships, and established personality traits.
%
%    EXPECTED INPUT FACTS:
%    - character(id).
%    - location_entity(id).
%    - object(id).
%    - event(id).
%    - event_type(id, type).
%    - event_global(id, type, chapter).       % Global event with chapter number
%    - event_order(id, numeric_order).        % For cross-chapter event ordering
%    - event_source(id, source_text).         % Source text from chapter
%    - agent(id, character).
%    - patient(id, target).
%    - location(id, place).
%    - character_emotion(character, emotion).
%    - character_state(character, state).
%    - is_dead(character).                    % Accumulated across chapters
%    - event_emotion(event, emotion).
%    - previous_emotion(character, emotion).  % From prior chapters
%    - established_trait(character, trait).   % Accumulated character traits
%    - relationship(char1, char2, type).      % e.g., relationship(hero, villain, hostile)
%    - relationship_rule(subj, pred, obj, established_by).  % Dynamic story rules
%    - trait_rule(char, trait, established_by).             % Dynamic trait rules
%
%    VIOLATION OUTPUT FORMAT:
%    violation(category, type, event_or_entity, detail).
%
% =============================================================================


% =============================================================================
% CATEGORY A: CAUSALITY VIOLATIONS
% =============================================================================
% Every element must be properly caused; events need reasons to occur.

% --- Dead characters cannot perform actions (cross-chapter causality) ---
% A character who died in a previous chapter cannot be an agent later.
% Exception: Death events themselves are valid (dying is the character's final act).
%
% Phase Three Integration:
%     Uses alive/2 from narrative_state.lp when available.
%     Falls back to is_dead/1 for backward compatibility.
%     See narrative_state.lp for the canonical dead_character_acting violation.
%
% DISABLED: Generates FPs - deceased status in metadata doesn't mean dead in chapter
% violation(causality, dead_character_acting, E, C) :-
%     event(E),
%     agent(E, C),
%     is_dead(C),
%     not is_death_event(E).

% Death events are exempt - dying is a valid final action
is_death_event(E) :- event_type(E, die).
is_death_event(E) :- event_type(E, dies).
is_death_event(E) :- event_type(E, died).
is_death_event(E) :- event_type(E, death).
is_death_event(E) :- event_type(E, kill).  % Killing someone is valid even if killer dies after

% --- Dead characters cannot be interacted with (except posthumously or during death) ---
violation(causality, interacting_with_dead, E, C) :-
    event(E),
    patient(E, C),
    is_dead(C),
    not is_posthumous_action(E),
    not is_death_event(E).  % Exclude death events - victim is alive at moment of death

% Posthumous actions are valid (burial, remembering, mourning, etc.)
is_posthumous_action(E) :- event_type(E, burial).
is_posthumous_action(E) :- event_type(E, memorial).
is_posthumous_action(E) :- event_type(E, remember).
is_posthumous_action(E) :- event_type(E, remembering).
is_posthumous_action(E) :- event_type(E, mourning).
is_posthumous_action(E) :- event_type(E, funeral).
is_posthumous_action(E) :- event_type(E, tribute).
is_posthumous_action(E) :- event_type(E, talk_about).

% --- Unintroduced character acting (Chekhov's gun inverse) ---
% If a character acts but was never properly introduced, flag it
violation(causality, unintroduced_character, E, C) :-
    event(E),
    agent(E, C),
    not character(C),
    C != unknown.

% --- Effect without cause ---
% Reactions or responses without a triggering event
violation(causality, effect_without_cause, E, reaction) :-
    event(E),
    event_type(E, Type),
    is_reaction_type(Type),
    not has_triggering_event(E).

is_reaction_type(react).
is_reaction_type(respond).
is_reaction_type(retaliate).
is_reaction_type(revenge).

has_triggering_event(E) :- patient(E, _).  % Has a target suggests prior cause


% =============================================================================
% CATEGORY B: BASIC COHERENCE VIOLATIONS
% =============================================================================
% Semantic correctness - things must make logical sense.

% --- Unknown entities ---
% NOTE: unknown_agent removed - redundant with unintroduced_character in causality
% NOTE: unknown_patient removed - too strict, flags minor characters like "cat"
% NOTE: unknown_location kept but made informational

% Location should be declared (informational, not a hard violation)
% violation(coherence, unknown_location, E, L) :-
%     event(E),
%     location(E, L),
%     not location_entity(L),
%     L != unknown.

% --- Self-referential impossibilities ---
% Character can't be both agent and patient (except reflexive actions)
violation(coherence, impossible_self_action, E, C) :-
    event(E),
    agent(E, C),
    patient(E, C),
    not is_reflexive_action(E).

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
% Extended reflexive actions - common self-directed events from LLM extraction
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
is_reflexive_action(E) :- event_type(E, detention).
is_reflexive_action(E) :- event_type(E, read).
is_reflexive_action(E) :- event_type(E, cry).
is_reflexive_action(E) :- event_type(E, accident).
is_reflexive_action(E) :- event_type(E, disturbance).
is_reflexive_action(E) :- event_type(E, bow).
is_reflexive_action(E) :- event_type(E, sing).
% Death events are self-directed (the dying character is the agent)
is_reflexive_action(E) :- event_type(E, die).
is_reflexive_action(E) :- event_type(E, dies).
is_reflexive_action(E) :- event_type(E, died).
is_reflexive_action(E) :- event_type(E, death).
is_reflexive_action(E) :- event_type(E, faint).
is_reflexive_action(E) :- event_type(E, collapse).
is_reflexive_action(E) :- event_type(E, fall).
is_reflexive_action(E) :- event_type(E, stumble).
% Phase 3: Refined event types - posture and consciousness changes are reflexive
is_reflexive_action(E) :- event_type(E, sit).
is_reflexive_action(E) :- event_type(E, sit_down).
is_reflexive_action(E) :- event_type(E, stand).
is_reflexive_action(E) :- event_type(E, stand_up).
is_reflexive_action(E) :- event_type(E, lie_down).
is_reflexive_action(E) :- event_type(E, lie).
is_reflexive_action(E) :- event_type(E, recline).
is_reflexive_action(E) :- event_type(E, wake_up).
is_reflexive_action(E) :- event_type(E, awaken).
is_reflexive_action(E) :- event_type(E, fall_asleep).
is_reflexive_action(E) :- event_type(E, doze).
is_reflexive_action(E) :- event_type(E, nap).
is_reflexive_action(E) :- event_type(E, rise).
% Phase 3: Refined movement types are reflexive
is_reflexive_action(E) :- event_type(E, enter).
is_reflexive_action(E) :- event_type(E, exit).

% --- Communication requires two parties (except internal thoughts and public speeches) ---
%
% Phase Three Integration:
%     Communication requires present_in_scene for BOTH parties.
%     Does NOT require physically_at (talking without location is VALID).
%     See narrative_state.lp for is_scene_action/1 classification.
%
violation(coherence, solo_communication, E, Type) :-
    event(E),
    event_type(E, Type),
    is_communication_type(Type),
    agent(E, _),
    not has_second_party(E),
    not is_internal_thought(E),
    not is_public_speech(E).

% Phase Three: Communication violation when parties aren't in the same scene
% This checks scene presence, not physical co-location
violation(coherence, communication_absent_party, E, Patient) :-
    event(E),
    event_type(E, Type),
    is_communication_type(Type),
    agent(E, Agent),
    patient(E, Patient),
    event_time(E, T),
    present_in_scene(Agent, T),
    explicitly_absent(Patient, T),
    not is_remote_action(E).

is_communication_type(talk).
is_communication_type(speak).
is_communication_type(conversation).
is_communication_type(dialogue).
is_communication_type(discuss).
is_communication_type(argue).
is_communication_type(negotiate).
is_communication_type(chat).

has_second_party(E) :- patient(E, _).

% Internal thoughts don't require a second party
is_internal_thought(E) :- event_type(E, think).
is_internal_thought(E) :- event_type(E, ponder).
is_internal_thought(E) :- event_type(E, reflect).
is_internal_thought(E) :- event_type(E, realize).
is_internal_thought(E) :- event_type(E, wonder).
is_internal_thought(E) :- event_type(E, remember).
is_internal_thought(E) :- event_type(E, monologue).

% Public speeches/announcements don't require specific patient
% (speaking to a crowd, making an announcement, etc.)
is_public_speech(E) :- event_type(E, announce).
is_public_speech(E) :- event_type(E, speech).
is_public_speech(E) :- event_type(E, proclaim).
is_public_speech(E) :- event_type(E, declare).
is_public_speech(E) :- agent(E, sorting_hat).  % Sorting hat sings/talks to crowd
is_public_speech(E) :- agent(E, A), is_authority_figure(A), not has_second_party(E).

% Authority figures often address crowds
is_authority_figure(professor_mcgonagall).
is_authority_figure(mcgonagall).
is_authority_figure(albus_dumbledore).
is_authority_figure(dumbledore).
is_authority_figure(snape).
is_authority_figure(professor_snape).
is_authority_figure(hagrid).

% Hogwarts ghosts often address crowds or talk generally
is_authority_figure(fat_friar).
is_authority_figure(nearly_headless_nick).
is_authority_figure(bloody_baron).
is_authority_figure(grey_lady).
is_authority_figure(peeves).  % Poltergeist, shouts at people

% Adults who may talk on phones, to themselves, or make announcements
% Use canonical IDs (uncle_vernon, aunt_petunia) - aliases like mr_dursley 
% are resolved via CHARACTER_ALIASES in event_executor.py
is_authority_figure(uncle_vernon).
is_authority_figure(aunt_petunia).

% Main characters who may talk to animals, themselves, or think aloud
is_authority_figure(harry_potter).
is_authority_figure(harry).

% --- Physical state contradictions ---
% Character cannot be in contradictory states simultaneously WITHIN THE SAME CHAPTER.
% NOTE: This rule should only trigger for facts from current chapter, not cross-chapter.
% States like present/absent are chapter-specific and reset each chapter.
% Only truly persistent states (dead/alive) should be tracked cross-chapter.
%
% Phase 3 Update: Posture and consciousness state conflicts are now handled 
% in core.lp via posture_conflict and consciousness_conflict violations.
% This rule is kept for backward compatibility with legacy state facts.
violation(coherence, contradictory_state, C, pair(S1, S2)) :-
    current_chapter_state(C, S1),
    current_chapter_state(C, S2),
    S1 != S2,
    are_contradictory_states(S1, S2).

% Alternative: Use character_state for within-chapter checks only
% (Cross-chapter state should use is_dead/1 predicate instead)
% Fallback for backward compatibility:
violation(coherence, contradictory_state, C, pair(S1, S2)) :-
    character_state(C, S1),
    character_state(C, S2),
    S1 != S2,
    are_persistent_contradictory_states(S1, S2).

% Only truly incompatible persistent states
are_persistent_contradictory_states(alive, dead).
are_persistent_contradictory_states(dead, alive).

% Phase 3: Refined contradictory states
% Posture conflicts (seated vs lying vs standing)
are_contradictory_states(seated, lying).
are_contradictory_states(lying, seated).
are_contradictory_states(seated, standing).
are_contradictory_states(standing, seated).
are_contradictory_states(lying, standing).
are_contradictory_states(standing, lying).

% Consciousness conflicts
are_contradictory_states(asleep, awake).
are_contradictory_states(awake, asleep).

% Life/death conflicts
are_contradictory_states(alive, dead).
are_contradictory_states(dead, alive).

% Presence conflicts (legacy - deprecated in Phase Three)
% NOTE: For Phase Three, use presence_contradiction/2 from narrative_state.lp instead.
% This pair is kept for backward compatibility with legacy character_state facts.
% New code should NOT use present/absent as character_state values.
are_contradictory_states(present, absent).
are_contradictory_states(absent, present).

% Visibility conflicts
are_contradictory_states(visible, invisible).
are_contradictory_states(invisible, visible).


% =============================================================================
% CATEGORY C: TEMPORAL ORDER VIOLATIONS (Phase One Refactor)
% =============================================================================
%
% NOTE: Main temporal violation rules are now in rules/universal/temporal.lp
%
% This section contains:
%   - Event ordering helpers (for cross-chapter sequencing)
%   - Death tracking (for causality violations)
%   - Contradictory state definitions (used by temporal.lp)
%
% PHASE ONE CHANGES:
%   - Temporal violations now require EXPLICIT state assertions
%   - Assumed/persisted states cannot trigger violations
%   - See temporal.lp for explicit_state vs assumed_state framework
%
% =============================================================================

% --- Global Event Ordering ---
% Derive time_order from event_order for cross-chapter event sequencing
time_order(E1, E2) :-
    event_order(E1, N1),
    event_order(E2, N2),
    N1 < N2.

% --- Death types for tracking ---
is_death_type(die).
is_death_type(dies).
is_death_type(died).
is_death_type(death).
is_death_type(kill).
is_death_type(killed).
is_death_type(murder).
is_death_type(execute).
is_death_type(execution).

% Track death events in current chapter (explicit evidence)
has_death_event(C) :-
    event(E),
    event_type(E, Type),
    is_death_type(Type),
    agent(E, C).

has_death_event(C) :-
    event(E),
    event_type(E, Type),
    is_death_type(Type),
    patient(E, C).

% Inherit is_dead from has_death_event (for same-chapter detection)
% This is EXPLICIT: death was witnessed in an event
is_dead(C) :- has_death_event(C).

% --- Explicit Death State for Temporal Rules ---
% Links death events to the explicit_state framework in temporal.lp
explicit_death_event(C, E, T) :-
    event(E),
    event_time(E, T),
    event_type(E, Type),
    is_death_type(Type),
    patient(E, C).

explicit_death_event(C, E, T) :-
    event(E),
    event_time(E, T),
    event_type(E, Type),
    is_death_type(Type),
    agent(E, C),
    Type = die.

explicit_death_event(C, E, T) :-
    event(E),
    event_time(E, T),
    event_type(E, Type),
    is_death_type(Type),
    agent(E, C),
    Type = dies.

% NOTE: Simultaneous contradictory action violations are now in temporal.lp
% using the explicit_state framework


% =============================================================================
% CATEGORY D: LOCATION CORRECTNESS VIOLATIONS  
% =============================================================================
% Locations and distances must be correct for actions to be possible.
%
% Phase Three Integration:
%     Location violations use physically_at/3 from narrative_state.lp.
%     A character can be present_in_scene without physically_at.
%     Talking without a location is VALID (scene-only action).
%     Physical actions (grab, fight) require physically_at co-location.
%
% NOTE: Main location violation rules are now in rules/universal/location.lp
%       This section provides helper predicates and legacy compatibility.
%
% NOTE: Without timestamps, we cannot reliably detect ubiquity (being in two
% places at once) since characters legitimately move during a chapter.

% --- Track character locations (informational) ---
character_at(C, L, E) :-
    event(E),
    agent(E, C),
    location(E, L),
    L != unknown.

% --- Ubiquity detection via explicit_state ---
% Now handled in temporal.lp using explicit_state framework.
% Only fires when two EXPLICIT location assertions overlap in time.

% --- Co-location tracking (informational only, not a violation) ---
% Tracks when interactions happen across locations - useful for analysis
possible_remote_interaction(E, Agent, Patient) :-
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    character(Patient),
    location(E, L1),
    character_at(Patient, L2, _),
    L1 != L2,
    L1 != unknown,
    L2 != unknown,
    not is_remote_action(E).

% Some actions can be done remotely
is_remote_action(E) :- event_type(E, call).
is_remote_action(E) :- event_type(E, phone).
is_remote_action(E) :- event_type(E, message).
is_remote_action(E) :- event_type(E, letter).
is_remote_action(E) :- event_type(E, telepathy).
is_remote_action(E) :- event_type(E, telekinesis).
is_remote_action(E) :- event_type(E, curse).

% Track travel events for location change analysis
% Phase 3: Include refined movement event types
is_travel_event(E) :- event_type(E, travel).
is_travel_event(E) :- event_type(E, walk).
is_travel_event(E) :- event_type(E, run).
is_travel_event(E) :- event_type(E, go).
is_travel_event(E) :- event_type(E, move).
is_travel_event(E) :- event_type(E, fly).
is_travel_event(E) :- event_type(E, drive).
is_travel_event(E) :- event_type(E, apparate).
is_travel_event(E) :- event_type(E, enter).    % Phase 3: entering a location
is_travel_event(E) :- event_type(E, exit).     % Phase 3: exiting a location
is_travel_event(E) :- event_type(E, teleport). % Phase 3: teleportation

% --- Unreachable location detection ---
% Track reachability through connected locations
reachable(L1, L2) :- connected(L1, L2).
reachable(L1, L2) :- connected(L2, L1).  % Bidirectional
reachable(L1, L3) :- reachable(L1, L2), connected(L2, L3).
reachable(L1, L3) :- reachable(L1, L2), connected(L3, L2).  % Bidirectional

% Contains implies connectivity (can move from container to contained)
reachable(L1, L2) :- contains(L1, L2).
reachable(L2, L1) :- contains(L1, L2).

% Check if we have any connectivity info at all
has_connectivity_info :- connected(_, _).
has_connectivity_info :- contains(_, _).

% Track which locations are part of the known connectivity graph
% (only these should be checked for reachability)
in_location_graph(L) :- connected(L, _).
in_location_graph(L) :- connected(_, L).
in_location_graph(L) :- contains(L, _).
in_location_graph(L) :- contains(_, L).

% =============================================================================
% CATEGORY D-2: LOCATION CONTINUITY (Refined)
% =============================================================================
%
% GOAL: Detect impossible travel while allowing implicit narrative transitions.
%
% KEY INSIGHT: In narrative, time advances implicitly between events.
%   - e1: Harry at station (time 5)
%   - e2: Harry at platform (time 7)
%   This is VALID - Harry could have walked there between events.
%
% VIOLATION should only fire when:
%   1. SAME character is at two locations in CONSECUTIVE events (no time gap)
%   2. Those locations are unreachable from each other
%   3. No travel/transport event intervenes
%
% =============================================================================

% --- Implicit Transition Detection ---
% Events allow implicit movement when there's a time gap between them
% (narrative implicitly advances time and location)
allows_implicit_transition(E1, E2) :-
    event_time(E1, T1),
    event_time(E2, T2),
    T2 > T1.  % Any time progression allows implicit travel

% Fallback: If no event_time, use event_order gaps
allows_implicit_transition(E1, E2) :-
    event_order(E1, N1),
    event_order(E2, N2),
    N2 > N1 + 1,  % Non-consecutive events allow implicit travel
    not event_time(E1, _),
    not event_time(E2, _).

% --- Per-Character Location Tracking ---
% Track previous location for the SAME character, not just any event
previous_character_location(C, E2, L1, E1) :-
    agent(E1, C),
    agent(E2, C),
    location(E1, L1),
    time_order(E1, E2),
    L1 != unknown,
    not has_intervening_event(C, E1, E2).

% Helper: Character has an event between E1 and E2
has_intervening_event(C, E1, E2) :-
    agent(E1, C),
    agent(E2, C),
    agent(E_mid, C),
    time_order(E1, E_mid),
    time_order(E_mid, E2),
    E1 != E_mid,
    E_mid != E2.

% --- VIOLATION: Unreachable Location (Refined) ---
% Fires ONLY when:
%   - Same character moves between events
%   - Events are consecutive for that character (no intervening events)
%   - Events do NOT allow implicit transition (simultaneous or very close)
%   - Locations are in same subgraph but not reachable
%
violation(location, unreachable_location, E2, pair(PrevLoc, CurrentLoc)) :-
    event(E2),
    agent(E2, C),
    location(E2, CurrentLoc),
    previous_character_location(C, E2, PrevLoc, E1),
    CurrentLoc != PrevLoc,
    CurrentLoc != unknown,
    PrevLoc != unknown,
    same_location_subgraph(PrevLoc, CurrentLoc),
    not reachable(PrevLoc, CurrentLoc),
    not allows_implicit_transition(E1, E2),
    not is_travel_exempt(E2).

% Two locations are in the same subgraph if they're connected (directly or transitively)
same_location_subgraph(L1, L2) :- reachable(L1, L2).
same_location_subgraph(L1, L2) :- reachable(L2, L1).

% Travel/transport events are exempt (car trips, walks, journeys between areas)
is_travel_exempt(E) :- event_type(E, teleport).
is_travel_exempt(E) :- event_type(E, apparate).
is_travel_exempt(E) :- event_type(E, transport).
is_travel_exempt(E) :- event_type(E, fly).
is_travel_exempt(E) :- event_type(E, travel).
is_travel_exempt(E) :- event_type(E, drive).
is_travel_exempt(E) :- event_type(E, walk).
is_travel_exempt(E) :- event_type(E, journey).
% "arrive" at a new area implies travel happened (car trip, walk, etc.)
is_travel_exempt(E) :- event_type(E, arrive).
is_travel_exempt(E) :- event_type(E, leave).  % Leaving for another area
is_travel_exempt(E) :- event_type(E, enter).  % Entering a new location
is_travel_exempt(E) :- event_type(E, exit).   % Exiting current location
is_travel_exempt(E) :- event_type(E, move).   % Generic movement

% Movement within the same container is coherent (not teleportation)
% e.g., kitchen → hallway within "house" is exempt from reachability checks
is_travel_exempt(E) :-
    event(E),
    agent(E, C),
    location(E, CurrentLoc),
    previous_character_location(C, E, PrevLoc, _),
    CurrentLoc != PrevLoc,
    travel_within_container(PrevLoc, CurrentLoc).


% =============================================================================
% CATEGORY E: EMOTIONAL RELATIONS VIOLATIONS
% =============================================================================
%
% Phase Five: Evidence-Gated Emotional Violations
%
% IMPORTANT: Main emotional violation rules are now in rules/universal/emotional.lp
%            These require explicit relationship evidence before firing.
%
% The rules below are DEPRECATED in favor of:
%   - emotional.lp: relationship_action_mismatch (evidence-gated)
%   - emotional.lp: trait_action_mismatch (evidence-gated)
%   - emotional.lp: unexplained_relationship_change
%
% Phase Five Requirements Met:
%   1. Violations fire ONLY when relationship is explicitly established BEFORE event
%   2. No violations when relationship data is missing or first interaction
%   3. Relationship changes require explicit events
%   4. All violations include triggering event ID and relationship state
%
% =============================================================================

% --- Emotional contradiction with previous chapter ---
% Character shows opposite emotion from established pattern
% NOTE: This remains as it uses cross-chapter previous_emotion tracking
violation(emotional, emotional_contradiction, C, pair(Current, Previous)) :-
    character_emotion(C, Current),
    previous_emotion(C, Previous),
    is_opposite_emotion(Current, Previous).

% --- Trait contradiction ---
% Character behaves opposite to established personality trait
% NOTE: Phase Five moves this to emotional.lp with evidence-gating
% This rule is kept for backward compatibility with previous_emotion
violation(emotional, trait_contradiction, C, pair(Current, Trait)) :-
    character_emotion(C, Current),
    established_trait(C, Trait),
    is_opposite_emotion(Current, Trait).

% --- Relationship-behavior mismatch ---
% DEPRECATED in Phase Five: Use emotional.lp relationship_action_mismatch instead.
% This rule uses atemporal relationship/3 which doesn't track evidence.
% Kept commented for reference.
%
% violation(emotional, relationship_behavior_mismatch, E, pair(Agent, Patient)) :-
%     event(E),
%     agent(E, Agent),
%     patient(E, Patient),
%     event_emotion(E, Emotion),
%     relationship(Agent, Patient, RelType),
%     is_contrary_to_relationship(Emotion, RelType).

% If you love someone, you shouldn't be hostile to them (unexplained)
is_contrary_to_relationship(hostile, love).
is_contrary_to_relationship(nasty, love).
is_contrary_to_relationship(cruel, love).
is_contrary_to_relationship(violent, love).
is_contrary_to_relationship(angry, love).

% If you hate someone, being kind is suspicious
is_contrary_to_relationship(kind, hate).
is_contrary_to_relationship(warm, hate).
is_contrary_to_relationship(friendly, hate).
is_contrary_to_relationship(loving, hate).

% Hostile relationships
is_contrary_to_relationship(kind, hostile).
is_contrary_to_relationship(warm, hostile).
is_contrary_to_relationship(friendly, hostile).
is_contrary_to_relationship(loving, hostile).

% Friendly relationships
is_contrary_to_relationship(hostile, friendly).
is_contrary_to_relationship(nasty, friendly).
is_contrary_to_relationship(cruel, friendly).
is_contrary_to_relationship(violent, friendly).

% --- Opposite emotion pairs ---
is_opposite_emotion(happy, sad).
is_opposite_emotion(sad, happy).
is_opposite_emotion(kind, nasty).
is_opposite_emotion(nasty, kind).
is_opposite_emotion(kind, cruel).
is_opposite_emotion(cruel, kind).
is_opposite_emotion(angry, calm).
is_opposite_emotion(calm, angry).
is_opposite_emotion(friendly, hostile).
is_opposite_emotion(hostile, friendly).
is_opposite_emotion(warm, cold).
is_opposite_emotion(cold, warm).
is_opposite_emotion(loving, hateful).
is_opposite_emotion(hateful, loving).
is_opposite_emotion(brave, cowardly).
is_opposite_emotion(cowardly, brave).
is_opposite_emotion(generous, selfish).
is_opposite_emotion(selfish, generous).

% --- Unmotivated hostile action ---
% DEPRECATED in Phase Five: Use emotional.lp relationship_action_mismatch instead.
% This rule fired without checking if relationship was established BEFORE event.
% Kept commented for reference.
%
% violation(emotional, unmotivated_hostility, E, pair(Agent, Patient)) :-
%     event(E),
%     agent(E, Agent),
%     patient(E, Patient),
%     event_type(E, Type),
%     is_hostile_action(Type),
%     relationship(Agent, Patient, RelType),
%     not is_hostile_relationship(RelType),
%     not has_recent_conflict(Agent, Patient).

is_hostile_action(attack).
is_hostile_action(fight).
is_hostile_action(hit).
is_hostile_action(curse).
is_hostile_action(insult).
is_hostile_action(betray).
is_hostile_action(kill).
is_hostile_action(hurt).
is_hostile_action(threaten).
is_hostile_action(steal).
is_hostile_action(deceive).

is_hostile_relationship(hostile).
is_hostile_relationship(enemy).
is_hostile_relationship(rival).
is_hostile_relationship(hate).

has_recent_conflict(A, B) :- conflict_event(A, B, _).


% =============================================================================
% CATEGORY F: RELATIONSHIP-BASED VIOLATIONS (Phase Five Update)
% =============================================================================
%
% DEPRECATED in Phase Five: Most relationship violations have moved to emotional.lp
%                           with proper evidence-gating.
%
% The new emotional.lp violations:
%   - Fire ONLY when relationship is explicitly established BEFORE the event
%   - Include triggering event ID and relationship state at that time
%   - Skip first interactions between characters
%
% =============================================================================

% --- Harmful actions classification ---
% (Kept for backward compatibility with other rules)
is_harmful_action(kill).
is_harmful_action(attack).
is_harmful_action(hurt).
is_harmful_action(betray).
is_harmful_action(abandon).
is_harmful_action(steal).
is_harmful_action(deceive).
is_harmful_action(threaten).
is_harmful_action(curse).
is_harmful_action(poison).

% --- Helpful actions classification ---
is_helpful_action(help).
is_helpful_action(save).
is_helpful_action(protect).
is_helpful_action(give).
is_helpful_action(heal).
is_helpful_action(rescue).
is_helpful_action(comfort).
is_helpful_action(defend).
is_helpful_action(support).

% --- Harming a loved one (without justification) ---
% DEPRECATED in Phase Five: Use emotional.lp relationship_action_mismatch instead.
% Kept commented for reference.
%
% violation(emotional, harm_loved_one, E, pair(Agent, Patient)) :-
%     event(E),
%     agent(E, Agent),
%     patient(E, Patient),
%     event_type(E, Type),
%     is_harmful_action(Type),
%     relationship(Agent, Patient, RelType),
%     is_positive_relationship(RelType).

is_positive_relationship(love).
is_positive_relationship(friendly).
is_positive_relationship(family).
is_positive_relationship(ally).
is_positive_relationship(friend).

% --- Helping an enemy (unexplained) ---
% DEPRECATED in Phase Five: Use emotional.lp relationship_action_mismatch instead.
%
% violation(emotional, help_enemy, E, pair(Agent, Patient)) :-
%     event(E),
%     agent(E, Agent),
%     patient(E, Patient),
%     event_type(E, Type),
%     is_helpful_action(Type),
%     relationship(Agent, Patient, RelType),
%     is_hostile_relationship(RelType).

% --- Relationship consistency (cross-chapter) ---
% DEPRECATED in Phase Five: Use emotional.lp unexplained_relationship_change instead.
% The new rule requires an explicit event to change relationships.
%
% violation(emotional, relationship_flip, pair(C1, C2), pair(OldType, NewType)) :-
%     relationship(C1, C2, NewType),
%     previous_relationship(C1, C2, OldType),
%     is_relationship_flip(OldType, NewType).

% Relationship flips that are suspicious without explanation
is_relationship_flip(hostile, friendly).
is_relationship_flip(hostile, love).
is_relationship_flip(hostile, family).  % Can't suddenly become family
is_relationship_flip(fear, love).
is_relationship_flip(hate, love).
is_relationship_flip(hate, friendly).


% =============================================================================
% OUTPUT CONTROL
% =============================================================================

#show violation/4.
% Informational tracking (not violations, but useful for analysis)
% #show possible_remote_interaction/3.
% #show character_at/3.
