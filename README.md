# SPNATI-AI: Strip Poker with AI-Generated Characters

A reimagined Strip Poker Night at the Inventory, powered by local AI. Import any character from [Chub.ai](https://chub.ai) via character cards, and the game generates dialogue and artwork in real-time using your locally hosted LLM (KoboldCPP) and image generator (ComfyUI).

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Browser (Frontend)                 │
│  Poker Game UI ← WebSocket → Game State Manager     │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼──────────────────────────────┐
│              FastAPI Backend Server                   │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Chub.ai  │  │  KoboldCPP   │  │   ComfyUI     │  │
│  │ Service  │  │  Service     │  │   Service     │  │
│  │          │  │              │  │               │  │
│  │ Fetch &  │  │ Generate     │  │ Generate art  │  │
│  │ parse    │  │ dialogue in  │  │ per clothing  │  │
│  │ cards    │  │ character    │  │ state change  │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────┘
         │                │                │
    chub.ai API    localhost:5001    localhost:8188
                   (KoboldCPP)       (ComfyUI)
```

## Prerequisites

1. **Python 3.10+**
2. **KoboldCPP** running on `http://localhost:5001`
   - Any GGUF model works; recommended: a 7B+ model with good RP capabilities
   - Launch with: `koboldcpp --model your_model.gguf --port 5001`
3. **ComfyUI** running on `http://localhost:8188`
   - Requires a Stable Diffusion checkpoint loaded
   - The included workflow (`comfyui_workflows/character_render.json`) handles clothing-state rendering
4. **Chub.ai** account (optional, for browsing; direct card URLs work without auth)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure endpoints (edit as needed)
cp config/settings.example.yaml config/settings.yaml

# Start the backend
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Open browser to http://localhost:8000
```

## How It Works

### Character Import
1. Paste a Chub.ai character URL or upload a character card (PNG with embedded JSON / JSON file)
2. The system parses the V2 TavernAI character card spec
3. Personality, scenario, first message, and example dialogues are extracted
4. Clothing is parsed from the card description; missing items are auto-filled

### Clothing System
Each character needs a fair set of clothing to play. The system:
- Scans the character description for clothing mentions (NLP keyword + LLM extraction)
- If fewer than 4 items found, fills in standard defaults (jacket/hoodie, shirt/top, pants/skirt, underwear, socks, shoes)
- Ensures parity with other players (±1 item tolerance)
- Each removal triggers a new image generation

### Dialogue Generation
- Character card personality + system prompt → KoboldCPP
- Context includes: game state, current clothing, opponent actions, poker hand results
- Characters react in-character to wins, losses, and clothing removal
- Supports multi-turn memory within a game session

### Image Generation
- ComfyUI workflow receives: character description, current clothing list, removed item, pose/emotion
- Generates a portrait for each clothing state
- Images are cached per character + clothing combination
- Supports img2img if the card includes a reference image

## Configuration

See `config/settings.example.yaml` for all options including:
- KoboldCPP endpoint and generation parameters
- ComfyUI endpoint and workflow configuration
- Default clothing sets and game rules
- Image generation quality/speed tradeoffs

## Project Structure

```
spnati-ai/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── models/
│   │   ├── character.py     # Character data models
│   │   ├── game.py          # Game state models
│   │   └── clothing.py      # Clothing system models
│   ├── services/
│   │   ├── chub.py          # Chub.ai card fetcher/parser
│   │   ├── kobold.py        # KoboldCPP dialogue generation
│   │   ├── comfyui.py       # ComfyUI image generation
│   │   ├── clothing.py      # Clothing detection & normalization
│   │   └── poker.py         # Poker game engine
│   ├── routes/
│   │   ├── game.py          # Game WebSocket & REST endpoints
│   │   └── characters.py    # Character import endpoints
│   └── utils/
│       ├── card_parser.py   # TavernAI card V1/V2 parser
│       └── prompt_builder.py# LLM prompt construction
├── frontend/
│   ├── index.html           # Main game page
│   ├── css/
│   │   └── game.css         # Game styles
│   ├── js/
│   │   ├── app.js           # Main application
│   │   ├── poker.js         # Poker UI logic
│   │   ├── characters.js    # Character management UI
│   │   └── websocket.js     # WebSocket client
│   └── assets/
│       └── cards/           # Playing card sprites
├── comfyui_workflows/
│   └── character_render.json# ComfyUI workflow template
├── config/
│   ├── settings.example.yaml
│   └── settings.yaml
├── requirements.txt
└── README.md
```

## License

Based on the original SPNATI project. Poker engine and game logic adapted under the original license.
AI integration layer is MIT licensed.
