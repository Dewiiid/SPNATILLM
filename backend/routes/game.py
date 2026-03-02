"""Game session management with WebSocket support for real-time play."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..models.character import GameCharacter
from ..models.game import GamePhase, GameState, PlayerAction
from ..services.clothing import equalize_clothing_counts
from ..services.comfyui import ComfyUIService
from ..services.kobold import KoboldService
from ..services.poker import PokerEngine
from .characters import get_character_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/game", tags=["game"])

# Active games
_games: dict[str, "GameSession"] = {}


class StartGameRequest(BaseModel):
    character_ids: list[str]  # IDs of AI opponents
    player_name: str = "Player"


class GameActionRequest(BaseModel):
    action: str  # fold, check, call, raise
    amount: int = 0


class GameSession:
    """Manages a complete game session with all integrations."""

    def __init__(
        self,
        game_id: str,
        human_player: GameCharacter,
        ai_players: list[GameCharacter],
    ):
        self.game_id = game_id
        self.human = human_player
        self.ai_players = ai_players
        self.all_players = [human_player] + ai_players
        self.player_map = {p.id: p for p in self.all_players}

        self.engine = PokerEngine()
        self.kobold = KoboldService()
        self.comfyui = ComfyUIService()

        self.game_state: Optional[GameState] = None
        self.websockets: list[WebSocket] = []
        self.log: list[dict] = []

    async def broadcast(self, event: dict):
        """Send an event to all connected WebSocket clients."""
        msg = json.dumps(event)
        dead = []
        for ws in self.websockets:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.websockets.remove(ws)

    async def start(self):
        """Initialize and start the game."""
        player_ids = [p.id for p in self.all_players]
        self.game_state = self.engine.new_game(player_ids)
        self.game_state.phase = GamePhase.DEALING

        # Equalize clothing
        states = [p.clothing for p in self.all_players]
        equalized = equalize_clothing_counts(states)
        for player, state in zip(self.all_players, equalized):
            player.clothing = state

        # Generate initial images for all AI characters
        await self._generate_all_images()

        # Generate intro dialogue
        await self._generate_intro_dialogue()

        await self.broadcast({
            "type": "game_started",
            "players": [self._player_info(p) for p in self.all_players],
            "round": 0,
        })

        # Start first round
        await self.start_round()

    async def start_round(self):
        """Begin a new poker round."""
        self.game_state = self.engine.start_round(self.game_state)

        await self.broadcast({
            "type": "round_started",
            "round": self.game_state.round_number,
            "dealer": self.game_state.player_ids[self.game_state.dealer_index],
            "pot": self.game_state.pot,
        })

        # Send hole cards to human player
        human_hand = self.game_state.player_hands.get(self.human.id, [])
        await self.broadcast({
            "type": "hole_cards",
            "cards": [{"rank": c.display_rank, "suit": c.suit.value} for c in human_hand],
        })

        # AI pre-flop actions
        await self._run_ai_betting_round()

    async def process_human_action(self, action_str: str, amount: int = 0):
        """Process the human player's action."""
        try:
            action = PlayerAction(action_str)
        except ValueError:
            await self.broadcast({
                "type": "error",
                "message": f"Invalid action: {action_str}",
            })
            return

        result = self.engine.process_action(
            self.game_state, self.human.id, action, amount
        )

        await self.broadcast({
            "type": "player_action",
            "player_id": self.human.id,
            "player_name": self.human.display_name,
            "action": action.value,
            "amount": result.get("amount", 0),
            "pot": self.game_state.pot,
        })

        if result.get("round_complete"):
            await self._advance_street()
        else:
            # Continue with AI actions
            await self._run_ai_betting_round()

    async def _run_ai_betting_round(self):
        """Process AI player actions for the current betting round."""
        gs = self.game_state

        for _ in range(len(gs.player_ids)):
            current_pid = gs.player_ids[gs.current_player_index]

            # Skip human — they act via WebSocket
            if current_pid == self.human.id:
                await self.broadcast({
                    "type": "your_turn",
                    "current_bet": gs.current_bet,
                    "your_bet": gs.player_bets.get(self.human.id, 0),
                    "pot": gs.pot,
                    "can_check": gs.player_bets.get(self.human.id, 0) >= gs.current_bet,
                })
                return  # Wait for human input

            if gs.player_folded.get(current_pid, False):
                self.engine._advance_player(gs)
                continue

            # AI decision
            player = self.player_map.get(current_pid)
            if not player:
                continue

            hand_strength = self.engine.estimate_hand_strength(
                gs.player_hands.get(current_pid, []),
                gs.community_cards,
            )

            action, amount = self.engine.get_ai_action(gs, current_pid, hand_strength)
            result = self.engine.process_action(gs, current_pid, action, amount)

            await self.broadcast({
                "type": "player_action",
                "player_id": current_pid,
                "player_name": player.display_name,
                "action": action.value,
                "amount": result.get("amount", 0),
                "pot": gs.pot,
            })

            # Small delay for dramatic effect
            await asyncio.sleep(0.8)

            if result.get("round_complete"):
                await self._advance_street()
                return

    async def _advance_street(self):
        """Advance to the next street (flop, turn, river) or showdown."""
        gs = self.game_state
        community_count = len(gs.community_cards)

        # Check if only one player remains
        if len(gs.active_player_ids) <= 1:
            await self._showdown()
            return

        if community_count == 0:
            # Deal flop
            cards = self.engine.deal_community(gs, 3)
            await self.broadcast({
                "type": "community_cards",
                "stage": "flop",
                "cards": [{"rank": c.display_rank, "suit": c.suit.value} for c in cards],
                "all_community": [
                    {"rank": c.display_rank, "suit": c.suit.value}
                    for c in gs.community_cards
                ],
            })
        elif community_count == 3:
            # Deal turn
            cards = self.engine.deal_community(gs, 1)
            await self.broadcast({
                "type": "community_cards",
                "stage": "turn",
                "cards": [{"rank": c.display_rank, "suit": c.suit.value} for c in cards],
                "all_community": [
                    {"rank": c.display_rank, "suit": c.suit.value}
                    for c in gs.community_cards
                ],
            })
        elif community_count == 4:
            # Deal river
            cards = self.engine.deal_community(gs, 1)
            await self.broadcast({
                "type": "community_cards",
                "stage": "river",
                "cards": [{"rank": c.display_rank, "suit": c.suit.value} for c in cards],
                "all_community": [
                    {"rank": c.display_rank, "suit": c.suit.value}
                    for c in gs.community_cards
                ],
            })
        else:
            # All streets dealt — showdown
            await self._showdown()
            return

        # Reset bets for new street
        for pid in gs.player_ids:
            gs.player_bets[pid] = 0
        gs.current_bet = 0
        gs.current_player_index = (gs.dealer_index + 1) % len(gs.player_ids)

        await asyncio.sleep(1.0)
        await self._run_ai_betting_round()

    async def _showdown(self):
        """Resolve the round — determine winner/loser, handle stripping."""
        gs = self.game_state
        gs.phase = GamePhase.SHOWDOWN

        winner_id, loser_id, winning_hand = self.engine.determine_winner(gs)
        winner = self.player_map[winner_id]
        loser = self.player_map[loser_id]

        # Reveal all hands
        hand_reveal = {}
        for pid in gs.active_player_ids:
            cards = gs.player_hands.get(pid, [])
            hand_reveal[pid] = [
                {"rank": c.display_rank, "suit": c.suit.value} for c in cards
            ]

        await self.broadcast({
            "type": "showdown",
            "winner_id": winner_id,
            "winner_name": winner.display_name,
            "winning_hand": winning_hand.display,
            "loser_id": loser_id,
            "loser_name": loser.display_name,
            "hands": hand_reveal,
            "pot": gs.pot,
        })

        await asyncio.sleep(1.5)

        # Loser strips
        gs.phase = GamePhase.STRIPPING
        removed_item = loser.clothing.remove_next()

        if removed_item:
            gs.loser_removed_item = removed_item.name

            await self.broadcast({
                "type": "strip",
                "player_id": loser_id,
                "player_name": loser.display_name,
                "removed_item": removed_item.name,
                "remaining_clothing": loser.clothing.remaining_layers,
                "clothing_description": loser.clothing_description,
                "is_naked": loser.is_naked,
            })

            # Generate new image for the loser
            if not loser.is_human:
                new_image = await self.comfyui.generate_removal_sequence(loser)
                if new_image:
                    loser.current_image_url = f"data:image/png;base64,{new_image}"
                    await self.broadcast({
                        "type": "image_update",
                        "player_id": loser_id,
                        "image_url": loser.current_image_url,
                    })

            # Generate dialogue reactions
            await self._generate_strip_dialogue(winner, loser, removed_item.name)

        # Check for elimination
        if loser.is_naked:
            loser.is_eliminated = True
            await self.broadcast({
                "type": "eliminated",
                "player_id": loser_id,
                "player_name": loser.display_name,
            })

            # Remove from active players
            gs.player_ids = [pid for pid in gs.player_ids if pid != loser_id]

        # Check for game over
        active_non_human = [
            pid for pid in gs.player_ids if pid != self.human.id
        ]
        if not active_non_human or (self.human.is_eliminated):
            gs.phase = GamePhase.GAME_OVER
            await self.broadcast({
                "type": "game_over",
                "winner_id": gs.player_ids[0] if gs.player_ids else None,
            })
            return

        # Next round
        self.engine.finish_round(gs)
        await asyncio.sleep(2.0)
        await self.start_round()

    async def _generate_intro_dialogue(self):
        """Generate introduction dialogue for each AI character."""
        for player in self.ai_players:
            try:
                dialogue = await self.kobold.generate_with_situation(
                    character=player,
                    situation_key="game_start",
                    opponent_count=len(self.all_players) - 1,
                )
                player.last_dialogue = dialogue
                await self.broadcast({
                    "type": "dialogue",
                    "player_id": player.id,
                    "player_name": player.display_name,
                    "text": dialogue,
                    "emotion": "neutral",
                })
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Intro dialogue failed for {player.display_name}: {e}")

    async def _generate_strip_dialogue(
        self,
        winner: GameCharacter,
        loser: GameCharacter,
        removed_item: str,
    ):
        """Generate dialogue for a stripping event."""
        opponents_info = [
            {
                "name": p.display_name,
                "clothing_desc": p.clothing_description,
                "chips": p.chips,
            }
            for p in self.all_players
            if p.id != loser.id and not p.is_eliminated
        ]

        # Loser's reaction
        if not loser.is_human:
            try:
                if loser.is_naked:
                    situation_key = "you_naked"
                    kwargs = {}
                else:
                    situation_key = "lose_round"
                    kwargs = {"removed_item": removed_item}

                dialogue = await self.kobold.generate_with_situation(
                    character=loser,
                    situation_key=situation_key,
                    opponent_count=len(self.all_players) - 1,
                    opponents=opponents_info,
                    **kwargs,
                )
                loser.last_dialogue = dialogue
                loser.current_emotion = "embarrassed" if loser.clothing.remaining_layers < 3 else "nervous"

                await self.broadcast({
                    "type": "dialogue",
                    "player_id": loser.id,
                    "player_name": loser.display_name,
                    "text": dialogue,
                    "emotion": loser.current_emotion,
                })
            except Exception as e:
                logger.error(f"Loser dialogue failed: {e}")

        await asyncio.sleep(1.0)

        # Winner's reaction
        if not winner.is_human:
            try:
                dialogue = await self.kobold.generate_with_situation(
                    character=winner,
                    situation_key="win_round",
                    opponent_count=len(self.all_players) - 1,
                    opponents=opponents_info,
                    loser_name=loser.display_name,
                    removed_item=removed_item,
                )
                winner.last_dialogue = dialogue
                winner.current_emotion = "smug"

                await self.broadcast({
                    "type": "dialogue",
                    "player_id": winner.id,
                    "player_name": winner.display_name,
                    "text": dialogue,
                    "emotion": winner.current_emotion,
                })
            except Exception as e:
                logger.error(f"Winner dialogue failed: {e}")

        # Occasional reactions from observers
        observers = [
            p for p in self.ai_players
            if p.id not in (winner.id, loser.id) and not p.is_eliminated
        ]
        if observers:
            import random
            observer = random.choice(observers)
            try:
                dialogue = await self.kobold.generate_with_situation(
                    character=observer,
                    situation_key="watch_strip",
                    opponent_count=len(self.all_players) - 1,
                    stripper_name=loser.display_name,
                    removed_item=removed_item,
                )
                observer.last_dialogue = dialogue

                await self.broadcast({
                    "type": "dialogue",
                    "player_id": observer.id,
                    "player_name": observer.display_name,
                    "text": dialogue,
                    "emotion": "neutral",
                })
            except Exception as e:
                logger.error(f"Observer dialogue failed: {e}")

    async def _generate_all_images(self):
        """Generate initial images for all AI characters."""
        for player in self.ai_players:
            try:
                image_b64 = await self.comfyui.generate_character_image(
                    player, emotion="neutral"
                )
                if image_b64:
                    player.current_image_url = f"data:image/png;base64,{image_b64}"
            except Exception as e:
                logger.warning(f"Initial image gen failed for {player.display_name}: {e}")

    def _player_info(self, player: GameCharacter) -> dict:
        return {
            "id": player.id,
            "name": player.display_name,
            "is_human": player.is_human,
            "clothing_count": player.clothing.total_layers,
            "clothing_items": [item.name for item in player.clothing.items],
            "clothing_description": player.clothing_description,
            "image_url": player.current_image_url,
        }


