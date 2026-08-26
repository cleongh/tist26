% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - LOCATION (v3.1)
%    ==================================================================
%
%    ERROR CATEGORY: LOCATION
%    -------------------------
%    Per docs/ILASP_INTEGRATION.md:
%        "Ubiquity, impossible travel"
%
%    All violations produced by this file are in the LOCATION category.
%    Violations are structured as: violation(location, TYPE, EVENT, ENTITY)
%
%    Default world assumptions for spatial constraints.
%    These rules can be overridden by story-specific rules.
%
%    Per LOGIC_DESIGN.md Section 3.3:
%        NON-UBIQUITY: An entity cannot be present in more than one 
%        location at the same time.
%
%    VERSION 3.0 CHANGES (Phase Two):
%        - Presence is EVIDENCE-BASED, not continuous
%        - Characters can "disappear" from tracking without violation
%        - Containment hierarchy: contains(Parent, Child)
%        - Movement within containment chain is always allowed
%        - Movement across disjoint trees requires explicit travel/connection
%        - Non-ubiquity only fires on EXPLICIT presence facts
%        - No time-progression-based location inference
%    VERSION 3.1: Added ERROR CATEGORY documentation for consistency audit
%
%    DESIGN PRINCIPLE:
%        Presence is evidence, not state.
%        A character is present ONLY if:
%          a) An event explicitly places them there, OR
%          b) They are in a sub-location (containment hierarchy)
%        Missing location info is NOT a violation.
%
%    LOCATION VIOLATIONS PRODUCED:
%        - explicit_ubiquity: Entity cannot be explicitly at two disjoint locations simultaneously
%        - impossible_travel: Travel across disjoint containment trees requires explicit connection
%        - invalid_remote: Remote interaction requires remote action type
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(location_explicit_ubiquity, universal, "Entity cannot be explicitly at two disjoint locations simultaneously").
rule(location_impossible_travel, universal, "Travel across disjoint containment trees requires explicit connection").
rule(location_invalid_remote, universal, "Remote interaction requires remote action type").
rule(location_item_impossible_relocation, universal, "An item cannot move between disjoint locations without being carried by a traveling character").
rule(location_item_unreachable, universal, "An agent cannot physically interact with an item at a disjoint, uncarried location").


% =============================================================================
% PART A: CONTAINMENT HIERARCHY (Phase Two Core)
% =============================================================================
%
% contains(Parent, Child) - Child is inside Parent
%
% Examples:
%     contains(hogwarts, great_hall).
%     contains(hogwarts, gryffindor_tower).
%     contains(house, kitchen).
%     contains(house, living_room).
%     contains(diagon_alley, ollivanders).
%
% Containment is:
%     - Transitive: A contains B, B contains C → A contains C
%     - Asymmetric: A contains B → B does NOT contain A
%     - Acyclic: No loops in containment
%
% =============================================================================

% --- Transitive Containment ---
% If A contains B and B contains C, then A transitively contains C
contains_transitive(Parent, Child) :- contains(Parent, Child).
contains_transitive(Ancestor, Child) :- 
    contains(Ancestor, Intermediate),
    contains_transitive(Intermediate, Child).

% --- Containment Depth (for hierarchy queries) ---
% Depth 1 = direct containment
containment_depth(Parent, Child, 1) :- contains(Parent, Child).
containment_depth(Ancestor, Child, D+1) :-
    contains(Ancestor, Intermediate),
    containment_depth(Intermediate, Child, D),
    D < 10.  % Prevent infinite recursion

% --- Root Locations ---
% A location is a root if it is not contained in anything
root_location(L) :- 
    is_location(L), 
    not contains(_, L).

% --- Container of a Location ---
% Direct parent container
parent_container(Child, Parent) :- contains(Parent, Child).

