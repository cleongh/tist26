% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - APPEARANCE (v1.1)
%    ============================================================
%
%    ERROR CATEGORY: COHERENCE
%    -------------------------
%    Per docs/ILASP_INTEGRATION.md:
%        "Dead agent acting, trait conflicts"
%    Appearance violations are part of the COHERENCE category as they 
%    represent physical state inconsistencies.
%
%    All violations produced by this file are in the COHERENCE category.
%    Violations are structured as: violation(coherence, appearance_TYPE, EVENT, ENTITY)
%
%    ASP rules to detect appearance and physical state inconsistencies.
%
%    Per LOGIC_DESIGN.md Section 3.2:
%        Relations (Edges/Predicates) - Time-Indexed
%
%    VERSION 1.0 CHANGES (Phase Four):
%        - appearance(Character, Trait, Time) - time-indexed appearance state
%        - persistent_appearance(Trait) - traits that should persist without cause
%        - exclusive_appearance(TraitA, TraitB) - mutually exclusive trait pairs
%        - appearance_cause(Trait) - event types that can cause trait changes
%        - Violations for sudden changes, exclusive traits, unexplained reversions
%    VERSION 1.1: Added ERROR CATEGORY documentation for consistency audit
%
%    DESIGN PRINCIPLE:
%        Appearance is narrative state, not prose decoration.
%        Changes require causal events. Reversions need explanations.
%        "Pale green" errors become detectable as coherence violations.
%
%    APPEARANCE VIOLATIONS PRODUCED (Category: COHERENCE):
%        - appearance_sudden_change: Trait appeared without causal event
%        - appearance_exclusive_conflict: Mutually exclusive traits at same time
%        - appearance_unexplained_reversion: Trait reverted without intervention
%        - appearance_persistent_lost: Persistent trait disappeared without cause
%
% =============================================================================

% --- Rule Registration (Step 2.4) ---
rule(appearance_sudden_change, universal, "Appearance trait changed without causal event").
rule(appearance_exclusive_conflict, universal, "Character has mutually exclusive appearance traits").
rule(appearance_unexplained_reversion, universal, "Appearance trait reverted without intervention").
rule(appearance_persistent_lost, universal, "Persistent appearance trait lost without cause").


% =============================================================================
% PART A: APPEARANCE PREDICATES
% =============================================================================
%
% appearance(Character, Trait, Time) - Character has Trait at Time
%
% Derived from:
%     1. Explicit extraction: character_appearance(C, Trait, T, E)
%     2. Fluent persistence: holds(appearance(C, Trait), T)
%     3. Event effects: initiates(E, appearance(C, Trait))
%
% =============================================================================

% --- Bridge to Extraction Layer ---
% Explicit appearance assertion from LLM extraction
% character_appearance(Character, Trait, Time, Event) - extracted fact
% Converts to time-indexed appearance predicate

appearance(C, Trait, T) :-
    character_appearance(C, Trait, T, _).

% --- Bridge to Fluent System ---
% If appearance is tracked as a fluent in core.lp
appearance(C, Trait, T) :-
    holds(appearance(C, Trait), T).

% --- From Event Initiation ---
% Events can initiate appearance changes
appearance(C, Trait, T) :-
    event_time(E, T),
    initiates(E, appearance(C, Trait)).

% Appearance persists unless terminated
holds(appearance(C, Trait), T+1) :-
    holds(appearance(C, Trait), T),
    time(T),
    time(T+1),
    not terminated(appearance(C, Trait), T).

% --- Initial Appearance ---
% Characters can have initial appearance traits
holds(appearance(C, Trait), 0) :-
    initially(appearance(C, Trait)).

initially(appearance(C, Trait)) :-
    initial_appearance(C, Trait).


% =============================================================================
% PART B: APPEARANCE TRAIT CLASSIFICATIONS
% =============================================================================
%
% Classify traits by their persistence and exclusivity properties.
%
% =============================================================================

% --- Persistent Appearance Traits ---
% These traits should NOT disappear without a causal event
% Once you have a scar, you keep the scar (unless healed)

