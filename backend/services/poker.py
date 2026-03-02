"""Texas Hold'em poker engine for strip poker.

Simplified poker rules:
- Standard 5-card Texas Hold'em hand evaluation
- Betting rounds: pre-flop, flop, turn, river
- Loser of each round removes one clothing item
- Player eliminated when all clothing removed + loses again
"""
from __future__ import annotations

import random
from collections import Counter
from typing import Optional

from ..models.game import (
    Card,
    GamePhase,
    GameState,
    HandRank,
    PlayerAction,
    PokerHand,
    Suit,
)


def evaluate_hand(hole_cards: list[Card], community: list[Card]) -> PokerHand:
    """Evaluate the best 5-card poker hand from hole + community cards."""
    all_cards = hole_cards + community
    if len(all_cards) < 5:
        # Not enough cards yet — just rank what we have
        ranks = sorted([c.rank for c in all_cards], reverse=True)
        return PokerHand(
            cards=all_cards,
            rank=HandRank.HIGH_CARD,
            rank_cards=ranks[:1],
            kickers=ranks[1:5],
        )

    best_hand: Optional[PokerHand] = None

    # Check all 5-card combinations
    from itertools import combinations

    for combo in combinations(all_cards, 5):
        hand = _evaluate_five(list(combo))
        if best_hand is None or _compare_hands(hand, best_hand) > 0:
            best_hand = hand

    return best_hand or PokerHand(cards=all_cards[:5])


def _evaluate_five(cards: list[Card]) -> PokerHand:
    """Evaluate exactly 5 cards."""
    ranks = sorted([c.rank for c in cards], reverse=True)
    suits = [c.suit for c in cards]
    rank_counts = Counter(ranks)
    is_flush = len(set(suits)) == 1
    is_straight, high = _check_straight(ranks)

    # Royal Flush
    if is_flush and is_straight and high == 14:
        return PokerHand(
            cards=cards, rank=HandRank.ROYAL_FLUSH,
            rank_cards=[14], kickers=[]
        )

    # Straight Flush
    if is_flush and is_straight:
        return PokerHand(
            cards=cards, rank=HandRank.STRAIGHT_FLUSH,
            rank_cards=[high], kickers=[]
        )

    # Four of a Kind
    fours = [r for r, c in rank_counts.items() if c == 4]
    if fours:
        kicker = [r for r in ranks if r != fours[0]][:1]
        return PokerHand(
            cards=cards, rank=HandRank.FOUR_OF_A_KIND,
            rank_cards=fours, kickers=kicker
        )

    # Full House
    threes = [r for r, c in rank_counts.items() if c == 3]
    twos = [r for r, c in rank_counts.items() if c == 2]
    if threes and twos:
        return PokerHand(
            cards=cards, rank=HandRank.FULL_HOUSE,
            rank_cards=[threes[0], twos[0]], kickers=[]
        )

    # Flush
    if is_flush:
        return PokerHand(
            cards=cards, rank=HandRank.FLUSH,
            rank_cards=ranks[:5], kickers=[]
        )

    # Straight
    if is_straight:
        return PokerHand(
            cards=cards, rank=HandRank.STRAIGHT,
            rank_cards=[high], kickers=[]
        )

    # Three of a Kind
    if threes:
        kickers = sorted([r for r in ranks if r != threes[0]], reverse=True)[:2]
        return PokerHand(
            cards=cards, rank=HandRank.THREE_OF_A_KIND,
            rank_cards=threes, kickers=kickers
        )

    # Two Pair
    if len(twos) >= 2:
        twos_sorted = sorted(twos, reverse=True)[:2]
        kicker = [r for r in ranks if r not in twos_sorted][:1]
        return PokerHand(
            cards=cards, rank=HandRank.TWO_PAIR,
            rank_cards=twos_sorted, kickers=kicker
        )

    # One Pair
    if twos:
        kickers = sorted([r for r in ranks if r != twos[0]], reverse=True)[:3]
        return PokerHand(
            cards=cards, rank=HandRank.ONE_PAIR,
            rank_cards=twos, kickers=kickers
        )

    # High Card
    return PokerHand(
        cards=cards, rank=HandRank.HIGH_CARD,
        rank_cards=ranks[:1], kickers=ranks[1:5]
    )


