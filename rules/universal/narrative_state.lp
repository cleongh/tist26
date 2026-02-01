% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - NARRATIVE STATE (v1.1)
%    ==================================================================
%
%    ERROR CATEGORIES: CAUSALITY, COHERENCE
%    --------------------------------------
%    This file produces violations in multiple categories:
%        - CAUSALITY: Dead characters cannot act (cause-effect)
%        - COHERENCE: State contradictions (narrative consistency)
%
%    Per docs/ILASP_INTEGRATION.md:
%        Causality: "Effect without cause, broken causal chain"
%        Coherence: "Dead agent acting, trait conflicts"
%
%    Explicit narrative state predicates that separate:
%        - EXISTENCE: Whether a character is alive or dead
%        - SCENE PRESENCE: Whether a character is "in the scene" narratively
%        - PHYSICAL LOCATION: Where a character physically is in space
%
%    Per LOGIC_DESIGN.md Section 3.2:
%        Relations (Edges/Predicates) - Time-Indexed
%
%    VERSION 1.0 CHANGES (Phase Three):
%        - alive(Character, Time) - existence state
%        - present_in_scene(Character, Time) - narrative scene presence
%        - physically_at(Character, Location, Time) - spatial location
%        - Talking without location is valid
%        - Being alive but off-scene is valid
%        - Coherence violations reflect true contradictions, not missing data
%    VERSION 1.1: Added ERROR CATEGORY documentation for consistency audit
%
%    DESIGN PRINCIPLE:
%        These three states are INDEPENDENT:
%        - A character can be alive but not present_in_scene (off-camera)
%        - A character can be present_in_scene without physically_at (location unknown)
%        - A character with physically_at is automatically present_in_scene
%        - Dead characters cannot become present_in_scene
%
%    STATE HIERARCHY:
%        alive → can be present_in_scene → can have physically_at
%        (Each level requires the previous)
%
%    NARRATIVE STATE VIOLATIONS PRODUCED:
%        - narrative_dead_in_scene (Category: COHERENCE): Dead character in scene after death
%        - narrative_absent_acting (Category: COHERENCE): Explicitly absent character acting
%        - narrative_dead_acting (Category: CAUSALITY): Dead character performing action
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(narrative_dead_in_scene, universal, "Dead characters cannot appear in scene after death").
rule(narrative_absent_acting, universal, "Characters explicitly absent cannot act in scene").
rule(narrative_dead_acting, universal, "Dead characters cannot perform actions").


% =============================================================================
% PART A: EXISTENCE STATE - alive(Character, Time)
% =============================================================================
%
% alive(C, T) indicates a character exists and is alive at time T.
% This is derived from holds(alive(C), T) in core.lp.
%
% Death terminates alive status via:
%     terminates(E, alive(C)) :- is_death_event(E), dies_in_event(E, C).
%
% =============================================================================

% --- Bridge to core.lp ---
% alive/2 is already defined in core.lp via:
%     alive(C, T) :- holds(alive(C), T).
% We add explicit helpers here.

% Death time tracking
death_time(C, T) :-
    event(E),
    is_death_event(E),
    dies_in_event(E, C),
    event_time(E, T).

% Character was alive at time T but is dead after
was_alive(C, T) :- alive(C, T).
died_before(C, T) :- death_time(C, T_death), T_death < T.
died_at_or_before(C, T) :- death_time(C, T_death), T_death <= T.

% --- Death Event Classification ---
% Extended from simple_narrative.lp for completeness
is_death_event(E) :- event_type(E, die).
is_death_event(E) :- event_type(E, dies).
is_death_event(E) :- event_type(E, died).
is_death_event(E) :- event_type(E, death).
is_death_event(E) :- event_type(E, kill).
is_death_event(E) :- event_type(E, murder).
is_death_event(E) :- event_type(E, execute).
is_death_event(E) :- event_type(E, sacrifice).

% Who dies in a death event
dies_in_event(E, C) :- is_death_event(E), agent(E, C), event_type(E, Type), is_self_death(Type).
dies_in_event(E, C) :- is_death_event(E), patient(E, C), event_type(E, Type), is_kill_type(Type).

