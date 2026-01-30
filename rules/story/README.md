# Story-Specific Rules Directory

This directory contains **story-specific override rules**.

Per LOGIC_DESIGN.md Section 3.1:
- **Story Rules** are priority layer 1 (highest priority)
- These rules **override all others** (learned and universal)
- They capture story-specific exceptions (ghosts, magic, etc.)

## How Rules Are Generated

1. The `ConflictResolver` detects when a story violates universal rules
2. If the violation is intentional (e.g., ghosts acting), a story rule is generated
3. The story rule overrides the universal rule for this story
4. The universal rule is **deactivated but retained** for auditing

## File Naming Convention

```
<story_id>_<rule_type>.lp
```

Example:
```
harry_potter_ghost_exceptions.lp
harry_potter_magic_physics.lp
```

## Rule Content

Each file contains:
- Header comments with conflict ID and reason
- ASP rules that override universal constraints
- Entity-specific exceptions if applicable

## Example: Ghost Exception

```asp
% Story override for Harry Potter
% Ghosts can act while technically "dead"

is_ghost(nearly_headless_nick).
is_ghost(fat_friar).
is_ghost(bloody_baron).
is_ghost(grey_lady).
is_ghost(peeves).

% Suppress dead_character_acting for ghosts
story_exception(dead_character_acting, C) :- is_ghost(C).
```

## Important Notes

- Story rules are generated per story, not shared
- They are reset when starting a new story
- Overridden universal rules are tracked for final analysis
