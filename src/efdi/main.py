"""Punto de entrada FastAPI."""
import logging
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from efdi import __version__
from efdi.api.dependencies import COOKIE_NAME, make_token, verify_token
from efdi.api.routes import router, router_di
from efdi.api.routes_captacion import router as router_captacion
from efdi.api.routes_caracterizacion import router as router_caracterizacion
from efdi.api.routes_dashboard import router as router_dashboard
from efdi.api.routes_findrisc import router as router_findrisc
from efdi.api.routes_me import router as router_me
from efdi.api.routes_planfami import router as router_planfami
from efdi.api.routes_pruebas import router as router_pruebas
from efdi.api.routes_users import router as router_users
from efdi.api.routes_vacunacion import router as router_vacunacion
from efdi.config import settings
from efdi.services.auth_service import autenticar, bootstrap_admin_si_vacio

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="SIEDFASER — Sistema Inteligente de Exportación de Datos para Facturación de Seragil",
    description=(
        "Sistema de exportación que toma datos desde SQL Server, los agrupa por afiliado "
        "y genera un .zip con un PDF por afiliado."
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

# ── Autenticación con cookie firmada (HMAC-SHA256) ─────────────────────────────
# Stateless: funciona con --workers N sin estado compartido entre procesos.
# El token sigue siendo HMAC (lo firma `make_token` en dependencies.py), pero el
# username dentro del token se valida ahora contra la tabla `users` en DB —
# permite múltiples usuarios, roles y permisos por módulo.
_SESSION_TTL = timedelta(hours=8)
_PUBLIC_PATHS = {"/auth/login", "/auth/logout", "/health"}
_PUBLIC_PREFIXES = ("/static/",)


@app.on_event("startup")
async def _bootstrap() -> None:
    """Si la tabla `users` está vacía, crea el primer admin con las credenciales
    del .env. A partir de ese momento, .env queda como referencia pero ya no es
    fuente de autenticación: todos los logins van contra DB con bcrypt."""
    try:
        u = bootstrap_admin_si_vacio()
        if u is not None:
            logging.getLogger(__name__).info(
                "auth: bootstrap admin '%s' creado (DB vacía)", u.username
            )
    except Exception:
        logging.getLogger(__name__).exception("auth: bootstrap_admin falló")


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)

    token = request.cookies.get(COOKIE_NAME)
    if not token or verify_token(token) is None:
        # Para JSON APIs devolver 401; para páginas redirigir al login.
        if path.startswith("/api/") or request.headers.get("accept", "").startswith("application/json"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "No autenticado"}, status_code=401)
        return RedirectResponse("/auth/login", status_code=302)

    return await call_next(request)


# ── Auth routes ────────────────────────────────────────────────────────────────
WEB_DIR = Path(__file__).parent / "web"


@app.get("/auth/login", include_in_schema=False)
async def login_page() -> FileResponse:
    return FileResponse(WEB_DIR / "login.html")


@app.post("/auth/login", include_in_schema=False)
async def do_login(
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    user = autenticar(username, password)
    if user is None:
        return RedirectResponse("/auth/login?error=1", status_code=303)

    token = make_token(user.username)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True,
        samesite="lax",
        max_age=int(_SESSION_TTL.total_seconds()),
    )
    return resp


@app.post("/auth/logout", include_in_schema=False)
async def do_logout() -> RedirectResponse:
    resp = RedirectResponse("/auth/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ── App routes ─────────────────────────────────────────────────────────────────
app.include_router(router)
app.include_router(router_di)
app.include_router(router_findrisc)
app.include_router(router_captacion)
app.include_router(router_planfami)
app.include_router(router_pruebas)
app.include_router(router_vacunacion)
app.include_router(router_caracterizacion)
app.include_router(router_dashboard)
app.include_router(router_users)
app.include_router(router_me)

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


def main() -> None:
    import uvicorn
    uvicorn.run(
        "efdi.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
