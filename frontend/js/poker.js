/**
 * Poker game UI rendering.
 */
class PokerUI {
    constructor() {
        this.opponentsArea = document.getElementById('opponents-area');
        this.communityCards = document.getElementById('community-cards');
        this.playerHand = document.getElementById('player-hand');
        this.dialogueArea = document.getElementById('dialogue-area');
        this.actionBar = document.getElementById('action-bar');
        this.roundNumber = document.getElementById('round-number');
        this.potAmount = document.getElementById('pot-amount');
        this.playerClothingDesc = document.getElementById('player-clothing-desc');

        this.players = {};
        this.maxDialogues = 6;
    }

    /**
     * Initialize the game UI with player data.
     */
    initPlayers(players) {
        this.players = {};
        this.opponentsArea.innerHTML = '';

        players.forEach(p => {
            this.players[p.id] = p;
            if (!p.is_human) {
                this._createOpponentSlot(p);
            }
        });
    }

    _createOpponentSlot(player) {
        const slot = document.createElement('div');
        slot.className = 'opponent-slot';
        slot.id = `opponent-${player.id}`;
        slot.innerHTML = `
            <div class="opponent-portrait" id="portrait-${player.id}">
                ${player.image_url
                    ? `<img src="${player.image_url}" alt="${player.name}">`
                    : `<div class="opponent-portrait-placeholder">?</div>`
                }
            </div>
            <div class="opponent-name">${this._escapeHtml(player.name)}</div>
            <div class="opponent-clothing-info" id="clothing-info-${player.id}">
                ${player.clothing_count} items
            </div>
        `;
        this.opponentsArea.appendChild(slot);
    }

    /**
     * Update round and pot display.
     */
    updateGameInfo(round, pot) {
        this.roundNumber.textContent = round;
        this.potAmount.textContent = pot;
    }

    /**
     * Display the player's hole cards.
     */
    showHoleCards(cards) {
        this.playerHand.innerHTML = '';
        cards.forEach(card => {
            this.playerHand.appendChild(this._createCard(card.rank, card.suit));
        });
    }

    /**
     * Display community cards.
     */
    showCommunityCards(cards) {
        this.communityCards.innerHTML = '';
        cards.forEach(card => {
            this.communityCards.appendChild(this._createCard(card.rank, card.suit));
        });
    }

    /**
     * Add community cards (for progressive dealing).
     */
    addCommunityCards(newCards) {
        newCards.forEach(card => {
            this.communityCards.appendChild(this._createCard(card.rank, card.suit));
        });
    }

    /**
     * Show the action bar for the player's turn.
     */
    showActions(canCheck, currentBet, myBet) {
        this.actionBar.hidden = false;
        const toCall = currentBet - myBet;

        const checkBtn = this.actionBar.querySelector('.btn-check');
        const callBtn = this.actionBar.querySelector('.btn-call');

        if (canCheck) {
            checkBtn.hidden = false;
            callBtn.hidden = true;
        } else {
            checkBtn.hidden = true;
            callBtn.hidden = false;
            callBtn.textContent = `Call ${toCall}`;
        }
    }

    /**
     * Hide the action bar.
     */
    hideActions() {
        this.actionBar.hidden = true;
    }

    /**
     * Add a dialogue bubble.
     */
    addDialogue(playerName, text, emotion = 'neutral') {
        const bubble = document.createElement('div');
        bubble.className = 'dialogue-bubble';
        bubble.innerHTML = `
            <span class="speaker">${this._escapeHtml(playerName)}:</span>
            <span class="speech">${this._escapeHtml(text)}</span>
        `;
        this.dialogueArea.appendChild(bubble);

        // Limit dialogue history
        while (this.dialogueArea.children.length > this.maxDialogues) {
            this.dialogueArea.removeChild(this.dialogueArea.firstChild);
        }

        // Scroll to bottom
        this.dialogueArea.scrollTop = this.dialogueArea.scrollHeight;
    }

    /**
     * Clear all dialogue bubbles.
     */
    clearDialogue() {
        this.dialogueArea.innerHTML = '';
    }

    /**
     * Update a player's portrait image.
     */
    updatePortrait(playerId, imageUrl) {
        const portrait = document.getElementById(`portrait-${playerId}`);
        if (portrait) {
            portrait.innerHTML = `<img src="${imageUrl}" alt="character">`;
        }
    }

    /**
     * Update a player's clothing info.
     */
    updateClothingInfo(playerId, description, remaining) {
        const info = document.getElementById(`clothing-info-${playerId}`);
        if (info) {
            info.textContent = description;
        }
    }

    /**
     * Mark a player as having their turn.
     */
    setActiveTurn(playerId) {
        document.querySelectorAll('.opponent-slot').forEach(slot => {
            slot.classList.remove('is-turn');
        });
        const slot = document.getElementById(`opponent-${playerId}`);
        if (slot) slot.classList.add('is-turn');
    }

    /**
     * Mark a player as eliminated.
     */
    setEliminated(playerId) {
        const slot = document.getElementById(`opponent-${playerId}`);
        if (slot) slot.classList.add('eliminated');
    }

    /**
     * Highlight a stripping event.
     */
    async showStripEvent(playerName, removedItem, isNaked) {
        const msg = isNaked
            ? `${playerName} removes their ${removedItem} — they're completely exposed!`
            : `${playerName} reluctantly removes their ${removedItem}...`;

        this.addDialogue('📢', msg);
    }

    /**
     * Show showdown results.
     */
    showShowdown(winnerName, handName, pot) {
        this.addDialogue('📢', `${winnerName} wins with ${handName}! (Pot: ${pot})`);
    }

    /**
     * Reset for a new round.
     */
    resetRound() {
        this.communityCards.innerHTML = '';
        this.playerHand.innerHTML = '';
        this.hideActions();

        // Remove turn highlights
        document.querySelectorAll('.opponent-slot').forEach(slot => {
            slot.classList.remove('is-turn');
        });
    }

    /**
     * Create a playing card element.
     */
    _createCard(rank, suit) {
        const suitSymbols = {
            hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠'
        };
        const card = document.createElement('div');
        card.className = `playing-card ${suit}`;
        card.innerHTML = `
            <span class="card-rank">${rank}</span>
            <span class="card-suit">${suitSymbols[suit] || suit}</span>
        `;
        return card;
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

window.pokerUI = new PokerUI();
