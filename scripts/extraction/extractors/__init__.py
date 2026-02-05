"""
Extractors for the split extraction pipeline.

Each extractor is responsible for extracting a specific type of data from chapter text.
"""

from .character_and_location_extractor import CharacterAndLocationExtractor
from .items_extractor import ItemsExtractor
from .relationships_extractor import RelationshipsExtractor
from .events_extractor import EventsExtractor

__all__ = [
    "CharacterAndLocationExtractor",
    "ItemsExtractor",
    "RelationshipsExtractor",
    "EventsExtractor",
]
