% =============================================================================
%
%    STORY-SPECIFIC RULES - THE HUNGER GAMES
%    ========================================
%
%    Known relationships and facts for The Hunger Games story.
%
% =============================================================================

% --- Character Declarations ---
character(katniss).
character(katniss_everdeen).
character(peeta).
character(peeta_mellark).
character(gale).
character(gale_hawthorne).
character(haymitch).
character(prim).
character(primrose).
character(primrose_everdeen).
character(mother).
character(katniss_mother).
character(effie).
character(cinna).
character(finnick).
character(johanna).
character(president_snow).
character(snow).

% --- Character Aliases ---
same_character(katniss_everdeen, katniss).
same_character(peeta_mellark, peeta).
same_character(gale_hawthorne, gale).
same_character(primrose_everdeen, prim).
same_character(primrose, prim).
same_character(president_snow, snow).

% --- FRIENDLY/FAMILY Relationships ---
% Katniss and Peeta
initial_relationship(katniss, peeta, friendly).
initial_relationship(peeta, katniss, friendly).
initial_relationship(katniss_everdeen, peeta_mellark, friendly).
initial_relationship(peeta_mellark, katniss_everdeen, friendly).

% Katniss and Gale
initial_relationship(katniss, gale, friendly).
initial_relationship(gale, katniss, friendly).
initial_relationship(katniss_everdeen, gale_hawthorne, friendly).
initial_relationship(gale_hawthorne, katniss_everdeen, friendly).

% Katniss and her family - LOVE
initial_relationship(katniss, mother, loves).
initial_relationship(mother, katniss, loves).
initial_relationship(katniss, prim, loves).
initial_relationship(prim, katniss, loves).
initial_relationship(katniss, primrose, loves).
initial_relationship(katniss_mother, katniss, loves).
initial_relationship(katniss, katniss_mother, loves).

% Family relationships
initial_relationship(katniss, mother, family).
initial_relationship(mother, katniss, family).
initial_relationship(katniss, prim, family).
initial_relationship(prim, katniss, family).

% --- HOSTILE Relationships ---
initial_relationship(katniss, president_snow, hostile).
initial_relationship(president_snow, katniss, hostile).
initial_relationship(katniss, snow, hostile).
initial_relationship(snow, katniss, hostile).

% --- Detection Rules ---

% Mother showing hatred toward Katniss (Error in Ch 63, 80)
mother_hates_katniss(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_katniss_mother(Agent),
    is_katniss(Patient),
    is_hostile_expression(E).

is_katniss_mother(mother).
is_katniss_mother(katniss_mother).

is_katniss(katniss).
is_katniss(katniss_everdeen).

is_hostile_expression(E) :- social_action(E, insult).
is_hostile_expression(E) :- social_action(E, dismissal).
is_hostile_expression(E) :- event_type(E, hate).
is_hostile_expression(E) :- event_type(E, disgust).
is_hostile_expression(E) :- character_emotion(_, disgusted), agent(E, _).

violation(emotional, mother_hates_child, E, contradiction(Agent, Patient)) :-
    modified_story,
    mother_hates_katniss(E),
    agent(E, Agent),
    patient(E, Patient).

% Warm tone in hostile situation (Error in Ch 35 - "warmly back at him")
inappropriate_warmth(E) :-
    modified_story,
    event(E),
    social_action(E, warm).

inappropriate_warmth(E) :-
    modified_story,
    event(E),
    event_emotion(E, warm).

violation(emotional, inappropriate_warmth, E, anomaly) :-
    modified_story,
    inappropriate_warmth(E).

% Coherence: translucent bones (Error in Ch 36)
translucent_anomaly(C) :-
    character_appearance(C, translucent).
translucent_anomaly(C) :-
    character_appearance(C, translucid).

violation(coherence, translucent_body_part, C, appearance) :-
    modified_story,
    translucent_anomaly(C).

% Coherence: bowl full after eating (Error in Ch 7)
% This requires semantic understanding - approximate with state contradiction
bowl_contradiction(E) :-
    modified_story,
    event(E),
    event_type(E, push),
    patient(E, bowl),
    event_source(E, Source),
    contains_text(Source, "untouched").

bowl_contradiction(E) :-
    modified_story,
    event(E),
    patient(E, bowl),
    item_state(bowl, full),
    event_emotion(E, full).

violation(coherence, bowl_state_contradiction, E, anomaly) :-
    modified_story,
    bowl_contradiction(E).

% --- Output ---
#show violation/4.