% --- Same Containment Tree ---
% Two locations are in the same containment tree if they share a common ancestor
% or one contains the other
same_containment_tree(L1, L2) :- contains_transitive(L1, L2).
same_containment_tree(L1, L2) :- contains_transitive(L2, L1).
same_containment_tree(L1, L2) :- 
    contains_transitive(Ancestor, L1),
    contains_transitive(Ancestor, L2).
same_containment_tree(L, L) :- is_location(L).

% --- Disjoint Locations ---
% Two locations are disjoint if:
%   1. They are different
%   2. Neither contains the other (directly or transitively)
%   3. They don't share a common container
disjoint_locations(L1, L2) :-
    is_location(L1),
    is_location(L2),
    L1 != L2,
    not same_containment_tree(L1, L2),
    not connected(L1, L2).


% =============================================================================
% PART B: EXPLICIT PRESENCE (Evidence-Based)
% =============================================================================
%
% A character has EXPLICIT PRESENCE at a location only if:
%   1. An event explicitly places them there (explicit_presence_event)
%   2. They inherit presence from a sub-location (derived_container_presence)
%
% CRITICAL: We do NOT infer presence from time progression.
%           Characters can "disappear" between events without contradiction.
%
% =============================================================================

% --- Explicit Presence from Events ---
% A character is explicitly present if an event places them at a location
explicit_presence(Entity, Location, T, E) :-
    event(E),
    event_time(E, T),
    agent(E, Entity),
    event_location(E, Location),
    Location != unknown.

% Also from movement events with destination
explicit_presence(Entity, Location, T, E) :-
    event(E),
    event_time(E, T),
    is_movement_event(E),
    agent(E, Entity),
    event_destination(E, Location),
    Location != unknown.

% Patient presence (for non-movement events, patient is also at location)
explicit_presence(Entity, Location, T, E) :-
    event(E),
    event_time(E, T),
    patient(E, Entity),
    character(Entity),
    event_location(E, Location),
    Location != unknown,
    not is_movement_event(E).

% --- Derived Container Presence ---
% If a character is explicitly in a sub-location, they are implicitly in the container
% BUT this is NOT "explicit" - it won't trigger ubiquity violations
derived_container_presence(Entity, Container, T, E) :-
    explicit_presence(Entity, SubLocation, T, E),
    contains_transitive(Container, SubLocation).

% --- Any Presence Query ---
% For queries, presence includes both explicit and derived container
has_presence(Entity, Location, T) :-
    explicit_presence(Entity, Location, T, _).

has_presence(Entity, Location, T) :-
    derived_container_presence(Entity, Location, T, _).

% --- Explicit Presence Pair (for violation detection) ---
% Two explicit presence facts at the same time
explicit_presence_pair(Entity, L1, L2, T, E1, E2) :-
    explicit_presence(Entity, L1, T, E1),
    explicit_presence(Entity, L2, T, E2),
    L1 != L2,
    L1 != unknown,
    L2 != unknown,
    E1 != E2.

% --- Character's Previous Explicit Location (Before This Event) ---
% explicit_presence(Entity, Location, T, E) ties Location to E's OWN time T,
% so for a travel event using that same-T fact as "origin" is self-
% referential -- it just reproduces the event's own destination, since the
% only explicit_presence fact at that exact T comes from the event itself.
% Origin needs the entity's most recent explicit presence STRICTLY BEFORE
% this event's time instead.
previous_presence_time(Entity, T, T_prev) :-
    event(E),
    event_time(E, T),
    agent(E, Entity),
    T_prev = #max { T2 : explicit_presence(Entity, _, T2, _), T2 < T }.

previous_location(Entity, Location, T) :-
    previous_presence_time(Entity, T, T_prev),
    explicit_presence(Entity, Location, T_prev, _).


% =============================================================================
% PART C: CONNECTIVITY GRAPH (Updated for Containment)
% =============================================================================

% Locations can be explicitly connected (bidirectional)
connected(L1, L2) :- connection(L1, L2).
connected(L1, L2) :- connection(L2, L1).