persistent_appearance(scarred).
persistent_appearance(scar).
persistent_appearance(tattooed).
persistent_appearance(birthmark).
persistent_appearance(branded).
persistent_appearance(missing_eye).
persistent_appearance(missing_limb).
persistent_appearance(missing_hand).
persistent_appearance(missing_arm).
persistent_appearance(amputated).
persistent_appearance(disfigured).
persistent_appearance(burned).  % Burn scars are permanent
persistent_appearance(mutilated).

% Physical characteristics (usually permanent)
persistent_appearance(tall).
persistent_appearance(short).
persistent_appearance(thin).
persistent_appearance(fat).
persistent_appearance(heavy).
persistent_appearance(elderly).
persistent_appearance(old).
persistent_appearance(young).
persistent_appearance(bald).

% --- Transient Appearance Traits ---
% These can change without explicit causal events (emotional states, etc.)
transient_appearance(pale).
transient_appearance(flushed).
transient_appearance(red_faced).
transient_appearance(sweaty).
transient_appearance(tearful).
transient_appearance(smiling).
transient_appearance(frowning).
transient_appearance(tired).
transient_appearance(exhausted).
transient_appearance(alert).
transient_appearance(nervous).
transient_appearance(calm).
transient_appearance(tense).
transient_appearance(relaxed).

% --- Exclusive Appearance Trait Pairs ---
% These traits are mutually exclusive - cannot hold simultaneously
% Symmetric: if (A, B) is exclusive, so is (B, A)

exclusive_appearance(pale, flushed).
exclusive_appearance(flushed, pale).

exclusive_appearance(pale, red_faced).
exclusive_appearance(red_faced, pale).

exclusive_appearance(smiling, frowning).
exclusive_appearance(frowning, smiling).

exclusive_appearance(calm, nervous).
exclusive_appearance(nervous, calm).

exclusive_appearance(tense, relaxed).
exclusive_appearance(relaxed, tense).

exclusive_appearance(tired, alert).
exclusive_appearance(alert, tired).

exclusive_appearance(clean, dirty).
exclusive_appearance(dirty, clean).

exclusive_appearance(wet, dry).
exclusive_appearance(dry, wet).

exclusive_appearance(dressed, naked).
exclusive_appearance(naked, dressed).

exclusive_appearance(visible, invisible).
exclusive_appearance(invisible, visible).

% Color appearance exclusions (skin tone at same time)
exclusive_appearance(pale, tan).
exclusive_appearance(tan, pale).
exclusive_appearance(pale, dark).
exclusive_appearance(dark, pale).

% Health-related exclusions
exclusive_appearance(healthy, sick).
exclusive_appearance(sick, healthy).
exclusive_appearance(healthy, ill).
exclusive_appearance(ill, healthy).

exclusive_appearance(alive_looking, dead_looking).
exclusive_appearance(dead_looking, alive_looking).

exclusive_appearance(conscious, unconscious).
exclusive_appearance(unconscious, conscious).

% Size exclusions (cannot be both)
exclusive_appearance(thin, fat).
exclusive_appearance(fat, thin).
exclusive_appearance(tall, short).
exclusive_appearance(short, tall).

% --- Abnormal Appearance Traits ---
% These suggest something is wrong - potential errors or plot points
abnormal_appearance(green).
abnormal_appearance(pale_green).
abnormal_appearance(blue).
abnormal_appearance(purple).
abnormal_appearance(gray).
abnormal_appearance(grey).
abnormal_appearance(grayish).
abnormal_appearance(greyish).
abnormal_appearance(grayish_white).
abnormal_appearance(greyish_white).
abnormal_appearance(sickly).
abnormal_appearance(sickly_green).
abnormal_appearance(deathly_pale).

% --- Injury Appearance Traits ---
% These indicate physical harm
injury_appearance(bloody).
injury_appearance(bloodied).
injury_appearance(bruised).
injury_appearance(wounded).
injury_appearance(injured).
injury_appearance(hurt).
injury_appearance(bleeding).
injury_appearance(cut).
injury_appearance(gashed).
injury_appearance(scratched).
injury_appearance(battered).
injury_appearance(beaten).

