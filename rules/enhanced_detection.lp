% =============================================================================
%
%    ENHANCED DETECTION RULES v1
%    ===========================
%
%    This module adds additional detection rules designed to maximize recall
%    while maintaining reasonable precision. Uses a multi-signal approach
%    where chapters accumulate evidence scores.
%
% =============================================================================

% =============================================================================
% SECTION 1: APPEARANCE-BASED ANOMALIES
% =============================================================================

% Abnormal color appearances that indicate potential errors
abnormal_color_appearance(C) :- character_appearance(C, App), 
    appearance_contains(App, "pale green").
abnormal_color_appearance(C) :- character_appearance(C, App),
    appearance_contains(App, "grayish").
abnormal_color_appearance(C) :- character_appearance(C, App),
    appearance_contains(App, "translucent").
abnormal_color_appearance(C) :- character_appearance(C, App),
    appearance_contains(App, "gray white").
abnormal_color_appearance(C) :- character_appearance(C, App),
    appearance_contains(App, "metallic").

% Generate violation for abnormal color
violation(coherence, abnormal_color, C, appearance, App) :-
    modified_story,
    abnormal_color_appearance(C),
    character_appearance(C, App).

% =============================================================================
% SECTION 2: RELATIONSHIP-ACTION CONTRADICTIONS
% =============================================================================

% Build hostile pairs from initial rules
hostile_pair(A, B) :- initial_relationship(A, B, hostile).
hostile_pair(A, B) :- initial_relationship(A, B, hates).
hostile_pair(A, B) :- initial_relationship(A, B, enemy).

% Build friendly pairs from initial rules
friendly_pair(A, B) :- initial_relationship(A, B, friendly).
friendly_pair(A, B) :- initial_relationship(A, B, loves).
friendly_pair(A, B) :- initial_relationship(A, B, trusts).
friendly_pair(A, B) :- initial_relationship(A, B, family).

% Warm/positive actions
warm_action(farewell).
warm_action(praise).
warm_action(comfort).
warm_action(hug).
warm_action(kiss).
warm_action(gift).
warm_action(respect).
warm_action(encourage).
warm_action(warm).

% Hostile actions
hostile_action(insult).
hostile_action(attack).
hostile_action(threaten).
hostile_action(mock).
hostile_action(criticize).
hostile_action(report).
hostile_action(betray).
hostile_action(refuse).
hostile_action(reject).
hostile_action(disgust).
hostile_action(recoil).
hostile_action(dismissal).
hostile_action(abandon).

