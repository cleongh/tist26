% =============================================================================
%
%    STORY-SPECIFIC DYNAMIC RULES
%    =============================
%
%    These rules handle DYNAMIC story state that is modified by events.
%    General rules (simple_narrative.lp) remain static and universal.
%
%    This module detects when an action contradicts an established rule
%    WITHOUT a valid modifier event occurring in between.
%
%    RULE TYPES:
%    - relationship_rule(Subject, Predicate, Object, EstablishedBy)
%      e.g., relationship_rule(uncle_vernon, hates, harry_potter, e0).
%
%    - trait_rule(Character, Trait, EstablishedBy)
%      e.g., trait_rule(uncle_vernon, cruel, e0).
%
%    - possession_rule(Character, Item, EstablishedBy)
%      e.g., possession_rule(harry_potter, wand, e15).
%
%    - location_rule(Character, Location, EstablishedBy)
%      e.g., location_rule(harry_potter, hogwarts, e20).
%
%    EVENT FORMAT:
%    - event_global(EventId, Type, Chapter)
%      e.g., event_global(e7, congratulates, 2).
%
%    - event_source(EventId, SourceText)
%      e.g., event_source(e7, "Vernon smiled warmly...").
%
% =============================================================================


% =============================================================================
% ACTION-RELATIONSHIP CONTRADICTIONS
% =============================================================================
% Define which actions contradict which relationship predicates.
% If someone hates another, they shouldn't congratulate them (without reason).

% Actions that contradict HATE/HOSTILE relationships
action_contradicts_relationship(congratulates, hates).
action_contradicts_relationship(congratulate, hates).
action_contradicts_relationship(thanks, hates).
action_contradicts_relationship(thank, hates).
action_contradicts_relationship(hugs, hates).
action_contradicts_relationship(hug, hates).
action_contradicts_relationship(kisses, hates).
action_contradicts_relationship(kiss, hates).
action_contradicts_relationship(helps, hates).
action_contradicts_relationship(help, hates).
action_contradicts_relationship(comforts, hates).
action_contradicts_relationship(comfort, hates).
action_contradicts_relationship(praises, hates).
action_contradicts_relationship(praise, hates).
action_contradicts_relationship(gifts, hates).
action_contradicts_relationship(gift, hates).
action_contradicts_relationship(protects, hates).
action_contradicts_relationship(protect, hates).
action_contradicts_relationship(saves, hates).
action_contradicts_relationship(save, hates).
action_contradicts_relationship(cares_for, hates).
action_contradicts_relationship(care_for, hates).
action_contradicts_relationship(smiles_warmly_at, hates).
action_contradicts_relationship(smile_warmly, hates).
action_contradicts_relationship(warm_smile, hates).
action_contradicts_relationship(sad_farewell, hates).
action_contradicts_relationship(farewell, hates).
% NEW: Additional affectionate/positive actions
action_contradicts_relationship(warm_farewell, hates).
action_contradicts_relationship(kind_words, hates).
action_contradicts_relationship(smile, hates).
action_contradicts_relationship(smiles, hates).
action_contradicts_relationship(wave, hates).
action_contradicts_relationship(waves, hates).
action_contradicts_relationship(encourage, hates).
action_contradicts_relationship(encourages, hates).
action_contradicts_relationship(wish_well, hates).
action_contradicts_relationship(wishes_well, hates).
action_contradicts_relationship(support, hates).
action_contradicts_relationship(supports, hates).
action_contradicts_relationship(embrace, hates).
action_contradicts_relationship(embraces, hates).
action_contradicts_relationship(welcome, hates).
action_contradicts_relationship(welcomes, hates).
action_contradicts_relationship(apologize, hates).
action_contradicts_relationship(apologizes, hates).
action_contradicts_relationship(forgive, hates).
action_contradicts_relationship(forgives, hates).
action_contradicts_relationship(cheer, hates).
action_contradicts_relationship(cheers, hates).
action_contradicts_relationship(bless, hates).
action_contradicts_relationship(blesses, hates).
action_contradicts_relationship(compliment, hates).
action_contradicts_relationship(compliments, hates).