% Injury appearances can be caused by violence events
is_injury_cause_event(E) :- event_type(E, fight).
is_injury_cause_event(E) :- event_type(E, attack).
is_injury_cause_event(E) :- event_type(E, hit).
is_injury_cause_event(E) :- event_type(E, punch).
is_injury_cause_event(E) :- event_type(E, kick).
is_injury_cause_event(E) :- event_type(E, stab).
is_injury_cause_event(E) :- event_type(E, cut).
is_injury_cause_event(E) :- event_type(E, slash).
is_injury_cause_event(E) :- event_type(E, wound).
is_injury_cause_event(E) :- event_type(E, injure).
is_injury_cause_event(E) :- event_type(E, hurt).
is_injury_cause_event(E) :- event_type(E, fall).
is_injury_cause_event(E) :- event_type(E, crash).
is_injury_cause_event(E) :- event_type(E, accident).

% --- Healing Events ---
% These can remove injury appearance
is_healing_event(E) :- event_type(E, heal).
is_healing_event(E) :- event_type(E, healed).
is_healing_event(E) :- event_type(E, cure).
is_healing_event(E) :- event_type(E, recover).
is_healing_event(E) :- event_type(E, recovery).
is_healing_event(E) :- event_type(E, treat).
is_healing_event(E) :- event_type(E, treatment).
is_healing_event(E) :- event_type(E, bandage).
is_healing_event(E) :- event_type(E, mend).


% =============================================================================
% PART C: APPEARANCE STATE TRACKING
% =============================================================================
%
% Track when appearances are introduced, changed, or removed.
% Link appearance states to causal events.
%
% =============================================================================

% --- Appearance Introduction Event ---
% The first event that gives a character a trait
appearance_introduced_by(C, Trait, T, E) :-
    character_appearance(C, Trait, T, E),
    not appearance_prior(C, Trait, T).

% Character had this trait at some earlier time
appearance_prior(C, Trait, T) :-
    appearance(C, Trait, T_prev),
    T_prev < T.

% --- Appearance Continuation ---
% Trait persists from previous time
appearance_continues(C, Trait, T) :-
    appearance(C, Trait, T),
    appearance(C, Trait, T_prev),
    adjacent_times(T_prev, T).

% Helper: Adjacent time points
adjacent_times(T1, T2) :- time(T1), time(T2), T2 = T1 + 1.

% --- Appearance Removal ---
% Trait was present but is now gone
appearance_removed(C, Trait, T) :-
    appearance(C, Trait, T_prev),
    adjacent_times(T_prev, T),
    not appearance(C, Trait, T).

% --- Appearance Reversion ---
% Trait that was removed has come back
appearance_reverted(C, Trait, T) :-
    appearance(C, Trait, T),
    appearance_removed(C, Trait, T_mid),
    appearance(C, Trait, T_prev),
    T_prev < T_mid,
    T_mid < T.

% --- Appearance Change Event ---
% Event that caused an appearance change
appearance_change_event(C, Trait, T, E) :-
    appearance_introduced_by(C, Trait, T, E).

appearance_change_event(C, Trait, T, E) :-
    event_time(E, T),
    initiates(E, appearance(C, Trait)).


% =============================================================================
% PART D: APPEARANCE VIOLATIONS
% =============================================================================
%
% Detect coherence violations related to appearance.
% All violations are classified as coherence/appearance_anomaly.
%
% =============================================================================

% --- VIOLATION: Mutually Exclusive Traits at Same Time ---
% Character cannot be both pale AND flushed simultaneously
violation(coherence, appearance_exclusive_conflict,
          violation_info(C, has_exclusive_traits, Trait1, and, Trait2, at_time, T)) :-
    rule_active(appearance_exclusive_conflict),
    appearance(C, Trait1, T),
    appearance(C, Trait2, T),
    exclusive_appearance(Trait1, Trait2),
    Trait1 < Trait2.  % Avoid duplicate violations

% --- VIOLATION: Sudden Appearance Change Without Cause ---
% A non-transient trait appeared without a causal event
violation(coherence, appearance_sudden_change,
          violation_info(C, acquired_trait, Trait, at_time, T, without_cause)) :-
    rule_active(appearance_sudden_change),
    appearance_introduced_by(C, Trait, T, E),
    not transient_appearance(Trait),
    not has_appearance_cause(C, Trait, T, E).

