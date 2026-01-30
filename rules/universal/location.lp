% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - LOCATION (v2.0)
%    ============================================
%
%    Default world assumptions for spatial constraints.
%    These rules can be overridden by story-specific rules.
%
%    Per LOGIC_DESIGN.md Section 3.3:
%        NON-UBIQUITY: An entity cannot be present in more than one 
%        location at the same time.
%
%    VERSION 2.0: Uses time-indexed fluents, rule registration
%
%    LOCATION VIOLATIONS:
%        - Ubiquity (being in two places at once) - in core.lp
%        - Unreachable location travel
%        - Remote interaction without means
%        - Simultaneous presence at distant locations
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(location_unreachable_destination, universal, "Travel requires path between locations").
rule(location_simultaneous_distant, universal, "Characters cannot be at distant locations simultaneously").
rule(location_invalid_remote, universal, "Remote interaction requires remote action type").

% =============================================================================
% CONNECTIVITY GRAPH
% =============================================================================

% Locations can be connected (bidirectional by default)
connected(L1, L2) :- connected(L2, L1).

% Containment implies connectivity
connected(L1, L2) :- contains(L1, L2).
connected(L2, L1) :- contains(L1, L2).

% Reachability (transitive closure of connectivity)
reachable(L1, L2) :- connected(L1, L2).
reachable(L1, L3) :- reachable(L1, L2), connected(L2, L3).

% Track if we have connectivity info
has_connectivity_info :- connected(_, _).
has_connectivity_info :- contains(_, _).

% Distant locations (not connected and not the same)
distant(L1, L2) :- 
    is_location(L1), 
    is_location(L2), 
    L1 != L2, 
    has_connectivity_info,
    not reachable(L1, L2).

% =============================================================================
% TRAVEL EVENT TYPES
% =============================================================================

% Travel event types
is_travel_event(E) :- event_type(E, travel).
is_travel_event(E) :- event_type(E, walk).
is_travel_event(E) :- event_type(E, run).
is_travel_event(E) :- event_type(E, go).
is_travel_event(E) :- event_type(E, move).
is_travel_event(E) :- event_type(E, fly).
is_travel_event(E) :- event_type(E, drive).
is_travel_event(E) :- event_type(E, apparate).
is_travel_event(E) :- event_type(E, teleport).

% Teleportation events (exempt from reachability)
is_teleport_event(E) :- event_type(E, apparate).
is_teleport_event(E) :- event_type(E, teleport).
is_teleport_event(E) :- event_type(E, transport).
is_teleport_event(E) :- event_type(E, portal).
is_teleport_event(E) :- event_type(E, floo).

% =============================================================================
% TRAVEL VIOLATIONS (Time-Indexed)
% =============================================================================

% VIOLATION: Travel to unreachable location (uses time-indexed present/3)
violation(location, unreachable_destination, E, pair(Origin, Dest)) :-
    rule_active(location_unreachable_destination),
    event(E),
    is_travel_event(E),
    not is_teleport_event(E),
    event_time(E, T),
    agent(E, C),
    event_destination(E, Dest),
    present(C, Origin, T),
    has_connectivity_info,
    not reachable(Origin, Dest),
    Dest != unknown,
    Origin != unknown.

% Alternative: using location(E, Dest) when destination is location
violation(location, unreachable_destination, E, pair(Origin, Dest)) :-
    rule_active(location_unreachable_destination),
    event(E),
    is_travel_event(E),
    not is_teleport_event(E),
    event_time(E, T),
    agent(E, C),
    location(E, Dest),
    present(C, Origin, T),
    T > 0,
    has_connectivity_info,
    not reachable(Origin, Dest),
    Dest != unknown,
    Origin != unknown,
    Origin != Dest.

% =============================================================================
% SIMULTANEOUS PRESENCE VIOLATIONS (Time-Indexed)
% =============================================================================

% VIOLATION: Character at distant locations at same time
% More specific than generic non-ubiquity in core.lp
violation(location, simultaneous_distant, E, triple(C, L1, L2)) :-
    rule_active(location_simultaneous_distant),
    event(E),
    event_time(E, T),
    character(C),
    present(C, L1, T),
    present(C, L2, T),
    distant(L1, L2),
    L1 < L2.  % Avoid duplicate violations

% =============================================================================
% REMOTE INTERACTION
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

% VIOLATION: Non-remote action with participants in different locations
violation(location, invalid_remote, E, pair(Agent, Patient)) :-
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
    L1 != L2,
    L1 != unknown,
    L2 != unknown,
    not is_remote_action(E),
    not is_location(Patient).  % Exclude when "patient" is actually a location

% =============================================================================
% LOCATION STATE HELPERS
% =============================================================================

% Derive location from present/3 fluent
character_location(C, L, T) :- present(C, L, T).

% Characters at same location at a given time
same_location(C1, C2, T) :-
    present(C1, L, T),
    present(C2, L, T),
    C1 != C2.

% Track location changes
location_change(C, L1, L2, T1, T2) :-
    present(C, L1, T1),
    present(C, L2, T2),
    next_time(T1, T2),
    L1 != L2.
