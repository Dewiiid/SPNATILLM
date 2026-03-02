/**
 * Character import and management for the lobby.
 */
class CharacterManager {
    constructor() {
        this.characters = new Map(); // id → character data
        this.onUpdate = null; // callback when roster changes
    }

    /**
     * Import a character from a Chub.ai URL.
     */
    async importFromUrl(url) {
        const resp = await fetch('/api/characters/import/url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Import failed' }));
            throw new Error(err.detail || `Import failed (${resp.status})`);
        }

        const data = await resp.json();
        this.characters.set(data.id, data);
        this._notify();
        return data;
    }

    /**
     * Import a character from an uploaded file.
     */
    async importFromFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        const resp = await fetch('/api/characters/import/file', {
            method: 'POST',
            body: formData,
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(err.detail || `Upload failed (${resp.status})`);
        }

        const data = await resp.json();
        this.characters.set(data.id, data);
        this._notify();
        return data;
    }

    /**
     * Search for characters on Chub.ai.
     */
    async search(query) {
        const resp = await fetch('/api/characters/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, limit: 10 }),
        });

        if (!resp.ok) return [];
        const data = await resp.json();
        return data.results || [];
    }

    /**
     * Remove a character from the roster.
     */
    async remove(characterId) {
        await fetch(`/api/characters/${characterId}`, { method: 'DELETE' }).catch(() => {});
        this.characters.delete(characterId);
        this._notify();
    }

    /**
     * Get all character IDs.
     */
    getIds() {
        return Array.from(this.characters.keys());
    }

    /**
     * Get character count.
     */
    get count() {
        return this.characters.size;
    }

    _notify() {
        if (this.onUpdate) this.onUpdate(this.characters);
    }
}

window.characterManager = new CharacterManager();