% Check if there's a causal event for the appearance
% Injury appearances are caused by violence events
has_appearance_cause(C, Trait, T, _) :-
    injury_appearance(Trait),
    event_time(E2, T_cause),
    is_injury_cause_event(E2),
    patient(E2, C),
    T_cause <= T.

% Abnormal appearances can be caused by sickness events
has_appearance_cause(C, Trait, T, _) :-
    abnormal_appearance(Trait),
    event_time(E2, T_cause),
    event_type(E2, sick),
    agent(E2, C),
    T_cause <= T.

has_appearance_cause(C, Trait, T, _) :-
    abnormal_appearance(Trait),
    event_time(E2, T_cause),
    event_type(E2, poison),
    patient(E2, C),
    T_cause <= T.

has_appearance_cause(C, Trait, T, _) :-
    abnormal_appearance(Trait),
    event_time(E2, T_cause),
    event_type(E2, transform),
    patient(E2, C),
    T_cause <= T.

% Initial appearances don't need causes
has_appearance_cause(C, Trait, T, _) :-
    initial_appearance(C, Trait),
    T = 0.

% Explicitly marked as caused (story-specific)
has_appearance_cause(C, Trait, T, E) :-
    appearance_caused_by(C, Trait, T, E).

% --- VIOLATION: Persistent Trait Lost Without Cause ---
% A persistent trait disappeared without a healing/transformation event
violation(coherence, appearance_persistent_lost,
          violation_info(C, lost_persistent_trait, Trait, at_time, T, without_healing)) :-
    rule_active(appearance_persistent_lost),
    appearance_removed(C, Trait, T),
    persistent_appearance(Trait),
    not has_removal_cause(C, Trait, T).

% Check if there's a cause for removing a persistent trait
has_removal_cause(C, Trait, T) :-
    persistent_appearance(Trait),
    injury_appearance(Trait),
    event_time(E, T_heal),
    is_healing_event(E),
    patient(E, C),
    T_heal <= T.

has_removal_cause(C, Trait, T) :-
    persistent_appearance(Trait),
    event_time(E, T_trans),
    event_type(E, transform),
    patient(E, C),
    T_trans <= T.

% Magic can remove persistent traits
has_removal_cause(C, Trait, T) :-
    persistent_appearance(Trait),
    event_time(E, T_magic),
    event_type(E, magic),
    patient(E, C),
    T_magic <= T.

has_removal_cause(C, Trait, T) :-
    persistent_appearance(Trait),
    event_time(E, T_spell),
    event_type(E, spell),
    patient(E, C),
    T_spell <= T.

% --- VIOLATION: Unexplained Appearance Reversion ---
% A trait that was removed came back without an intervening event
violation(coherence, appearance_unexplained_reversion,
          violation_info(C, trait_reverted, Trait, at_time, T, without_event)) :-
    rule_active(appearance_unexplained_reversion),
    appearance_reverted(C, Trait, T),
    not has_reversion_cause(C, Trait, T).

% Check if there's a cause for the reversion
has_reversion_cause(C, Trait, T) :-
    injury_appearance(Trait),
    event_time(E, T_injury),
    is_injury_cause_event(E),
    patient(E, C),
    appearance_removed(C, Trait, T_removed),
    T_removed < T_injury,
    T_injury < T.

has_reversion_cause(C, Trait, T) :-
    transient_appearance(Trait).  % Transient traits can revert freely


% =============================================================================
% PART E: ABNORMAL APPEARANCE VIOLATIONS (Error Detection)
% =============================================================================
%
% Detect likely extraction errors where appearances don't make sense.
% These are the "pale green food" type errors.
%
% =============================================================================

% --- VIOLATION: Abnormal Character Appearance ---
% Character has an abnormal appearance (e.g., "green face")
% This is flagged as a potential error unless there's a story justification
violation(coherence, appearance_anomaly,
          violation_info(C, has_abnormal_appearance, Trait, at_time, T, potential_error)) :-
    rule_active(appearance_sudden_change),  % Uses same rule flag
    appearance(C, Trait, T),
    abnormal_appearance(Trait),
    character(C),
    not is_non_human(C),
    not has_abnormal_appearance_justification(C, Trait, T).

% Non-human entities can have abnormal appearances
is_non_human(C) :- creature(C).
is_non_human(C) :- monster(C).
is_non_human(C) :- alien(C).
is_non_human(C) :- is_ghost(C).
is_non_human(C) :- is_undead(C).

