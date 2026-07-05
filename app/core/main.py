from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from app.core import db, llm, registry
from app.core.config import settings
from app.core.templates import module_templates

templates = module_templates()

router = APIRouter(include_in_schema=False)


@router.get("/")
async def home(request: Request):
    """Hub d'accueil : une tuile par module découvert par le registre."""
    return templates.TemplateResponse(request, "home.html", {"active": "home"})


@router.get("/about")
async def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {"active": "about"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    for module in registry.modules:
        if module.on_startup is not None:
            await module.on_startup()
    yield
    await db.disconnect()


def create_app() -> FastAPI:
    """App factory : monte le socle (santé, hub, static) puis les modules du registre."""
    app = FastAPI(
        title="AtelIA",
        description=f"AtelIA — atelier IA de {settings.company_name} (PME fictive). "
        "Plateforme modulaire de démonstration AI Engineering, souveraine.",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.include_router(router)
    for module in registry.modules:
        app.include_router(module.router)

    @app.get("/health")
    async def health():
        database = await db.health()
        if not (database["connected"] and database["pgvector"]):
            raise HTTPException(
                status_code=503, detail={"status": "degraded", "database": database}
            )
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

    return app


app = create_app()