% Self-death types (agent dies)
is_self_death(die).
is_self_death(dies).
is_self_death(died).
is_self_death(death).
is_self_death(sacrifice).  % Self-sacrifice

% Kill types (patient dies)
is_kill_type(kill).
is_kill_type(murder).
is_kill_type(execute).

% If no patient in a kill event, agent may be the victim (suicide)
dies_in_event(E, C) :- 
    is_death_event(E), 
    agent(E, C), 
    event_type(E, Type), 
    is_kill_type(Type),
    not patient(E, _).


% =============================================================================
% PART B: SCENE PRESENCE - present_in_scene(Character, Time)
% =============================================================================
%
% present_in_scene(C, T) indicates a character is "in the narrative scene"
% at time T. This is a NARRATIVE concept, not a PHYSICAL one.
%
% A character is present_in_scene if:
%     1. They are an agent or patient in an event at time T, OR
%     2. They are explicitly noted as present, OR
%     3. They have a physical location (physically_at) at time T
%
% CRITICAL: present_in_scene does NOT require a known location.
%           "Harry talked to Ron" is valid even if no location is specified.
%
% =============================================================================

% --- Derived from Event Participation ---
% If a character participates in an event, they are in the scene
present_in_scene(C, T) :-
    event(E),
    event_time(E, T),
    agent(E, C),
    character(C),
    alive(C, T).

present_in_scene(C, T) :-
    event(E),
    event_time(E, T),
    patient(E, C),
    character(C),
    alive(C, T).

% --- Derived from Physical Location ---
% If we know where a character physically is, they are in the scene
present_in_scene(C, T) :-
    physically_at(C, _, T),
    alive(C, T).

% --- Explicitly Declared Scene Presence ---
% Story can declare characters as present without specifying how
present_in_scene(C, T) :- 
    explicitly_present(C, T),
    alive(C, T).

% --- Explicit Absence ---
% Characters can be explicitly marked as absent from the scene
% explicitly_absent(Character, Time) is asserted by extraction
% This contradicts present_in_scene

% Helper: Is character explicitly absent?
is_explicitly_absent(C, T) :- explicitly_absent(C, T).


% =============================================================================
% PART C: PHYSICAL LOCATION - physically_at(Character, Location, Time)
% =============================================================================
%
% physically_at(C, L, T) indicates a character's physical location at time T.
% This is a SPATIAL concept separate from scene presence.
%
% A character has physically_at if:
%     1. An event explicitly places them at a location, OR
%     2. They are derived from explicit_presence (Phase Two)
%
% CRITICAL: A character can be present_in_scene WITHOUT physically_at.
%           Location violations only check physically_at.
%
% =============================================================================

% --- Bridge to Phase Two explicit_presence ---
% explicit_presence(Entity, Location, T, E) is defined in location.lp
% We convert it to physically_at
physically_at(C, L, T) :-
    explicit_presence(C, L, T, _),
    character(C),
    alive(C, T),
    L != unknown.

% --- From Event Location (if not already covered by explicit_presence) ---
physically_at(C, L, T) :-
    event(E),
    event_time(E, T),
    agent(E, C),
    event_location(E, L),
    character(C),
    alive(C, T),
    L != unknown.

physically_at(C, L, T) :-
    event(E),
    event_time(E, T),
    patient(E, C),
    event_location(E, L),
    character(C),
    alive(C, T),
    not is_movement_event(E),
    L != unknown.

% --- Explicitly Declared Physical Location ---
% Story can declare physical location directly
physically_at(C, L, T) :-
    declared_at(C, L, T),
    alive(C, T),
    L != unknown.