# ── REST Endpoints ──────────────────────────────────────────────────────

@router.post("/start")
async def start_game(request: StartGameRequest):
    """Start a new game session."""
    store = get_character_store()

    # Validate character IDs
    ai_characters = []
    for cid in request.character_ids:
        char = store.get(cid)
        if not char:
            raise HTTPException(
                status_code=404, detail=f"Character '{cid}' not found"
            )
        ai_characters.append(char)

    if not ai_characters:
        raise HTTPException(
            status_code=400, detail="At least one AI opponent is required"
        )

    # Create human player
    human = GameCharacter(
        id="human_player",
        card=__import__("..models.character", fromlist=["CharacterCard"]).CharacterCard(
            name=request.player_name,
        ),
        is_human=True,
    )
    # Give human standard clothing
    from ..services.clothing import normalize_clothing, DEFAULT_CLOTHING
    human.clothing = normalize_clothing(
        [item.model_copy() for item in DEFAULT_CLOTHING]
    )

    # Create game session
    import uuid as _uuid
    game_id = f"game_{_uuid.uuid4().hex[:8]}"
    session = GameSession(game_id, human, ai_characters)
    _games[game_id] = session

    return {"game_id": game_id, "player_count": len(ai_characters) + 1}


@router.get("/{game_id}/state")
async def get_game_state(game_id: str):
    """Get current game state."""
    session = _games.get(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    gs = session.game_state
    return {
        "game_id": game_id,
        "phase": gs.phase.value if gs else "lobby",
        "round": gs.round_number if gs else 0,
        "pot": gs.pot if gs else 0,
        "players": [session._player_info(p) for p in session.all_players],
    }


@router.post("/{game_id}/action")
async def game_action(game_id: str, request: GameActionRequest):
    """Submit a player action (for non-WebSocket clients)."""
    session = _games.get(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    await session.process_human_action(request.action, request.amount)
    return {"status": "ok"}


@router.get("/health")
async def health_check():
    """Check if backend services are available."""
    kobold = KoboldService()
    comfyui = ComfyUIService()

    return {
        "koboldcpp": await kobold.check_health(),
        "comfyui": await comfyui.check_health(),
        "active_games": len(_games),
    }


# ── WebSocket Endpoint ──────────────────────────────────────────────────

@router.websocket("/{game_id}/ws")
async def game_websocket(websocket: WebSocket, game_id: str):
    """WebSocket connection for real-time game play."""
    await websocket.accept()

    session = _games.get(game_id)
    if not session:
        await websocket.send_text(
            json.dumps({"type": "error", "message": "Game not found"})
        )
        await websocket.close()
        return

    session.websockets.append(websocket)

    try:
        # If game hasn't started, start it now
        if session.game_state is None or session.game_state.phase == GamePhase.LOBBY:
            await session.start()

        # Listen for player actions
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "action":
                await session.process_human_action(
                    msg.get("action", "check"),
                    msg.get("amount", 0),
                )
            elif msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        session.websockets.remove(websocket)
        logger.info(f"WebSocket disconnected from game {game_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in session.websockets:
            session.websockets.remove(websocket)