% Containment implies connectivity (movement between container and child)
connected(Parent, Child) :- contains(Parent, Child).
connected(Child, Parent) :- contains(Parent, Child).

% Siblings in same container are connected (can move between them)
connected(L1, L2) :- 
    contains(Parent, L1),
    contains(Parent, L2),
    L1 != L2.

% --- Mined Connectivity (data-driven, from original/unmodified text) ---
% mined_connected(L1, L2) is a learned fact asserted by
% mine_location_connectivity() (scripts/kfold_experiment_runner_conflict_resolver.py)
% when a story's own ORIGINAL (unmodified) chapters show a character
% repeatedly moving between two locations that were never given an
% explicit connections/contains declaration -- LLM extractions routinely
% omit an exhaustive location graph even when the narrative itself
% demonstrates the path exists. Kept as a DISTINCT predicate from an
% authored connection/contains fact (rather than asserting connected/2
% directly from Python) so mined connectivity stays separately
% attributable, per this file's own provenance/evidence-based design
% principle above -- it is still folded into connected/2 here so every
% existing rule that consults connectivity benefits without further changes.
connected(L1, L2) :- mined_connected(L1, L2).
connected(L2, L1) :- mined_connected(L1, L2).

% Reachability (transitive closure)
reachable(L1, L2) :- connected(L1, L2).
reachable(L1, L3) :- 
    reachable(L1, L2), 
    connected(L2, L3),
    L1 != L3.

% Track if we have connectivity info
has_connectivity_info :- connected(_, _).
has_connectivity_info :- contains(_, _).

% A location is "in the graph" if it has AT LEAST ONE declared/mined
% connection or containment edge of its own. has_connectivity_info alone is
% a GLOBAL flag (true story-wide the moment ANY two locations anywhere are
% connected), so gating impossible-travel-style rules on it alone treats
% every OTHER location pair as closed-world-disjoint even when we have zero
% actual graph data about THOSE specific locations. Requiring both
% endpoints to be in_location_graph narrows "no path" claims to places we
% actually have partial connectivity evidence for.
in_location_graph(L) :- connected(L, _).
in_location_graph(L) :- connected(_, L).
in_location_graph(L) :- contains(L, _).
in_location_graph(L) :- contains(_, L).


% =============================================================================
% PART D: TRAVEL EVENT CLASSIFICATION
% =============================================================================

% Standard travel types
is_travel_event(E) :- event_type(E, travel).
is_travel_event(E) :- event_type(E, walk).
is_travel_event(E) :- event_type(E, run).
is_travel_event(E) :- event_type(E, go).
is_travel_event(E) :- event_type(E, move).
is_travel_event(E) :- event_type(E, fly).
is_travel_event(E) :- event_type(E, drive).
is_travel_event(E) :- event_type(E, ride).
is_travel_event(E) :- event_type(E, enter).
is_travel_event(E) :- event_type(E, exit).
is_travel_event(E) :- event_type(E, leave).
is_travel_event(E) :- event_type(E, arrive).

% Teleportation events (bypass normal connectivity)
is_teleport_event(E) :- event_type(E, apparate).
is_teleport_event(E) :- event_type(E, teleport).
is_teleport_event(E) :- event_type(E, transport).
is_teleport_event(E) :- event_type(E, portal).
is_teleport_event(E) :- event_type(E, floo).
is_teleport_event(E) :- event_type(E, portkey).

% Within-container movement (always allowed)
is_local_movement(E) :-
    is_travel_event(E),
    agent(E, C),
    event_time(E, T),
    previous_location(C, Origin, T),
    event_location(E, Dest),
    same_containment_tree(Origin, Dest).

is_local_movement(E) :-
    is_travel_event(E),
    agent(E, C),
    event_time(E, T),
    previous_location(C, Origin, T),
    event_destination(E, Dest),
    same_containment_tree(Origin, Dest).

% No previously known location -- nothing to contradict, so travel is allowed
is_local_movement(E) :-
    is_travel_event(E),
    agent(E, C),
    event_time(E, T),
    not previous_location(C, _, T).