% =============================================================================
% PART D: SCENE INTERACTION REQUIREMENTS
% =============================================================================
%
% Different event types have different presence requirements:
%
% 1. SCENE ACTIONS (talk, interact, emote):
%    - Require present_in_scene only
%    - Do NOT require physically_at (location can be unknown)
%
% 2. LOCATION ACTIONS (travel, move, enter, exit):
%    - Require physically_at or at least destination
%    - Covered by location.lp
%
% 3. PHYSICAL ACTIONS (fight, grab, give):
%    - Require physically_at (need to be in same physical space)
%    - May require same_location check
%
% =============================================================================

% --- Scene Action Types (require present_in_scene, not physically_at) ---
is_scene_action(E) :- event_type(E, talk).
is_scene_action(E) :- event_type(E, speak).
is_scene_action(E) :- event_type(E, say).
is_scene_action(E) :- event_type(E, tell).
is_scene_action(E) :- event_type(E, ask).
is_scene_action(E) :- event_type(E, reply).
is_scene_action(E) :- event_type(E, answer).
is_scene_action(E) :- event_type(E, conversation).
is_scene_action(E) :- event_type(E, discuss).
is_scene_action(E) :- event_type(E, argue).
is_scene_action(E) :- event_type(E, negotiate).
is_scene_action(E) :- event_type(E, chat).
is_scene_action(E) :- event_type(E, whisper).
is_scene_action(E) :- event_type(E, shout).
is_scene_action(E) :- event_type(E, yell).
is_scene_action(E) :- event_type(E, laugh).
is_scene_action(E) :- event_type(E, cry).
is_scene_action(E) :- event_type(E, smile).
is_scene_action(E) :- event_type(E, frown).
is_scene_action(E) :- event_type(E, nod).
is_scene_action(E) :- event_type(E, wave).
is_scene_action(E) :- event_type(E, gesture).
is_scene_action(E) :- event_type(E, react).
is_scene_action(E) :- event_type(E, respond).
is_scene_action(E) :- event_type(E, greet).
is_scene_action(E) :- event_type(E, farewell).
is_scene_action(E) :- event_type(E, observe).
is_scene_action(E) :- event_type(E, watch).
is_scene_action(E) :- event_type(E, listen).
is_scene_action(E) :- event_type(E, notice).
is_scene_action(E) :- event_type(E, look).
is_scene_action(E) :- event_type(E, glance).
is_scene_action(E) :- event_type(E, stare).

% --- Emotional/Mental Actions (require present_in_scene for external, none for internal) ---
is_scene_action(E) :- event_type(E, show_emotion).
is_scene_action(E) :- event_type(E, express).
is_scene_action(E) :- event_type(E, display).

% Internal actions don't require scene presence (can happen anywhere)
is_internal_action(E) :- event_type(E, think).
is_internal_action(E) :- event_type(E, feel).
is_internal_action(E) :- event_type(E, realize).
is_internal_action(E) :- event_type(E, remember).
is_internal_action(E) :- event_type(E, wonder).
is_internal_action(E) :- event_type(E, dream).
is_internal_action(E) :- event_type(E, imagine).
is_internal_action(E) :- event_type(E, decide).
is_internal_action(E) :- event_type(E, plan).

% --- Physical Action Types (require physically_at and co-location) ---
is_physical_action(E) :- event_type(E, fight).
is_physical_action(E) :- event_type(E, attack).
is_physical_action(E) :- event_type(E, hit).
is_physical_action(E) :- event_type(E, punch).
is_physical_action(E) :- event_type(E, kick).
is_physical_action(E) :- event_type(E, grab).
is_physical_action(E) :- event_type(E, push).
is_physical_action(E) :- event_type(E, pull).
is_physical_action(E) :- event_type(E, carry).
is_physical_action(E) :- event_type(E, lift).
is_physical_action(E) :- event_type(E, drop).
is_physical_action(E) :- event_type(E, give).
is_physical_action(E) :- event_type(E, take).
is_physical_action(E) :- event_type(E, receive).
is_physical_action(E) :- event_type(E, touch).
is_physical_action(E) :- event_type(E, hug).
is_physical_action(E) :- event_type(E, kiss).
is_physical_action(E) :- event_type(E, shake_hands).


% =============================================================================
% PART E: NARRATIVE STATE VIOLATIONS
% =============================================================================

