"""
Engine-based extraction prompt with continuity context.

Used by _structure_chapter_standalone for Phase 5 engine evaluation.
"""

ENGINE_EXTRACTION_PROMPT = """Extract structured narrative data from the text below.

=== CONTINUITY CONTEXT (AUTHORITATIVE) ===
The following facts are TRUE before this chapter begins.
You MUST treat them as ground truth.
Do NOT reinterpret, soften, or restate them unless the chapter EXPLICITLY changes them.

KNOWN CHARACTERS:
{known_characters_json}

KNOWN RELATIONSHIPS:
{known_relationships_json}

KNOWN CHARACTER STATES:
{known_character_states_json}

IDENTITY RULES:
- Each character has ONE canonical id.
- If the text uses a title, nickname, or alternate name, map it to the canonical id.
- DO NOT create a new character if an alias matches a known character.
- Use the canonical id in ALL outputs.

=== CONSISTENCY RULES CONTEXT ===
Your extraction will be checked by a logic-based consistency verifier. The system detects:

1. RELATIONSHIP VIOLATIONS:
   - Sudden hostile→friendly or friendly→hostile flips without cause
   - Characters helping enemies or harming loved ones unexpectedly
   - CRITICAL: If someone who hates another shows warmth/kindness, this MUST be extracted

2. COHERENCE VIOLATIONS:
   - Characters in contradictory states
   - Actions that contradict established relationships

TEXT:
{chapter_text}

=== CHARACTER BEHAVIOR ANALYSIS (VERY IMPORTANT) ===
Pay SPECIAL ATTENTION to character behavior and emotional interactions:
- If a character who is normally HOSTILE shows WARMTH, KINDNESS, or AFFECTION → this is significant!
- If an enemy gives a farewell, hug, encouragement, or praise → ALWAYS extract this as an event
- Look for CONTRADICTIONS between established relationships and current actions
- Populate "aliases" ONLY if the chapter introduces a new way to refer to an existing character

If hostility, warmth, or affection is described for a GROUP
(e.g., "the family", "the guards", "his classmates"):

- Extract the relationship for EACH named individual in that group.
- Do not collapse group behavior into a single representative character.
Example:
"The group despised Alex" →
  member_1 -> alex (hostile)
  member_2 -> alex (hostile)
  member_3 -> alex (hostile)

EXAMPLES OF CRITICAL BEHAVIOR TO CAPTURE:
- "Uncle Vernon gave Harry a warm smile" → event type: "farewell" or "praise"
- "Have a good term," said the usually cold teacher warmly → event type: "farewell"
- An enemy wishing someone well → MUST be extracted as "farewell" event

=== ITEM EXTRACTION RULES (CRITICAL) ===

ONLY extract an item if AT LEAST ONE of the following is true:
1. The item is carried, given, taken, used, lost, discovered, or destroyed
2. The item affects an event or a character's behavior
3. The item is mentioned with clear narrative emphasis (focus, repetition, or consequence)
4. The item is likely to persist across scenes or chapters
5. The item enables or blocks future actions (keys, weapons, letters, tools, artifacts)

DO NOT extract items that are:
- Ordinary background objects (chairs, tables, doors, food, clothing)
- Mentioned only as scenery or setting flavor
- Not interacted with by any character
- Immediately irrelevant and never referred to again in the chapter

=== OUTPUT FORMAT ===
Return ONLY this JSON structure:

{{
  "entities": {{
    "characters": [{{"id": "name_in_snake_case", "name": "Full Name", "aliases": [], "state": "normal/dead", "emotion": "emotion", "appearance": "normal/unusual"}}],
    "locations": [{{"id": "location_id", "name": "Location Name", "connections": []}}],
    "items": [{{"id": "item_id", "name": "Item Name", "state": "intact", "relevance": "causal|latent"}}],
    "relationships": [{{"from": "char_id", "to": "char_id", "type": "hostile/friendly/family/love/fear"}}]
  }},
  "events": [
    {{
      "id": "e1",
      "type": "meet|talk|give|take|attack|help|discover|arrive|leave|die|hug|praise|farewell|encourage|smile|wave|report|learn",
      "agent": "character_id",
      "patient": "character_id_or_null",
      "recipient": "character_id (ONLY for type=report - the authority being informed)",
      "fact": "short literal description of learned content (ONLY for type=learn)",
      "source": "character_id or item_id providing the information (OPTIONAL, ONLY for type=learn)",
      "location": "location_id_or_null",
      "social_action_type": "OPTIONAL - farewell|neutral_departure|dismissal|good_riddance|encourage|comfort|insult|threaten|apologize (see SOCIAL ACTION TYPING)",
      "source_text": "exact quote from text (max 80 chars)"
    }}
  ],
  "initial_rules": [
    {{"subject": "char_id", "predicate": "hates|loves|hostile|friendly", "object": "char_id"}}
  ],
  "implied_presence": [
    {{"entity": "entity_id", "location": "location_id"}}
  ]
}}

=== SOCIAL ACTION TYPING (OPTIONAL FIELD) ===
DO NOT perform sentiment analysis. DO NOT infer emotions not explicitly present.
This is LEXICAL MATCHING only — use ONLY explicit textual cues.

Events may include an OPTIONAL field: social_action_type
Assign ONLY when the text contains EXPLICIT lexical indicators.

ALLOWED VALUES (closed set):

--- DEPARTURE CATEGORIES (mutually exclusive, use MOST SPECIFIC match) ---

farewell:
  MEANING: Explicit goodwill on departure
  LEXICAL TRIGGERS:
  - "wished him/her well"
  - "said goodbye warmly"
  - "gave a warm farewell"
  - "have a good term/trip/journey"
  - "take care"
  - "good luck" (on departure)
  - "waved goodbye fondly/warmly"

neutral_departure:
  MEANING: Procedural, emotionless leaving or parting
  LEXICAL TRIGGERS:
  - "said goodbye" (no adverb or qualifier)
  - "left without comment"
  - "departed shortly after"
  - "took his/her leave"
  - "headed out"
  - parting with no emotional markers

dismissal:
  MEANING: Cold, indifferent, or curt send-off
  LEXICAL TRIGGERS:
  - "dismissed him/her"
  - "said coldly"
  - "without warmth"
  - "curtly told him/her to go"
  - "brushed him/her aside"
  - "waved him/her off dismissively"
  - "turned away without a word"

good_riddance:
  MEANING: Hostile or contemptuous send-off
  LEXICAL TRIGGERS:
  - "glad to see him/her go"
  - "good riddance"
  - "with obvious contempt"
  - "smirked as he/she left"
  - "sneered at his/her departure"
  - "muttered 'finally' as he/she left"

--- OTHER SOCIAL ACTIONS ---

encourage:
  MEANING: Explicit words of support or confidence-building
  LEXICAL TRIGGERS: "you can do it", "I believe in you", "encouraged him/her"

comfort:
  MEANING: Explicit soothing or consoling someone upset
  LEXICAL TRIGGERS: "it's okay", "don't worry", "comforted him/her", "patted his/her back"

insult:
  MEANING: Explicit verbal attack, mockery, or degradation
  LEXICAL TRIGGERS: "called him/her [slur]", "mocked", "insulted", "sneered"

threaten:
  MEANING: Explicit warning of harm or negative consequences
  LEXICAL TRIGGERS: "I'll make you pay", "you'll regret", "threatened", "or else"

apologize:
  MEANING: Explicit expression of regret
  LEXICAL TRIGGERS: "I'm sorry", "forgive me", "apologized", "my apologies"

CATEGORY SELECTION RULES:
1. Choose the MOST SPECIFIC category supported by explicit text
2. If no explicit lexical cue exists, OMIT social_action_type entirely
3. Do NOT downgrade or upgrade categories without textual support
4. Do NOT infer hostility from relationships or context
5. Departure categories are MUTUALLY EXCLUSIVE — pick ONE

EXAMPLES:
- "'Have a good term,' he said warmly." → social_action_type: "farewell"
- "'Goodbye,' she said." → social_action_type: "neutral_departure" (no emotion marker)
- "He dismissed her with a wave." → social_action_type: "dismissal"
- "'Good riddance,' he muttered." → social_action_type: "good_riddance"
- "They parted ways." → OMIT social_action_type (no explicit cue)
- "She praised him for his excellent work." → social_action_type: "praise"
- "'I'm sorry,' Harry muttered." → social_action_type: "apologize"
- "He nodded at her." → OMIT social_action_type (no explicit social intent)

OUTPUT RULE: If social_action_type is not explicitly indicated by lexical cues, OMIT the field entirely (do not set to null).

=== REPORT EVENTS (INFORMING AUTHORITIES) ===
Use type: "report" when a character EXPLICITLY informs an authority about another character.

REQUIRED FIELDS for report events:
- agent: character who does the reporting
- patient: character being reported about
- recipient: authority figure being informed (teacher, official, parent, etc.)

EXTRACT ONLY IF EXPLICITLY STATED:
- "told X about Y"
- "reported Y to X"
- "informed the teacher about Y"
- "went to tell X what Y had done"

DO NOT:
- Infer reporting from consequences alone (e.g., "X got in trouble" doesn't mean someone reported)
- Invent recipients not mentioned in the text
- Extract if patient (the person reported) is not explicit

EXAMPLES:
- "Neville told McGonagall about Harry"
  → type: "report", agent: "neville_longbottom", patient: "harry_potter", recipient: "professor_mcgonagall"
  
- "She informed the headmaster about what he had done"
  → type: "report", agent: "she_id", patient: "he_id", recipient: "headmaster"
  
- "He got detention" (no explicit reporting action)
  → DO NOT extract as report (consequence only, no explicit informing)

=== LEARN EVENTS (KNOWLEDGE ACQUISITION) ===
Use type: "learn" when a character EXPLICITLY acquires knowledge.

IMPORTANT: This is NOT inference or mind reading.
Extract ONLY when the text EXPLICITLY states learning or being told.

REQUIRED FIELDS for learn events:
- agent: character who acquires the knowledge
- fact: a short, literal description of what is learned (must be text-grounded, not abstract)

OPTIONAL FIELDS:
- source: character or item providing the information (if explicitly stated)

EXPLICIT TRIGGERS (extract ONLY when these appear):
- "learned that ..."
- "found out that ..."
- "was told that ..."
- "heard that ..."
- "read that ..."
- "discovered that ..."
- "realized that ..." (only if discovery is explicit, not internal inference)

RULES:
1. Extract a learn event ONLY if the text explicitly indicates knowledge acquisition
2. The fact field must:
   - Be directly supported by the text
   - Not be paraphrased beyond recognition
   - Be short and literal (a few words describing the learned content)
3. If the learned content is vague or unclear, OMIT the event
4. DO NOT infer knowledge from reactions alone (e.g., "He looked surprised" does not mean he learned something)
5. DO NOT extract if the character already knew the information

EXAMPLES:
- "Hermione found out that the stone was missing."
  → type: "learn", agent: "hermione_granger", fact: "stone_missing"
  
- "Harry learned that Sirius was his godfather."
  → type: "learn", agent: "harry_potter", fact: "sirius_is_godfather", source: null
  
- "Ron was told by Fred that the train would leave at eleven."
  → type: "learn", agent: "ron_weasley", fact: "train_leaves_at_eleven", source: "fred_weasley"
  
- "She read in the Daily Prophet that the prisoner had escaped."
  → type: "learn", agent: "she_id", fact: "prisoner_escaped", source: "daily_prophet"
  
- "He seemed surprised by the news." (no explicit learning)
  → DO NOT extract as learn (reaction only, no explicit knowledge acquisition)

=== IMPLIED PRESENCE (OPTIONAL) ===
Use "implied_presence" to record when an entity is EXPLICITLY tied to a location without a direct movement event.

TRIGGERS (extract ONLY when EXPLICITLY stated):
1. POSSESSED OBJECT AT LOCATION: "His wand was on the table in the kitchen"
   → The wand is in the kitchen (implied_presence: wand at kitchen)
   
2. BODY/SELF-REFERENCE: "He found himself in a dark room" / "She noticed her hands were shaking in the library"
   → The character is at that location (implied_presence: character at location)
   
3. OWNED CONTAINER/ROOM: "Harry's trunk was in his bedroom at Privet Drive"
   → The trunk is in the bedroom (implied_presence: trunk at bedroom)

FORMAT:
- entity: character_id OR item_id (the entity whose presence is implied)
- location: location_id (the location where the entity is present)

EXAMPLES:
- "Harry's wand lay on the nightstand in the dormitory"
  → implied_presence: [{{"entity": "harry_wand", "location": "dormitory"}}]
  
- "She woke up in the hospital wing"
  → implied_presence: [{{"entity": "character_id", "location": "hospital_wing"}}]
  
- "His books were scattered across the common room floor"
  → implied_presence: [{{"entity": "books", "location": "common_room"}}]

DO NOT EXTRACT implied_presence if:
- The presence is only inferred (not explicitly stated)
- A movement event (arrive, leave) already captures the location
- The location is vague or unidentified

If no implied_presence exists, return empty array: "implied_presence": []

CRITICAL RULES:
- Extract ALL farewell/praise/encourage events, especially from hostile characters
- Include initial_rules ONLY for relationships EXPLICITLY stated or MODIFIED in this chapter
- DO NOT restate known relationships from the continuity context
- source_text MUST be an actual quote from the chapter
- Use relevance="causal" if the item participates in an event in this chapter
- Use relevance="latent" if the item is extracted under the CHEKHOV RULE
- Treat this chapter as a DELTA over the continuity context:
  - DO NOT restate unchanged relationships or states
  - ONLY extract new events, changes, or contradictions introduced in this chapter

Return ONLY valid JSON, no markdown or explanations."""