% Actions that contradict HOSTILE relationships
action_contradicts_relationship(congratulates, hostile).
action_contradicts_relationship(thanks, hostile).
action_contradicts_relationship(hugs, hostile).
action_contradicts_relationship(hug, hostile).
action_contradicts_relationship(helps, hostile).
action_contradicts_relationship(help, hostile).
action_contradicts_relationship(comforts, hostile).
action_contradicts_relationship(comfort, hostile).
action_contradicts_relationship(praises, hostile).
action_contradicts_relationship(praise, hostile).
action_contradicts_relationship(protects, hostile).
action_contradicts_relationship(protect, hostile).
action_contradicts_relationship(saves, hostile).
action_contradicts_relationship(save, hostile).
% NEW: Additional affectionate/positive actions for hostile
action_contradicts_relationship(farewell, hostile).
action_contradicts_relationship(warm_farewell, hostile).
action_contradicts_relationship(kind_words, hostile).
action_contradicts_relationship(smile, hostile).
action_contradicts_relationship(smiles, hostile).
action_contradicts_relationship(wave, hostile).
action_contradicts_relationship(waves, hostile).
action_contradicts_relationship(encourage, hostile).
action_contradicts_relationship(encourages, hostile).
action_contradicts_relationship(wish_well, hostile).
action_contradicts_relationship(wishes_well, hostile).
action_contradicts_relationship(support, hostile).
action_contradicts_relationship(supports, hostile).
action_contradicts_relationship(embrace, hostile).
action_contradicts_relationship(embraces, hostile).
action_contradicts_relationship(welcome, hostile).
action_contradicts_relationship(welcomes, hostile).
action_contradicts_relationship(kiss, hostile).
action_contradicts_relationship(kisses, hostile).

% Actions that contradict LOVE/FRIENDLY relationships
action_contradicts_relationship(attacks, loves).
action_contradicts_relationship(attack, loves).
action_contradicts_relationship(insults, loves).
action_contradicts_relationship(insult, loves).
action_contradicts_relationship(betrays, loves).
action_contradicts_relationship(betray, loves).
action_contradicts_relationship(abandons, loves).
action_contradicts_relationship(abandon, loves).
action_contradicts_relationship(hurts, loves).
action_contradicts_relationship(hurt, loves).
action_contradicts_relationship(kills, loves).
action_contradicts_relationship(kill, loves).
action_contradicts_relationship(curses, loves).
action_contradicts_relationship(curse, loves).

action_contradicts_relationship(attacks, friendly).
action_contradicts_relationship(insults, friendly).
action_contradicts_relationship(betrays, friendly).
action_contradicts_relationship(abandons, friendly).
action_contradicts_relationship(hurts, friendly).

% Actions that contradict FEAR relationships (from fearful party)
action_contradicts_relationship(confronts, fears).
action_contradicts_relationship(challenges, fears).
action_contradicts_relationship(attacks, fears).

% Actions that contradict TRUSTS relationships
action_contradicts_relationship(betrays, trusts).
action_contradicts_relationship(deceives, trusts).
action_contradicts_relationship(lies_to, trusts).
action_contradicts_relationship(steals_from, trusts).


% =============================================================================
% ACTION-TRAIT CONTRADICTIONS
% =============================================================================
% Actions that contradict established character traits.

action_contradicts_trait(helps, cruel).
action_contradicts_trait(comforts, cruel).
action_contradicts_trait(cares_for, cruel).
action_contradicts_trait(smiles_warmly, cruel).

action_contradicts_trait(hurts, kind).
action_contradicts_trait(attacks, kind).
action_contradicts_trait(insults, kind).
action_contradicts_trait(cruel_to, kind).

action_contradicts_trait(brave_action, cowardly).
action_contradicts_trait(confronts, cowardly).
action_contradicts_trait(stands_up_to, cowardly).

action_contradicts_trait(flees, brave).
action_contradicts_trait(cowers, brave).
action_contradicts_trait(hides_from, brave).


% =============================================================================
% MODIFIER EVENTS - PREDEFINED
% =============================================================================
% Events that can legitimately change a relationship from negative to positive.

positive_modifier(forgive).
positive_modifier(forgives).
positive_modifier(reconcile).
positive_modifier(reconciles).
positive_modifier(apologize).
positive_modifier(apologizes).
positive_modifier(apology).
positive_modifier(make_peace).
positive_modifier(makes_peace).
positive_modifier(befriend).
positive_modifier(befriends).
positive_modifier(accept).
positive_modifier(accepts).
positive_modifier(warm_up_to).
positive_modifier(warms_up_to).
positive_modifier(save).  % Saving someone can change the relationship
positive_modifier(saves).
positive_modifier(rescue).
positive_modifier(rescues).

