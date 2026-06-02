# SIEDFASER — Sistema Inteligente de Exportación de Datos para Facturación de Seragil

Herramienta web que extrae registros desde SQL Server (BD `seragil`), los agrupa por afiliado y genera un `.zip` con un PDF por paciente. Soporta múltiples módulos de extracción, cada uno con su propia consulta, modelo de datos y diseño de PDF.

---

## Módulos disponibles

### Demanda Inducida

Extrae registros de `AVS_REGISTRO_SERAGIL` cruzados con `AVS_PROGRAMA_ASOCIADO_DEMIND`. Genera un PDF por afiliado por día con todas sus atenciones y el catálogo de 124 programas marcado.

```
lote_001.zip
├── CC_12345678/
│   └── CC_12345678_2026-05-15.pdf
├── TI_98765432/
│   └── TI_98765432_2026-05-10.pdf
└── …
```

**Filtro fuente:** `FLG_REGIND_DEMIND = 'SI'`  
**API:** `/extractions/...`

---

### FINDRISC *(Evaluación de Riesgo de Diabetes Tipo 2)*

Extrae registros de `SRG_FORMATO_FINDRISC`. Genera un PDF por afiliado con datos demográficos, mediciones antropométricas, respuestas al cuestionario FINDRISC, desglose de puntajes por criterio y clasificación de riesgo con color indicativo.

```
lote_001.zip
├── CC_12345678/
│   └── CC_12345678_2026-05-15.pdf   ← puntaje total + nivel de riesgo
└── …
```

**Filtro fuente:** `FLG_FORMATO_COLDRISC = 'SI'`  
**API:** `/findrisc/extractions/...`

**Clasificación de riesgo FINDRISC:**

| Puntaje | Nivel | Riesgo estimado DM2 |
|---------|-------|---------------------|
| 0 – 6   | BAJO | ~1% |
| 7 – 11  | LIGERAMENTE ELEVADO | ~4% |
| 12 – 14 | MODERADO | ~17% |
| 15 – 20 | ALTO | ~33% |
| ≥ 21    | MUY ALTO | ~50% |

---

## Stack

| Capa | Tecnología |
|---|---|
| Backend | **FastAPI + Pydantic v2** |
| PDF | **ReportLab** |
| DB | **pyodbc** — SQL Server via ODBC Driver 17 |
| Persistencia jobs | **SQLite** (WAL mode) — sobrevive reinicios |
| Frontend | **HTML + Tailwind CDN + Vanilla JS** — SPA sin build step |

---

## Instalación

### Requisitos

- Python ≥ 3.10
- (Solo para SQL real) ODBC Driver 17 for SQL Server

```bash
# Clonar y entrar al proyecto
cd D:\proyecto

# Entorno virtual
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# Dependencias base
pip install -e ".[dev]"

# Dependencias con SQL Server real
pip install -e ".[dev,sqlserver]"

# Configuración
cp .env.example .env
# Editar .env con tus valores
```

---

## Configuración (`.env`)

```bash
USE_MOCK=false              # false=SQL Server real | true=datos ficticios

DB_HOST=10.244.21.11
DB_PORT=1433
DB_NAME=seragil
DB_USER=sa
DB_PASSWORD=tu-password
DB_DRIVER=ODBC Driver 17 for SQL Server

DATA_DIR=./data             # Directorio de salida de ZIPs y PDFs
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO

LOTE_WORKERS=2              # Lotes procesados en paralelo
PDF_WORKERS=-1              # -1=auto (todos los cores) | 0=secuencial
PDF_PARALLEL_THRESHOLD=100  # Mínimo de afiliados para activar Pool
```

> `.env` está en `.gitignore`. Nunca lo commitees.

---

## Cómo correr

```bash
# Desarrollo (auto-reload)
python -m efdi.main

# O con uvicorn directo
uvicorn efdi.main:app --reload --host 0.0.0.0 --port 8000
```

### URLs

| URL | Qué tiene |
|---|---|
| `http://localhost:8000/` | **Vista web** |
| `http://localhost:8000/docs` | Swagger interactivo (todos los módulos) |
| `http://localhost:8000/health` | Estado de la API y modo |
| `http://localhost:8000/db/ping` | Test de conectividad SQL Server |
| `http://localhost:8000/diagnostics` | Diagnóstico completo (DB, disco, métricas) |

---

## Cómo usar (vista web)

1. Abrir `http://localhost:8000/`
2. Seleccionar el módulo en las pestañas superiores: **Demanda Inducida** o **FINDRISC**
3. Hacer clic en **Nueva extracción** → elegir rango de fechas → Generar
4. La vista muestra en tiempo real el progreso de cada lote con su fase actual
5. Al completar → explorar archivos o descargar el `.zip`

El badge superior derecho indica si la conexión es **SQL Server** o **Mock**.

---

## API REST

### Meta

```
GET  /health
GET  /db/ping
GET  /diagnostics
```

### Módulo Demanda Inducida

