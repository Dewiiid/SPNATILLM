"""Clothing system models for strip poker."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ClothingLayer(str, Enum):
    OUTERWEAR = "outerwear"
    TOP = "top"
    BOTTOM = "bottom"
    UNDERWEAR = "underwear"
    FOOTWEAR = "footwear"
    ACCESSORIES = "accessories"


class ClothingPosition(str, Enum):
    HEAD = "head"
    TORSO = "torso"
    LEGS = "legs"
    FEET = "feet"
    HANDS = "hands"
    NECK = "neck"
    WAIST = "waist"
    FULL_BODY = "full_body"


# Removal priority: higher number = removed first
LAYER_PRIORITY = {
    ClothingLayer.ACCESSORIES: 10,
    ClothingLayer.OUTERWEAR: 20,
    ClothingLayer.FOOTWEAR: 30,
    ClothingLayer.TOP: 40,
    ClothingLayer.BOTTOM: 50,
    ClothingLayer.UNDERWEAR: 60,
}


class ClothingItem(BaseModel):
    """A single piece of clothing."""

    name: str = Field(..., description="Display name of the clothing item")
    layer: ClothingLayer = Field(..., description="Which layer this item belongs to")
    position: ClothingPosition = Field(
        default=ClothingPosition.TORSO, description="Body position"
    )
    generic: bool = Field(
        default=False, description="Whether this is a default/generic item"
    )
    description: str = Field(
        default="", description="Visual description for image generation"
    )
    removed: bool = Field(default=False, description="Whether this has been removed")

    @property
    def removal_priority(self) -> int:
        return LAYER_PRIORITY.get(self.layer, 50)


class ClothingState(BaseModel):
    """Complete clothing state for a character."""

    items: list[ClothingItem] = Field(default_factory=list)

    @property
    def worn_items(self) -> list[ClothingItem]:
        return [item for item in self.items if not item.removed]

    @property
    def removed_items(self) -> list[ClothingItem]:
        return [item for item in self.items if item.removed]

    @property
    def total_layers(self) -> int:
        return len(self.items)

    @property
    def remaining_layers(self) -> int:
        return len(self.worn_items)

    @property
    def is_fully_stripped(self) -> bool:
        return self.remaining_layers == 0

    def get_next_removal(self) -> Optional[ClothingItem]:
        """Get the next item to remove based on layer priority."""
        worn = self.worn_items
        if not worn:
            return None
        return min(worn, key=lambda item: -item.removal_priority)

    def remove_item(self, item_name: str) -> Optional[ClothingItem]:
        """Remove a specific clothing item by name."""
        for item in self.items:
            if item.name.lower() == item_name.lower() and not item.removed:
                item.removed = True
                return item
        return None

    def remove_next(self) -> Optional[ClothingItem]:
        """Remove the next item in priority order."""
        next_item = self.get_next_removal()
        if next_item:
            next_item.removed = True
        return next_item

    def describe_current(self) -> str:
        """Generate a text description of current clothing state."""
        worn = self.worn_items
        if not worn:
            return "completely naked"
        names = [item.name for item in worn]
        if len(names) == 1:
            return f"wearing only {names[0]}"
        return "wearing " + ", ".join(names[:-1]) + f" and {names[-1]}"

    def describe_for_image(self) -> str:
        """Generate a prompt-friendly description for image generation."""
        worn = self.worn_items
        if not worn:
            return "nude, no clothing"
        descriptions = []
        for item in worn:
            if item.description:
                descriptions.append(item.description)
            else:
                descriptions.append(item.name)
        return ", ".join(descriptions)