% Events that can legitimately change a relationship from positive to negative.
negative_modifier(betray).
negative_modifier(betrays).
negative_modifier(attack).
negative_modifier(attacks).
negative_modifier(insult).
negative_modifier(insults).
negative_modifier(abandon).
negative_modifier(abandons).
negative_modifier(deceive).
negative_modifier(deceives).
negative_modifier(hurt).
negative_modifier(hurts).
negative_modifier(steal_from).
negative_modifier(steals_from).
negative_modifier(lie_to).
negative_modifier(lies_to).
negative_modifier(reject).
negative_modifier(rejects).

% ILASP-learnable modifier placeholder
% learned_positive_modifier(EventType).
% learned_negative_modifier(EventType).


% =============================================================================
% PREDICATE CLASSIFICATION
% =============================================================================

is_negative_predicate(hates).
is_negative_predicate(hate).
is_negative_predicate(hostile).
is_negative_predicate(enemy).
is_negative_predicate(enemies).
is_negative_predicate(fears).
is_negative_predicate(fear).
is_negative_predicate(despises).
is_negative_predicate(despise).
is_negative_predicate(dislikes).
is_negative_predicate(dislike).
is_negative_predicate(resents).
is_negative_predicate(resent).

is_positive_predicate(loves).
is_positive_predicate(love).
is_positive_predicate(friendly).
is_positive_predicate(friend).
is_positive_predicate(friends).
is_positive_predicate(family).
is_positive_predicate(trusts).
is_positive_predicate(trust).
is_positive_predicate(likes).
is_positive_predicate(like).
is_positive_predicate(respects).
is_positive_predicate(respect).
is_positive_predicate(admires).
is_positive_predicate(admire).
is_positive_predicate(cares_for).
is_positive_predicate(care_for).


% =============================================================================
% EVENT ID COMPARISON
% =============================================================================
% Extract numeric part of event IDs for comparison.
% Event IDs are in format: e1, e2, e3, ..., e100, etc.

% We define event ordering based on the numeric suffix
% This requires events to be declared with event_order/2 from Python
% event_order(e1, 1). event_order(e2, 2). etc.

event_before(E1, E2) :-
    event_order(E1, N1),
    event_order(E2, N2),
    N1 < N2.

event_after(E1, E2) :- event_before(E2, E1).

event_between(E, E1, E2) :-
    event_before(E1, E),
    event_before(E, E2).


% =============================================================================
% VIOLATION: ACTION CONTRADICTS ESTABLISHED RELATIONSHIP RULE
% =============================================================================
% Detect when an action contradicts an established relationship
% WITHOUT a valid modifier event occurring in between.

violation(rule_contradiction, relationship_action_mismatch, EventId, 
          pair(Agent, Patient)) :-
    event_global(EventId, ActionType, _),
    agent(EventId, Agent),
    patient(EventId, Patient),
    relationship_rule(Agent, RulePredicate, Patient, EstablishedBy),
    action_contradicts_relationship(ActionType, RulePredicate),
    event_before(EstablishedBy, EventId),
    not has_positive_modifier_between(Agent, Patient, EstablishedBy, EventId),
    is_negative_predicate(RulePredicate).

% Also check for negative actions against positive relationships
violation(rule_contradiction, relationship_action_mismatch, EventId,
          pair(Agent, Patient)) :-
    event_global(EventId, ActionType, _),
    agent(EventId, Agent),
    patient(EventId, Patient),
    relationship_rule(Agent, RulePredicate, Patient, EstablishedBy),
    action_contradicts_relationship(ActionType, RulePredicate),
    event_before(EstablishedBy, EventId),
    not has_negative_modifier_between(Agent, Patient, EstablishedBy, EventId),
    is_positive_predicate(RulePredicate).


% =============================================================================
% VIOLATION: ACTION CONTRADICTS ESTABLISHED TRAIT RULE
% =============================================================================

violation(rule_contradiction, trait_action_mismatch, EventId,
          pair(Agent, Trait)) :-
    event_global(EventId, ActionType, _),
    agent(EventId, Agent),
    trait_rule(Agent, Trait, EstablishedBy),
    action_contradicts_trait(ActionType, Trait),
    event_before(EstablishedBy, EventId),
    not has_trait_modifier_between(Agent, Trait, EstablishedBy, EventId).


% =============================================================================
% MODIFIER DETECTION
% =============================================================================
% Check if there's a modifier event between rule establishment and current event.

