% =============================================================================
%
%    STORY-SPECIFIC RULES - GOOSEBUMPS
%    ===================================
%
%    Known relationships and facts for Goosebumps story.
%
% =============================================================================

% --- Character Declarations ---
character(evan).
character(evan_ross).
character(andy).
character(andrea).
character(trigger).
character(mom).
character(evan_mom).
character(kathryn).
character(aunt_kathryn).
character(slappy).

% --- Character Aliases ---
same_character(evan_ross, evan).
same_character(andrea, andy).
same_character(aunt_kathryn, kathryn).
same_character(evan_mom, mom).

% --- FRIENDLY Relationships ---
initial_relationship(evan, andy, friendly).
initial_relationship(andy, evan, friendly).
initial_relationship(evan, trigger, friendly).
initial_relationship(trigger, evan, friendly).
initial_relationship(evan, mom, loves).
initial_relationship(mom, evan, loves).
initial_relationship(evan_ross, mom, loves).
initial_relationship(mom, evan_ross, loves).

% --- FAMILY Relationships ---
initial_relationship(evan, mom, family).
initial_relationship(mom, evan, family).
initial_relationship(evan, kathryn, family).
initial_relationship(kathryn, evan, family).
initial_relationship(evan, aunt_kathryn, family).
initial_relationship(aunt_kathryn, evan, family).

% --- Detection Rules ---

% Mom abandoning Evan (Error in Ch 32)
mom_abandons_evan(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_evan_mom(Agent),
    is_evan(Patient),
    is_abandonment_action(E).

is_evan_mom(mom).
is_evan_mom(evan_mom).

is_evan(evan).
is_evan(evan_ross).

is_abandonment_action(E) :- event_type(E, abandon).
is_abandonment_action(E) :- event_type(E, leave).
is_abandonment_action(E) :- social_action(E, ignore).
is_abandonment_action(E) :- event_emotion(E, cold).

violation(emotional, parent_abandons_child, E, contradiction(Agent, Patient)) :-
    modified_story,
    mom_abandons_evan(E),
    agent(E, Agent),
    patient(E, Patient).

% Mom betraying Evan (Error in Ch 74)
mom_betrays_evan(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_evan_mom(Agent),
    is_evan(Patient),
    is_betrayal_action(E).

is_betrayal_action(E) :- event_type(E, betray).
is_betrayal_action(E) :- social_action(E, betray).
is_betrayal_action(E) :- event_emotion(E, disgust).
is_betrayal_action(E) :- event_type(E, blame).

violation(emotional, parent_betrays_child, E, contradiction(Agent, Patient)) :-
    modified_story,
    mom_betrays_evan(E),
    agent(E, Agent),
    patient(E, Patient).

% Andy refusing to help (Error in Ch 54)
andy_refuses_help(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_andy(Agent),
    is_evan(Patient),
    is_refusal_action(E).

is_andy(andy).
is_andy(andrea).

is_refusal_action(E) :- event_type(E, refuse).
is_refusal_action(E) :- social_action(E, dismissal).
is_refusal_action(E) :- event_type(E, reject).

violation(emotional, friend_refuses_help, E, contradiction(Agent, Patient)) :-
    modified_story,
    andy_refuses_help(E),
    agent(E, Agent),
    patient(E, Patient).

% Coherence: Metallic arm contradiction (Error in Ch 57)
metallic_arm_anomaly(C) :-
    character_appearance(C, metallic).

metallic_arm_anomaly(C) :-
    character_appearance(C, metal).

violation(coherence, metallic_body_anomaly, C, appearance) :-
    modified_story,
    metallic_arm_anomaly(C).

% Coherence: "Sly smile" anomaly (Error in Ch 67)
sly_anomaly(C) :-
    character_emotion(C, sly).

sly_anomaly(C) :-
    character_appearance(C, sly).

violation(coherence, sly_expression_anomaly, C, appearance) :-
    modified_story,
    sly_anomaly(C).

% Coherence: Running inside house (Error in Ch 73)
running_inside_anomaly(E) :-
    modified_story,
    event(E),
    event_type(E, run),
    location(E, house).

running_inside_anomaly(E) :-
    modified_story,
    event(E),
    event_type(E, run),
    location(E, room).

violation(coherence, running_inside, E, location) :-
    modified_story,
    running_inside_anomaly(E).

% --- Output ---
#show violation/4.
