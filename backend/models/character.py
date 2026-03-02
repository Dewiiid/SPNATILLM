"""Character models — parsed from TavernAI / Chub.ai character cards."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .clothing import ClothingState


class CharacterCard(BaseModel):
    """Raw character card data (TavernAI V2 spec)."""

    name: str = ""
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    creator_notes: str = ""
    tags: list[str] = Field(default_factory=list)
    # V2 extensions
    character_book: Optional[dict[str, Any]] = None
    extensions: dict[str, Any] = Field(default_factory=dict)


class GameCharacter(BaseModel):
    """A character loaded into the game with all state."""

    id: str = Field(..., description="Unique identifier for this game instance")
    card: CharacterCard = Field(..., description="Original character card data")
    clothing: ClothingState = Field(
        default_factory=ClothingState, description="Current clothing state"
    )
    # Image state
    current_image_url: Optional[str] = Field(
        default=None, description="URL of current rendered image"
    )
    reference_image_b64: Optional[str] = Field(
        default=None, description="Base64 reference image from card (for img2img)"
    )
    # Game state
    chips: int = Field(default=100, description="Current chip count")
    is_eliminated: bool = Field(default=False, description="Whether player is out")
    is_human: bool = Field(default=False, description="Whether this is the human player")
    # Dialogue state
    last_dialogue: str = Field(default="", description="Last spoken line")
    dialogue_history: list[dict[str, str]] = Field(
        default_factory=list, description="Chat history for context"
    )
    # Visual description extracted/inferred from card
    visual_description: str = Field(
        default="", description="Character's physical appearance for image gen"
    )
    # Emotion tracking for more expressive dialogue
    current_emotion: str = Field(default="neutral", description="Current emotional state")

    @property
    def display_name(self) -> str:
        return self.card.name or "Unknown"

    @property
    def clothing_description(self) -> str:
        return self.clothing.describe_current()

    @property
    def is_naked(self) -> bool:
        return self.clothing.is_fully_stripped

    def add_dialogue(self, role: str, content: str):
        """Add a dialogue entry to history."""
        self.dialogue_history.append({"role": role, "content": content})
        # Keep history manageable — last 20 exchanges
        if len(self.dialogue_history) > 40:
            self.dialogue_history = self.dialogue_history[-40:]