% Justifications for abnormal appearances
has_abnormal_appearance_justification(C, Trait, T) :-
    abnormal_appearance(Trait),
    event_time(E, T_cause),
    event_type(E, poison),
    patient(E, C),
    T_cause <= T.

has_abnormal_appearance_justification(C, Trait, T) :-
    abnormal_appearance(Trait),
    event_time(E, T_cause),
    event_type(E, sick),
    agent(E, C),
    T_cause <= T.

has_abnormal_appearance_justification(C, Trait, T) :-
    abnormal_appearance(Trait),
    event_time(E, T_cause),
    event_type(E, transform),
    patient(E, C),
    T_cause <= T.

has_abnormal_appearance_justification(C, Trait, T) :-
    abnormal_appearance(Trait),
    event_time(E, T_cause),
    event_type(E, curse),
    patient(E, C),
    T_cause <= T.

% Death can justify deathly appearances
has_abnormal_appearance_justification(C, Trait, T) :-
    Trait = deathly_pale,
    death_time(C, T_death),
    T_death <= T.

has_abnormal_appearance_justification(C, Trait, T) :-
    Trait = gray,
    death_time(C, T_death),
    T_death <= T.

has_abnormal_appearance_justification(C, Trait, T) :-
    Trait = grey,
    death_time(C, T_death),
    T_death <= T.


% =============================================================================
% PART F: ITEM/FOOD APPEARANCE ANOMALIES
% =============================================================================
%
% Detect abnormal appearances for items and food that suggest errors.
% "Grayish white food" is likely an extraction error.
%
% =============================================================================

% Item/food appearance tracking
item_appearance(Item, Trait, T) :-
    object_appearance(Item, Trait, T, _).

item_appearance(Item, Trait, T) :-
    holds(appearance(Item, Trait), T),
    item(Item).

% Normal food colors
normal_food_color(red).
normal_food_color(orange).
normal_food_color(yellow).
normal_food_color(green).  % For vegetables
normal_food_color(brown).
normal_food_color(white).
normal_food_color(golden).
normal_food_color(pink).
normal_food_color(cream).
normal_food_color(beige).

% Abnormal food colors (suggest spoilage or error)
abnormal_food_color(gray).
abnormal_food_color(grey).
abnormal_food_color(grayish).
abnormal_food_color(greyish).
abnormal_food_color(grayish_white).
abnormal_food_color(greyish_white).
abnormal_food_color(blue).
abnormal_food_color(purple).
abnormal_food_color(black).
abnormal_food_color(moldy).
abnormal_food_color(sickly).
abnormal_food_color(pale_green).  % Not natural green

% --- VIOLATION: Abnormal Food Appearance ---
violation(coherence, appearance_anomaly,
          violation_info(Item, has_abnormal_food_appearance, Trait, at_time, T, potential_error)) :-
    rule_active(appearance_sudden_change),
    item_appearance(Item, Trait, T),
    is_food(Item),
    abnormal_food_color(Trait),
    not is_intentionally_abnormal(Item).

% Food type classification
is_food(X) :- food(X).
is_food(X) :- item_type(X, food).
is_food(X) :- item_type(X, drink).
is_food(X) :- item_type(X, meal).

% Story can mark items as intentionally abnormal
% is_intentionally_abnormal(Item) :- story_abnormal_item(Item).


% =============================================================================
% PART G: QUERY HELPERS
% =============================================================================

% All appearances at a given time
all_appearances(C, T, Trait) :- appearance(C, Trait, T).

% Has any appearance
has_appearance(C, T) :- appearance(C, _, T).

% Appearance trait categories
is_appearance_category(Trait, persistent) :- persistent_appearance(Trait).
is_appearance_category(Trait, transient) :- transient_appearance(Trait).
is_appearance_category(Trait, abnormal) :- abnormal_appearance(Trait).
is_appearance_category(Trait, injury) :- injury_appearance(Trait).


% =============================================================================
% SHOW DIRECTIVES
% =============================================================================

#show appearance/3.
#show appearance_introduced_by/4.
#show appearance_removed/3.
#show appearance_reverted/3.
#show exclusive_appearance/2.
#show violation/4.
