"""Service for generating character dialogue via KoboldCPP."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from ..models.character import GameCharacter
from ..models.game import PokerHand
from ..utils.prompt_builder import (
    build_game_prompt,
    build_system_prompt,
    get_situation_prompt,
)

logger = logging.getLogger(__name__)


class KoboldService:
    """Generate in-character dialogue using a locally hosted KoboldCPP instance."""

    def __init__(
        self,
        url: str = "http://localhost:5001",
        max_length: int = 300,
        temperature: float = 0.75,
        top_p: float = 0.9,
        top_k: int = 40,
        rep_pen: float = 1.15,
        timeout: float = 60.0,
    ):
        self.url = url.rstrip("/")
        self.max_length = max_length
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.rep_pen = rep_pen
        self.timeout = timeout

    async def check_health(self) -> bool:
        """Check if KoboldCPP is running and responding."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.url}/api/v1/info/version")
                return resp.status_code == 200
        except Exception:
            return False

    async def get_model_info(self) -> Optional[dict]:
        """Get info about the loaded model."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.url}/api/v1/model")
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return None

    async def generate_dialogue(
        self,
        character: GameCharacter,
        situation: str,
        round_number: int = 1,
        pot: int = 0,
        hand: Optional[PokerHand] = None,
        opponents: Optional[list[dict]] = None,
        opponent_count: int = 3,
    ) -> str:
        """Generate in-character dialogue for a game situation.

        Args:
            character: The character to generate dialogue for.
            situation: Description of what's happening (e.g., "You just lost and must remove your shirt").
            round_number: Current round number.
            pot: Current pot size.
            hand: Character's poker hand (if visible).
            opponents: List of opponent info dicts.
            opponent_count: Total number of opponents.

        Returns:
            Generated dialogue string.
        """
        system_prompt = build_system_prompt(character, opponent_count)
        game_prompt = build_game_prompt(
            character,
            situation=situation,
            round_number=round_number,
            pot=pot,
            hand=hand,
            opponents=opponents,
        )

        # Build the full prompt with chat history for context
        full_prompt = self._build_instruct_prompt(
            system_prompt, character, game_prompt
        )

        try:
            response_text = await self._generate(full_prompt)
            # Clean up the response
            cleaned = self._clean_response(response_text, character.display_name)
            # Store in dialogue history
            character.add_dialogue("assistant", cleaned)
            return cleaned

        except Exception as e:
            logger.error(f"Dialogue generation failed: {e}")
            return self._fallback_dialogue(situation)

    def _build_instruct_prompt(
        self,
        system_prompt: str,
        character: GameCharacter,
        game_prompt: str,
    ) -> str:
        """Build a complete instruct-format prompt.

        Uses a generic instruct format that works with most models.
        KoboldCPP handles template conversion if the model has a chat template.
        """
        parts = []

        # System context
        parts.append(f"### System:\n{system_prompt}\n")

        # Recent dialogue history (last 6 exchanges for context)
        recent_history = character.dialogue_history[-12:]
        for entry in recent_history:
            role = entry["role"]
            content = entry["content"]
            if role == "user" or role == "system":
                parts.append(f"### Instruction:\n{content}\n")
            else:
                parts.append(f"### Response:\n{content}\n")

        # Current game situation
        parts.append(f"### Instruction:\n{game_prompt}\n")

        # Prompt for response
        parts.append(f"### Response:\n{character.display_name}: ")

        return "\n".join(parts)

    async def _generate(self, prompt: str) -> str:
        """Send a generation request to KoboldCPP."""
        payload = {
            "prompt": prompt,
            "max_length": self.max_length,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "rep_pen": self.rep_pen,
            "stop_sequence": [
                "\n### ",
                "\n## ",
                "\nSystem:",
                "\nInstruction:",
                "\nHuman:",
                "\nUser:",
                "\n\n\n",
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Try the KoboldCPP API v1 endpoint first
            resp = await client.post(
                f"{self.url}/api/v1/generate",
                json=payload,
            )

            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    return results[0].get("text", "")

            # Fallback: try the /api/extra/generate endpoint
            resp = await client.post(
                f"{self.url}/api/extra/generate/stream",
                json=payload,
            )

            if resp.status_code == 200:
                return resp.text

        raise RuntimeError(
            f"KoboldCPP generation failed with status {resp.status_code}: {resp.text}"
        )

    def _clean_response(self, text: str, character_name: str) -> str:
        """Clean up generated text."""
        text = text.strip()

        # Remove character name prefix if model added it
        prefixes = [f"{character_name}:", f"{character_name} :", f'"{character_name}:']
        for prefix in prefixes:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix) :].strip()

        # Remove surrounding quotes if present
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]

        # Remove any trailing incomplete sentences
        if text and text[-1] not in ".!?\"'…~)":
            last_punct = max(
                text.rfind("."), text.rfind("!"), text.rfind("?"), text.rfind("~")
            )
            if last_punct > len(text) * 0.5:
                text = text[: last_punct + 1]

        # Truncate if too long (shouldn't happen with max_length but safety check)
        if len(text) > 500:
            last_punct = text[:500].rfind(".")
            if last_punct > 200:
                text = text[: last_punct + 1]
            else:
                text = text[:500] + "..."

        return text or "..."

    def _fallback_dialogue(self, situation: str) -> str:
        """Provide a generic fallback if generation fails."""
        if "win" in situation.lower():
            return "Heh, lucky me~"
        elif "lose" in situation.lower() or "remove" in situation.lower():
            return "Ugh... fine."
        elif "start" in situation.lower():
            return "Let's get this game going."
        else:
            return "..."

    async def generate_with_situation(
        self,
        character: GameCharacter,
        situation_key: str,
        opponent_count: int = 3,
        round_number: int = 1,
        pot: int = 0,
        hand: Optional[PokerHand] = None,
        opponents: Optional[list[dict]] = None,
        **situation_kwargs: str,
    ) -> str:
        """Convenience method: generate dialogue from a situation key.

        Uses pre-built situation templates from prompt_builder.
        """
        situation = get_situation_prompt(situation_key, **situation_kwargs)
        return await self.generate_dialogue(
            character=character,
            situation=situation,
            round_number=round_number,
            pot=pot,
            hand=hand,
            opponents=opponents,
            opponent_count=opponent_count,
        )
