"""Game state models for strip poker."""
from __future__ import annotations

import random
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Suit(str, Enum):
    HEARTS = "hearts"
    DIAMONDS = "diamonds"
    CLUBS = "clubs"
    SPADES = "spades"


class Card(BaseModel):
    rank: int = Field(..., ge=2, le=14, description="2-14 where 11=J, 12=Q, 13=K, 14=A")
    suit: Suit

    @property
    def display_rank(self) -> str:
        specials = {11: "J", 12: "Q", 13: "K", 14: "A"}
        return specials.get(self.rank, str(self.rank))

    @property
    def display(self) -> str:
        suit_symbols = {"hearts": "♥", "diamonds": "♦", "clubs": "♣", "spades": "♠"}
        return f"{self.display_rank}{suit_symbols[self.suit]}"


class HandRank(int, Enum):
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9


class PokerHand(BaseModel):
    cards: list[Card] = Field(default_factory=list)
    rank: HandRank = HandRank.HIGH_CARD
    rank_cards: list[int] = Field(default_factory=list, description="Cards that make the hand rank")
    kickers: list[int] = Field(default_factory=list, description="Kicker cards for tiebreaks")

    @property
    def display(self) -> str:
        names = {
            HandRank.HIGH_CARD: "High Card",
            HandRank.ONE_PAIR: "One Pair",
            HandRank.TWO_PAIR: "Two Pair",
            HandRank.THREE_OF_A_KIND: "Three of a Kind",
            HandRank.STRAIGHT: "Straight",
            HandRank.FLUSH: "Flush",
            HandRank.FULL_HOUSE: "Full House",
            HandRank.FOUR_OF_A_KIND: "Four of a Kind",
            HandRank.STRAIGHT_FLUSH: "Straight Flush",
            HandRank.ROYAL_FLUSH: "Royal Flush",
        }
        return names[self.rank]


class GamePhase(str, Enum):
    LOBBY = "lobby"
    DEALING = "dealing"
    BETTING = "betting"
    SHOWDOWN = "showdown"
    STRIPPING = "stripping"
    DIALOGUE = "dialogue"
    GAME_OVER = "game_over"


class PlayerAction(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"
    ALL_IN = "all_in"


class GameState(BaseModel):
    """Complete state of a poker game."""

    id: str = Field(..., description="Game session ID")
    phase: GamePhase = Field(default=GamePhase.LOBBY)
    round_number: int = Field(default=0)

    # Players — index 0 is always the human
    player_ids: list[str] = Field(default_factory=list)

    # Poker state
    deck: list[Card] = Field(default_factory=list)
    community_cards: list[Card] = Field(default_factory=list)
    pot: int = Field(default=0)
    current_bet: int = Field(default=0)
    dealer_index: int = Field(default=0)
    current_player_index: int = Field(default=0)

    # Per-player state keyed by player_id
    player_hands: dict[str, list[Card]] = Field(default_factory=dict)
    player_bets: dict[str, int] = Field(default_factory=dict)
    player_folded: dict[str, bool] = Field(default_factory=dict)

    # Round results
    round_winner_id: Optional[str] = None
    round_loser_id: Optional[str] = None
    loser_removed_item: Optional[str] = None

    def init_deck(self):
        """Create and shuffle a fresh 52-card deck."""
        self.deck = []
        for suit in Suit:
            for rank in range(2, 15):
                self.deck.append(Card(rank=rank, suit=suit))
        random.shuffle(self.deck)

    def deal_card(self) -> Card:
        return self.deck.pop()

    @property
    def active_player_ids(self) -> list[str]:
        """Players still in this round (not folded)."""
        return [
            pid for pid in self.player_ids if not self.player_folded.get(pid, False)
        ]