% --- VIOLATION: Dead Character in Scene ---
% A character who died cannot appear in the scene after death
% Exception: Flashbacks, memories, ghosts (story-specific override)
violation(narrative, dead_in_scene, 
          violation_info(C, died_at, T_death, but_present_at, T, in_event, E)) :-
    rule_active(narrative_dead_in_scene),
    event(E),
    event_time(E, T),
    agent(E, C),
    character(C),
    death_time(C, T_death),
    T_death < T,
    not is_posthumous_action(E),
    not allows_dead_appearance(C).

violation(narrative, dead_in_scene, 
          violation_info(C, died_at, T_death, but_present_at, T, in_event, E)) :-
    rule_active(narrative_dead_in_scene),
    event(E),
    event_time(E, T),
    patient(E, C),
    character(C),
    death_time(C, T_death),
    T_death < T,
    not is_posthumous_action(E),
    not allows_dead_appearance(C).

% Story can allow dead characters to appear (ghosts, flashbacks)
% allows_dead_appearance(Character) :- story_has_ghosts(Character).
% allows_dead_appearance(Character) :- story_has_flashbacks.

% --- VIOLATION: Explicitly Absent Character Acting ---
% A character marked as explicitly absent cannot act in the scene
violation(narrative, absent_acting,
          violation_info(C, explicitly_absent_at, T, but_acts_in, E)) :-
    rule_active(narrative_absent_acting),
    event(E),
    event_time(E, T),
    agent(E, C),
    character(C),
    is_explicitly_absent(C, T),
    not is_internal_action(E).  % Internal actions allowed while "absent" (still alive, thinking)

% --- VIOLATION: Dead Character Acting (Causality) ---
% Dead characters cannot perform actions (agent role after death)
% This is a CAUSALITY violation, not just a narrative one
violation(causality, dead_character_acting,
          violation_info(C, died_at, T_death, acts_at, T, in_event, E)) :-
    rule_active(narrative_dead_acting),
    event(E),
    event_time(E, T),
    agent(E, C),
    character(C),
    death_time(C, T_death),
    T_death < T,
    not is_death_event(E).


% =============================================================================
% PART F: PRESENCE CONTRADICTION RULES
% =============================================================================
%
% Contradictory presence means:
%     present_in_scene(C, T) AND explicitly_absent(C, T)
%
% NOT inferred from location gaps (character can be in scene without location).
%
% =============================================================================

% --- Contradictory Presence States ---
presence_contradiction(C, T) :-
    present_in_scene(C, T),
    is_explicitly_absent(C, T).

% VIOLATION: Character both present and explicitly absent at same time
violation(coherence, presence_contradiction,
          violation_info(C, both_present_and_absent_at, T)) :-
    presence_contradiction(C, T).


% =============================================================================
% PART G: QUERY HELPERS
% =============================================================================

% Characters in scene at a given time
characters_in_scene(T, C) :- present_in_scene(C, T).

% Characters at a specific location at a given time
characters_at_location(L, T, C) :- physically_at(C, L, T).

% Same scene (both characters present, don't need same physical location)
same_scene(C1, C2, T) :-
    present_in_scene(C1, T),
    present_in_scene(C2, T),
    C1 != C2.

% Same physical location
same_physical_location(C1, C2, L, T) :-
    physically_at(C1, L, T),
    physically_at(C2, L, T),
    C1 != C2.

% Character can interact with another (in scene, not necessarily co-located for scene actions)
can_interact_scene(C1, C2, T) :-
    same_scene(C1, C2, T),
    alive(C1, T),
    alive(C2, T).

% Character can interact physically (requires same physical location)
can_interact_physically(C1, C2, T) :-
    same_physical_location(C1, C2, _, T),
    alive(C1, T),
    alive(C2, T).


% =============================================================================
% SHOW DIRECTIVES
% =============================================================================

#show present_in_scene/2.
#show physically_at/3.
#show death_time/2.
#show presence_contradiction/2.
#show violation/4.
