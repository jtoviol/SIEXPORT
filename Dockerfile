FROM python:3.10-slim

# ── Microsoft ODBC Driver 17 for SQL Server ────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg2 apt-transport-https unixodbc-dev \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl https://packages.microsoft.com/config/debian/12/prod.list \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── uv ────────────────────────────────────────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# ── Dependencias (capa cacheada; se invalida solo si pyproject.toml o uv.lock cambian) ──
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --extra sqlserver --no-install-project

# ── Código fuente ──────────────────────────────────────────────────────────────
COPY src/ ./src/
RUN uv sync --no-dev --extra sqlserver

# Directorio de datos persistente (SQLite + ZIPs generados)
RUN mkdir -p data

EXPOSE 8765

# Usa uvicorn directamente para evitar --reload en producción;
# API_PORT sobreescribe el puerto si se define en el entorno.
CMD sh -c "uv run uvicorn efdi.main:app --host 0.0.0.0 --port ${API_PORT:-8765}"
