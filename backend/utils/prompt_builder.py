"""Prompt construction for KoboldCPP dialogue generation."""
from __future__ import annotations

from ..models.character import GameCharacter
from ..models.game import GamePhase, PokerHand


SYSTEM_TEMPLATE = """You are playing the role of {name} in a strip poker game. Stay completely in character at all times.

CHARACTER DESCRIPTION:
{description}

PERSONALITY:
{personality}

{scenario_block}
RULES:
- You are playing Texas Hold'em strip poker with {opponent_count} other players.
- When you lose a round, you must remove one piece of clothing.
- React naturally to wins, losses, and the game situation.
- Keep responses to 1-3 sentences. Be expressive but concise.
- Never break character or acknowledge you are an AI.
- Your speech should match the character's established voice and mannerisms.
{example_block}"""


GAME_CONTEXT_TEMPLATE = """CURRENT GAME STATE:
- Round: {round_number}
- You are currently {clothing_description}.
- Your chips: {chips}
- Pot: {pot}
{hand_info}
{opponents_info}

SITUATION: {situation}

Respond as {name} would in this moment. Keep it to 1-3 sentences."""


def build_system_prompt(character: GameCharacter, opponent_count: int) -> str:
    """Build the system prompt from a character card."""
    card = character.card

    scenario_block = ""
    if card.scenario:
        scenario_block = f"SCENARIO CONTEXT:\n{card.scenario}\n\n"

    example_block = ""
    if card.mes_example:
        # Clean up example messages for context
        examples = card.mes_example.strip()
        if examples:
            example_block = (
                f"\nEXAMPLE DIALOGUE STYLE (use this as a guide for tone and speech patterns):\n"
                f"{examples}\n"
            )

    return SYSTEM_TEMPLATE.format(
        name=character.display_name,
        description=card.description,
        personality=card.personality or "No specific personality notes.",
        scenario_block=scenario_block,
        opponent_count=opponent_count,
        example_block=example_block,
    )


def build_game_prompt(
    character: GameCharacter,
    situation: str,
    round_number: int = 1,
    pot: int = 0,
    hand: PokerHand | None = None,
    opponents: list[dict] | None = None,
) -> str:
    """Build a game-context prompt for dialogue generation."""
    hand_info = ""
    if hand:
        card_display = ", ".join(c.display for c in hand.cards)
        hand_info = f"- Your hand: {card_display} ({hand.display})"

    opponents_info = ""
    if opponents:
        lines = []
        for opp in opponents:
            lines.append(
                f"  - {opp['name']}: {opp.get('clothing_desc', 'unknown clothing')}, "
                f"{opp.get('chips', '?')} chips"
            )
        opponents_info = "- Other players:\n" + "\n".join(lines)

    return GAME_CONTEXT_TEMPLATE.format(
        round_number=round_number,
        clothing_description=character.clothing_description,
        chips=character.chips,
        pot=pot,
        hand_info=hand_info,
        opponents_info=opponents_info,
        situation=situation,
        name=character.display_name,
    )


# Pre-built situation strings for common game events
SITUATIONS = {
    "game_start": "The game is just beginning. Introduce yourself and react to sitting down at the poker table.",
    "deal": "Cards have just been dealt. React to seeing your hand.",
    "win_round": "You just won this round! {loser_name} has to remove their {removed_item}.",
    "lose_round": "You just lost this round and must remove your {removed_item}. React to having to strip.",
    "watch_strip": "{stripper_name} just lost and is removing their {removed_item}. React to watching them strip.",
    "good_hand": "You look at your cards and you have a great hand. Try not to give it away.",
    "bad_hand": "You look at your cards and they're terrible. Decide whether to bluff or fold.",
    "opponent_fold": "{folder_name} has folded. React to them giving up.",
    "all_in": "You're going all in! This is a high-stakes moment.",
    "someone_naked": "{naked_name} has lost all their clothes! React to seeing them fully exposed.",
    "you_naked": "You've just lost your last piece of clothing. You're now completely naked at the table.",
    "eliminated": "{eliminated_name} has been eliminated from the game. React to their departure.",
    "final_two": "It's down to just you and {opponent_name}. The tension is high.",
    "victory": "You've won the entire game! Everyone else has been stripped and eliminated.",
    "defeat": "You've been eliminated from the game. Give your final thoughts.",
    "idle_banter": "There's a lull in the game. Make some conversation or comment on the situation.",
    "raise_reaction": "{raiser_name} just raised the bet to {amount}. React to this bold move.",
    "big_pot": "The pot has grown to {pot} chips. This is a huge round.",
}


def get_situation_prompt(
    situation_key: str, **kwargs: str
) -> str:
    """Get a situation prompt with variable substitution."""
    template = SITUATIONS.get(situation_key, situation_key)
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def build_image_prompt(
    character: GameCharacter,
    emotion: str = "neutral",
) -> dict[str, str]:
    """Build prompts for ComfyUI image generation.

    Returns dict with 'positive' and 'negative' prompt strings.
    """
    clothing_desc = character.clothing.describe_for_image()
    visual = character.visual_description or character.card.description

    # Extract key visual features from description
    emotion_modifiers = {
        "neutral": "calm expression, relaxed pose",
        "happy": "smiling, cheerful expression",
        "smug": "smirking, confident expression",
        "embarrassed": "blushing, covering themselves slightly, embarrassed expression",
        "angry": "frowning, annoyed expression",
        "nervous": "anxious expression, fidgeting",
        "flirty": "playful smile, flirtatious expression",
        "sad": "downcast eyes, sad expression",
        "shocked": "wide eyes, surprised expression",
        "confident": "bold pose, self-assured expression",
    }
    emotion_desc = emotion_modifiers.get(emotion, emotion)

    positive = (
        f"portrait of a character, {visual}, "
        f"{clothing_desc}, {emotion_desc}, "
        f"sitting at a poker table, casino setting, "
        f"detailed face, high quality, best quality"
    )

    negative = (
        "lowres, bad anatomy, bad hands, text, error, missing fingers, "
        "extra digit, fewer digits, cropped, worst quality, low quality, "
        "normal quality, jpeg artifacts, signature, watermark, username, "
        "blurry, deformed, multiple people, extra limbs"
    )

    return {"positive": positive, "negative": negative}
