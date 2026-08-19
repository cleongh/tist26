% =============================================================================
%
%    STORY-SPECIFIC RULES - THE LORD OF THE RINGS
%    =============================================
%
%    Known relationships and facts for The Lord of the Rings story.
%
% =============================================================================

% --- Character Declarations ---
character(frodo).
character(frodo_baggins).
character(sam).
character(samwise).
character(samwise_gamgee).
character(gandalf).
character(aragorn).
character(strider).
character(legolas).
character(gimli).
character(boromir).
character(pippin).
character(peregrin).
character(merry).
character(meriadoc).
character(bilbo).
character(bilbo_baggins).
character(gollum).
character(smeagol).
character(sauron).
character(glorfindel).
character(faramir).
character(eowyn).

% --- Character Aliases ---
same_character(frodo_baggins, frodo).
same_character(samwise_gamgee, sam).
same_character(samwise, sam).
same_character(strider, aragorn).
same_character(peregrin, pippin).
same_character(meriadoc, merry).
same_character(bilbo_baggins, bilbo).
same_character(smeagol, gollum).

% --- FRIENDLY Relationships (Fellowship) ---
initial_relationship(frodo, sam, friendly).
initial_relationship(sam, frodo, friendly).
initial_relationship(frodo, gandalf, friendly).
initial_relationship(gandalf, frodo, friendly).
initial_relationship(frodo, aragorn, friendly).
initial_relationship(aragorn, frodo, friendly).
initial_relationship(frodo, pippin, friendly).
initial_relationship(pippin, frodo, friendly).
initial_relationship(frodo, merry, friendly).
initial_relationship(merry, frodo, friendly).
initial_relationship(frodo, legolas, friendly).
initial_relationship(frodo, gimli, friendly).
initial_relationship(frodo, boromir, friendly).

% Bilbo and Pippin are friends
initial_relationship(bilbo, pippin, friendly).
initial_relationship(pippin, bilbo, friendly).
initial_relationship(bilbo_baggins, pippin, friendly).
initial_relationship(bilbo_baggins, peregrin, friendly).

% Sam and Frodo - deep loyalty
initial_relationship(sam, frodo, trusts).
initial_relationship(frodo, sam, trusts).
initial_relationship(samwise, frodo, trusts).
initial_relationship(frodo, samwise, trusts).

% Aragorn and Glorfindel - friends/allies (NOT romantic)
initial_relationship(aragorn, glorfindel, friendly).
initial_relationship(glorfindel, aragorn, friendly).
initial_relationship(strider, glorfindel, friendly).

% Faramir and Eowyn - end up in love
initial_relationship(faramir, eowyn, loves).
initial_relationship(eowyn, faramir, loves).

% --- HOSTILE Relationships ---
initial_relationship(frodo, sauron, hostile).
initial_relationship(sauron, frodo, hostile).
initial_relationship(frodo, gollum, hostile).
initial_relationship(gollum, frodo, hostile).

% --- Detection Rules ---

% Bilbo acting hostile to friends (Error in Ch 59)
bilbo_hostile_to_friend(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_bilbo(Agent),
    initial_relationship(Agent, Patient, friendly),
    is_hostile_action(E).

is_bilbo(bilbo).
is_bilbo(bilbo_baggins).

is_hostile_action(E) :- event_type(E, throw).
is_hostile_action(E) :- event_emotion(E, angry).
is_hostile_action(E) :- social_action(E, insult).
is_hostile_action(E) :- event_type(E, grunt).

violation(emotional, friend_acts_hostile, E, contradiction(Agent, Patient)) :-
    modified_story,
    bilbo_hostile_to_friend(E),
    agent(E, Agent),
    patient(E, Patient).

% Glorfindel romantic with Aragorn (Error in Ch 12)
glorfindel_romantic_aragorn(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    is_glorfindel(Agent),
    is_aragorn(Patient),
    is_romantic_action(E).

is_glorfindel(glorfindel).

is_aragorn(aragorn).
is_aragorn(strider).

is_romantic_action(E) :- event_type(E, caress).
is_romantic_action(E) :- event_type(E, kiss).
is_romantic_action(E) :- social_action(E, caress).
is_romantic_action(E) :- event_emotion(E, romantic).
is_romantic_action(E) :- event_emotion(E, love).

violation(emotional, inappropriate_romance, E, contradiction(Agent, Patient)) :-
    modified_story,
    glorfindel_romantic_aragorn(E),
    agent(E, Agent),
    patient(E, Patient).

% Faramir/Eowyn showing coldness after declaring love (Error in Ch 58)
lovers_coldness(E) :-
    modified_story,
    event(E),
    agent(E, Agent),
    patient(E, Patient),
    initial_relationship(Agent, Patient, loves),
    is_cold_action(E).

is_cold_action(E) :- event_emotion(E, cold).
is_cold_action(E) :- event_type(E, recoil).
is_cold_action(E) :- social_action(E, dismissal).

violation(emotional, lovers_coldness, E, contradiction(Agent, Patient)) :-
    modified_story,
    lovers_coldness(E),
    agent(E, Agent),
    patient(E, Patient).

% Coherence: Hope in unequal world (Error in Ch 62)
hope_contradiction(C) :-
    character_emotion(C, hopeful),
    character_state(C, distressed).

hope_contradiction(C) :-
    character_emotion(C, hope),
    event_source(_, Source),
    contains_text(Source, "unequal").

violation(coherence, emotion_context_mismatch, C, anomaly) :-
    modified_story,
    hope_contradiction(C).

% Coherence: Balrog with joy/serenity (Error in Ch 17)
balrog_joy :-
    character_emotion(balrog, joy).
balrog_joy :-
    character_emotion(balrog, serenity).
balrog_joy :-
    event_emotion(_, gentle),
    character(balrog).

violation(coherence, balrog_emotion_anomaly, balrog, joy) :-
    modified_story,
    balrog_joy.

% Sitting on wall (Error in Ch 16) - physical impossibility
sit_on_wall(E) :-
    modified_story,
    event(E),
    event_type(E, sit),
    location(E, wall).

violation(coherence, physical_impossibility, E, sit_on_wall) :-
    modified_story,
    sit_on_wall(E).

% --- Output ---
#show violation/4.