def _check_straight(ranks: list[int]) -> tuple[bool, int]:
    """Check if sorted ranks form a straight. Returns (is_straight, high_card)."""
    unique = sorted(set(ranks), reverse=True)
    if len(unique) < 5:
        return False, 0

    # Check normal straight
    for i in range(len(unique) - 4):
        window = unique[i : i + 5]
        if window[0] - window[4] == 4:
            return True, window[0]

    # Check ace-low straight (A-2-3-4-5)
    if set([14, 2, 3, 4, 5]).issubset(set(unique)):
        return True, 5

    return False, 0


def _compare_hands(a: PokerHand, b: PokerHand) -> int:
    """Compare two hands. Returns positive if a > b, negative if a < b, 0 if tie."""
    if a.rank != b.rank:
        return a.rank.value - b.rank.value

    # Compare rank cards
    for ac, bc in zip(a.rank_cards, b.rank_cards):
        if ac != bc:
            return ac - bc

    # Compare kickers
    for ac, bc in zip(a.kickers, b.kickers):
        if ac != bc:
            return ac - bc

    return 0


class PokerEngine:
    """Manages the poker game flow."""

    def __init__(
        self,
        starting_chips: int = 100,
        small_blind: int = 5,
        big_blind: int = 10,
    ):
        self.starting_chips = starting_chips
        self.small_blind = small_blind
        self.big_blind = big_blind

    def new_game(self, player_ids: list[str]) -> GameState:
        """Initialize a new game with the given players."""
        game = GameState(
            id=f"game_{random.randint(10000, 99999)}",
            phase=GamePhase.LOBBY,
            player_ids=player_ids,
        )
        return game

    def start_round(self, game: GameState) -> GameState:
        """Start a new poker round."""
        game.round_number += 1
        game.phase = GamePhase.DEALING

        # Reset round state
        game.init_deck()
        game.community_cards = []
        game.pot = 0
        game.current_bet = 0
        game.round_winner_id = None
        game.round_loser_id = None
        game.loser_removed_item = None
        game.player_hands = {}
        game.player_bets = {pid: 0 for pid in game.player_ids}
        game.player_folded = {pid: False for pid in game.player_ids}

        # Deal hole cards
        for pid in game.player_ids:
            game.player_hands[pid] = [game.deal_card(), game.deal_card()]

        # Post blinds
        sb_idx = (game.dealer_index + 1) % len(game.player_ids)
        bb_idx = (game.dealer_index + 2) % len(game.player_ids)
        sb_player = game.player_ids[sb_idx]
        bb_player = game.player_ids[bb_idx]

        game.player_bets[sb_player] = self.small_blind
        game.player_bets[bb_player] = self.big_blind
        game.pot = self.small_blind + self.big_blind
        game.current_bet = self.big_blind

        # Action starts after big blind
        game.current_player_index = (bb_idx + 1) % len(game.player_ids)
        game.phase = GamePhase.BETTING

        return game

    def deal_community(self, game: GameState, count: int = 1) -> list[Card]:
        """Deal community cards (flop=3, turn=1, river=1)."""
        dealt = []
        for _ in range(count):
            card = game.deal_card()
            game.community_cards.append(card)
            dealt.append(card)
        return dealt

    def process_action(
        self, game: GameState, player_id: str, action: PlayerAction, amount: int = 0
    ) -> dict:
        """Process a player's action and return the result."""
        result = {"action": action, "player_id": player_id, "valid": True}

        if action == PlayerAction.FOLD:
            game.player_folded[player_id] = True

        elif action == PlayerAction.CHECK:
            if game.player_bets[player_id] < game.current_bet:
                result["valid"] = False
                result["error"] = "Cannot check — must call or fold"
                return result

        elif action == PlayerAction.CALL:
            call_amount = game.current_bet - game.player_bets[player_id]
            game.player_bets[player_id] = game.current_bet
            game.pot += call_amount
            result["amount"] = call_amount

        elif action == PlayerAction.RAISE:
            raise_to = max(amount, game.current_bet + self.big_blind)
            added = raise_to - game.player_bets[player_id]
            game.player_bets[player_id] = raise_to
            game.current_bet = raise_to
            game.pot += added
            result["amount"] = added

        elif action == PlayerAction.ALL_IN:
            # Simplified all-in
            game.player_bets[player_id] = game.current_bet
            game.pot += game.current_bet

        # Advance to next active player
        self._advance_player(game)

        # Check if betting round is over
        if self._is_betting_complete(game):
            result["round_complete"] = True

        return result

    def _advance_player(self, game: GameState):
        """Move to the next non-folded player."""
        for _ in range(len(game.player_ids)):
            game.current_player_index = (
                (game.current_player_index + 1) % len(game.player_ids)
            )
            pid = game.player_ids[game.current_player_index]
            if not game.player_folded.get(pid, False):
                break

    def _is_betting_complete(self, game: GameState) -> bool:
        """Check if all active players have matched the current bet."""
        active = game.active_player_ids
        if len(active) <= 1:
            return True
        return all(
            game.player_bets.get(pid, 0) >= game.current_bet for pid in active
        )

    def determine_winner(self, game: GameState) -> tuple[str, str, PokerHand]:
        """Determine the round winner and loser.

        Returns (winner_id, loser_id, winning_hand).
        """
        active = game.active_player_ids

        # If only one player didn't fold, they win
        if len(active) == 1:
            winner_id = active[0]
            # Loser is the last person who folded (simplification)
            losers = [
                pid for pid in game.player_ids
                if pid != winner_id and not game.player_folded.get(pid, True)
            ]
            if not losers:
                losers = [
                    pid for pid in game.player_ids if pid != winner_id
                ]
            loser_id = random.choice(losers) if losers else winner_id
            hand = evaluate_hand(
                game.player_hands.get(winner_id, []), game.community_cards
            )
            return winner_id, loser_id, hand

        # Evaluate all active hands
        best_player = None
        best_hand = None
        worst_player = None
        worst_hand = None

        for pid in active:
            hand = evaluate_hand(
                game.player_hands.get(pid, []), game.community_cards
            )
            if best_hand is None or _compare_hands(hand, best_hand) > 0:
                best_hand = hand
                best_player = pid
            if worst_hand is None or _compare_hands(hand, worst_hand) < 0:
                worst_hand = hand
                worst_player = pid

        return best_player, worst_player, best_hand

    def get_ai_action(
        self, game: GameState, player_id: str, hand_strength: float = 0.5
    ) -> tuple[PlayerAction, int]:
        """Simple AI decision-making for NPC poker actions.

        Args:
            game: Current game state.
            player_id: The AI player making a decision.
            hand_strength: 0.0 (worst) to 1.0 (best) hand quality.

        Returns:
            (action, amount) tuple.
        """
        current_bet = game.current_bet
        my_bet = game.player_bets.get(player_id, 0)
        to_call = current_bet - my_bet

        # Random factor for unpredictability
        luck = random.random()

        # Strong hand
        if hand_strength > 0.7:
            if luck > 0.3:
                raise_amount = current_bet + self.big_blind * random.randint(1, 3)
                return PlayerAction.RAISE, raise_amount
            return PlayerAction.CALL, to_call

        # Medium hand
        if hand_strength > 0.4:
            if to_call == 0:
                return PlayerAction.CHECK, 0
            if luck > 0.4:
                return PlayerAction.CALL, to_call
            return PlayerAction.FOLD, 0

        # Weak hand
        if to_call == 0:
            return PlayerAction.CHECK, 0
        if luck > 0.7:
            # Bluff sometimes
            return PlayerAction.CALL, to_call
        return PlayerAction.FOLD, 0

    def estimate_hand_strength(
        self, hole_cards: list[Card], community: list[Card]
    ) -> float:
        """Quick estimate of hand strength (0.0 to 1.0).

        This is a simplified evaluation — not a full Monte Carlo simulation.
        """
        if not hole_cards:
            return 0.5

        hand = evaluate_hand(hole_cards, community)

        # Base strength from hand rank
        rank_scores = {
            HandRank.HIGH_CARD: 0.1,
            HandRank.ONE_PAIR: 0.3,
            HandRank.TWO_PAIR: 0.45,
            HandRank.THREE_OF_A_KIND: 0.55,
            HandRank.STRAIGHT: 0.65,
            HandRank.FLUSH: 0.72,
            HandRank.FULL_HOUSE: 0.82,
            HandRank.FOUR_OF_A_KIND: 0.92,
            HandRank.STRAIGHT_FLUSH: 0.97,
            HandRank.ROYAL_FLUSH: 1.0,
        }

        base = rank_scores.get(hand.rank, 0.1)

        # Adjust for high cards
        if hand.rank_cards:
            high_card_bonus = (max(hand.rank_cards) - 8) * 0.02
            base = min(1.0, base + high_card_bonus)

        return base

    def finish_round(self, game: GameState):
        """Move dealer button for next round."""
        game.dealer_index = (game.dealer_index + 1) % len(game.player_ids)
        game.phase = GamePhase.DEALING
        # Reset bets for next round
        for pid in game.player_ids:
            game.player_bets[pid] = 0
        game.current_bet = 0
