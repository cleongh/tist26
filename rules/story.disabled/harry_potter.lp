% =============================================================================
%
%    STORY-SPECIFIC RULES - HARRY POTTER
%    ====================================
%
%    Known relationships and facts for Harry Potter story.
%    These provide the background knowledge needed for error detection.
%
% =============================================================================

% --- Character Declarations ---
character(harry_potter).
character(harry).
character(ron_weasley).
character(ron).
character(hermione_granger).
character(hermione).
character(uncle_vernon).
character(vernon_dursley).
character(aunt_petunia).
character(petunia_dursley).
character(dudley_dursley).
character(dudley).
character(neville_longbottom).
character(neville).
character(ginny_weasley).
character(ginny).
character(draco_malfoy).
character(draco).
character(dumbledore).
character(snape).
character(mcgonagall).
character(hagrid).
character(voldemort).

% --- Character Aliases (same person) ---
same_character(harry_potter, harry).
same_character(ron_weasley, ron).
same_character(hermione_granger, hermione).
same_character(vernon_dursley, uncle_vernon).
same_character(petunia_dursley, aunt_petunia).
same_character(dudley_dursley, dudley).
same_character(neville_longbottom, neville).
same_character(ginny_weasley, ginny).
same_character(draco_malfoy, draco).

% --- HOSTILE Relationships (Dursleys hate Harry) ---
% These are the key relationships that enable emotional error detection
initial_relationship(uncle_vernon, harry_potter, hostile).
initial_relationship(aunt_petunia, harry_potter, hostile).
initial_relationship(dudley_dursley, harry_potter, hostile).
initial_relationship(vernon_dursley, harry, hostile).
initial_relationship(petunia_dursley, harry, hostile).
initial_relationship(dudley, harry, hostile).
initial_relationship(uncle_vernon, harry, hostile).
initial_relationship(aunt_petunia, harry, hostile).

% Dursleys hostile to each other towards Harry (reflexive)
initial_relationship(harry_potter, uncle_vernon, hostile).
initial_relationship(harry_potter, aunt_petunia, hostile).
initial_relationship(harry_potter, dudley_dursley, hostile).
initial_relationship(harry, vernon_dursley, hostile).
initial_relationship(harry, petunia_dursley, hostile).
initial_relationship(harry, dudley, hostile).

% --- FRIENDLY Relationships (Harry's friends) ---
initial_relationship(harry_potter, ron_weasley, friendly).
initial_relationship(harry_potter, hermione_granger, friendly).
initial_relationship(harry, ron, friendly).
initial_relationship(harry, hermione, friendly).
initial_relationship(ron_weasley, harry_potter, friendly).
initial_relationship(hermione_granger, harry_potter, friendly).
initial_relationship(ron, harry, friendly).
initial_relationship(hermione, harry, friendly).

% Neville is friends with Harry, Ron, Hermione
initial_relationship(neville_longbottom, harry_potter, friendly).
initial_relationship(neville, harry, friendly).
initial_relationship(harry_potter, neville_longbottom, friendly).
initial_relationship(harry, neville, friendly).
initial_relationship(neville_longbottom, ron_weasley, friendly).
initial_relationship(neville_longbottom, hermione_granger, friendly).
initial_relationship(neville, ron, friendly).
initial_relationship(neville, hermione, friendly).

% Ginny is friends with Harry (and later more)
initial_relationship(ginny_weasley, harry_potter, friendly).
initial_relationship(ginny, harry, friendly).
initial_relationship(harry_potter, ginny_weasley, friendly).
initial_relationship(harry, ginny, friendly).

% --- ENEMY Relationships ---
initial_relationship(draco_malfoy, harry_potter, hostile).
initial_relationship(draco, harry, hostile).
initial_relationship(harry_potter, draco_malfoy, hostile).
initial_relationship(harry, draco, hostile).
initial_relationship(voldemort, harry_potter, hostile).
initial_relationship(harry_potter, voldemort, hostile).

% --- Warm Actions Detection (Dursley-Harry specific) ---
% If a Dursley acts warmly toward Harry, it's a violation
dursley_warm_to_harry(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_dursley(Agent),
    is_harry(Patient),
    is_warm_action_type(E).

is_dursley(uncle_vernon).
is_dursley(vernon_dursley).
is_dursley(aunt_petunia).
is_dursley(petunia_dursley).
is_dursley(dudley_dursley).
is_dursley(dudley).

is_harry(harry_potter).
is_harry(harry).

is_warm_action_type(E) :- event_type(E, farewell).
is_warm_action_type(E) :- event_type(E, hug).
is_warm_action_type(E) :- event_type(E, praise).
is_warm_action_type(E) :- event_type(E, comfort).
is_warm_action_type(E) :- event_type(E, smile).
is_warm_action_type(E) :- social_action(E, farewell).
is_warm_action_type(E) :- social_action(E, comfort).
is_warm_action_type(E) :- social_action(E, praise).
is_warm_action_type(E) :- social_action(E, encourage).

% Generate violation for Dursley warm behavior
violation(emotional, dursley_warm_to_harry, E, contradiction(Agent, Patient)) :-
    modified_story,
    dursley_warm_to_harry(E),
    agent(E, Agent),
    patient(E, Patient).

% --- Friend Betrayal Detection (Neville reporting Harry) ---
friend_betrays_friend(E) :-
    modified_story,
    event(E),
    event_type(E, report),
    agent(E, Agent),
    patient(E, Patient),
    initial_relationship(Agent, Patient, friendly).

% Also catch talk events that mention "tell McGonagall" or similar
friend_betrays_friend(E) :-
    modified_story,
    event(E),
    social_action(E, report),
    agent(E, Agent),
    patient(E, Patient),
    initial_relationship(Agent, Patient, friendly).

violation(emotional, friend_betrayal, E, contradiction(Agent, Patient)) :-
    modified_story,
    friend_betrays_friend(E),
    agent(E, Agent),
    patient(E, Patient).

% --- Ginny Dismissive of Harry Detection ---
ginny_dismissive_to_harry(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_ginny(Agent),
    is_harry(Patient),
    is_dismissive_action(E).

is_ginny(ginny_weasley).
is_ginny(ginny).

is_dismissive_action(E) :- social_action(E, dismissal).
is_dismissive_action(E) :- social_action(E, insult).
is_dismissive_action(E) :- social_action(E, mock).
is_dismissive_action(E) :- event_type(E, criticize).

violation(emotional, ginny_dismissive, E, contradiction(Agent, Patient)) :-
    modified_story,
    ginny_dismissive_to_harry(E),
    agent(E, Agent),
    patient(E, Patient).

% --- Appearance Anomaly Detection ---
% "pale green" face for anger is wrong (should be red)
% "grayish white of bubble and squeak" is wrong description
appearance_anomaly(C, App) :-
    character_appearance(C, App),
    App = pale_green.
appearance_anomaly(C, App) :-
    character_appearance(C, App),
    App = grayish_white.
appearance_anomaly(C, App) :-
    character_appearance(C, App),
    App = gray_white.
appearance_anomaly(C, App) :-
    character_appearance(C, App),
    App = bubble_and_squeak.

violation(coherence, appearance_anomaly, C, App) :-
    modified_story,
    appearance_anomaly(C, App).

% --- Output ---
#show violation/4.
