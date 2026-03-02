"""SPNATI-AI: Strip Poker with AI-Generated Characters.

FastAPI application serving both the API and the frontend.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routes.characters import router as characters_router
from .routes.game import router as game_router

# ── Logging ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("spnati-ai")

# ── App ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SPNATI-AI",
    description="Strip Poker Night with AI-Generated Characters",
    version="1.0.0",
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ──────────────────────────────────────────────────────────

app.include_router(characters_router)
app.include_router(game_router)


# ── Static Files & Frontend ─────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIR / "assets")),
        name="assets",
    )

    @app.get("/")
    async def serve_frontend():
        return FileResponse(str(FRONTEND_DIR / "index.html"))


# ── Startup ─────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("  SPNATI-AI Starting Up")
    logger.info("=" * 60)

    # Check backend services
    from .services.kobold import KoboldService
    from .services.comfyui import ComfyUIService

    kobold = KoboldService()
    comfyui = ComfyUIService()

    kobold_ok = await kobold.check_health()
    comfyui_ok = await comfyui.check_health()

    logger.info(f"  KoboldCPP:  {'✓ Connected' if kobold_ok else '✗ Not available'}")
    logger.info(f"  ComfyUI:    {'✓ Connected' if comfyui_ok else '✗ Not available'}")

    if kobold_ok:
        info = await kobold.get_model_info()
        if info:
            logger.info(f"  Model:      {info.get('result', 'unknown')}")

    if comfyui_ok:
        checkpoints = await comfyui.get_checkpoints()
        if checkpoints:
            logger.info(f"  Checkpoints: {', '.join(checkpoints[:3])}")

    if not kobold_ok:
        logger.warning(
            "  KoboldCPP not available — dialogue will use fallback text. "
            "Start KoboldCPP on port 5001 for AI dialogue."
        )
    if not comfyui_ok:
        logger.warning(
            "  ComfyUI not available — will use card avatar images only. "
            "Start ComfyUI on port 8188 for AI image generation."
        )

    logger.info("=" * 60)
    logger.info("  Ready at http://localhost:8000")
    logger.info("=" * 60)