```
GET  /extractions/count?desde=&hasta=        # Preview de registros antes de generar
POST /extractions                            # Crear extracción (202 Accepted)
GET  /extractions                            # Listar extracciones
GET  /extractions/{id}                       # Estado + métricas
GET  /extractions/{id}/lotes                 # Lotes con fase en tiempo real
GET  /extractions/{id}/lotes/{n}/download    # ZIP de un lote
GET  /extractions/{id}/download              # Mega-ZIP (todos los lotes)
GET  /extractions/{id}/files                 # Árbol de archivos
GET  /extractions/{id}/files/{doc}/{file}    # PDF individual
POST /extractions/{id}/cancel                # Cancelar
DELETE /extractions/{id}                     # Eliminar + borrar disco
```

### Módulo FINDRISC

Misma estructura bajo el prefijo `/findrisc/`:

```
GET  /findrisc/extractions/count?desde=&hasta=
POST /findrisc/extractions
GET  /findrisc/extractions
GET  /findrisc/extractions/{id}
GET  /findrisc/extractions/{id}/lotes
GET  /findrisc/extractions/{id}/lotes/{n}/download
GET  /findrisc/extractions/{id}/download
GET  /findrisc/extractions/{id}/files
GET  /findrisc/extractions/{id}/files/{doc}/{file}
POST /findrisc/extractions/{id}/cancel
DELETE /findrisc/extractions/{id}
```

### Ejemplo: crear extracción FINDRISC

```bash
curl -X POST http://localhost:8000/findrisc/extractions \
  -H "Content-Type: application/json" \
  -d '{"desde": "2026-05-01", "hasta": "2026-05-31"}'
```

---

## Procesamiento por lotes

Cada extracción se divide automáticamente en lotes para manejar volúmenes grandes:

```
POST /extractions
  └─ Calcula N lotes según el total de registros
      └─ ThreadPoolExecutor (LOTE_WORKERS=2)
          └─ Por cada lote:
              ├─ "Consultando base de datos…"  → query SQL con OFFSET/FETCH
              ├─ "Generando PDFs (N afiliados)…" → ReportLab multiprocessing
              └─ "Empaquetando ZIP…" → lote_NNN.zip
```

La fase actual de cada lote se muestra en tiempo real en la vista web.

---

## Conexión a SQL Server real

### Windows — instalar driver ODBC

Descargar e instalar [ODBC Driver 17 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server).

```bash
pip install -e ".[sqlserver]"
```

### Linux/WSL

```bash
sudo apt update && sudo apt install -y curl gnupg unixodbc-dev
curl https://packages.microsoft.com/keys/microsoft.asc | \
  sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | \
  sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt update
sudo ACCEPT_EULA=Y apt install -y msodbcsql17
pip install -e ".[sqlserver]"
```

### Verificar

```bash
# Debe responder "ok": true
curl http://localhost:8000/db/ping
```

---

## Estructura del proyecto

```
D:\proyecto\
├── pyproject.toml
├── .env / .env.example
├── README.md
└── src/efdi/
    ├── main.py                         # FastAPI app — registra routers de ambos módulos
    ├── config.py                       # Settings desde .env
    ├── api/
    │   ├── routes.py                   # Endpoints Demanda Inducida (/extractions/...)
    │   ├── routes_findrisc.py          # Endpoints FINDRISC (/findrisc/extractions/...)
    │   └── schemas.py                  # Request/response Pydantic
    ├── domain/
    │   ├── models.py                   # Atencion, AfiliadoConAtenciones,
    │   │                               # RegistroFindrisc, AfiliadoConFindrisc,
    │   │                               # Extraccion, Lote, ExtraccionTipo
    │   └── services.py                 # agrupar_por_afiliado / agrupar_por_afiliado_findrisc
    ├── infrastructure/
    │   ├── db.py                       # SQLite schema v3 con migraciones
    │   ├── job_store.py                # Persistencia de extracciones y lotes
    │   ├── repository.py              # Consulta Demanda Inducida (SQL Server + mock)
    │   └── repository_findrisc.py     # Consulta FINDRISC (SQL Server + mock)
    ├── pdf/
    │   ├── generator.py               # PDF Demanda Inducida — catálogo 124 programas
    │   ├── generator_findrisc.py      # PDF FINDRISC — puntajes + clasificación de riesgo
    │   ├── parallel.py                # Worker multiprocessing Demanda Inducida
    │   ├── parallel_findrisc.py       # Worker multiprocessing FINDRISC
    │   └── programas_catalogo.py      # Carga programas.txt (124 programas)
    ├── services/
    │   ├── extraction.py              # Orquestador Demanda Inducida
    │   └── extraction_findrisc.py     # Orquestador FINDRISC
    ├── templates/
    │   ├── logo.png
    │   └── programas.txt              # 124 códigos + descripciones de programas DI
    └── web/
        └── index.html                 # SPA — pestañas por módulo, progreso en tiempo real
```

---

## Solución de problemas

**Puerto en uso:**
```bash
uvicorn efdi.main:app --port 8888
```

**`/db/ping` devuelve `ok: false`:**
- `pyodbc no instalado` → `pip install -e ".[sqlserver]"`
- `IM002 Data source name not found` → instalar ODBC Driver 17
- `08001 connection failed` → verificar red/VPN/firewall/credenciales

**La vista web no carga:**
```bash
curl -I http://localhost:8000/
# Debe responder HTTP 200 text/html
```

**Migración de base de datos:** Al actualizar desde versiones anteriores, la BD SQLite se migra automáticamente al arrancar. El schema actual es v3 (añade `lotes.fase` y `extracciones.tipo`).
