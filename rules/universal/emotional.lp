% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - EMOTIONAL/RELATIONSHIP (v2.0)
%    ==========================================================
%
%    Default world assumptions for character behavior and relationships.
%    These rules can be overridden by story-specific rules.
%
%    Per LOGIC_DESIGN.md Section 3.2:
%        relationship(Character1, Character2, Type, Time) tracks relationships.
%
%    VERSION 2.0: Uses time-indexed fluents, rule registration
%
%    EMOTIONAL VIOLATIONS:
%        - Actions contradicting established relationships
%        - Behavior contradicting established traits
%        - Emotional state contradictions
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(emotional_relationship_action_mismatch, universal, "Actions must be consistent with relationships").
rule(emotional_trait_action_mismatch, universal, "Actions must be consistent with character traits").

% =============================================================================
% RELATIONSHIP TYPES
% =============================================================================

% Positive relationship types
is_positive_relationship(loves).
is_positive_relationship(likes).
is_positive_relationship(trusts).
is_positive_relationship(respects).
is_positive_relationship(friendly).
is_positive_relationship(ally).
is_positive_relationship(friend).
is_positive_relationship(family).

% Negative relationship types
is_negative_relationship(hates).
is_negative_relationship(dislikes).
is_negative_relationship(distrusts).
is_negative_relationship(fears).
is_negative_relationship(hostile).
is_negative_relationship(enemy).
is_negative_relationship(rival).

% =============================================================================
% ACTION-RELATIONSHIP CONTRADICTIONS
% =============================================================================

% Actions that contradict negative relationships (friendly actions)
action_contradicts_negative(help).
action_contradicts_negative(save).
action_contradicts_negative(protect).
action_contradicts_negative(hug).
action_contradicts_negative(kiss).
action_contradicts_negative(gift).
action_contradicts_negative(praise).
action_contradicts_negative(comfort).
action_contradicts_negative(defend).
action_contradicts_negative(farewell).
action_contradicts_negative(congratulates).

% Actions that contradict positive relationships (hostile actions)
action_contradicts_positive(attack).
action_contradicts_positive(hit).
action_contradicts_positive(hurt).
action_contradicts_positive(betray).
action_contradicts_positive(abandon).
action_contradicts_positive(insult).
action_contradicts_positive(curse).
action_contradicts_positive(threaten).
action_contradicts_positive(steal_from).

% =============================================================================
% RELATIONSHIP VIOLATIONS (Time-Indexed)
% =============================================================================

% VIOLATION: Friendly action toward someone you hate
% Uses time-indexed relationship/4 from core.lp
violation(emotional, relationship_action_mismatch, E, pair(Agent, Patient)) :-
    rule_active(emotional_relationship_action_mismatch),
    event(E),
    event_time(E, T),
    event_type(E, Type),
    action_contradicts_negative(Type),
    agent(E, Agent),
    patient(E, Patient),
    relationship(Agent, Patient, RelType, T),
    is_negative_relationship(RelType).

% VIOLATION: Hostile action toward someone you love
violation(emotional, relationship_action_mismatch, E, pair(Agent, Patient)) :-
    rule_active(emotional_relationship_action_mismatch),
    event(E),
    event_time(E, T),
    event_type(E, Type),
    action_contradicts_positive(Type),
    agent(E, Agent),
    patient(E, Patient),
    relationship(Agent, Patient, RelType, T),
    is_positive_relationship(RelType).

% Backward compatibility: atemporal relationship/3
violation(emotional, relationship_action_mismatch, E, pair(Agent, Patient)) :-
    rule_active(emotional_relationship_action_mismatch),
    event(E),
    event_type(E, Type),
    action_contradicts_negative(Type),
    agent(E, Agent),
    patient(E, Patient),
    relationship(Agent, Patient, RelType),
    is_negative_relationship(RelType),
    not event_time(E, _).

violation(emotional, relationship_action_mismatch, E, pair(Agent, Patient)) :-
    rule_active(emotional_relationship_action_mismatch),
    event(E),
    event_type(E, Type),
    action_contradicts_positive(Type),
    agent(E, Agent),
    patient(E, Patient),
    relationship(Agent, Patient, RelType),
    is_positive_relationship(RelType),
    not event_time(E, _).

% =============================================================================
% STORY RULE INTEGRATION
% =============================================================================

% Story rules can establish relationships
% relationship_rule(Subject, Predicate, Object, EstablishedBy)

% Convert relationship rules to initial relationships
initial_relationship(S, O, P) :- relationship_rule(S, P, O, _).

% Action-relationship contradiction from story rules
action_contradicts_relationship(Action, RelType) :-
    action_contradicts_negative(Action),
    is_negative_relationship(RelType).

action_contradicts_relationship(Action, RelType) :-
    action_contradicts_positive(Action),
    is_positive_relationship(RelType).

% VIOLATION: Action contradicts relationship rule
violation(emotional, relationship_action_mismatch, E, pair(Agent, Patient)) :-
    rule_active(emotional_relationship_action_mismatch),
    event(E),
    event_type(E, Action),
    agent(E, Agent),
    patient(E, Patient),
    relationship_rule(Agent, RelType, Patient, _),
    action_contradicts_relationship(Action, RelType).

% =============================================================================
% TRAIT VIOLATIONS
% =============================================================================

% Trait-action contradictions
% trait_contradicts_action(Trait, Action)
trait_contradicts_action(coward, attack).
trait_contradicts_action(coward, fight).
trait_contradicts_action(coward, challenge).
trait_contradicts_action(pacifist, attack).
trait_contradicts_action(pacifist, fight).
trait_contradicts_action(pacifist, kill).
trait_contradicts_action(honest, lie).
trait_contradicts_action(honest, deceive).
trait_contradicts_action(honest, cheat).

% VIOLATION: Action contradicts established trait
violation(emotional, trait_action_mismatch, E, pair(C, Trait)) :-
    rule_active(emotional_trait_action_mismatch),
    event(E),
    event_type(E, Action),
    agent(E, C),
    trait(C, Trait),
    trait_contradicts_action(Trait, Action).

% VIOLATION: Action contradicts trait rule
violation(emotional, trait_action_mismatch, E, pair(C, Trait)) :-
    rule_active(emotional_trait_action_mismatch),
    event(E),
    event_type(E, Action),
    agent(E, C),
    trait_rule(C, Trait, _),
    trait_contradicts_action(Trait, Action).

% =============================================================================
% EMOTIONAL STATE TRACKING (Time-Indexed)
% =============================================================================

% Track emotional states using fluents
% holds(emotion(C, Emotion), T) - character's emotion at time T
emotion(C, Emo, T) :- holds(emotion(C, Emo), T).

% Initialize emotions
initially(emotion(C, Emo)) :- initial_emotion(C, Emo).

% Events can change emotions
initiates(E, emotion(C, NewEmo)) :-
    event(E),
    event_emotion(E, NewEmo),
    agent(E, C).

terminates(E, emotion(C, OldEmo)) :-
    event(E),
    event_emotion(E, NewEmo),
    agent(E, C),
    event_time(E, T),
    emotion(C, OldEmo, T),
    OldEmo != NewEmo.

% Emotional shift tracking (informational)
emotional_shift(C, T1, T2, From, To) :-
    emotion(C, From, T1),
    emotion(C, To, T2),
    next_time(T1, T2),
    From != To.