has_positive_modifier_between(Agent, Patient, EstablishedBy, CurrentEvent) :-
    event_global(ModifierId, ModType, _),
    agent(ModifierId, Agent),
    patient(ModifierId, Patient),
    event_between(ModifierId, EstablishedBy, CurrentEvent),
    positive_modifier(ModType).

% Also check if Patient did something positive to Agent (bidirectional)
has_positive_modifier_between(Agent, Patient, EstablishedBy, CurrentEvent) :-
    event_global(ModifierId, ModType, _),
    agent(ModifierId, Patient),
    patient(ModifierId, Agent),
    event_between(ModifierId, EstablishedBy, CurrentEvent),
    positive_modifier(ModType).

has_negative_modifier_between(Agent, Patient, EstablishedBy, CurrentEvent) :-
    event_global(ModifierId, ModType, _),
    agent(ModifierId, Agent),
    patient(ModifierId, Patient),
    event_between(ModifierId, EstablishedBy, CurrentEvent),
    negative_modifier(ModType).

has_negative_modifier_between(Agent, Patient, EstablishedBy, CurrentEvent) :-
    event_global(ModifierId, ModType, _),
    agent(ModifierId, Patient),
    patient(ModifierId, Agent),
    event_between(ModifierId, EstablishedBy, CurrentEvent),
    negative_modifier(ModType).

% Trait modifiers (character undergoes significant change)
% Note: Trait is ignored here - any transformation/development event counts as a modifier
has_trait_modifier_between(Character, Trait, EstablishedBy, CurrentEvent) :-
    event_global(ModifierId, transformation, _),
    agent(ModifierId, Character),
    event_between(ModifierId, EstablishedBy, CurrentEvent),
    trait_rule(Character, Trait, _).  % Bind Trait to an existing trait

has_trait_modifier_between(Character, Trait, EstablishedBy, CurrentEvent) :-
    event_global(ModifierId, character_development, _),
    agent(ModifierId, Character),
    event_between(ModifierId, EstablishedBy, CurrentEvent),
    trait_rule(Character, Trait, _).  % Bind Trait to an existing trait


% =============================================================================
% LOCATION RULES AND VIOLATIONS
% =============================================================================
% Track where characters are located and detect location contradictions.
%
% location_rule(Character, Location, EstablishedBy)
%   - Character is at Location, established by event EstablishedBy
%   - Updated by travel/move events
%
% Violations:
% - Character acts at location X when last known at location Y (without travel)
% - Character interacts with someone at different location (without remote action)

% --- Movement event types ---
is_movement_type(travel).
is_movement_type(travels).
is_movement_type(move).
is_movement_type(moves).
is_movement_type(go).
is_movement_type(goes).
is_movement_type(walk).
is_movement_type(walks).
is_movement_type(run).
is_movement_type(runs).
is_movement_type(fly).
is_movement_type(flies).
is_movement_type(drive).
is_movement_type(drives).
is_movement_type(arrive).
is_movement_type(arrives).
is_movement_type(enter).
is_movement_type(enters).
is_movement_type(leave).
is_movement_type(leaves).
is_movement_type(depart).
is_movement_type(departs).
is_movement_type(apparate).
is_movement_type(apparates).
is_movement_type(teleport).
is_movement_type(teleports).
is_movement_type(return).
is_movement_type(returns).

