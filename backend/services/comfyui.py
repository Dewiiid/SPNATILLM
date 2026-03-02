"""Service for generating character art via a locally hosted ComfyUI instance."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

from ..models.character import GameCharacter
from ..utils.prompt_builder import build_image_prompt

logger = logging.getLogger(__name__)


# Default ComfyUI API workflow for text-to-image generation.
# This is a minimal workflow; users can swap in their own via config.
DEFAULT_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 7.0,
            "denoise": 1.0,
            "latent_image": ["5", 0],
            "model": ["4", 0],
            "negative": ["7", 0],
            "positive": ["6", 0],
            "sampler_name": "euler_ancestral",
            "scheduler": "normal",
            "seed": -1,
            "steps": 25,
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "PLACEHOLDER"},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"batch_size": 1, "height": 768, "width": 512},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["4", 1], "text": "POSITIVE_PROMPT"},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["4", 1], "text": "NEGATIVE_PROMPT"},
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "spnati_character", "images": ["8", 0]},
    },
}


class ComfyUIService:
    """Generate character portrait art using a locally hosted ComfyUI instance."""

    def __init__(
        self,
        url: str = "http://localhost:8188",
        workflow_path: Optional[str] = None,
        width: int = 512,
        height: int = 768,
        steps: int = 25,
        cfg_scale: float = 7.0,
        sampler: str = "euler_ancestral",
        negative_prompt: str = "",
        timeout: float = 120.0,
        cache_dir: str = "image_cache",
    ):
        self.url = url.rstrip("/")
        self.width = width
        self.height = height
        self.steps = steps
        self.cfg_scale = cfg_scale
        self.sampler = sampler
        self.negative_prompt = negative_prompt
        self.timeout = timeout
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load custom workflow or use default
        self.workflow = self._load_workflow(workflow_path)

    def _load_workflow(self, path: Optional[str]) -> dict[str, Any]:
        """Load a ComfyUI workflow from file or use default."""
        if path:
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load workflow from {path}: {e}. Using default.")
        return json.loads(json.dumps(DEFAULT_WORKFLOW))

    async def check_health(self) -> bool:
        """Check if ComfyUI is running."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.url}/system_stats")
                return resp.status_code == 200
        except Exception:
            return False

    async def get_checkpoints(self) -> list[str]:
        """List available SD checkpoints."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.url}/object_info/CheckpointLoaderSimple"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return (
                        data.get("CheckpointLoaderSimple", {})
                        .get("input", {})
                        .get("required", {})
                        .get("ckpt_name", [[]])[0]
                    )
        except Exception as e:
            logger.warning(f"Could not list checkpoints: {e}")
        return []

    def _get_cache_key(self, character_id: str, clothing_hash: str, emotion: str) -> str:
        """Generate a cache key for a specific character+clothing+emotion combo."""
        return f"{character_id}_{clothing_hash}_{emotion}"

    def _get_cached_image(self, cache_key: str) -> Optional[str]:
        """Check if we have a cached image for this state."""
        cache_file = self.cache_dir / f"{cache_key}.png"
        if cache_file.exists():
            with open(cache_file, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        return None

    def _save_to_cache(self, cache_key: str, image_data: bytes):
        """Save an image to the cache."""
        cache_file = self.cache_dir / f"{cache_key}.png"
        with open(cache_file, "wb") as f:
            f.write(image_data)

    def _build_workflow(
        self,
        positive_prompt: str,
        negative_prompt: str,
        seed: int = -1,
    ) -> dict[str, Any]:
        """Build a ComfyUI workflow with the given prompts."""
        workflow = json.loads(json.dumps(self.workflow))

        # Walk the workflow and fill in our values
        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            inputs = node.get("inputs", {})

            if class_type == "KSampler":
                inputs["steps"] = self.steps
                inputs["cfg"] = self.cfg_scale
                inputs["sampler_name"] = self.sampler
                if seed >= 0:
                    inputs["seed"] = seed
                else:
                    inputs["seed"] = int.from_bytes(
                        uuid.uuid4().bytes[:4], byteorder="big"
                    )

            elif class_type == "EmptyLatentImage":
                inputs["width"] = self.width
                inputs["height"] = self.height

            elif class_type == "CLIPTextEncode":
                text = inputs.get("text", "")
                if text == "POSITIVE_PROMPT" or "positive" in text.lower():
                    inputs["text"] = positive_prompt
                elif text == "NEGATIVE_PROMPT" or "negative" in text.lower():
                    inputs["text"] = negative_prompt

        return workflow

    async def generate_character_image(
        self,
        character: GameCharacter,
        emotion: str = "neutral",
        use_cache: bool = True,
    ) -> Optional[str]:
        """Generate a portrait image for a character in their current clothing state.

        Args:
            character: The character to render.
            emotion: Emotional expression for the portrait.
            use_cache: Whether to use cached images.

        Returns:
            Base64-encoded PNG image data, or None on failure.
        """
        # Build a clothing hash for cache lookup
        worn_names = sorted(
            item.name for item in character.clothing.worn_items
        )
        clothing_hash = "_".join(worn_names).replace(" ", "").lower() or "naked"
        cache_key = self._get_cache_key(character.id, clothing_hash, emotion)

        # Check cache first
        if use_cache:
            cached = self._get_cached_image(cache_key)
            if cached:
                logger.info(f"Cache hit for {character.display_name} [{clothing_hash}]")
                return cached

        # Build prompts
        prompts = build_image_prompt(character, emotion)
        positive = prompts["positive"]
        negative = prompts["negative"]
        if self.negative_prompt:
            negative = f"{self.negative_prompt}, {negative}"

        logger.info(
            f"Generating image for {character.display_name} "
            f"[{clothing_hash}] [{emotion}]"
        )

        try:
            # Queue the workflow
            workflow = self._build_workflow(positive, negative)
            image_data = await self._queue_and_wait(workflow)

            if image_data:
                # Cache the result
                self._save_to_cache(cache_key, image_data)
                return base64.b64encode(image_data).decode("ascii")

        except Exception as e:
            logger.error(f"Image generation failed: {e}")

        # If we have a reference image from the card, return that as fallback
        if character.reference_image_b64:
            return character.reference_image_b64

        return None

    async def _queue_and_wait(self, workflow: dict[str, Any]) -> Optional[bytes]:
        """Queue a workflow in ComfyUI and wait for the result."""
        client_id = str(uuid.uuid4())

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Queue the prompt
            resp = await client.post(
                f"{self.url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )

            if resp.status_code != 200:
                logger.error(f"ComfyUI queue failed: {resp.status_code} {resp.text}")
                return None

            prompt_data = resp.json()
            prompt_id = prompt_data.get("prompt_id")

            if not prompt_id:
                logger.error("No prompt_id returned from ComfyUI")
                return None

            # Poll for completion
            image_data = await self._poll_for_result(client, prompt_id, client_id)
            return image_data

    async def _poll_for_result(
        self,
        client: httpx.AsyncClient,
        prompt_id: str,
        client_id: str,
        poll_interval: float = 1.0,
        max_polls: int = 120,
    ) -> Optional[bytes]:
        """Poll ComfyUI history until the image is ready."""
        for _ in range(max_polls):
            await asyncio.sleep(poll_interval)

            try:
                resp = await client.get(f"{self.url}/history/{prompt_id}")

                if resp.status_code == 200:
                    history = resp.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})

                        # Find the SaveImage node output
                        for node_id, node_output in outputs.items():
                            images = node_output.get("images", [])
                            if images:
                                # Fetch the first image
                                img_info = images[0]
                                filename = img_info.get("filename", "")
                                subfolder = img_info.get("subfolder", "")
                                img_type = img_info.get("type", "output")

                                img_resp = await client.get(
                                    f"{self.url}/view",
                                    params={
                                        "filename": filename,
                                        "subfolder": subfolder,
                                        "type": img_type,
                                    },
                                )

                                if img_resp.status_code == 200:
                                    return img_resp.content

            except httpx.ReadTimeout:
                continue
            except Exception as e:
                logger.warning(f"Poll error: {e}")
                continue

        logger.error(f"Timed out waiting for image generation (prompt_id={prompt_id})")
        return None

    async def generate_removal_sequence(
        self,
        character: GameCharacter,
        removed_item_name: str,
    ) -> Optional[str]:
        """Generate an image specifically for the moment of clothing removal.

        This creates a more expressive image showing the character's reaction
        to losing a piece of clothing.
        """
        # Determine emotion based on remaining clothing
        remaining = character.clothing.remaining_layers
        total = character.clothing.total_layers

        if remaining == 0:
            emotion = "embarrassed"
        elif remaining <= total * 0.3:
            emotion = "nervous"
        elif remaining <= total * 0.6:
            emotion = "embarrassed"
        else:
            emotion = "neutral"

        return await self.generate_character_image(character, emotion=emotion)