% =============================================================================
% PART E: LOCATION VIOLATIONS (Explicit Only)
% =============================================================================
%
% Phase Three Integration:
%     Location violations operate ONLY on physically_at, not present_in_scene.
%     A character can be present_in_scene without physically_at (unknown location).
%     This means talking without a location is VALID.
%
%     physically_at is derived from explicit_presence (see narrative_state.lp)
%
% =============================================================================

% --- NON-UBIQUITY (Explicit Presence Only) ---
% VIOLATION: Entity explicitly at two DISJOINT locations at the same time
% Does NOT fire for:
%   - Container + sub-location (coherent)
%   - Assumed/persisted presence (not explicit)
%   - Unknown locations
%   - present_in_scene without physically_at (valid)
%   
violation(location, explicit_ubiquity, 
          violation_info(Entity, at, L1, via_event, E1, and_at, L2, via_event, E2, at_time, T)) :-
    rule_active(location_explicit_ubiquity),
    explicit_presence_pair(Entity, L1, L2, T, E1, E2),
    disjoint_locations(L1, L2),
    L1 < L2.  % Avoid duplicate violations

% --- IMPOSSIBLE TRAVEL ---
% VIOLATION: Travel between unreachable locations (non-teleport)
% Does NOT fire for:
%   - Movement within same containment tree
%   - Teleportation events
%   - Missing connectivity info
%   - Scene-only presence without physical location
%
violation(location, impossible_travel,
          violation_info(Entity, travels_from, Origin, to, Dest, via_event, E, no_path)) :-
    rule_active(location_impossible_travel),
    event(E),
    is_travel_event(E),
    not is_teleport_event(E),
    not is_local_movement(E),
    event_time(E, T),
    agent(E, Entity),
    previous_location(Entity, Origin, T),
    event_location(E, Dest),
    Dest != unknown,
    Origin != unknown,
    Origin != Dest,
    has_connectivity_info,
    in_location_graph(Origin),
    in_location_graph(Dest),
    not reachable(Origin, Dest).

% Alternative: using event_destination
violation(location, impossible_travel,
          violation_info(Entity, travels_from, Origin, to, Dest, via_event, E, no_path)) :-
    rule_active(location_impossible_travel),
    event(E),
    is_travel_event(E),
    not is_teleport_event(E),
    not is_local_movement(E),
    event_time(E, T),
    agent(E, Entity),
    previous_location(Entity, Origin, T),
    event_destination(E, Dest),
    Dest != unknown,
    Origin != unknown,
    Origin != Dest,
    has_connectivity_info,
    in_location_graph(Origin),
    in_location_graph(Dest),
    not reachable(Origin, Dest).


