"""Clothing detection and normalization from character card descriptions.

Responsible for:
1. Extracting clothing items mentioned in character descriptions
2. Filling in missing items to ensure a fair game
3. Normalizing clothing into a consistent removal order
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ..models.clothing import ClothingItem, ClothingLayer, ClothingPosition, ClothingState

logger = logging.getLogger(__name__)


# Comprehensive keyword→(layer, position) mapping
CLOTHING_KEYWORDS: dict[str, tuple[ClothingLayer, ClothingPosition]] = {
    # Outerwear
    "jacket": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "coat": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "hoodie": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "blazer": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "cardigan": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "vest": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "cape": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "cloak": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "sweater": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "pullover": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "parka": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "windbreaker": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "overcoat": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "trench coat": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "leather jacket": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "denim jacket": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "bomber jacket": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "robe": (ClothingLayer.OUTERWEAR, ClothingPosition.FULL_BODY),
    "kimono": (ClothingLayer.OUTERWEAR, ClothingPosition.FULL_BODY),
    "poncho": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "shawl": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    # Tops
    "shirt": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "blouse": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "t-shirt": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "tee": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "tank top": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "crop top": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "tube top": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "camisole": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "corset": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "bustier": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "bodysuit": (ClothingLayer.TOP, ClothingPosition.FULL_BODY),
    "halter": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "polo": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "dress shirt": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "button-up": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "henley": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "turtleneck": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "uniform top": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "sailor top": (ClothingLayer.TOP, ClothingPosition.TORSO),
    "school shirt": (ClothingLayer.TOP, ClothingPosition.TORSO),
    # Bottoms
    "pants": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "jeans": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "shorts": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "skirt": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "trousers": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "leggings": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "sweatpants": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "joggers": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "slacks": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "miniskirt": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "pleated skirt": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "cargo pants": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "school skirt": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "uniform skirt": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    "culottes": (ClothingLayer.BOTTOM, ClothingPosition.LEGS),
    # Full-body (counts as both top + bottom)
    "dress": (ClothingLayer.TOP, ClothingPosition.FULL_BODY),
    "gown": (ClothingLayer.TOP, ClothingPosition.FULL_BODY),
    "jumpsuit": (ClothingLayer.TOP, ClothingPosition.FULL_BODY),
    "romper": (ClothingLayer.TOP, ClothingPosition.FULL_BODY),
    "overalls": (ClothingLayer.OUTERWEAR, ClothingPosition.FULL_BODY),
    "catsuit": (ClothingLayer.TOP, ClothingPosition.FULL_BODY),
    "leotard": (ClothingLayer.TOP, ClothingPosition.FULL_BODY),
    "swimsuit": (ClothingLayer.TOP, ClothingPosition.FULL_BODY),
    "bikini": (ClothingLayer.TOP, ClothingPosition.TORSO),
    # Underwear
    "underwear": (ClothingLayer.UNDERWEAR, ClothingPosition.LEGS),
    "panties": (ClothingLayer.UNDERWEAR, ClothingPosition.LEGS),
    "boxers": (ClothingLayer.UNDERWEAR, ClothingPosition.LEGS),
    "briefs": (ClothingLayer.UNDERWEAR, ClothingPosition.LEGS),
    "thong": (ClothingLayer.UNDERWEAR, ClothingPosition.LEGS),
    "bra": (ClothingLayer.UNDERWEAR, ClothingPosition.TORSO),
    "sports bra": (ClothingLayer.UNDERWEAR, ClothingPosition.TORSO),
    "bikini top": (ClothingLayer.UNDERWEAR, ClothingPosition.TORSO),
    "bikini bottom": (ClothingLayer.UNDERWEAR, ClothingPosition.LEGS),
    "undershirt": (ClothingLayer.UNDERWEAR, ClothingPosition.TORSO),
    "lingerie": (ClothingLayer.UNDERWEAR, ClothingPosition.TORSO),
    # Footwear
    "shoes": (ClothingLayer.FOOTWEAR, ClothingPosition.FEET),
    "boots": (ClothingLayer.FOOTWEAR, ClothingPosition.FEET),
    "sneakers": (ClothingLayer.FOOTWEAR, ClothingPosition.FEET),
    "heels": (ClothingLayer.FOOTWEAR, ClothingPosition.FEET),
    "high heels": (ClothingLayer.FOOTWEAR, ClothingPosition.FEET),
    "sandals": (ClothingLayer.FOOTWEAR, ClothingPosition.FEET),
    "slippers": (ClothingLayer.FOOTWEAR, ClothingPosition.FEET),
    "loafers": (ClothingLayer.FOOTWEAR, ClothingPosition.FEET),
    "socks": (ClothingLayer.FOOTWEAR, ClothingPosition.FEET),
    "stockings": (ClothingLayer.FOOTWEAR, ClothingPosition.LEGS),
    "thigh-highs": (ClothingLayer.FOOTWEAR, ClothingPosition.LEGS),
    "knee socks": (ClothingLayer.FOOTWEAR, ClothingPosition.LEGS),
    # Accessories
    "hat": (ClothingLayer.ACCESSORIES, ClothingPosition.HEAD),
    "cap": (ClothingLayer.ACCESSORIES, ClothingPosition.HEAD),
    "beret": (ClothingLayer.ACCESSORIES, ClothingPosition.HEAD),
    "headband": (ClothingLayer.ACCESSORIES, ClothingPosition.HEAD),
    "ribbon": (ClothingLayer.ACCESSORIES, ClothingPosition.HEAD),
    "hairpin": (ClothingLayer.ACCESSORIES, ClothingPosition.HEAD),
    "glasses": (ClothingLayer.ACCESSORIES, ClothingPosition.HEAD),
    "sunglasses": (ClothingLayer.ACCESSORIES, ClothingPosition.HEAD),
    "gloves": (ClothingLayer.ACCESSORIES, ClothingPosition.HANDS),
    "scarf": (ClothingLayer.ACCESSORIES, ClothingPosition.NECK),
    "tie": (ClothingLayer.ACCESSORIES, ClothingPosition.NECK),
    "necktie": (ClothingLayer.ACCESSORIES, ClothingPosition.NECK),
    "bow tie": (ClothingLayer.ACCESSORIES, ClothingPosition.NECK),
    "choker": (ClothingLayer.ACCESSORIES, ClothingPosition.NECK),
    "necklace": (ClothingLayer.ACCESSORIES, ClothingPosition.NECK),
    "belt": (ClothingLayer.ACCESSORIES, ClothingPosition.WAIST),
    "watch": (ClothingLayer.ACCESSORIES, ClothingPosition.HANDS),
    "bracelet": (ClothingLayer.ACCESSORIES, ClothingPosition.HANDS),
    "earrings": (ClothingLayer.ACCESSORIES, ClothingPosition.HEAD),
    "armor": (ClothingLayer.OUTERWEAR, ClothingPosition.TORSO),
    "gauntlets": (ClothingLayer.ACCESSORIES, ClothingPosition.HANDS),
}


# Default clothing set — used to fill in missing layers
DEFAULT_CLOTHING = [
    ClothingItem(
        name="jacket", layer=ClothingLayer.OUTERWEAR,
        position=ClothingPosition.TORSO, generic=True
    ),
    ClothingItem(
        name="shirt", layer=ClothingLayer.TOP,
        position=ClothingPosition.TORSO, generic=True
    ),
    ClothingItem(
        name="pants", layer=ClothingLayer.BOTTOM,
        position=ClothingPosition.LEGS, generic=True
    ),
    ClothingItem(
        name="shoes", layer=ClothingLayer.FOOTWEAR,
        position=ClothingPosition.FEET, generic=True
    ),
    ClothingItem(
        name="socks", layer=ClothingLayer.FOOTWEAR,
        position=ClothingPosition.FEET, generic=True
    ),
    ClothingItem(
        name="underwear", layer=ClothingLayer.UNDERWEAR,
        position=ClothingPosition.LEGS, generic=True
    ),
]

MIN_CLOTHING_ITEMS = 5
MAX_CLOTHING_ITEMS = 8


def detect_clothing_from_text(text: str) -> list[ClothingItem]:
    """Extract clothing items from a character description using keyword matching.

    Scans the text for known clothing keywords and returns a deduplicated
    list of ClothingItems.
    """
    if not text:
        return []

    text_lower = text.lower()
    found: dict[str, ClothingItem] = {}

    # Sort keywords by length (longest first) to match multi-word items first
    sorted_keywords = sorted(CLOTHING_KEYWORDS.keys(), key=len, reverse=True)

    for keyword in sorted_keywords:
        # Use word boundary matching to avoid false positives
        pattern = r"\b" + re.escape(keyword) + r"s?\b"
        if re.search(pattern, text_lower):
            if keyword not in found:
                layer, position = CLOTHING_KEYWORDS[keyword]
                found[keyword] = ClothingItem(
                    name=keyword,
                    layer=layer,
                    position=position,
                    generic=False,
                    description=_extract_clothing_context(text, keyword),
                )

    return list(found.values())


def _extract_clothing_context(text: str, keyword: str) -> str:
    """Extract surrounding context for a clothing item to improve image generation.

    For example, if the description says "a red leather jacket", we want to
    capture "red leather jacket" not just "jacket".
    """
    pattern = r"(?:\w+\s+){0,3}" + re.escape(keyword) + r"s?"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return keyword


def normalize_clothing(
    detected_items: list[ClothingItem],
    min_items: int = MIN_CLOTHING_ITEMS,
    max_items: int = MAX_CLOTHING_ITEMS,
    target_items: Optional[int] = None,
) -> ClothingState:
    """Normalize a set of detected clothing items into a valid game clothing state.

    Rules:
    1. Must have at least `min_items` items
    2. Should not exceed `max_items`
    3. Missing essential layers are filled with defaults
    4. If target_items is set, pad/trim to match (for fairness between players)
    """
    items = list(detected_items)

    # Track which layers we have
    layers_present = {item.layer for item in items}

    # Essential layers that must be present
    essential_layers = {
        ClothingLayer.TOP,
        ClothingLayer.BOTTOM,
        ClothingLayer.UNDERWEAR,
    }

    # Fill in missing essential layers
    for default_item in DEFAULT_CLOTHING:
        if default_item.layer in essential_layers and default_item.layer not in layers_present:
            items.append(default_item.model_copy())
            layers_present.add(default_item.layer)

    # If still under minimum, add more defaults
    if len(items) < min_items:
        for default_item in DEFAULT_CLOTHING:
            if len(items) >= min_items:
                break
            # Don't duplicate items we already have
            existing_names = {item.name.lower() for item in items}
            if default_item.name.lower() not in existing_names:
                items.append(default_item.model_copy())

    # If we have a target and are still short, add accessories
    target = target_items or min_items
    if len(items) < target:
        filler_accessories = [
            ClothingItem(name="belt", layer=ClothingLayer.ACCESSORIES,
                        position=ClothingPosition.WAIST, generic=True),
            ClothingItem(name="watch", layer=ClothingLayer.ACCESSORIES,
                        position=ClothingPosition.HANDS, generic=True),
            ClothingItem(name="hat", layer=ClothingLayer.ACCESSORIES,
                        position=ClothingPosition.HEAD, generic=True),
        ]
        existing_names = {item.name.lower() for item in items}
        for filler in filler_accessories:
            if len(items) >= target:
                break
            if filler.name.lower() not in existing_names:
                items.append(filler)

    # If over max, trim accessories first, then outerwear
    if len(items) > max_items:
        # Sort by: generic first, then accessories first
        items.sort(
            key=lambda x: (
                not x.generic,
                x.layer != ClothingLayer.ACCESSORIES,
                x.layer != ClothingLayer.OUTERWEAR,
            )
        )
        items = items[:max_items]

    # Final sort by removal order (accessories → outerwear → footwear → top → bottom → underwear)
    items.sort(key=lambda x: x.removal_priority)

    return ClothingState(items=items)


def equalize_clothing_counts(
    states: list[ClothingState],
) -> list[ClothingState]:
    """Ensure all players have roughly the same number of clothing items.

    Pads shorter lists up to match the longest, within ±1 item tolerance.
    """
    if not states:
        return states

    max_count = max(s.total_layers for s in states)
    target = max(max_count, MIN_CLOTHING_ITEMS)

    result = []
    for state in states:
        if state.total_layers < target - 1:
            # Re-normalize with the target count
            state = normalize_clothing(
                state.items,
                min_items=target - 1,
                target_items=target,
            )
        result.append(state)

    return result


def build_clothing_for_card(
    description: str,
    personality: str = "",
    target_count: Optional[int] = None,
) -> ClothingState:
    """Full pipeline: detect clothing from card text, normalize, and return state.

    This is the main entry point for converting a character card's description
    into a playable clothing configuration.
    """
    # Combine description and personality for better detection
    full_text = f"{description}\n{personality}"

    detected = detect_clothing_from_text(full_text)

    logger.info(
        f"Detected {len(detected)} clothing items: "
        f"{[item.name for item in detected]}"
    )

    state = normalize_clothing(
        detected,
        min_items=MIN_CLOTHING_ITEMS,
        max_items=MAX_CLOTHING_ITEMS,
        target_items=target_count,
    )

    logger.info(
        f"Normalized to {state.total_layers} items: "
        f"{[item.name for item in state.items]}"
    )

    return state