% Hostile character performing warm action = contradiction (checked against
% both social_action/2 -- an explicit interaction label -- and event_emotion/2
% -- the tone/affect attached to the event itself -- since either field can
% carry the same warm/hostile vocabulary depending on how the extraction
% tagged a given event).
%
% NOTE: a has_corroborated_relationship/not first_interaction gate (matching
% relationship_action_mismatch's gating in rules/universal/emotional.lp) was
% tried here and measured on the OpenAI k=1 dataset: it dropped recall
% 42.67%->40.00% and precision 6.05%->5.88% (lost 2 emotional-category TPs
% while removing fewer FPs), so it was reverted. Do not reintroduce that gate
% without re-measuring against ground truth first.
violation(emotional, hostile_warm_action, E, Agent, contradiction(Agent, Type, Patient)) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    social_action(E, Type),
    warm_action(Type),
    hostile_pair(Agent, Patient).

violation(emotional, hostile_warm_action, E, Agent, contradiction(Agent, Type, Patient)) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    event_emotion(E, Type),
    warm_action(Type),
    hostile_pair(Agent, Patient).

% Friendly character performing hostile action = contradiction
violation(emotional, friendly_hostile_action, E, Agent, contradiction(Agent, Type, Patient)) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    social_action(E, Type),
    hostile_action(Type),
    friendly_pair(Agent, Patient).

violation(emotional, friendly_hostile_action, E, Agent, contradiction(Agent, Type, Patient)) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    event_emotion(E, Type),
    hostile_action(Type),
    friendly_pair(Agent, Patient).

% =============================================================================
% SECTION 3: MULTI-SIGNAL ANOMALY DETECTION
% =============================================================================



% Signal: Multiple negative emotions in chapter
has_high_neg_emotion_signal :- 
    N = #count { C : character_emotion(C, angry) },
    N >= 3.
has_high_neg_emotion_signal :- 
    N = #count { C : character_emotion(C, afraid) },
    N >= 3.
has_high_neg_emotion_signal :- 
    N = #count { C : character_emotion(C, sad) },
    N >= 2.

% Signal: Mixed relationship types present
has_mixed_relationship_signal :-
    hostile_pair(_, _),
    friendly_pair(_, _).

% Signal: Report events present
has_report_signal :- report(_).
has_report_signal :- social_action(_, report).

% Signal: Unusual character states
has_unusual_state_signal :- character_state(_, injured).
has_unusual_state_signal :- character_state(_, unconscious).
has_unusual_state_signal :- character_state(_, petrified).

% Signal: Pale/dark appearances (less specific)
has_unusual_appearance_signal :- 
    character_appearance(_, App),
    appearance_contains(App, "pale").
has_unusual_appearance_signal :- 
    character_appearance(_, App),
    appearance_contains(App, "dark").
has_unusual_appearance_signal :- 
    character_appearance(_, App),
    appearance_contains(App, "cold").

% Signal: Hostile social actions (insult, good_riddance, etc)
has_hostile_action_signal :- social_action(_, insult).
has_hostile_action_signal :- social_action(_, good_riddance).
has_hostile_action_signal :- social_action(_, dismissal).
has_hostile_action_signal :- social_action(_, threaten).
has_hostile_action_signal :- social_action(_, mock).

% Signal: Comfort/encourage in context with hostile (contextual contradiction)
has_comfort_hostile_signal :-
    social_action(_, comfort),
    hostile_pair(_, _).
has_comfort_hostile_signal :-
    social_action(_, encourage),
    hostile_pair(_, _).

% Count signals (more granular)
total_anomaly_signals(N) :- N = #count {
    1 : has_high_neg_emotion_signal;
    2 : has_mixed_relationship_signal;
    3 : has_report_signal;
    4 : has_unusual_state_signal;
    5 : has_unusual_appearance_signal;
    6 : has_hostile_action_signal;
    7 : has_comfort_hostile_signal
}.

% Fire when multiple signals present.
% Threshold is density-adaptive (mined per-story from the ORIGINAL/unmodified
% chapters' own event volume, see mine_signal_density_threshold in
% kfold_experiment_runner_conflict_resolver.py), so denser extractions (e.g.
% Kimi) require more concurrent signals than sparser ones (e.g. OpenAI)
% before this fires. Falls back to 3 (the paper's fixed value) when nothing
% overrides it, e.g. in the live LLM pipeline.
default_multi_signal_threshold(3).
multi_signal_threshold(T) :- default_multi_signal_threshold(T), not mined_multi_signal_threshold(_).
multi_signal_threshold(T) :- mined_multi_signal_threshold(T).

violation(coherence, multi_signal_anomaly, chapter, signals, N) :-
    modified_story,
    total_anomaly_signals(N),
    multi_signal_threshold(T),
    N >= T.

% =============================================================================
% SECTION 3B: CATEGORY-SPECIFIC ANOMALY SIGNALS
% =============================================================================

% --- LOCATION SIGNALS ---
% Multiple distinct locations in chapter suggests spatial complexity
has_location_complexity_signal :-
    N = #count { L : location_entity(L) },
    N >= 4.

% Multiple location changes for same character
has_location_change_signal :-
    location(E1, L1),
    location(E2, L2),
    agent(E1, A),
    agent(E2, A),
    L1 != L2.

% Character at disjoint locations (impossible in same chapter)
has_location_disjoint_signal :-
    location(E1, L1),
    location(E2, L2),
    agent(E1, A),
    agent(E2, A),
    not connected(L1, L2),
    not connected(L2, L1),
    L1 != L2.

% Arrive/leave events present
has_travel_event_signal :-
    event(E),
    event_type(E, arrive).
has_travel_event_signal :-
    event(E),
    event_type(E, leave).

% Location signal count
location_anomaly_signals(N) :- N = #count {
    1 : has_location_complexity_signal;
    2 : has_location_change_signal;
    3 : has_location_disjoint_signal;
    4 : has_travel_event_signal
}.

