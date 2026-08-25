% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - EMOTIONAL/RELATIONSHIP (v3.1)
%    ========================================================================
%
%    ERROR CATEGORY: EMOTIONAL
%    -------------------------
%    Per docs/ILASP_INTEGRATION.md:
%        "Sudden mood swings without trigger"
%
%    All violations produced by this file are in the EMOTIONAL category.
%    Violations are structured as: violation(emotional, TYPE, VIOLATION_INFO)
%
%    Evidence-gated emotional and relationship rules.
%    Violations fire ONLY when explicit evidence exists.
%
%    Per LOGIC_DESIGN.md Section 3.2:
%        relationship(Character1, Character2, Type, Time) tracks relationships.
%
%    VERSION 2.0: Uses time-indexed fluents, rule registration
%    VERSION 3.0: Phase Five - Evidence-gated violations
%    VERSION 3.1: Added ERROR CATEGORY documentation for consistency audit
%
%    PHASE FIVE REQUIREMENTS:
%        1. Emotional violations fire ONLY when:
%           - relationship is explicitly established BEFORE the event
%           - action contradicts that relationship
%        2. No violations when:
%           - relationship data is missing for that time
%           - characters are interacting for the first time
%        3. Relationship changes require:
%           - explicit event or rule override
%        4. All violations attach:
%           - triggering event ID
%           - relationship state at that time
%
%    EMOTIONAL VIOLATIONS PRODUCED:
%        - relationship_action_mismatch: Actions contradict established relationships
%        - trait_action_mismatch: Actions contradict established character traits
%        - unexplained_relationship_change: Relationships changed without causal event
%
%    RESULT:
%        - Emotional errors are rare, precise, and narratively meaningful
%        - Original story emotional noise drops toward zero
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(emotional_relationship_action_mismatch, universal, "Actions must be consistent with established relationships").
rule(emotional_relationship_betrayal, universal, "Reporting a friend or family member to authorities is betrayal").
rule(emotional_trait_action_mismatch, universal, "Actions must be consistent with character traits").
rule(emotional_unexplained_relationship_change, universal, "Relationships require events to change").
rule(emotional_learned_relationship_action_mismatch, universal, "Actions must be consistent with story-mined relationship-action compatibility patterns").

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
is_positive_relationship(love).  % Alias

% Negative relationship types
is_negative_relationship(hates).
is_negative_relationship(dislikes).
is_negative_relationship(distrusts).
is_negative_relationship(fears).
is_negative_relationship(hostile).
is_negative_relationship(enemy).
is_negative_relationship(rival).
is_negative_relationship(hate).  % Alias


% =============================================================================
% PART A: EXPLICIT RELATIONSHIP TRACKING (Phase Five)
% =============================================================================
%
% Relationships must be EXPLICITLY established before violations can fire.
% Implicit/assumed relationships do not trigger violations.
%
% =============================================================================

% --- Symmetric Relationship Types ---
% Certain relationships are inherently symmetric (if A is friends with B, B is friends with A)
symmetric_relationship_type(friendly).
symmetric_relationship_type(friend).
symmetric_relationship_type(ally).
symmetric_relationship_type(hostile).
symmetric_relationship_type(enemy).
symmetric_relationship_type(rival).
symmetric_relationship_type(family).

% Derive symmetric initial relationships
initial_relationship(C2, C1, Type) :-
    initial_relationship(C1, C2, Type),
    symmetric_relationship_type(Type),
    C1 != C2.

% Derive symmetric relationship facts
relationship(C2, C1, Type) :-
    relationship(C1, C2, Type),
    symmetric_relationship_type(Type),
    C1 != C2.

% --- Explicit Relationship Evidence ---
% A relationship is explicit if established by:
%   1. Initial relationship declaration
%   2. An event that creates/modifies the relationship
%   3. A story rule declaration

% Relationship explicitly established at time T
explicit_relationship(C1, C2, Type, T) :-
    initial_relationship(C1, C2, Type),
    T = 0.

