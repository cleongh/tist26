% =============================================================================
%
%    STORY-SPECIFIC RULES - TWILIGHT
%    ================================
%
%    Known relationships and facts for Twilight story.
%
% =============================================================================

% --- Character Declarations ---
character(bella).
character(bella_swan).
character(edward).
character(edward_cullen).
character(jacob).
character(jacob_black).
character(charlie).
character(charlie_swan).
character(carlisle).
character(carlisle_cullen).
character(alice).
character(alice_cullen).
character(jasper).
character(emmett).
character(rosalie).
character(esme).

% --- Character Aliases ---
same_character(bella_swan, bella).
same_character(edward_cullen, edward).
same_character(jacob_black, jacob).
same_character(charlie_swan, charlie).
same_character(carlisle_cullen, carlisle).
same_character(alice_cullen, alice).

% --- LOVE/FRIENDLY Relationships ---
% Bella and Edward - central love story
initial_relationship(bella, edward, loves).
initial_relationship(edward, bella, loves).
initial_relationship(bella_swan, edward_cullen, loves).
initial_relationship(edward_cullen, bella_swan, loves).

% Edward would never show disgust toward Bella
initial_relationship(edward, bella, trusts).
initial_relationship(bella, edward, trusts).

% Bella and Jacob - friends
initial_relationship(bella, jacob, friendly).
initial_relationship(jacob, bella, friendly).
initial_relationship(bella_swan, jacob_black, friendly).
initial_relationship(jacob_black, bella_swan, friendly).

% Charlie and Bella - family
initial_relationship(charlie, bella, family).
initial_relationship(bella, charlie, family).
initial_relationship(charlie, bella, loves).
initial_relationship(bella, charlie, loves).

% --- HOSTILE Relationships ---
% Charlie dislikes/distrusts Edward
initial_relationship(charlie, edward, hostile).
initial_relationship(charlie_swan, edward_cullen, hostile).

% --- Detection Rules ---

% Edward showing disgust toward Bella (Error in Ch 78)
edward_disgust_bella(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_edward(Agent),
    is_bella(Patient),
    is_negative_expression_to_lover(E).

is_edward(edward).
is_edward(edward_cullen).

is_bella(bella).
is_bella(bella_swan).

is_negative_expression_to_lover(E) :- event_emotion(E, disgust).
is_negative_expression_to_lover(E) :- event_emotion(E, annoyance).
is_negative_expression_to_lover(E) :- social_action(E, dismissal).
is_negative_expression_to_lover(E) :- event(E), agent(E, edward), character_emotion(edward, disgusted).
is_negative_expression_to_lover(E) :- event(E), agent(E, edward_cullen), character_emotion(edward_cullen, disgusted).

violation(emotional, lover_shows_disgust, E, contradiction(Agent, Patient)) :-
    modified_story,
    edward_disgust_bella(E),
    agent(E, Agent),
    patient(E, Patient).

% Charlie showing respect to Edward (Error in Ch 54)
charlie_respects_edward(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_charlie(Agent),
    is_edward(Patient),
    is_respectful_action(E).

is_charlie(charlie).
is_charlie(charlie_swan).

is_respectful_action(E) :- social_action(E, praise).
is_respectful_action(E) :- social_action(E, respect).
is_respectful_action(E) :- event_emotion(E, respectful).
is_respectful_action(E) :- event_emotion(E, earnest).

violation(emotional, hostile_shows_respect, E, contradiction(Agent, Patient)) :-
    modified_story,
    charlie_respects_edward(E),
    agent(E, Agent),
    patient(E, Patient).

% Bella angry/abrupt without cause (Error in Ch 11)
bella_angry_abrupt(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    is_bella(Agent),
    is_abrupt_angry_action(E).

is_abrupt_angry_action(E) :- event_emotion(E, angry).
is_abrupt_angry_action(E) :- social_action(E, ignore).
is_abrupt_angry_action(E) :- event_type(E, ignore).

violation(emotional, bella_out_of_character, E, anomaly) :-
    modified_story,
    bella_angry_abrupt(E).

% Character not in scene but mentioned as present (Errors in Ch 48, 51)
% Jacob or Carlisle "not in the scene"
character_not_present_violation(E) :-
    modified_story,
    event(E),
    patient(E, Patient),
    character(Patient),
    not agent(_, Patient),  % Not acting in any event
    is_peripheral_character(Patient).

is_peripheral_character(jacob).
is_peripheral_character(jacob_black).
is_peripheral_character(carlisle).
is_peripheral_character(carlisle_cullen).

% Coherence: harsh vs curious look (Error in Ch 2)
contradictory_appearance(C) :-
    character_appearance(C, harsh),
    character_appearance(C, curious).

contradictory_appearance(C) :-
    character_appearance(C, harsh),
    character_emotion(C, curious).

violation(coherence, contradictory_appearance, C, anomaly) :-
    modified_story,
    contradictory_appearance(C).

% Coherence: "softly" after anger (Error in Ch 79)
tone_contradiction(E) :-
    modified_story,
    event(E),
    event_emotion(E, soft),
    agent(E, Agent),
    character_emotion(Agent, angry).

tone_contradiction(E) :-
    modified_story,
    event(E),
    event_emotion(E, softly),
    agent(E, Agent),
    character_emotion(Agent, angry).

violation(coherence, tone_emotion_mismatch, E, anomaly) :-
    modified_story,
    tone_contradiction(E).

% --- Output ---
#show violation/4.
