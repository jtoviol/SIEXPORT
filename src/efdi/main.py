"""Punto de entrada FastAPI."""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from efdi import __version__
from efdi.api.routes import router
from efdi.api.routes_findrisc import router as router_findrisc
from efdi.config import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="SIEXPORT — Sistema Inteligente de Exportación de Facturación",
    description=(
        "Sistema de exportación que toma datos desde SQL Server, los agrupa por afiliado "
        "y genera un .zip con un PDF por atención. "
        "Estructura: `CC_XXXXX/atencion_NNN_YYYY-MM-DD.pdf`."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(router_findrisc)


WEB_DIR = Path(__file__).parent / "web"

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


def main() -> None:
    """Entry point para `python -m efdi.main`."""
    import uvicorn

    uvicorn.run(
        "efdi.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