explicit_relationship(C1, C2, Type, T) :-
    initial_relationship(C1, C2, Type),
    time(T),
    not relationship_changed_by(C1, C2, _, T).

explicit_relationship(C1, C2, Type, T) :-
    event(E),
    event_time(E, T_establish),
    creates_relationship(E, C1, C2, Type),
    time(T),
    T >= T_establish,
    not relationship_changed_after(C1, C2, T_establish, T).

explicit_relationship(C1, C2, Type, T) :-
    relationship_rule(C1, Type, C2, E),
    event_time(E, T_establish),
    time(T),
    T >= T_establish,
    not relationship_changed_after(C1, C2, T_establish, T).

% Track when relationship was changed by an event
relationship_changed_by(C1, C2, Type, T) :-
    event(E),
    event_time(E, T),
    changes_relationship(E, C1, C2, Type, _).

relationship_changed_by(C1, C2, Type, T) :-
    event(E),
    event_time(E, T),
    creates_relationship(E, C1, C2, Type).

% Relationship changed between establishment and current time
relationship_changed_after(C1, C2, T_establish, T) :-
    relationship_changed_by(C1, C2, _, T_change),
    time(T_establish),
    time(T),
    T_change > T_establish,
    T_change <= T.

% --- Relationship Established Before Event ---
% Key predicate: relationship existed BEFORE the event in question
relationship_established_before(C1, C2, Type, T_event, T_establish) :-
    explicit_relationship(C1, C2, Type, T_establish),
    time(T_event),
    T_establish < T_event.

% --- Earliest Establishment Time ---
% To avoid duplicate violations, we identify the earliest time a relationship
% was established.
% NOTE: computing this via #min over relationship_established_before/5 (as
% before) re-scans every T for every T_event pair -- an O(relationship_pairs
% * time^2) join. Chapters with many events (a large time/1 domain) and many
% relationships combine combinatorially and make grounding/solving extremely
% expensive, regardless of story. The earliest explicit-establishment time
% for a (C1, C2, Type) triple does not actually depend on T_event, so it can
% be computed ONCE per triple (an O(relationship_pairs * time) aggregate)
% and then just compared against each T_event, avoiding the T_event-indexed
% rescan entirely while keeping the same "first establishment" semantics.
first_explicit_relationship_time(C1, C2, Type, T_min) :-
    explicit_relationship(C1, C2, Type, _),
    T_min = #min { T : explicit_relationship(C1, C2, Type, T) }.

earliest_relationship_establishment(C1, C2, Type, T_event, T_min) :-
    first_explicit_relationship_time(C1, C2, Type, T_min),
    time(T_event),
    T_min < T_event.

% Convenience: Has any explicit relationship at time T
has_explicit_relationship(C1, C2, T) :-
    explicit_relationship(C1, C2, _, T).

% --- First Interaction Detection ---
% Characters interacting for the first time have no prior relationship
first_interaction(C1, C2, E) :-
    event(E),
    event_time(E, T),
    agent(E, C1),
    patient(E, C2),
    character(C1),
    character(C2),
    not has_prior_relationship(C1, C2, T),
    not has_prior_relationship(C2, C1, T),
    not has_prior_interaction(C1, C2, T).

% Prior relationship exists before time T
has_prior_relationship(C1, C2, T) :-
    explicit_relationship(C1, C2, _, T_prior),
    time(T),
    T_prior < T.

% Prior interaction exists (any event before this one)
has_prior_interaction(C1, C2, T) :-
    event(E),
    event_time(E, T_prior),
    time(T),
    T_prior < T,
    agent(E, C1),
    patient(E, C2).

has_prior_interaction(C1, C2, T) :-
    event(E),
    event_time(E, T_prior),
    time(T),
    T_prior < T,
    agent(E, C2),
    patient(E, C1).

% =============================================================================
% ACTION-RELATIONSHIP CONTRADICTIONS
% =============================================================================

