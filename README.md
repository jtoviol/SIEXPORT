# SIEXPORT — Sistema Inteligente de Exportación de Facturación

Herramienta web que extrae registros desde SQL Server (o datos mock para pruebas), los agrupa por afiliado y genera un `.zip` con un PDF limpio por cada registro.

```
extraccion.zip
├── CC_18327520862/
│   └── atencion_001_2026-05-11.pdf
├── CC_50839198571/
│   ├── atencion_001_2026-04-02.pdf
│   ├── atencion_002_2026-04-16.pdf
│   └── atencion_003_2026-04-18.pdf
└── …
```

---

## Stack

| Capa | Tecnología | Por qué |
|---|---|---|
| Backend | **FastAPI + Pydantic v2** | Validación tipada + Swagger automático |
| PDF | **ReportLab** | Generación nativa, diseño propio |
| DB | **pyodbc** (opcional) | Driver oficial SQL Server |
| Frontend | **HTML + Tailwind CDN + Vanilla JS** | Sin build step, una página, servida por FastAPI |
| Tests | **pytest + httpx** | 10 tests E2E + unit |

---

## Instalación

### Requisitos

- Python ≥ 3.10
- pip
- (Solo para SQL real) ODBC Driver 17 for SQL Server

### Pasos

```bash
cd /mnt/d/proyecto

# Recomendado: venv aislado
python3 -m venv .venv
source .venv/bin/activate

# Dependencias
pip install -e ".[dev]"
# Si vas a SQL Server real, agregar el extra:
pip install -e ".[dev,sqlserver]"

# Config
cp .env.example .env
# editar .env con tus valores
```

---

## Configuración (`.env`)

```bash
USE_MOCK=true              # true=mock | false=SQL Server real
LIMITE_REGISTROS=25

DB_HOST=10.244.21.11
DB_PORT=1433
DB_NAME=seragil
DB_USER=sa
DB_PASSWORD=tu-password
DB_DRIVER=ODBC Driver 17 for SQL Server

DATA_DIR=./data
API_HOST=0.0.0.0
API_PORT=8765
LOG_LEVEL=INFO
```

> ⚠️ Nunca commitees `.env`. Ya está en `.gitignore`.

---

## Cómo correr

### Desarrollo (con auto-reload)

```bash
python3 -m efdi.main
```

O con uvicorn directo:

```bash
uvicorn efdi.main:app --reload --host 127.0.0.1 --port 8765
```

### Producción

```bash
uvicorn efdi.main:app --host 0.0.0.0 --port 8765 --workers 4
```

### URLs

| URL | Qué tiene |
|---|---|
| `http://127.0.0.1:8765/` | **Vista web** |
| `http://127.0.0.1:8765/docs` | Swagger |
| `http://127.0.0.1:8765/health` | Status |
| `http://127.0.0.1:8765/db/ping` | Test SQL Server |

---

## Cómo usar (vista web)

1. Abrir http://127.0.0.1:8765/
2. **Nueva extracción** → elegir rango + límite → Generar
3. Tabla **Extracciones recientes** se actualiza sola (1s con jobs activos, 5s si no)
4. Cuando el badge dice **Completado** → click **Descargar**

El badge superior derecho indica modo **Mock** o **SQL Server**.

---

## API REST

### `GET /health`
```json
{ "status": "ok", "version": "0.1.0", "modo": "mock" }
```

### `GET /db/ping`
```json
{ "host": "10.244.21.11", "database": "seragil", "ok": true }
```

### `POST /extractions`
```json
// Request
{ "desde": "2026-04-01", "hasta": "2026-05-28", "limite": 25 }

// Response 202
{ "id": "uuid", "estado": "pending", ... }
```

### `GET /extractions`
Lista todas las extracciones.

### `GET /extractions/{id}`
Estado + métricas. Estados: `pending` → `running` → `completed` / `failed`.

### `GET /extractions/{id}/download`
Devuelve el `.zip` (solo si está `completed`).

---

## Conexión a SQL Server real

### Linux/WSL — instalar driver

```bash
sudo apt update && sudo apt install -y curl gnupg unixodbc-dev
curl https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt update
sudo ACCEPT_EULA=Y apt install -y msodbcsql17

pip install -e ".[sqlserver]"
```

### Verificar

1. `USE_MOCK=false` en `.env`
2. Reiniciar server
3. `curl http://127.0.0.1:8765/db/ping` → esperar `"ok": true`

Si responde `false`:
- Driver no instalado → instalar `msodbcsql17`
- Host inalcanzable → necesitás estar en la red corporativa / VPN
- Credenciales mal → verificar `DB_USER` / `DB_PASSWORD`

---

## Tests

```bash
pytest -v
```

Resultado: **10/10 PASS**.

---

## Estructura

```
/mnt/d/proyecto/
├── pyproject.toml
├── .env / .env.example
├── README.md
├── src/efdi/
│   ├── main.py              # FastAPI app + sirve /
│   ├── config.py            # settings
│   ├── api/                 # routes + schemas
│   ├── domain/              # models + lógica
│   ├── infrastructure/      # mock, repository, job_store
│   ├── services/            # orquestador
│   ├── pdf/generator.py     # ReportLab
│   └── web/index.html       # vista web
├── tests/
└── data/                    # zips generados (gitignored)
```

---

## Solución de problemas

**`address already in use`** → otro proceso usa el puerto. Cambiar a otro:
```bash
uvicorn efdi.main:app --port 8888
```

**`/db/ping` devuelve `ok: false`** → mirar logs del server:
- `pyodbc no instalado` → `pip install -e ".[sqlserver]"`
- `IM002 Data source name not found` → falta `msodbcsql17`
- `08001 connection failed` → red/firewall/credenciales

**La vista web no carga** → confirmar endpoint:
```bash
curl -I http://127.0.0.1:8765/
# debe responder HTTP 200 con text/html
```

---

## Roadmap

- [ ] Persistencia de jobs (SQLite/Redis) — hoy se pierde al reiniciar
- [ ] Auth básica
- [ ] Dockerfile + compose
- [ ] Logs estructurados con `structlog`
- [ ] Métricas Prometheus
