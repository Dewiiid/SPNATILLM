/**
 * SPNATI-AI — Main Application Controller
 *
 * Orchestrates the lobby, game flow, and WebSocket events.
 */
(function () {
    'use strict';

    const cm = window.characterManager;
    const ui = window.pokerUI;
    const ws = window.gameSocket;

    let currentGameId = null;

    // ── Screen Management ──────────────────────────────────────

    function showScreen(screenId) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        document.getElementById(screenId).classList.add('active');
    }

    function showLoading(message = 'Loading...') {
        document.getElementById('loading-message').textContent = message;
        document.getElementById('loading-overlay').hidden = false;
    }

    function hideLoading() {
        document.getElementById('loading-overlay').hidden = true;
    }

    // ── Lobby ──────────────────────────────────────────────────

    function initLobby() {
        // Import via URL
        document.getElementById('btn-import-url').addEventListener('click', async () => {
            const input = document.getElementById('chub-url');
            const url = input.value.trim();
            if (!url) return;

            showLoading('Importing character...');
            try {
                const char = await cm.importFromUrl(url);
                input.value = '';
                console.log('Imported:', char);
            } catch (err) {
                alert(`Import failed: ${err.message}`);
            } finally {
                hideLoading();
            }
        });

        // Import via file
        document.getElementById('card-file-input').addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            showLoading('Parsing character card...');
            try {
                const char = await cm.importFromFile(file);
                console.log('Uploaded:', char);
            } catch (err) {
                alert(`Upload failed: ${err.message}`);
            } finally {
                hideLoading();
                e.target.value = '';
            }
        });

        // Search
        document.getElementById('btn-search').addEventListener('click', async () => {
            const query = document.getElementById('chub-search').value.trim();
            if (!query) return;

            showLoading('Searching...');
            try {
                const results = await cm.search(query);
                renderSearchResults(results);
            } catch (err) {
                console.error('Search failed:', err);
            } finally {
                hideLoading();
            }
        });

        // Enter key handlers
        document.getElementById('chub-url').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') document.getElementById('btn-import-url').click();
        });
        document.getElementById('chub-search').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') document.getElementById('btn-search').click();
        });

        // Start game
        document.getElementById('btn-start-game').addEventListener('click', startGame);

        // Character roster updates
        cm.onUpdate = renderRoster;

        // Check backend status
        checkBackendStatus();
    }

    function renderRoster(characters) {
        const roster = document.getElementById('opponent-roster');
        const count = document.getElementById('opponent-count');
        const startBtn = document.getElementById('btn-start-game');

        count.textContent = characters.size;
        startBtn.disabled = characters.size === 0;

        if (characters.size === 0) {
            roster.innerHTML = `
                <div class="roster-empty">
                    <p>No characters loaded yet. Import characters above to start playing.</p>
                </div>
            `;
            return;
        }

        roster.innerHTML = '';
        characters.forEach((char, id) => {
            const card = document.createElement('div');
            card.className = 'roster-card';
            card.innerHTML = `
                <button class="roster-card-remove" data-id="${id}" title="Remove">×</button>
                <div class="roster-card-name">${escapeHtml(char.name)}</div>
                <div class="roster-card-clothing">${char.clothing_items.join(', ')}</div>
            `;
            roster.appendChild(card);
        });

        // Remove buttons
        roster.querySelectorAll('.roster-card-remove').forEach(btn => {
            btn.addEventListener('click', () => cm.remove(btn.dataset.id));
        });
    }

    function renderSearchResults(results) {
        const container = document.getElementById('search-results');
        container.hidden = results.length === 0;

        container.innerHTML = '';
        results.forEach(r => {
            const item = document.createElement('div');
            item.className = 'search-result-item';
            item.innerHTML = `
                <div>
                    <div class="search-result-name">${escapeHtml(r.name)}</div>
                    <div class="search-result-desc">${escapeHtml(r.description || '')}</div>
                </div>
            `;
            item.addEventListener('click', async () => {
                showLoading(`Importing ${r.name}...`);
                try {
                    await cm.importFromUrl(r.slug);
                    container.hidden = true;
                } catch (err) {
                    alert(`Import failed: ${err.message}`);
                } finally {
                    hideLoading();
                }
            });
            container.appendChild(item);
        });
    }

    async function checkBackendStatus() {
        try {
            const resp = await fetch('/api/game/health');
            if (resp.ok) {
                const data = await resp.json();
                setStatusDot('status-kobold', data.koboldcpp);
                setStatusDot('status-comfyui', data.comfyui);
            }
        } catch (e) {
            setStatusDot('status-kobold', false);
            setStatusDot('status-comfyui', false);
        }
    }

    function setStatusDot(elementId, ok) {
        const dot = document.querySelector(`#${elementId} .status-dot`);
        if (dot) {
            dot.classList.toggle('ok', ok);
            dot.classList.toggle('err', !ok);
        }
    }

    // ── Game Start ─────────────────────────────────────────────

    async function startGame() {
        const playerName = document.getElementById('player-name').value.trim() || 'Player';
        const characterIds = cm.getIds();

        if (characterIds.length === 0) {
            alert('Import at least one character to play against!');
            return;
        }

        showLoading('Setting up the table...');

        try {
            // Create game session
            const resp = await fetch('/api/game/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    character_ids: characterIds,
                    player_name: playerName,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || 'Failed to start game');
            }

            const { game_id } = await resp.json();
            currentGameId = game_id;

            // Switch to game screen
            showScreen('screen-game');
            ui.clearDialogue();
            ui.resetRound();

            // Connect WebSocket
            setupGameEvents();
            await ws.connect(game_id);

        } catch (err) {
            alert(`Failed to start: ${err.message}`);
            showScreen('screen-lobby');
        } finally {
            hideLoading();
        }
    }

    // ── Game Events ────────────────────────────────────────────

    function setupGameEvents() {
        // Clear previous handlers by creating fresh socket
        // (in production, use proper handler cleanup)

        ws.on('game_started', (data) => {
            ui.initPlayers(data.players);
            ui.updateGameInfo(0, 0);
        });

        ws.on('round_started', (data) => {
            ui.resetRound();
            ui.updateGameInfo(data.round, data.pot);
            ui.addDialogue('📢', `Round ${data.round} begins.`);
        });

        ws.on('hole_cards', (data) => {
            ui.showHoleCards(data.cards);
        });

        ws.on('community_cards', (data) => {
            ui.showCommunityCards(data.all_community);
        });

        ws.on('your_turn', (data) => {
            ui.showActions(data.can_check, data.current_bet, data.your_bet);
            ui.updateGameInfo(undefined, data.pot);
        });

        ws.on('player_action', (data) => {
            const actionText = {
                fold: 'folds',
                check: 'checks',
                call: `calls ${data.amount || ''}`,
                raise: `raises to ${data.amount || ''}`,
                all_in: 'goes all in!',
            };
            ui.addDialogue('📢', `${data.player_name} ${actionText[data.action] || data.action}.`);
            ui.updateGameInfo(undefined, data.pot);
            ui.hideActions();
        });

        ws.on('showdown', (data) => {
            ui.showShowdown(data.winner_name, data.winning_hand, data.pot);
        });

        ws.on('strip', (data) => {
            ui.showStripEvent(data.player_name, data.removed_item, data.is_naked);
            ui.updateClothingInfo(data.player_id, data.clothing_description, data.remaining_clothing);
        });

        ws.on('image_update', (data) => {
            ui.updatePortrait(data.player_id, data.image_url);
        });

        ws.on('dialogue', (data) => {
            ui.addDialogue(data.player_name, data.text, data.emotion);
        });

        ws.on('eliminated', (data) => {
            ui.setEliminated(data.player_id);
            ui.addDialogue('📢', `${data.player_name} has been eliminated!`);
        });

        ws.on('game_over', (data) => {
            showScreen('screen-gameover');
            const title = document.getElementById('gameover-title');
            const msg = document.getElementById('gameover-message');

            if (data.winner_id === 'human_player') {
                title.textContent = 'You Win!';
                msg.textContent = "You've stripped everyone at the table. Well played.";
            } else {
                title.textContent = 'Game Over';
                msg.textContent = "Better luck next time...";
            }
        });

        ws.on('error', (data) => {
            console.error('Game error:', data);
            ui.addDialogue('⚠️', data.message || 'An error occurred.');
        });
    }

    // ── Action Buttons ─────────────────────────────────────────

    function initActionButtons() {
        document.querySelectorAll('.btn-action').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                let amount = 0;

                if (action === 'raise') {
                    const input = prompt('Raise to how much?', '20');
                    if (input === null) return;
                    amount = parseInt(input) || 20;
                }

                ws.sendAction(action, amount);
                ui.hideActions();
            });
        });
    }

    // ── Game Over ──────────────────────────────────────────────

    function initGameOver() {
        document.getElementById('btn-new-game').addEventListener('click', () => {
            ws.disconnect();
            currentGameId = null;
            showScreen('screen-lobby');
        });

        document.getElementById('btn-quit').addEventListener('click', () => {
            if (confirm('Quit the current game?')) {
                ws.disconnect();
                currentGameId = null;
                showScreen('screen-lobby');
            }
        });
    }

    // ── Utilities ──────────────────────────────────────────────

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ── Boot ───────────────────────────────────────────────────

    document.addEventListener('DOMContentLoaded', () => {
        initLobby();
        initActionButtons();
        initGameOver();
        showScreen('screen-lobby');
        console.log('[SPNATI-AI] Initialized');
    });

})();
