% =============================================================================
%
%    UNIVERSAL NARRATIVE RULES - ITEMS (v1.1)
%    =========================================
%
%    ERROR CATEGORY: CAUSALITY
%    -------------------------
%    Per docs/ILASP_INTEGRATION.md:
%        "Effect without cause, broken causal chain"
%
%    Item violations are primarily in the CAUSALITY category as they
%    represent cause-effect failures (e.g., giving without having).
%
%    Default world assumptions for item handling and Chekhov's Gun.
%    These rules can be overridden by story-specific rules.
%
%    Per LOGIC_DESIGN.md Section 3.2:
%        - item(X): Entity is an item
%        - carries(Character, Item, Time): Character has item at time T
%
%    VERSION 1.0: Initial item rules with Chekhov tracking
%    VERSION 1.1: Added ERROR CATEGORY documentation for consistency audit
%
%    Phase 5: Item Relevance & Chekhov Tracking
%        - item_relevance(Item, causal|latent): Item classification
%        - Only causal items trigger constraints
%        - Latent items are tracked for Chekhov detection
%
%    ITEM VIOLATIONS PRODUCED (Category: CAUSALITY):
%        - chekhov_gun: Latent items introduced must eventually be used
%        - possession_constraint: Item actions require possession
%        - causal_action: Items in actions must be causal items
%        - give_without_having: Cannot give item not possessed (via causality.lp)
%        - take_nonexistent: Cannot take non-existent item
%        - use_without_having: Cannot use item not possessed
%
% =============================================================================

% --- Rule Registration ---
rule(items_chekhov_gun, universal, "Latent items introduced must eventually be used").
rule(items_possession_constraint, universal, "Only causal items participate in possession checks").
rule(items_causal_action, universal, "Items in actions must be causal").

% =============================================================================
% ITEM RELEVANCE CLASSIFICATION
% =============================================================================

% Item is considered causal if explicitly marked or referenced in events
is_causal_item(Item) :- item_relevance(Item, causal).

% Item is considered latent (Chekhov tracking) if explicitly marked
is_latent_item(Item) :- item_relevance(Item, latent).
is_latent_item(Item) :- latent_item(Item).  % Backward compatibility

% Item is background if neither causal nor latent
is_background_item(Item) :- 
    item(Item),
    not is_causal_item(Item),
    not is_latent_item(Item).

% =============================================================================
% CAUSAL ITEMS ONLY IN CONSTRAINTS
% =============================================================================

% Only causal items participate in give/take validations
% This wraps the causality rules to filter out latent/background items

% An item can be given only if it's causal
can_be_given(Item) :- is_causal_item(Item).

% An item can be taken only if it's causal  
can_be_taken(Item) :- is_causal_item(Item).

% =============================================================================
% LATENT ITEMS - PASSIVE UNTIL ACTIVATED
% =============================================================================

% Latent items become causal when they participate in certain events
latent_item_activated(Item, E) :-
    is_latent_item(Item),
    event(E),
    event_type(E, Type),
    is_item_activation_event(Type),
    patient(E, Item).

latent_item_activated(Item, E) :-
    is_latent_item(Item),
    event(E),
    event_type(E, Type),
    is_item_activation_event(Type),
    item_used(E, Item).

% Event types that activate latent items
is_item_activation_event(use).
is_item_activation_event(give).
is_item_activation_event(take).
is_item_activation_event(destroy).
is_item_activation_event(wield).
is_item_activation_event(drink).
is_item_activation_event(eat).
is_item_activation_event(read).
is_item_activation_event(open).
is_item_activation_event(break).
is_item_activation_event(consume).
is_item_activation_event(activate).

% Once activated, latent item becomes causal
is_causal_item(Item) :- latent_item_activated(Item, _).

% =============================================================================
% CHEKHOV'S GUN DETECTION
% =============================================================================

% Track when latent items were introduced (for cross-chapter tracking)
latent_item_introduced(Item, T) :-
    is_latent_item(Item),
    item_introduced(Item, T).

% Fallback: if no explicit introduction time, use first event time
latent_item_introduced(Item, T) :-
    is_latent_item(Item),
    event(E),
    event_time(E, T),
    patient(E, Item),
    not earlier_item_mention(Item, T).

earlier_item_mention(Item, T) :-
    event(E1),
    event_time(E1, T1),
    event(E2),
    event_time(E2, T),
    patient(E1, Item),
    T1 < T.

% Latent item that was NEVER activated is a Chekhov violation
% Note: This is checked in final analysis, not per-chapter
% because we need to wait until the end of the story
chekhov_candidate(Item) :-
    is_latent_item(Item),
    not latent_item_activated(Item, _).

% =============================================================================
% ITEM LIFECYCLE STATES (from ItemTracker)
% =============================================================================

% These facts are generated by Python's ItemTracker.to_asp_facts()
% item_lifecycle(Item, State) where State is:
%   - introduced
%   - carried  
%   - used
%   - discarded
%   - destroyed
%   - given

% Item is resolved if it reached a terminal state
item_resolved(Item) :- item_lifecycle(Item, destroyed).
item_resolved(Item) :- item_lifecycle(Item, discarded).
item_resolved(Item) :- item_lifecycle(Item, used).

% =============================================================================
% CONSTRAINT MODIFICATIONS
% =============================================================================

% Override: possession violations only apply to causal items
% This prevents latent items from triggering "give without having" errors
suppress_violation(give_without_having, Item) :- 
    not is_causal_item(Item),
    item(Item).

% Background items never trigger any violations
% Enumerate common violation types that should be suppressed for background items
suppress_violation(give_without_having, Item) :- is_background_item(Item).
suppress_violation(take_nonexistent, Item) :- is_background_item(Item).
suppress_violation(use_without_having, Item) :- is_background_item(Item).
suppress_violation(chekhov_violation, Item) :- is_background_item(Item).
suppress_violation(item_continuity, Item) :- is_background_item(Item).

% =============================================================================
% HELPER PREDICATES
% =============================================================================

% Item is in any event (for reference tracking)
item_in_event(Item, E) :- patient(E, Item), item(Item).
item_in_event(Item, E) :- item_used(E, Item).

% Item has been referenced multiple times
item_referenced_multiple_times(Item) :-
    item_in_event(Item, E1),
    item_in_event(Item, E2),
    E1 != E2.

% Item was introduced early (first quarter of story)
% Note: story_total_chapters/1 must be set by Python
item_introduced_early(Item, T) :-
    latent_item_introduced(Item, T),
    story_total_chapters(Total),
    EarlyThreshold = Total / 4,
    T <= EarlyThreshold.
