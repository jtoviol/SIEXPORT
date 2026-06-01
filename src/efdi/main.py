"""Punto de entrada FastAPI."""
import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
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
# _SECRET se deriva de las credenciales para que todos los workers obtengan
# exactamente el mismo valor — clave para que los tokens sean verificables
# independientemente del worker que los recibió.
_SECRET = hashlib.sha256(
    f"siexport-v1:{settings.auth_user}:{settings.auth_password}:{settings.auth_secret}".encode()
).digest()
_PWD_HASH = hashlib.sha256(settings.auth_password.encode()).hexdigest()
_SESSION_TTL = timedelta(hours=8)
_COOKIE = "siexport_session"

_PUBLIC_PATHS = {"/auth/login", "/auth/logout", "/health"}
_PUBLIC_PREFIXES = ("/static/",)


def _make_token(username: str) -> str:
    """Crea un token firmado con expiración."""
    expiry = int((datetime.now() + _SESSION_TTL).timestamp())
    payload = f"{username}|{expiry}"
    sig = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def _verify_token(token: str) -> str | None:
    """Retorna el username si el token es válido y no expiró, o None."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        # payload tiene exactamente 2 campos separados por |, la sig es el último
        *parts, sig = decoded.split("|")
        payload = "|".join(parts)
        expected = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected):
            return None
        username, expiry_str = parts
        if datetime.now().timestamp() > float(expiry_str):
            return None
        return username
    except Exception:
        return None


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)

    token = request.cookies.get(_COOKIE)
    if not token or _verify_token(token) is None:
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
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    if (
        not secrets.compare_digest(username.strip(), settings.auth_user)
        or not secrets.compare_digest(pwd_hash, _PWD_HASH)
    ):
        return RedirectResponse("/auth/login?error=1", status_code=303)

    token = _make_token(username.strip())
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        _COOKIE, token,
        httponly=True,
        samesite="lax",
        max_age=int(_SESSION_TTL.total_seconds()),
    )
    return resp


@app.post("/auth/logout", include_in_schema=False)
async def do_logout() -> RedirectResponse:
    resp = RedirectResponse("/auth/login", status_code=303)
    resp.delete_cookie(_COOKIE)
    return resp


# ── App routes ─────────────────────────────────────────────────────────────────
app.include_router(router)
app.include_router(router_findrisc)

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
