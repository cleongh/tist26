"""LLM prompts for introducing controlled narrative errors into text excerpts."""

INJECT_CAUSALITY = """You are rewriting a story excerpt to introduce exactly ONE causality error.

TEXT CONTEXT:
- Four preceding sentences (context only):
{previous}
- Target excerpt to rewrite:
{text}
- Four following sentences (context only):
{follows}

GOAL:
Rewrite ONLY the target excerpt so that it contains one clear CAUSALITY violation while preserving the original prose style, tone, characters, and setting
without increasing the length of the sentence more than 5 words.

VALID CAUSALITY ERRORS:
1. A dead character acts later as if alive.
2. An object is used without being mentioned or introduced.
3. A character appears in an event without being introduced or established.

STRICT RULES:
- Introduce exactly one causality error.
- Modify only the target excerpt, not the preceding or following context.
- Keep the excerpt fluent and natural; the contradiction should be narrative, not grammatical.
- Preserve names, formatting, and general length as much as possible.
- Do not explain the change.
- Do not return JSON.

OUTPUT:
Return only the rewritten target excerpt text."""


INJECT_BASIC_COHERENCE = """You are rewriting a story excerpt to introduce exactly ONE basic coherence error.

TEXT CONTEXT:
- Four preceding sentences (context only):
{previous}
- Target excerpt to rewrite:
{text}
- Four following sentences (context only):
{follows}

GOAL:
Rewrite ONLY the target excerpt so that it contains one clear COHERENCE violation while keeping the original narrative voice and surface readability intact
without increasing the length of the sentence more than 5 words.

VALID COHERENCE ERRORS:
1. Description of places that doesn't match the original.
2. Something is described with a colour that is not correct (a blue egg, a green dog).
3. Metaphors don't really match the sentence (a dense desert).

STRICT RULES:
- Introduce exactly one coherence error.
- Modify only the target excerpt.
- Keep the text grammatical, idiomatic, and stylistically close to the source.
- Preserve the same main characters, setting, and event flow whenever possible.
- Do not explain the change.
- Do not return JSON.

OUTPUT:
Return only the rewritten target excerpt text."""


INJECT_TEMPORAL_ORDER = """You are rewriting a story excerpt to introduce exactly ONE temporal-order error.

TEXT CONTEXT:
- Four preceding sentences (context only):
{previous}
- Target excerpt to rewrite:
{text}
- Four following sentences (context only):
{follows}

GOAL:
Rewrite ONLY the target excerpt so that events occur in an impossible or contradictory order while the passage still reads like normal story prose
without increasing the length of the sentence more than 5 words.

VALID TEMPORAL ERRORS:
1. An effect happens before its cause.
2. A later action is described as happening before a necessary earlier action.
3. A sequence contradicts its own explicit before/after ordering.

STRICT RULES:
- Introduce exactly one temporal-order error.
- Modify only the target excerpt.
- Keep the wording natural and preserve the original characters, setting, and style.
- Prefer small, targeted edits such as reordering, reversing, or lightly rewriting actions.
- Do not introduce causality, location, emotional relationship, or unrelated coherence errors.
- Do not explain the change.
- Do not return JSON.

OUTPUT:
Return only the rewritten target excerpt text."""


INJECT_LOCATION_CORRECTNESS = """You are rewriting a story excerpt to introduce exactly ONE location error.

TEXT CONTEXT:
- Four preceding sentences (context only):
{previous}
- Target excerpt to rewrite:
{text}
- Four following sentences (context only):
{follows}

GOAL:
Rewrite ONLY the target excerpt so that it contains one clear LOCATION violation while preserving the surrounding scene and prose style
without increasing the length of the sentence more than 5 words.

VALID LOCATION ERRORS:
1. A character moves between unconnected locations without any travel or transition.
2. A character is effectively in Four incompatible places within the same scene.
3. An action occurs in a location that contradicts the immediately established setting.

STRICT RULES:
- Introduce exactly one location error.
- Modify only the target excerpt.
- Keep the excerpt readable and close in length and style to the original.
- Preserve character identities and the general plot beat.
- Do not invent a second independent error type.
- Do not explain the change.
- Do not return JSON.

OUTPUT:
Return only the rewritten target excerpt text."""


INJECT_EMOTIONAL_RELATIONS = """You are rewriting a story excerpt to introduce exactly ONE emotional-relationship error.

TEXT CONTEXT:
- Four preceding sentences (context only):
{previous}
- Target excerpt to rewrite:
{text}
- Four following sentences (context only):
{follows}

GOAL:
Rewrite ONLY the target excerpt so that it contains one clear EMOTIONAL RELATIONSHIP violation while remaining stylistically consistent with the source text
without increasing the length of the sentence more than 5 words.

VALID EMOTIONAL RELATIONSHIP ERRORS:
1. A hostile character suddenly behaves warmly, affectionately, or supportively without cause.
2. A friendly or loving character suddenly behaves with hostility or cruelty without cause.
3. A character helps an enemy or harms a loved one in a way that contradicts the established relationship.

STRICT RULES:
- Introduce exactly one emotional-relationship error.
- Modify only the target excerpt.
- Keep the prose natural and preserve the same characters, setting, and broad scene.
- Make the contradiction clear through behavior, dialogue, or attitude.
- Do not introduce causality, location, temporal, or unrelated coherence errors.
- Do not explain the change.
- Do not return JSON.

OUTPUT:
Return only the rewritten target excerpt text."""
