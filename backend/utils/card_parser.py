"""Parser for TavernAI character card formats (V1, V2, PNG embedded)."""
from __future__ import annotations

import base64
import io
import json
import struct
import zlib
from typing import Any, Optional

from ..models.character import CharacterCard


def parse_card_json(data: dict[str, Any]) -> CharacterCard:
    """Parse a character card from a JSON dictionary.

    Handles both V1 (flat) and V2 (nested under 'data') formats.
    """
    # Check for V2 format (has 'spec' field or nested 'data')
    if "spec" in data and data.get("spec") in ("chara_card_v2", "chara_card_v3"):
        inner = data.get("data", {})
    elif "data" in data and isinstance(data["data"], dict) and "name" in data["data"]:
        inner = data["data"]
    else:
        # V1 format — fields are at top level
        inner = data

    return CharacterCard(
        name=inner.get("name", ""),
        description=inner.get("description", ""),
        personality=inner.get("personality", ""),
        scenario=inner.get("scenario", ""),
        first_mes=inner.get("first_mes", ""),
        mes_example=inner.get("mes_example", ""),
        system_prompt=inner.get("system_prompt", ""),
        post_history_instructions=inner.get("post_history_instructions", ""),
        creator_notes=inner.get("creator_notes", ""),
        tags=inner.get("tags", []),
        character_book=inner.get("character_book"),
        extensions=inner.get("extensions", {}),
    )


def extract_png_text_chunk(png_bytes: bytes, keyword: str = "chara") -> Optional[str]:
    """Extract a tEXt or iTXt chunk from a PNG file by keyword.

    TavernAI cards embed character JSON as base64 in a tEXt chunk with keyword 'chara'.
    """
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return None

    offset = 8
    while offset < len(png_bytes):
        if offset + 8 > len(png_bytes):
            break

        length = struct.unpack(">I", png_bytes[offset : offset + 4])[0]
        chunk_type = png_bytes[offset + 4 : offset + 8].decode("ascii", errors="replace")
        chunk_data = png_bytes[offset + 8 : offset + 8 + length]

        if chunk_type == "tEXt":
            # tEXt: keyword\0text
            null_idx = chunk_data.find(b"\x00")
            if null_idx != -1:
                key = chunk_data[:null_idx].decode("latin-1")
                if key == keyword:
                    text = chunk_data[null_idx + 1 :].decode("latin-1")
                    return text

        elif chunk_type == "iTXt":
            # iTXt: keyword\0compression_flag\0compression_method\0language\0translated_keyword\0text
            null_idx = chunk_data.find(b"\x00")
            if null_idx != -1:
                key = chunk_data[:null_idx].decode("utf-8", errors="replace")
                if key == keyword:
                    rest = chunk_data[null_idx + 1 :]
                    if len(rest) >= 2:
                        compression_flag = rest[0]
                        # Skip compression_method, language, translated_keyword
                        rest = rest[2:]  # skip flag + method
                        # Skip language tag
                        null2 = rest.find(b"\x00")
                        if null2 != -1:
                            rest = rest[null2 + 1 :]
                            # Skip translated keyword
                            null3 = rest.find(b"\x00")
                            if null3 != -1:
                                text_data = rest[null3 + 1 :]
                                if compression_flag:
                                    text_data = zlib.decompress(text_data)
                                return text_data.decode("utf-8", errors="replace")

        # Move to next chunk (length + type(4) + data(length) + crc(4))
        offset += 12 + length

        if chunk_type == "IEND":
            break

    return None


def parse_png_card(png_bytes: bytes) -> tuple[CharacterCard, Optional[str]]:
    """Parse a character card from a PNG file.

    Returns (card, base64_image) where base64_image is the PNG as base64
    for use as a reference image in image generation.
    """
    text = extract_png_text_chunk(png_bytes, "chara")
    if text is None:
        raise ValueError("No character data found in PNG. Is this a TavernAI card?")

    # The text chunk contains base64-encoded JSON
    try:
        json_str = base64.b64decode(text).decode("utf-8")
    except Exception:
        # Maybe it's already plain JSON
        json_str = text

    data = json.loads(json_str)
    card = parse_card_json(data)

    # Extract the image as base64 for reference
    image_b64 = base64.b64encode(png_bytes).decode("ascii")

    return card, image_b64


def parse_card_from_bytes(
    file_bytes: bytes, filename: str = ""
) -> tuple[CharacterCard, Optional[str]]:
    """Auto-detect format and parse a character card.

    Returns (card, optional_reference_image_b64).
    """
    fname = filename.lower()

    # Try PNG first if it looks like one
    if fname.endswith(".png") or file_bytes[:4] == b"\x89PNG":
        return parse_png_card(file_bytes)

    # Try JSON
    try:
        data = json.loads(file_bytes.decode("utf-8"))
        return parse_card_json(data), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    raise ValueError(
        f"Could not parse character card from file '{filename}'. "
        "Supported formats: PNG (TavernAI card), JSON (V1/V2 spec)."
    )