% Actions that contradict negative relationships (friendly actions)
% NOTE: help/save/protect/heal/rescue removed - these can occur in survival contexts,
% professional situations (mentors), or between enemies forced to cooperate (common in HG/LOTR)
% Keeping only strong emotional signals: hug, kiss, gift, comfort, farewell, etc.
action_contradicts_negative(hug).
action_contradicts_negative(kiss).
action_contradicts_negative(gift).
action_contradicts_negative(praise).
action_contradicts_negative(comfort).
action_contradicts_negative(defend).
action_contradicts_negative(farewell).
action_contradicts_negative(congratulates).
% General warmth/affection verbs (not tied to any specific story's vocabulary)
action_contradicts_negative(smile).
action_contradicts_negative(embrace).
action_contradicts_negative(console).
action_contradicts_negative(reassure).
action_contradicts_negative(welcome).
action_contradicts_negative(caress).

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
action_contradicts_positive(kill).
action_contradicts_positive(murder).
action_contradicts_positive(poison).
action_contradicts_positive(deceive).
% General hostility/coldness verbs (not tied to any specific story's vocabulary)
action_contradicts_positive(scowl).
action_contradicts_positive(sneer).
action_contradicts_positive(mock).
action_contradicts_positive(ridicule).
action_contradicts_positive(scorn).
action_contradicts_positive(recoil).
% NOTE: "report" disabled - context-dependent (can be protective like Hermione protecting Harry)
% action_contradicts_positive(report).

% NOTE: "attack" disabled for friends - often defensive (Hermione petrifying Neville)
% attack is handled separately by is_protective_action checks


% =============================================================================
% PART B: EVIDENCE-GATED RELATIONSHIP VIOLATIONS (Phase Five)
% =============================================================================
%
% Violations fire ONLY when:
%   1. Relationship is EXPLICITLY established BEFORE the event
%   2. Action contradicts that relationship
%   3. No story override exists
%
% Violations DO NOT fire when:
%   - Relationship data is missing for that time
%   - Characters are interacting for the first time
%   - Story has overridden the relationship rule
%
% =============================================================================

% --- Pair Interaction Corroboration ---
% A single-chapter relationship tag (initial_relationship/relationship_rule)
% is a weak, easily-noisy signal on its own -- "not first_interaction" only
% requires ONE prior interaction/relationship fact. Require the pair to have
% interacted (in either direction) more than once before trusting a
% mismatch, so a one-off mislabeled relationship can't cascade into a
% mismatch violation against every later action for that pair.
pair_interaction_event(C1, C2, E) :- event(E), agent(E, C1), patient(E, C2).
pair_interaction_event(C1, C2, E) :- event(E), agent(E, C2), patient(E, C1).

pair_total_events(C1, C2, N) :-
    character(C1), character(C2), C1 != C2,
    N = #count { E : pair_interaction_event(C1, C2, E) }.

has_corroborated_relationship(C1, C2) :-
    pair_total_events(C1, C2, N),
    N >= 2.

% --- VIOLATION: Friendly Action Toward Explicit Enemy ---
% Uses explicit_relationship, NOT assumed relationship
% NOTE: Uses earliest_relationship_establishment to avoid duplicate violations
% NOTE: Only fires in modified stories to avoid false positives
violation(emotional, relationship_action_mismatch, 
          violation_info(E, agent, Agent, acted, Type, toward, Patient, 
                        despite, RelType, established_at, T_establish)) :-
    modified_story,
    rule_active(emotional_relationship_action_mismatch),
    event(E),
    event_time(E, T_event),
    event_type(E, Type),
    action_contradicts_negative(Type),
    agent(E, Agent),
    patient(E, Patient),
    earliest_relationship_establishment(Agent, Patient, RelType, T_event, T_establish),
    is_negative_relationship(RelType),
    has_corroborated_relationship(Agent, Patient),
    not first_interaction(Agent, Patient, E),
    not story_exception(relationship_action_mismatch, E).

% --- VIOLATION: Hostile Action Toward Explicit Ally ---
% NOTE: Uses earliest_relationship_establishment to avoid duplicate violations
% NOTE: Does NOT fire for defensive/protective actions (e.g., petrifying friend to stop them)
% NOTE: Does NOT fire for family members (siblings often fight without narrative error)
violation(emotional, relationship_action_mismatch, 
          violation_info(E, agent, Agent, acted, Type, toward, Patient, 
                        despite, RelType, established_at, T_establish)) :-
    modified_story,
    rule_active(emotional_relationship_action_mismatch),
    event(E),
    event_time(E, T_event),
    event_type(E, Type),
    action_contradicts_positive(Type),
    not is_protective_action(E),                 % NOT protective/defensive
    not is_family_conflict(Agent, Patient),      % NOT family squabbles
    agent(E, Agent),
    patient(E, Patient),
    earliest_relationship_establishment(Agent, Patient, RelType, T_event, T_establish),
    is_positive_relationship(RelType),
    RelType != family,                           % Exclude family relationships from attack violations
    has_corroborated_relationship(Agent, Patient),
    not first_interaction(Agent, Patient, E),
    not story_exception(relationship_action_mismatch, E).

% Family conflict exception - siblings fight, parents discipline
is_family_conflict(A, B) :- relationship(A, B, family).
is_family_conflict(A, B) :- initial_relationship(A, B, family).
is_family_conflict(A, B) :- family(A, B).

% Protective/defensive actions - not true hostile actions toward friends
% These are actions taken to protect the patient or others, even if harmful
is_protective_action(E) :- event_type(E, immobilize).
is_protective_action(E) :- event_type(E, restrain).
is_protective_action(E) :- event_type(E, petrify).
is_protective_action(E) :- event_type(E, stun).
is_protective_action(E) :- event_type(E, stop).

% --- VIOLATION: Friendly Social Action Toward Explicit Enemy ---
% Uses social_action/2 for explicit emotion-aware social actions
% Fires when a hostile relationship exists and agent performs a friendly social action
% NOTE: Uses earliest_relationship_establishment to avoid duplicate violations
violation(emotional, relationship_action_mismatch, 
          violation_info(E, agent, Agent, social_action, Action, toward, Patient, 
                        despite, RelType, established_at, T_establish)) :-
    modified_story,
    rule_active(emotional_relationship_action_mismatch),
    event(E),
    event_time(E, T_event),
    social_action(E, Action),
    social_action_contradicts_negative(Action),
    agent(E, Agent),
    patient(E, Patient),
    earliest_relationship_establishment(Agent, Patient, RelType, T_event, T_establish),
    is_negative_relationship(RelType),
    has_corroborated_relationship(Agent, Patient),
    not first_interaction(Agent, Patient, E),
    not story_exception(relationship_action_mismatch, E).

% Social actions that contradict negative (hostile) relationships
% These are EXPLICITLY FRIENDLY social actions - performing them toward an explicit enemy is a violation
% Per LOGIC_DESIGN.md: evidence-gated, no inference
% Note: help/encourage removed - these can occur in professional/survival contexts (mentors, allies of necessity)
friendly_social_action(farewell).
friendly_social_action(comfort).
friendly_social_action(praise).
% General warmth synonyms (not tied to any specific story's vocabulary)
friendly_social_action(smile).
friendly_social_action(embrace).
friendly_social_action(reassure).
friendly_social_action(welcome).

% Backward compatibility alias
social_action_contradicts_negative(A) :- friendly_social_action(A).

% Social actions that contradict positive (friendly/family) relationships
% These are HOSTILE social actions - performing them toward an explicit ally is a violation
hostile_social_action(good_riddance).
hostile_social_action(insult).
hostile_social_action(threaten).
% General hostility/coldness synonyms (not tied to any specific story's vocabulary)
hostile_social_action(mock).
hostile_social_action(scorn).
hostile_social_action(sneer).
hostile_social_action(disgust).
hostile_social_action(recoil).

% Backward compatibility alias
social_action_contradicts_positive(A) :- hostile_social_action(A).

% NEUTRAL social actions - do NOT trigger relationship violations
% These are procedural departures or cold/dismissive but not overtly hostile
% Per requirement: dismissal must NOT trigger violations unless explicitly overridden
neutral_social_action(neutral_departure).
neutral_social_action(dismissal).

% Helper: check if action is non-neutral (for future rule extensibility)
non_neutral_social_action(A) :- friendly_social_action(A).
non_neutral_social_action(A) :- hostile_social_action(A).

% --- VIOLATION: Hostile Social Action Toward Explicit Ally ---
% Uses social_action/2 for explicit emotion-aware social actions
% NOTE: Uses earliest_relationship_establishment to avoid duplicate violations
violation(emotional, relationship_action_mismatch, 
          violation_info(E, agent, Agent, social_action, Action, toward, Patient, 
                        despite, RelType, established_at, T_establish)) :-
    modified_story,
    rule_active(emotional_relationship_action_mismatch),
    event(E),
    event_time(E, T_event),
    social_action(E, Action),
    social_action_contradicts_positive(Action),
    agent(E, Agent),
    patient(E, Patient),
    earliest_relationship_establishment(Agent, Patient, RelType, T_event, T_establish),
    is_positive_relationship(RelType),
    has_corroborated_relationship(Agent, Patient),
    not first_interaction(Agent, Patient, E),
    not story_exception(relationship_action_mismatch, E).

% --- VIOLATION: Action Contradicts Story-Mined Relationship/Action Pattern ---
% Purely data-driven, no hand-written verb lists: compatible_relationship_action/2
% and has_relationship_action_data/1 are learned facts asserted by
% mine_relationship_action_compatibility() (scripts/kfold_experiment_runner_conflict_resolver.py)
% from this story's own ORIGINAL (unmodified) chapters -- never from error content.
% Fires only for relationship types with enough original-text track record
% (has_relationship_action_data), and only when the observed action (event
% type OR social action) was NEVER once seen accompanying that relationship
% type in the original text.
violation(emotional, learned_relationship_action_mismatch,
          violation_info(E, agent, Agent, acted, Type, toward, Patient,
                        despite, RelType, established_at, T_establish)) :-
    modified_story,
    rule_active(emotional_learned_relationship_action_mismatch),
    event(E),
    event_time(E, T_event),
    event_type(E, Type),
    agent(E, Agent),
    patient(E, Patient),
    earliest_relationship_establishment(Agent, Patient, RelType, T_event, T_establish),
    has_relationship_action_data(RelType),
    not compatible_relationship_action(RelType, Type),
    has_corroborated_relationship(Agent, Patient),
    not first_interaction(Agent, Patient, E),
    not story_exception(learned_relationship_action_mismatch, E).

violation(emotional, learned_relationship_action_mismatch,
          violation_info(E, agent, Agent, social_action, Action, toward, Patient,
                        despite, RelType, established_at, T_establish)) :-
    modified_story,
    rule_active(emotional_learned_relationship_action_mismatch),
    event(E),
    event_time(E, T_event),
    social_action(E, Action),
    agent(E, Agent),
    patient(E, Patient),
    earliest_relationship_establishment(Agent, Patient, RelType, T_event, T_establish),
    has_relationship_action_data(RelType),
    not compatible_relationship_action(RelType, Action),
    has_corroborated_relationship(Agent, Patient),
    not first_interaction(Agent, Patient, E),
    not story_exception(learned_relationship_action_mismatch, E).

% --- VIOLATION: Friend Reporting to Hostile Authority ---
% A friend reporting you to someone who is hostile towards you is a clear betrayal
% More targeted than generic betrayal - requires hostile relationship with recipient
violation(emotional, friend_hostile_report, 
          violation_info(E, agent, Agent, reported, Patient, to, Recipient,
                        despite_friendly_relationship, T_establish)) :-
    modified_story,
    rule_active(emotional_relationship_betrayal),
    event(E),
    event_time(E, T_event),
    report(E),
    agent(E, Agent),
    patient(E, Patient),
    recipient(E, Recipient),
    Recipient != Patient,
    Agent != Recipient,
    % Agent is friendly with patient
    earliest_relationship_establishment(Agent, Patient, friendly, T_event, T_establish),
    % Recipient is hostile to patient (this is what makes it a betrayal)
    relationship(Recipient, Patient, hostile),
    not first_interaction(Agent, Patient, E),
    not story_exception(relationship_betrayal, E).

% Protective reports - reporting out of concern, not betrayal
% These are reports made to authorities out of worry for safety
% Default: assume reports are NOT protective (stricter) unless marked
% is_protective_report(E) :- ... (can be specialized per story)

% Family relationship types (not strictly positive but betrayal-relevant)
is_family_relationship(family).
is_family_relationship(sibling).
is_family_relationship(parent).
is_family_relationship(child).
is_family_relationship(spouse).

% --- REMOVED: Backward compatibility violations ---
% The old atemporal relationship/3 violations are REMOVED in Phase Five.
% All violations now require explicit time-indexed evidence.

% =============================================================================
% PART C: RELATIONSHIP CHANGE RULES (Phase Five)
% =============================================================================
%
% Relationship changes REQUIRE an explicit event or rule override.
% Unexplained relationship changes are violations.
%
% =============================================================================

% --- Relationship Change Event Types ---
is_relationship_change_event(E) :- event_type(E, befriend).
is_relationship_change_event(E) :- event_type(E, betray).
is_relationship_change_event(E) :- event_type(E, forgive).
is_relationship_change_event(E) :- event_type(E, reconcile).
is_relationship_change_event(E) :- event_type(E, marry).
is_relationship_change_event(E) :- event_type(E, divorce).
is_relationship_change_event(E) :- event_type(E, declare_war).
is_relationship_change_event(E) :- event_type(E, make_peace).
is_relationship_change_event(E) :- event_type(E, alliance).
is_relationship_change_event(E) :- event_type(E, break_alliance).
is_relationship_change_event(E) :- event_type(E, fall_in_love).
is_relationship_change_event(E) :- event_type(E, hate).
is_relationship_change_event(E) :- event_type(E, trust).
is_relationship_change_event(E) :- event_type(E, distrust).

% Story can declare events that change relationships
is_relationship_change_event(E) :- story_relationship_event(E).

% --- Explicit Relationship Changes ---
% Events that explicitly create relationships
creates_relationship(E, Agent, Patient, ally) :-
    event(E),
    event_type(E, befriend),
    agent(E, Agent),
    patient(E, Patient).

creates_relationship(E, Agent, Patient, loves) :-
    event(E),
    event_type(E, fall_in_love),
    agent(E, Agent),
    patient(E, Patient).

creates_relationship(E, Agent, Patient, family) :-
    event(E),
    event_type(E, marry),
    agent(E, Agent),
    patient(E, Patient).

creates_relationship(E, Agent, Patient, enemy) :-
    event(E),
    event_type(E, declare_war),
    agent(E, Agent),
    patient(E, Patient).

creates_relationship(E, Agent, Patient, ally) :-
    event(E),
    event_type(E, alliance),
    agent(E, Agent),
    patient(E, Patient).

creates_relationship(E, Agent, Patient, friendly) :-
    event(E),
    event_type(E, reconcile),
    agent(E, Agent),
    patient(E, Patient).

creates_relationship(E, Agent, Patient, friendly) :-
    event(E),
    event_type(E, forgive),
    agent(E, Agent),
    patient(E, Patient).

% Events that change existing relationships
changes_relationship(E, Agent, Patient, enemy, OldType) :-
    event(E),
    event_type(E, betray),
    agent(E, Agent),
    patient(E, Patient),
    event_time(E, T),
    explicit_relationship(Agent, Patient, OldType, T_prior),
    T_prior < T,
    is_positive_relationship(OldType).

changes_relationship(E, Agent, Patient, hates, OldType) :-
    event(E),
    event_type(E, hate),
    agent(E, Agent),
    patient(E, Patient),
    event_time(E, T),
    explicit_relationship(Agent, Patient, OldType, T_prior),
    T_prior < T.

% --- VIOLATION: Unexplained Relationship Change ---
% Relationship changed without an explicit event
% DISABLED: Produces too many false positives in multi-chapter analysis
%           due to extraction differences between chapters
%
% violation(emotional, unexplained_relationship_change,
%           violation_info(C1, C2, changed_from, OldType, to, NewType, 
%                         at_time, T, without_event)) :-
%     rule_active(emotional_unexplained_relationship_change),
%     explicit_relationship(C1, C2, OldType, T_old),
%     explicit_relationship(C1, C2, NewType, T),
%     T_old < T,
%     OldType != NewType,
%     not has_relationship_change_event(C1, C2, T_old, T),
%     not story_override_relationship(C1, C2, NewType, T).

% Check if there's a relationship change event between times
has_relationship_change_event(C1, C2, T_old, T_new) :-
    event(E),
    event_time(E, T_event),
    time(T_old),
    time(T_new),
    T_old < T_event,
    T_event <= T_new,
    is_relationship_change_event(E),
    agent(E, C1),
    patient(E, C2).

has_relationship_change_event(C1, C2, T_old, T_new) :-
    event(E),
    event_time(E, T_event),
    time(T_old),
    time(T_new),
    T_old < T_event,
    T_event <= T_new,
    is_relationship_change_event(E),
    agent(E, C2),
    patient(E, C1).

% Story can override relationship without event
% story_override_relationship(C1, C2, Type, T) :- story_declares_relationship(C1, C2, Type, T).


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

% --- REMOVED: Old relationship_rule violation ---
% Replaced by evidence-gated violations above

% =============================================================================
% PART D: TRAIT VIOLATIONS (Phase Five - Evidence-Gated)
% =============================================================================
%
% Trait violations require explicit trait establishment.
%
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
trait_contradicts_action(kind, hurt).
trait_contradicts_action(kind, attack).
trait_contradicts_action(kind, insult).
trait_contradicts_action(loyal, betray).
trait_contradicts_action(loyal, abandon).

% Explicit trait tracking
explicit_trait(C, Trait, T) :-
    trait(C, Trait),
    time(T).

explicit_trait(C, Trait, T) :-
    trait_rule(C, Trait, E),
    event_time(E, T_establish),
    time(T),
    T >= T_establish.

explicit_trait(C, Trait, T) :-
    holds(trait(C, Trait), T).

% Trait established before event
trait_established_before(C, Trait, T_event) :-
    explicit_trait(C, Trait, T_establish),
    time(T_event),
    T_establish < T_event.

% VIOLATION: Action contradicts established trait (Evidence-Gated)
violation(emotional, trait_action_mismatch, 
          violation_info(E, agent, C, acted, Action, despite_trait, Trait)) :-
    rule_active(emotional_trait_action_mismatch),
    event(E),
    event_time(E, T_event),
    event_type(E, Action),
    agent(E, C),
    trait_established_before(C, Trait, T_event),
    trait_contradicts_action(Trait, Action),
    not story_exception(trait_action_mismatch, E).

% =============================================================================
% PART E: EMOTIONAL STATE TRACKING (Time-Indexed)
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


% =============================================================================
% PART F: QUERY HELPERS
% =============================================================================

% Characters with explicit relationships at time T
related_characters(C1, C2, T) :- explicit_relationship(C1, C2, _, T).
related_characters(C1, C2, T) :- explicit_relationship(C2, C1, _, T).

% Relationship type at time T
relationship_at(C1, C2, Type, T) :- explicit_relationship(C1, C2, Type, T).

% First interaction between characters
is_first_interaction(C1, C2, E) :- first_interaction(C1, C2, E).

% Relationship polarity
relationship_polarity(C1, C2, positive, T) :- 
    explicit_relationship(C1, C2, Type, T), 
    is_positive_relationship(Type).
    
relationship_polarity(C1, C2, negative, T) :- 
    explicit_relationship(C1, C2, Type, T), 
    is_negative_relationship(Type).


% =============================================================================
% SHOW DIRECTIVES
% =============================================================================

#show explicit_relationship/4.
#show first_interaction/3.
#show relationship_established_before/5.
#show violation/4.
