"""Character import and management endpoints."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..models.character import CharacterCard, GameCharacter
from ..services.chub import ChubService
from ..services.clothing import build_clothing_for_card
from ..utils.card_parser import parse_card_from_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/characters", tags=["characters"])

# In-memory character store (per session; reset on restart)
_characters: dict[str, GameCharacter] = {}


def get_chub_service() -> ChubService:
    """Get configured ChubService instance."""
    # In production, this would read from config
    return ChubService()


class ImportRequest(BaseModel):
    url: str  # Chub.ai URL or slug


class ImportResponse(BaseModel):
    id: str
    name: str
    clothing_items: list[str]
    has_image: bool
    description_preview: str


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


@router.post("/import/url", response_model=ImportResponse)
async def import_from_url(request: ImportRequest):
    """Import a character from a Chub.ai URL or slug."""
    chub = get_chub_service()

    try:
        card, avatar_b64 = await chub.fetch_character(request.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch character: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch character from Chub.ai: {e}",
        )

    character = _create_game_character(card, avatar_b64)
    return _character_to_response(character)


@router.post("/import/file", response_model=ImportResponse)
async def import_from_file(file: UploadFile = File(...)):
    """Import a character from an uploaded card file (PNG or JSON)."""
    content = await file.read()

    try:
        card, avatar_b64 = parse_card_from_bytes(content, file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    character = _create_game_character(card, avatar_b64)
    return _character_to_response(character)


@router.post("/search")
async def search_characters(request: SearchRequest):
    """Search for characters on Chub.ai."""
    chub = get_chub_service()
    results = await chub.search_characters(request.query, request.limit)
    return {"results": results}


@router.get("/{character_id}")
async def get_character(character_id: str):
    """Get a loaded character's details."""
    character = _characters.get(character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    return {
        "id": character.id,
        "name": character.display_name,
        "description": character.card.description[:500],
        "personality": character.card.personality,
        "clothing": [
            {
                "name": item.name,
                "layer": item.layer.value,
                "removed": item.removed,
                "generic": item.generic,
            }
            for item in character.clothing.items
        ],
        "clothing_description": character.clothing_description,
        "has_image": character.reference_image_b64 is not None,
        "visual_description": character.visual_description,
    }


@router.get("/")
async def list_characters():
    """List all loaded characters."""
    return {
        "characters": [
            {
                "id": c.id,
                "name": c.display_name,
                "clothing_count": c.clothing.total_layers,
                "has_image": c.reference_image_b64 is not None,
            }
            for c in _characters.values()
        ]
    }


@router.delete("/{character_id}")
async def remove_character(character_id: str):
    """Remove a loaded character."""
    if character_id not in _characters:
        raise HTTPException(status_code=404, detail="Character not found")
    del _characters[character_id]
    return {"status": "removed"}


def _create_game_character(
    card: CharacterCard, avatar_b64: Optional[str] = None
) -> GameCharacter:
    """Create a GameCharacter from a card, with clothing detection."""
    char_id = f"char_{uuid.uuid4().hex[:8]}"

    # Build clothing state from card description
    clothing = build_clothing_for_card(
        description=card.description,
        personality=card.personality,
    )

    # Extract visual description for image generation
    visual_desc = _extract_visual_description(card.description)

    character = GameCharacter(
        id=char_id,
        card=card,
        clothing=clothing,
        reference_image_b64=avatar_b64,
        visual_description=visual_desc,
    )

    _characters[char_id] = character
    logger.info(
        f"Imported character '{card.name}' as {char_id} "
        f"with {clothing.total_layers} clothing items"
    )

    return character


def _extract_visual_description(description: str) -> str:
    """Extract physical appearance details from a character description.

    Looks for common patterns like hair color, eye color, body type, etc.
    """
    # Simple heuristic: take the first paragraph or first 300 chars
    # that likely describes appearance
    lines = description.strip().split("\n")
    appearance_keywords = [
        "hair", "eyes", "eye", "skin", "tall", "short", "slim", "muscular",
        "athletic", "petite", "curvy", "build", "complexion", "face",
        "figure", "body", "appearance", "looks", "height", "weight",
    ]

    appearance_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(kw in line.lower() for kw in appearance_keywords):
            appearance_lines.append(line)

    if appearance_lines:
        return " ".join(appearance_lines)[:500]

    # Fallback: first 300 chars
    return description[:300]


def _character_to_response(character: GameCharacter) -> ImportResponse:
    return ImportResponse(
        id=character.id,
        name=character.display_name,
        clothing_items=[item.name for item in character.clothing.items],
        has_image=character.reference_image_b64 is not None,
        description_preview=character.card.description[:200],
    )


def get_character_store() -> dict[str, GameCharacter]:
    """Access the in-memory character store (used by game routes)."""
    return _characters
