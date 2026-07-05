from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app import api, db, llm, ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(
    title="AtelIA",
    description="Atelier IA de la Conserverie du Sud — POC facture électronique, souverain.",
    version="0.2.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api.router)
app.include_router(ui.router)


@app.get("/health")
async def health():
    database = await db.health()
    if not (database["connected"] and database["pgvector"]):
        raise HTTPException(status_code=503, detail={"status": "degraded", "database": database})
    return {"status": "ok", "database": database}


@app.get("/llm/ping")
async def llm_ping():
    """Appel test minimal : un chat + un embedding via la couche LiteLLM."""
    try:
        chat = await llm.complete("Réponds uniquement par le mot : pong", max_tokens=8)
        embedding = await llm.embed("ping")
    except Exception as exc:  # clé absente/invalide, réseau, quota…
        raise HTTPException(status_code=502, detail=f"Appel LLM échoué : {exc}") from exc
    return {"status": "ok", "chat": chat, "embedding": embedding}