% Fire LOCATION violation when location signals + general anomaly.
% Gated on the same density-adaptive multi_signal_threshold(T) as
% multi_signal_anomaly, so denser corpora need proportionally more overall
% anomaly signal before this fires too.
violation(location, spatial_anomaly, chapter, location_signals, N) :-
    modified_story,
    location_anomaly_signals(N),
    N >= 2,
    total_anomaly_signals(M),
    multi_signal_threshold(T),
    M >= T.

% --- TEMPORAL SIGNALS ---
% Learn events (gaining knowledge) can indicate temporal issues
has_knowledge_gain_signal :-
    event(E),
    event_type(E, learn).

% Sequence-related events
has_sequence_event_signal :-
    event(E),
    event_type(E, realize).
has_sequence_event_signal :-
    event(E),
    event_type(E, discover).
has_sequence_event_signal :-
    event(E),
    event_type(E, remember).

% Multiple learn events could indicate premature knowledge
has_premature_knowledge_signal :-
    N = #count { E : event_type(E, learn) },
    N >= 2.

% Temporal signal count
temporal_anomaly_signals(N) :- N = #count {
    1 : has_knowledge_gain_signal;
    2 : has_sequence_event_signal;
    3 : has_premature_knowledge_signal
}.

% Fire TEMPORAL violation when temporal signals + general anomaly.
% Same density-adaptive gate as spatial_anomaly above.
violation(temporal, sequence_anomaly, chapter, temporal_signals, N) :-
    modified_story,
    temporal_anomaly_signals(N),
    N >= 2,
    total_anomaly_signals(M),
    multi_signal_threshold(T),
    M >= T.

% --- CAUSALITY SIGNALS ---
% Unexplained state changes can indicate causality issues
has_unexplained_state_signal :-
    character_state(C, S),
    S != normal.

% Effect without visible cause
has_item_state_signal :-
    item_state(_, _).

% Causality signal count
causality_anomaly_signals(N) :- N = #count {
    1 : has_unexplained_state_signal;
    2 : has_item_state_signal
}.

% Fire CAUSALITY violation when causality signals + general anomaly.
% One step stricter than the density-adaptive threshold T (paper used a
% fixed +1 margin over the other Section 3B gates: M>=3 vs M>=2).
violation(causality, effect_anomaly, chapter, causality_signals, N) :-
    modified_story,
    causality_anomaly_signals(N),
    N >= 1,
    total_anomaly_signals(M),
    multi_signal_threshold(T),
    M >= T + 1.

% =============================================================================
% SECTION 4: STRING MATCHING HELPERS
% =============================================================================

% Helper to check if a string contains a substring
% This is approximated by checking if the appearance atom includes the keyword
% Handle both quoted strings and unquoted atoms
% Named appearance_contains/2 (not contains/2) so it never unifies with the
% unrelated location-containment contains/2 facts (Location, Sub-location).
appearance_contains(App, "pale green") :- App = "pale green".
appearance_contains(App, "pale green") :- App = "Pale green".
appearance_contains(App, "pale green") :- App = pale_green.
appearance_contains(App, "grayish") :- App = "grayish".
appearance_contains(App, "grayish") :- App = "Grayish".
appearance_contains(App, "grayish") :- App = grayish.
appearance_contains(App, "translucent") :- App = "translucent".
appearance_contains(App, "translucent") :- App = "Translucent".
appearance_contains(App, "translucent") :- App = translucent.
appearance_contains(App, "gray white") :- App = "gray white".
appearance_contains(App, "gray white") :- App = gray_white.
appearance_contains(App, "pale") :- App = pale.
appearance_contains(App, "pale") :- App = "pale".
appearance_contains(App, "pale") :- App = "Pale".
appearance_contains(App, "dark") :- App = dark.
appearance_contains(App, "dark") :- App = "dark".
appearance_contains(App, "cold") :- App = cold.
appearance_contains(App, "cold") :- App = "cold".
appearance_contains(App, "cold stone") :- App = "cold stone".
appearance_contains(App, "cold stone") :- App = cold_stone.

% =============================================================================
% OUTPUT
% =============================================================================

#show violation/5.