% --- ITEM IMPOSSIBLE RELOCATION ---
% VIOLATION: An item's explicit location jumps between disjoint locations
% without being carried there by a character (mirrors impossible_travel, but
% for items -- items can't relocate themselves; either a character carries
% them across a valid path, or the jump is unexplained).
% Does NOT fire for:
%   - Locations in the same containment tree (moving a sub-room within a house)
%   - The item's very first known location (no prior location to contradict)
%   - Missing connectivity info
%   - An item actively being carried by a character at the time (the
%     character's own travel is checked separately by impossible_travel)
previous_item_presence_time(Item, T, T_prev) :-
    event(E),
    event_time(E, T),
    patient(E, Item),
    item(Item),
    T_prev = #max { T2 : item_explicit_presence(Item, _, T2, _), T2 < T }.

previous_item_location(Item, Location, T) :-
    previous_item_presence_time(Item, T, T_prev),
    item_explicit_presence(Item, Location, T_prev, _).

violation(location, item_impossible_relocation,
          violation_info(Item, moved_from, Origin, to, Dest, via_event, E, no_path)) :-
    rule_active(location_item_impossible_relocation),
    event(E),
    event_time(E, T),
    item_explicit_presence(Item, Dest, T, E),
    previous_item_location(Item, Origin, T),
    Origin != Dest,
    Origin != unknown,
    Dest != unknown,
    has_connectivity_info,
    in_location_graph(Origin),
    in_location_graph(Dest),
    disjoint_locations(Origin, Dest),
    not carries(_, Item, T).


% --- ITEM UNREACHABLE ---
% VIOLATION: An agent physically interacts with an item (takes/uses/reads/
% etc., per items.lp's is_item_activation_event) whose last known location
% is disjoint from the agent's own current location, without already
% carrying it. Mirrors invalid_remote (agent/patient copresence), but for
% an item's last recorded place instead of a second character's presence.
% Does NOT fire for:
%   - The item's very first known location (nothing to contradict yet)
%   - The agent's own location being unknown (nothing to compare against)
%   - Missing connectivity info
%   - The agent already carrying the item at that time
violation(location, item_unreachable,
          violation_info(Agent, at, AgentLoc, item, Item, last_at, ItemLoc, via_event, E)) :-
    rule_active(location_item_unreachable),
    event(E),
    event_time(E, T),
    event_type(E, Type),
    is_item_activation_event(Type),
    agent(E, Agent),
    patient(E, Item),
    item(Item),
    character(Agent),
    previous_location(Agent, AgentLoc, T),
    previous_item_location(Item, ItemLoc, T),
    AgentLoc != ItemLoc,
    has_connectivity_info,
    in_location_graph(AgentLoc),
    in_location_graph(ItemLoc),
    disjoint_locations(AgentLoc, ItemLoc),
    not carries(Agent, Item, T).


% =============================================================================
% PART F: REMOTE INTERACTION
% =============================================================================

% Remote action types (can interact across locations)
is_remote_action(E) :- event_type(E, call).
is_remote_action(E) :- event_type(E, phone).
is_remote_action(E) :- event_type(E, message).
is_remote_action(E) :- event_type(E, letter).
is_remote_action(E) :- event_type(E, telepathy).
is_remote_action(E) :- event_type(E, curse).
is_remote_action(E) :- event_type(E, spell).
is_remote_action(E) :- event_type(E, floo_call).
is_remote_action(E) :- event_type(E, patronus_message).
is_remote_action(E) :- event_type(E, owl).
is_remote_action(E) :- event_type(E, send).

% VIOLATION: Non-remote action with participants at disjoint locations
% Uses EXPLICIT presence only
violation(location, invalid_remote, 
          violation_info(Agent, at, L1, and, Patient, at, L2, in_event, E, requires_copresence)) :-
    rule_active(location_invalid_remote),
    event(E),
    event_time(E, T),
    agent(E, Agent),
    patient(E, Patient),
    character(Agent),
    character(Patient),
    Agent != Patient,
    explicit_presence(Agent, L1, T, _),
    explicit_presence(Patient, L2, T, _),
    disjoint_locations(L1, L2),
    not is_remote_action(E),
    not is_location(Patient).


% =============================================================================
% PART G: LOCATION QUERY HELPERS
% =============================================================================

% --- Character Location (at a given time) ---
% Returns explicit location only (not assumed)
character_location_explicit(C, L, T) :- explicit_presence(C, L, T, _).

% Returns any presence (explicit or container-derived)
character_location(C, L, T) :- has_presence(C, L, T).

% --- Characters at Same Location ---
% Both must have explicit presence at the same location
same_location_explicit(C1, C2, T) :-
    explicit_presence(C1, L, T, _),
    explicit_presence(C2, L, T, _),
    C1 != C2.

% Or at locations within the same container
same_location(C1, C2, T) :-
    has_presence(C1, L, T),
    has_presence(C2, L, T),
    C1 != C2.

% --- Location Changes (Explicit Evidence Only) ---
% Tracks when a character's explicit location changes between events
location_change(C, L1, L2, T1, T2, E1, E2) :-
    explicit_presence(C, L1, T1, E1),
    explicit_presence(C, L2, T2, E2),
    T1 < T2,
    L1 != L2,
    not has_intervening_location(C, T1, T2).

% Helper: Character has explicit presence between two times
has_intervening_location(C, T1, T2) :-
    explicit_presence(C, _, T_mid, _),
    time(T1),
    time(T2),
    T1 < T_mid,
    T_mid < T2.

% --- Last Known Location ---
% The most recent explicit location for a character
last_known_location(C, L, T) :-
    explicit_presence(C, L, T, _),
    not has_later_explicit_presence(C, T).

has_later_explicit_presence(C, T) :-
    explicit_presence(C, _, T2, _),
    time(T),
    T < T2.


% =============================================================================
% PART H: COMPATIBILITY WITH CORE.LP
% =============================================================================
%
% The core.lp file defines present(E, L, T) via holds(present(E, L), T).
% We provide compatibility predicates to bridge the two systems.
%
% The key distinction:
%   - present/3 in core.lp uses frame axioms (persistence)
%   - explicit_presence/4 here is evidence-based (no persistence)
%
% Violations use explicit_presence to avoid false positives.
% Queries may use present/3 for backward compatibility.
% =============================================================================

% Derive explicit_presence from core.lp initiates (when available)
explicit_presence(Entity, Location, T, E) :-
    event(E),
    event_time(E, T),
    initiates(E, present(Entity, Location)),
    Location != unknown.

% Derive explicit_presence from implied_presence events
% These are synthetic events created from implied_presence extraction
explicit_presence(Entity, Location, T, E) :-
    implied_presence_event(E),
    event_time(E, T),
    agent(E, Entity),
    event_location(E, Location),
    Location != unknown.

% =============================================================================
% PART I: PRESENT/3 INTEGRATION (Implied Presence Support)
% =============================================================================
%
% present/3 facts can come from:
%   - core.lp EC framework: holds(present(E, L), T) -> present(E, L, T)
%   - Direct emission from implied_presence extraction
%
% We integrate present/3 with explicit_presence/4 for violation detection.
% A synthetic event marker (present_fact) is used when no specific event exists.
%
% IMPORTANT: This does NOT infer travel. It only enables violation detection
%            when an entity is simultaneously present at disjoint locations.
% =============================================================================

% Helper: Create a pair of present/3 facts at the same time for violation detection
% This is the equivalent of explicit_presence_pair for present/3 facts
present_pair(Entity, L1, L2, T) :-
    present(Entity, L1, T),
    present(Entity, L2, T),
    L1 != L2,
    L1 != unknown,
    L2 != unknown.

% VIOLATION: Entity present at two DISJOINT locations at the same time (via present/3)
% This catches implied presence contradictions without requiring event IDs
violation(location, simultaneous_presence,
          violation_info(Entity, present_at, L1, and_at, L2, at_time, T)) :-
    rule_active(location_explicit_ubiquity),
    present_pair(Entity, L1, L2, T),
    disjoint_locations(L1, L2),
    L1 < L2.  % Avoid duplicate violations

% VIOLATION: Non-remote action where agent and patient are at disjoint locations (via present/3)
% This extends invalid_remote to work with present/3 facts
violation(location, invalid_remote_action,
          violation_info(Agent, present_at, L1, and, Patient, present_at, L2, in_event, E)) :-
    rule_active(location_invalid_remote),
    event(E),
    event_time(E, T),
    agent(E, Agent),
    patient(E, Patient),
    character(Agent),
    character(Patient),
    Agent != Patient,
    present(Agent, L1, T),
    present(Patient, L2, T),
    disjoint_locations(L1, L2),
    not is_remote_action(E),
    not is_location(Patient).


% =============================================================================
% SHOW DIRECTIVES
% =============================================================================

#show violation/4.
#show explicit_presence/4.
#show disjoint_locations/2.
#show same_containment_tree/2.
