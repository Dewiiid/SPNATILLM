/**
 * WebSocket client for real-time game communication.
 */
class GameSocket {
    constructor() {
        this.ws = null;
        this.gameId = null;
        this.handlers = {};
        this.reconnectAttempts = 0;
        this.maxReconnects = 5;
    }

    /**
     * Register an event handler.
     * @param {string} eventType - Event type from server (e.g., 'round_started')
     * @param {Function} handler - Callback function
     */
    on(eventType, handler) {
        if (!this.handlers[eventType]) {
            this.handlers[eventType] = [];
        }
        this.handlers[eventType].push(handler);
    }

    /**
     * Remove an event handler.
     */
    off(eventType, handler) {
        if (this.handlers[eventType]) {
            this.handlers[eventType] = this.handlers[eventType].filter(h => h !== handler);
        }
    }

    /**
     * Emit an event to all registered handlers.
     */
    emit(eventType, data) {
        const handlers = this.handlers[eventType] || [];
        handlers.forEach(h => {
            try {
                h(data);
            } catch (err) {
                console.error(`Handler error for '${eventType}':`, err);
            }
        });

        // Also emit to wildcard handlers
        (this.handlers['*'] || []).forEach(h => {
            try {
                h(eventType, data);
            } catch (err) {
                console.error('Wildcard handler error:', err);
            }
        });
    }

    /**
     * Connect to a game session.
     * @param {string} gameId - Game session ID
     * @returns {Promise<void>}
     */
    connect(gameId) {
        return new Promise((resolve, reject) => {
            this.gameId = gameId;
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const url = `${protocol}//${window.location.host}/api/game/${gameId}/ws`;

            console.log(`[WS] Connecting to ${url}`);
            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                console.log('[WS] Connected');
                this.reconnectAttempts = 0;
                this.emit('connected', { gameId });
                resolve();
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('[WS] ←', data.type, data);
                    this.emit(data.type, data);
                } catch (err) {
                    console.error('[WS] Parse error:', err);
                }
            };

            this.ws.onclose = (event) => {
                console.log('[WS] Disconnected', event.code, event.reason);
                this.emit('disconnected', { code: event.code, reason: event.reason });

                // Auto-reconnect
                if (this.reconnectAttempts < this.maxReconnects) {
                    this.reconnectAttempts++;
                    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
                    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
                    setTimeout(() => this.connect(gameId).catch(() => {}), delay);
                }
            };

            this.ws.onerror = (error) => {
                console.error('[WS] Error:', error);
                this.emit('error', { error });
                reject(error);
            };
        });
    }

    /**
     * Send a player action to the server.
     */
    sendAction(action, amount = 0) {
        this.send({ type: 'action', action, amount });
    }

    /**
     * Send a raw message.
     */
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            console.log('[WS] →', data);
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('[WS] Cannot send — not connected');
        }
    }

    /**
     * Disconnect from the game.
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    /**
     * Check if connected.
     */
    get connected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }
}

// Global instance
window.gameSocket = new GameSocket();