% --- Remote action types (don't require co-location) ---
is_remote_type(call).
is_remote_type(calls).
is_remote_type(phone).
is_remote_type(phones).
is_remote_type(message).
is_remote_type(messages).
is_remote_type(letter).
is_remote_type(write).
is_remote_type(writes).
is_remote_type(send).
is_remote_type(sends).
is_remote_type(telepathy).
is_remote_type(think).
is_remote_type(thinks).
is_remote_type(remember).
is_remote_type(remembers).
is_remote_type(dream).
is_remote_type(dreams).

% --- Check if event is a movement event ---
is_movement_event(E) :-
    event_global(E, Type, _),
    is_movement_type(Type).

% --- Check if event is a remote action ---
is_remote_event(E) :-
    event_global(E, Type, _),
    is_remote_type(Type).

% --- Movement events update location (detected via location/2 predicate) ---
has_movement_between(Character, EstablishedBy, CurrentEvent) :-
    event_global(MovementId, MovementType, _),
    agent(MovementId, Character),
    event_between(MovementId, EstablishedBy, CurrentEvent),
    is_movement_type(MovementType).

% --- VIOLATION: Character acts at wrong location ---
% Character performs action at location X but was last known at Y
% Only trigger if no movement event occurred between
% NEW: Only trigger within the SAME CHAPTER to reduce cross-chapter false positives
violation(location, wrong_location, EventId, pair(Character, pair(ExpectedLoc, ActualLoc))) :-
    event_global(EventId, ActionType, ChapterNum),
    agent(EventId, Character),
    location(EventId, ActualLoc),
    location_rule(Character, ExpectedLoc, EstablishedBy),
    ActualLoc != ExpectedLoc,
    ActualLoc != unknown,
    ExpectedLoc != unknown,
    event_before(EstablishedBy, EventId),
    not has_movement_between(Character, EstablishedBy, EventId),
    not is_movement_event(EventId),
    not is_remote_event(EventId),
    % NEW: Only flag if rule was established in same chapter (reduce cross-chapter noise)
    event_global(EstablishedBy, _, EstChapter),
    ChapterNum = EstChapter.

% Fallback for e0 (initial state): only trigger if location_rule was from chapter 0
violation(location, wrong_location, EventId, pair(Character, pair(ExpectedLoc, ActualLoc))) :-
    event_global(EventId, ActionType, ChapterNum),
    agent(EventId, Character),
    location(EventId, ActualLoc),
    location_rule(Character, ExpectedLoc, e0),
    ActualLoc != ExpectedLoc,
    ActualLoc != unknown,
    ExpectedLoc != unknown,
    not has_movement_between(Character, e0, EventId),
    not is_movement_event(EventId),
    not is_remote_event(EventId),
    ChapterNum = 0.  % Only in first chapter

% --- VIOLATION: Interaction across locations ---
% Character A interacts with Character B, but they're at different locations
% (and it's not a remote action type)
% NEW: Only trigger within the SAME CHAPTER
violation(location, interaction_across_locations, EventId, pair(Agent, Patient)) :-
    event_global(EventId, ActionType, ChapterNum),
    agent(EventId, Agent),
    patient(EventId, Patient),
    character(Patient),
    location_rule(Agent, AgentLoc, EstablishedByA),
    location_rule(Patient, PatientLoc, EstablishedByP),
    AgentLoc != PatientLoc,
    AgentLoc != unknown,
    PatientLoc != unknown,
    event_before(EstablishedByA, EventId),
    event_before(EstablishedByP, EventId),
    not has_movement_between(Agent, EstablishedByA, EventId),
    not has_movement_between(Patient, EstablishedByP, EventId),
    not is_remote_event(EventId),
    not is_movement_event(EventId),
    % NEW: Both rules must be from same chapter as event
    event_global(EstablishedByA, _, ChapterNum),
    event_global(EstablishedByP, _, ChapterNum).


% =============================================================================
% TEMPORAL CONSTRAINT RULES AND VIOLATIONS
% =============================================================================
% Track temporal ordering constraints and detect when events violate them.
%
% temporal_rule(EventTypeA, must_precede, EventTypeB, EstablishedBy)
%   - EventTypeA must happen before EventTypeB
%   - E.g., receive_letter must_precede read_letter
%
% temporal_rule(EventTypeA, must_follow, EventTypeB, EstablishedBy)
%   - EventTypeA must happen after EventTypeB
%
% Violations:
% - Event B happens but A hasn't happened yet (prerequisite violation)
% - Event A happens after B when it should precede

% --- Prerequisite event types ---
% These are common patterns where one action requires another first
% Multiple prerequisite options are grouped - ANY ONE satisfies the requirement

% Action type groups - defines which actions have prerequisite requirements
action_needs_prerequisite(read).
action_needs_prerequisite(reads).
action_needs_prerequisite(use).
action_needs_prerequisite(uses).
action_needs_prerequisite(reply).
action_needs_prerequisite(replies).
action_needs_prerequisite(answer).
action_needs_prerequisite(answers).
action_needs_prerequisite(open).
action_needs_prerequisite(opens).
action_needs_prerequisite(wear).
action_needs_prerequisite(wears).
action_needs_prerequisite(eat).
action_needs_prerequisite(drink).

% Prerequisite options - ANY of these satisfies the action requirement
% Reading requires receiving/finding/discovering first
prereq_option(read, receive).
prereq_option(read, find).
prereq_option(read, discover).
prereq_option(read, get).
prereq_option(reads, receives).
prereq_option(reads, finds).
prereq_option(reads, discovers).

% Using requires having/getting first
prereq_option(use, get).
prereq_option(use, receive).
prereq_option(use, find).
prereq_option(use, buy).
prereq_option(uses, gets).
prereq_option(uses, receives).

% Replying requires receiving message first
prereq_option(reply, receive).
prereq_option(replies, receives).
prereq_option(answer, ask).
prereq_option(answers, asks).

% Opening requires approaching/having access
prereq_option(open, approach).
prereq_option(open, find).
prereq_option(opens, approaches).
prereq_option(opens, finds).

% Wearing requires getting/buying first
prereq_option(wear, get).
prereq_option(wear, buy).
prereq_option(wear, receive).
prereq_option(wears, gets).

% Eating/drinking requires getting/preparing
prereq_option(eat, get).
prereq_option(eat, cook).
prereq_option(eat, prepare).
prereq_option(drink, get).
prereq_option(drink, pour).

% --- Check if ANY prerequisite option was satisfied ---
has_any_prerequisite_satisfied(EventId, Patient) :-
    event_global(EventId, ActionType, _),
    patient(EventId, Patient),
    prereq_option(ActionType, PrereqType),
    event_global(PrereqId, PrereqType, _),
    patient(PrereqId, Patient),
    event_before(PrereqId, EventId).

% Also check if agent did the prerequisite (for self-actions)
has_any_prerequisite_satisfied(EventId, Patient) :-
    event_global(EventId, ActionType, _),
    agent(EventId, Agent),
    patient(EventId, Patient),
    prereq_option(ActionType, PrereqType),
    event_global(PrereqId, PrereqType, _),
    agent(PrereqId, Agent),
    patient(PrereqId, Patient),
    event_before(PrereqId, EventId).

% --- VIOLATION: Missing prerequisite ---
% Action requires a prerequisite but NONE of the acceptable options occurred
% Only flag in modified stories to avoid false positives
violation(temporal, missing_prerequisite, EventId, pair(ActionType, Patient)) :-
    modified_story,
    event_global(EventId, ActionType, _),
    patient(EventId, Patient),
    action_needs_prerequisite(ActionType),
    not has_any_prerequisite_satisfied(EventId, Patient).

% --- Explicit temporal constraints from story ---
% temporal_rule(EventA, must_precede, EventB, e0) means A must happen before B
% These are extracted from narrative statements like "before he could X, he had to Y"

violation(temporal, explicit_order_violated, EventB, pair(EventA, EventB)) :-
    modified_story,
    temporal_rule(TypeA, must_precede, TypeB, _),
    event_global(EventA, TypeA, _),
    event_global(EventB, TypeB, _),
    event_before(EventB, EventA).  % B happened before A, violating constraint

% NOTE: was originally a purely global existence check (not event_of_type_
% exists(TypeA)) -- since temporal_rule was LEARNED per-agent (every agent
% who does TypeB also does TypeA first), checking existence for the WHOLE
% story is far too blunt: if even one unrelated character ever performs
% TypeA, this could never fire for anyone; conversely if TypeA is simply
% absent from these particular modified chapters for reasons unrelated to
% any real error (natural extraction variance), it fires for every single
% TypeB instance regardless of agent. Scoping to the SAME agent performing
% TypeB matches how the rule was learned and is a much sharper signal.
agent_has_type_event(Agent, Type) :-
    event_global(E, Type, _),
    agent(E, Agent).

% Absence of a single action type is weak evidence for a minor/one-off
% character (who may simply never get much narrative attention at all) --
% it's only meaningful for characters established enough to have a real
% track record in this story. Gate on overall activity (any event types,
% not just TypeA/TypeB) rather than any one specific verb, so this stays
% generic and isn't tuned to any particular action vocabulary.
agent_activity_count(Agent, N) :-
    character(Agent),
    N = #count { E : event_global(E, _, _), agent(E, Agent) }.

violation(temporal, prerequisite_not_met, EventB, pair(TypeA, TypeB)) :-
    modified_story,
    temporal_rule(TypeA, must_precede, TypeB, _),
    event_global(EventB, TypeB, _),
    agent(EventB, Agent),
    agent_activity_count(Agent, N),
    N >= 3,
    not agent_has_type_event(Agent, TypeA).

event_of_type_exists(Type) :- event_global(_, Type, _).


% =============================================================================
% POSSESSION RULES AND VIOLATIONS
% =============================================================================
% Track what characters possess and detect possession contradictions.
%
% possession_rule(Character, Item, EstablishedBy)
%   - Character possesses Item, established by event EstablishedBy
%
% Violations:
% - Character uses item they don't possess (without acquiring it)
% - Character gives away item they don't have

% --- Acquisition event types ---
is_acquisition_type(get).
is_acquisition_type(gets).
is_acquisition_type(receive).
is_acquisition_type(receives).
is_acquisition_type(find).
is_acquisition_type(finds).
is_acquisition_type(discover).
is_acquisition_type(discovers).
is_acquisition_type(buy).
is_acquisition_type(buys).
is_acquisition_type(take).
is_acquisition_type(takes).
is_acquisition_type(steal).
is_acquisition_type(steals).
is_acquisition_type(pick_up).
is_acquisition_type(picks_up).
is_acquisition_type(grab).
is_acquisition_type(grabs).
is_acquisition_type(inherit).
is_acquisition_type(inherits).

% --- Loss event types ---
is_loss_type(give).
is_loss_type(gives).
is_loss_type(lose).
is_loss_type(loses).
is_loss_type(drop).
is_loss_type(drops).
is_loss_type(sell).
is_loss_type(sells).
is_loss_type(destroy).
is_loss_type(destroys).
is_loss_type(throw).
is_loss_type(throws).
is_loss_type(discard).
is_loss_type(discards).

% --- Use event types (require possession) ---
is_use_type(use).
is_use_type(uses).
is_use_type(wield).
is_use_type(wields).
is_use_type(wear).
is_use_type(wears).
is_use_type(read).
is_use_type(reads).
is_use_type(open).
is_use_type(opens).
is_use_type(eat).
is_use_type(eats).
is_use_type(drink).
is_use_type(drinks).

% --- Check for acquisition between events ---
has_acquisition_between(Character, Item, EstablishedBy, CurrentEvent) :-
    event_global(AcqId, AcqType, _),
    agent(AcqId, Character),
    patient(AcqId, Item),
    event_between(AcqId, EstablishedBy, CurrentEvent),
    is_acquisition_type(AcqType).

% NEW: Track if item has been possessed by ANYONE before
% This helps identify "first mention" items that shouldn't trigger violations
item_previously_possessed(Item, EventId) :-
    possession_rule(_, Item, EstBy),
    event_before(EstBy, EventId).

item_previously_possessed(Item, EventId) :-
    event_global(AcqId, AcqType, _),
    patient(AcqId, Item),
    is_acquisition_type(AcqType),
    event_before(AcqId, EventId).

% NEW: Check if this is first action involving the item (allow implicit possession)
is_first_item_use(EventId, Item) :-
    event_global(EventId, _, _),
    patient(EventId, Item),
    item(Item),
    not item_previously_possessed(Item, EventId).

% --- VIOLATION: Using item without possession ---
% Character uses item but doesn't have possession_rule for it
% and hasn't acquired it since e0
% NEW: Only trigger if item was previously possessed by someone (not first mention)
violation(possession, use_without_having, EventId, pair(Character, Item)) :-
    event_global(EventId, ActionType, _),
    agent(EventId, Character),
    patient(EventId, Item),
    item(Item),
    is_use_type(ActionType),
    not possession_rule(Character, Item, _),
    not has_acquisition_between(Character, Item, e0, EventId),
    item_previously_possessed(Item, EventId).  % NEW: Only if someone else had it

% --- VIOLATION: Giving item you don't have ---
% NEW: Only trigger if item was previously possessed by someone else
violation(possession, give_without_having, EventId, pair(Character, Item)) :-
    event_global(EventId, ActionType, _),
    agent(EventId, Character),
    patient(EventId, Item),
    item(Item),
    is_loss_type(ActionType),
    not possession_rule(Character, Item, _),
    not has_acquisition_between(Character, Item, e0, EventId),
    item_previously_possessed(Item, EventId).  % NEW: Only if someone else had it


% =============================================================================
% HARRY POTTER CANONICAL EVENT EXCEPTIONS
% =============================================================================
%
% These exceptions suppress violations for events that are CANONICAL in the
% original Harry Potter story. These events appear to violate relationship
% rules (friends attacking/reporting friends) but are actually valid plot points:
%
% 1. Hermione reports Harry & Ron to professors (Chapter 9) - she does this
%    out of concern for their safety when they go after the troll.
%
% 2. Hermione petrifies Neville (Chapter 15) - she uses Petrificus Totalus
%    to stop him from preventing them from going after the Philosopher's Stone.
%
% These are NOT errors - they are character-consistent actions where a friend
% takes an apparently hostile action for protective/greater-good reasons.
%
% =============================================================================

% Hermione's protective report (going after the troll)
story_exception(relationship_betrayal, E) :-
    event(E),
    report(E),
    agent(E, hermione_granger),
    patient(E, harry_potter).

story_exception(relationship_betrayal, E) :-
    event(E),
    report(E),
    agent(E, hermione_granger),
    patient(E, ron_weasley).

% Hermione's protective attack on Neville (Petrificus Totalus)
story_exception(relationship_action_mismatch, E) :-
    event(E),
    event_type(E, attack),
    agent(E, hermione_granger),
    patient(E, neville_longbottom).


% =============================================================================
% HOGWARTS LOCATION HIERARCHY
% =============================================================================
% Define the containment structure of Hogwarts to enable location violation detection
%
% Locations that are FAR APART should not be reachable without travel
% Dungeons and Dormitories (towers) are on opposite ends of the castle

is_location(hogwarts).
is_location(dungeons).
is_location(dungeon).
is_location(potions_classroom).
is_location(slytherin_common_room).
is_location(gryffindor_tower).
is_location(gryffindor_dormitory).
is_location(dormitory).
is_location(great_hall).
is_location(library).
is_location(astronomy_tower).
is_location(hagrid_house).
is_location(forbidden_forest).
is_location(hospital_wing).
is_location(headmasters_office).
is_location(quidditch_pitch).

% Containment - everything is in Hogwarts (or grounds)
contains(hogwarts, dungeons).
contains(hogwarts, dungeon).
contains(hogwarts, potions_classroom).
contains(hogwarts, gryffindor_tower).
contains(hogwarts, gryffindor_dormitory).
contains(hogwarts, dormitory).
contains(hogwarts, great_hall).
contains(hogwarts, library).
contains(hogwarts, astronomy_tower).
contains(hogwarts, hospital_wing).
contains(hogwarts, headmasters_office).

% Dungeons contain potions classroom
contains(dungeons, potions_classroom).
contains(dungeons, slytherin_common_room).

% Gryffindor tower contains dormitory
contains(gryffindor_tower, gryffindor_dormitory).

% Outside hogwarts main building
contains(hogwarts_grounds, hagrid_house).
contains(hogwarts_grounds, forbidden_forest).
contains(hogwarts_grounds, quidditch_pitch).

% DISJOINT LOCATIONS - dungeons and towers are far apart
% Characters cannot instantly access items in distant locations
disjoint_castle_areas(dungeons, gryffindor_tower).
disjoint_castle_areas(dungeons, dormitory).
disjoint_castle_areas(dungeons, gryffindor_dormitory).
disjoint_castle_areas(dungeon, gryffindor_tower).
disjoint_castle_areas(dungeon, dormitory).
disjoint_castle_areas(dungeon, gryffindor_dormitory).
disjoint_castle_areas(astronomy_tower, dungeons).
disjoint_castle_areas(astronomy_tower, dungeon).

% Make symmetric
disjoint_castle_areas(A, B) :- disjoint_castle_areas(B, A).

% VIOLATION: Character interacts with item at a disjoint location
% This catches cases where someone in the dungeons reaches for items in dormitory
violation(location, impossible_access, 
          violation_info(Character, at, Loc1, reaches_item_at, Loc2, in_event, E)) :-
    event(E),
    event_time(E, T),
    agent(E, Character),
    explicit_presence(Character, Loc1, T, _),
    event_type(E, Type),
    uses_item_action(Type),
    event_location(E, Loc2),
    Loc2 != unknown,
    disjoint_castle_areas(Loc1, Loc2).

% Actions that involve using/accessing items
uses_item_action(take).
uses_item_action(get).
uses_item_action(reach).
uses_item_action(grab).
uses_item_action(use).
uses_item_action(pick_up).


% =============================================================================
% RULE OVERRIDES
% =============================================================================
% Disable rules that produce too many false positives on multi-chapter analysis

% The unexplained_relationship_change rule fires when relationships differ
% between chapters due to extraction differences, not actual narrative errors
story_override(unexplained_relationship_change).


% =============================================================================
% OUTPUT CONTROL
% =============================================================================

#show violation/4.
