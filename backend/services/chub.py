"""Service for fetching and parsing character cards from Chub.ai."""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from ..models.character import CharacterCard
from ..utils.card_parser import parse_card_from_bytes, parse_card_json

logger = logging.getLogger(__name__)

# Matches URLs like:
#   https://chub.ai/characters/username/character-name
#   https://www.chub.ai/characters/username/character-name
#   https://venus.chub.ai/characters/username/character-name
CHUB_URL_PATTERN = re.compile(
    r"https?://(?:www\.|venus\.)?chub\.ai/characters/([^/]+/[^/?#]+)"
)


class ChubService:
    """Fetch and parse character cards from Chub.ai."""

    def __init__(
        self,
        api_url: str = "https://api.chub.ai",
        cdn_url: str = "https://avatars.charhub.io",
        api_key: str = "",
        timeout: float = 30.0,
    ):
        self.api_url = api_url.rstrip("/")
        self.cdn_url = cdn_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "SPNATI-AI/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def extract_slug(self, url_or_slug: str) -> str:
        """Extract the 'username/character-name' slug from a Chub URL or raw slug."""
        match = CHUB_URL_PATTERN.search(url_or_slug)
        if match:
            return match.group(1)
        # Assume it's already a slug like "username/character-name"
        if "/" in url_or_slug and not url_or_slug.startswith("http"):
            return url_or_slug.strip("/")
        raise ValueError(
            f"Could not parse Chub.ai character from: {url_or_slug}\n"
            f"Expected a URL like https://chub.ai/characters/username/name "
            f"or a slug like username/name"
        )

    async def fetch_character(
        self, url_or_slug: str
    ) -> tuple[CharacterCard, Optional[str]]:
        """Fetch a character card from Chub.ai.

        Args:
            url_or_slug: A Chub.ai character URL or 'username/character-name' slug.

        Returns:
            Tuple of (CharacterCard, optional base64 avatar image).
        """
        slug = self.extract_slug(url_or_slug)
        logger.info(f"Fetching character card for: {slug}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # First try the API endpoint for character data
            card, avatar_b64 = await self._fetch_via_api(client, slug)

            # If we got the card but no avatar, try fetching the avatar separately
            if card and not avatar_b64:
                avatar_b64 = await self._fetch_avatar(client, slug)

            if card:
                return card, avatar_b64

            # Fallback: try downloading the card as a PNG
            return await self._fetch_as_png(client, slug)

    async def _fetch_via_api(
        self, client: httpx.AsyncClient, slug: str
    ) -> tuple[Optional[CharacterCard], Optional[str]]:
        """Try fetching character data via the Chub API."""
        try:
            # The Chub API endpoint for character data
            url = f"{self.api_url}/api/characters/{slug}"
            resp = await client.get(url, headers=self._get_headers())

            if resp.status_code == 200:
                data = resp.json()
                # The API wraps the card data
                node = data.get("node", data)
                card_data = node.get("definition", node)

                # Handle case where definition is a string (JSON)
                if isinstance(card_data, str):
                    import json
                    card_data = json.loads(card_data)

                card = parse_card_json(card_data)

                # Try to get the name from the node if not in card
                if not card.name and "name" in node:
                    card.name = node["name"]

                # Get tags from the node
                if not card.tags and "topics" in node:
                    card.tags = node.get("topics", [])

                return card, None

            logger.warning(f"API returned {resp.status_code} for {slug}")
            return None, None

        except Exception as e:
            logger.warning(f"API fetch failed for {slug}: {e}")
            return None, None

    async def _fetch_avatar(
        self, client: httpx.AsyncClient, slug: str
    ) -> Optional[str]:
        """Fetch character avatar image."""
        try:
            # Try common avatar paths
            for path in [
                f"{self.cdn_url}/avatars/{slug}/avatar.webp",
                f"{self.cdn_url}/avatars/{slug}/chara",
                f"{self.api_url}/api/characters/{slug}/avatar",
            ]:
                resp = await client.get(path, headers=self._get_headers())
                if resp.status_code == 200 and len(resp.content) > 100:
                    import base64
                    return base64.b64encode(resp.content).decode("ascii")

        except Exception as e:
            logger.warning(f"Avatar fetch failed for {slug}: {e}")

        return None

    async def _fetch_as_png(
        self, client: httpx.AsyncClient, slug: str
    ) -> tuple[CharacterCard, Optional[str]]:
        """Fallback: download the character card as a PNG file."""
        try:
            url = f"{self.api_url}/api/characters/{slug}/download"
            resp = await client.get(url, headers=self._get_headers())

            if resp.status_code == 200:
                return parse_card_from_bytes(resp.content, f"{slug}.png")

        except Exception as e:
            logger.warning(f"PNG download failed for {slug}: {e}")

        raise ValueError(
            f"Could not fetch character '{slug}' from Chub.ai. "
            f"The character may not exist or may be private."
        )

    async def search_characters(
        self, query: str, limit: int = 10
    ) -> list[dict]:
        """Search for characters on Chub.ai.

        Returns a list of character summaries with name, slug, and tags.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    f"{self.api_url}/api/characters/search",
                    params={"search": query, "first": limit, "sort": "trending"},
                    headers=self._get_headers(),
                )

                if resp.status_code == 200:
                    data = resp.json()
                    nodes = data.get("nodes", data.get("data", []))
                    results = []
                    for node in nodes:
                        results.append({
                            "name": node.get("name", "Unknown"),
                            "slug": node.get("fullPath", ""),
                            "description": (node.get("tagline", "") or "")[:200],
                            "tags": node.get("topics", []),
                            "star_count": node.get("starCount", 0),
                        })
                    return results

            except Exception as e:
                logger.warning(f"Search failed: {e}")

        return []
