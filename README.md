<div align="center">

<img src="src/efdi/web/siedfaser_logo.png" alt="SIEDFASER" width="380" />

# SIEDFASER

### Sistema Inteligente de Exportación de Datos para Facturación de Seragil

<br/>

[![Python](https://img.shields.io/badge/Python-3.10%2B-1a2f6e?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-22a84a?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQL Server](https://img.shields.io/badge/SQL%20Server-ODBC%2017-234674?style=for-the-badge&logo=microsoftsqlserver&logoColor=white)](https://learn.microsoft.com/sql/connect/odbc/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-CDN-22a84a?style=for-the-badge&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![ReportLab](https://img.shields.io/badge/PDF-ReportLab-1a2f6e?style=for-the-badge)](https://www.reportlab.com)

[![Status](https://img.shields.io/badge/status-production-22a84a?style=flat-square)](#)
[![Multi-module](https://img.shields.io/badge/m%C3%B3dulos-2-1a2f6e?style=flat-square)](#módulos-disponibles)
[![Persistence](https://img.shields.io/badge/persistencia-SQLite%20WAL-234674?style=flat-square)](#stack)
[![Concurrency](https://img.shields.io/badge/concurrencia-Pool%20%2B%20Threads-22a84a?style=flat-square)](#procesamiento-por-lotes)

<br/>

</div>

---

## Resumen

**SIEDFASER** es una plataforma web para extracción y empaquetado masivo de datos clínicos de la base **Seragil** (SQL Server) con destino a facturación. Cada extracción agrupa los registros por afiliado y entrega un `.zip` con un PDF por paciente, listo para radicar como soporte de cuenta médica.

**6 módulos activos** — cada uno con su consulta SQL, su modelo de dominio y su plantilla de PDF:

| Módulo | Tabla origen | Filtro | API |
|---|---|---|---|
| Demanda Inducida | `AVS_REGISTRO_SERAGIL` + `AVS_PROGRAMA_ASOCIADO_DEMIND` | `FLG_REGIND_DEMIND = 'SI'` + rango fechas | `/extractions/...` |
| FINDRISC | `SRG_FORMATO_FINDRISC` | `FLG_FORMATO_COLDRISC = 'SI'` + rango fechas | `/findrisc/...` |
| Gestión Captación | `srg_captacion_afiliados` | rango `fec_captacion_afiliado` | `/gestion-captacion/...` |
| Planificación Familiar | `SRG_POBLACION_RIESGO_REPRODUCTIVO` + `SRG_DETALLE_RIESGO_REPRODUCTIVO` | rango `fec_gestion_seguimiento` | `/planificacion-familiar/...` |
| Vacunación | Excel `.xlsx` subido (sin SQL) | régimen del propio Excel | `/vacunacion/...` |
| Caracterización Familiar | `SBW_PERSONA_CARACTERIZADA` + `SBW_UBICACION_FAMILIA` (**base sibacom**, servidor aparte) | rango `fecha_reg` — sin factura | `/caracterizacion-familiar/...` |

> Caracterización Familiar agrupa **por familia** (jerarquía geográfica + vivienda + familia + ciuf): 1 PDF por familia con todos sus integrantes. Requiere las variables `DB_*_SIBACOM` en el `.env`.

Vista inicial: **Dashboard** con KPIs cross-módulo y actividad reciente (no se aterriza en un módulo específico al loguearse).

---

## Identidad visual

| Token | Hex | Uso |
|---|---|---|
| ![#22a84a](https://placehold.co/14x14/22a84a/22a84a.png) **Verde Seragil** | `#22a84a` | Acentos, énfasis, marca |
| ![#1a2f6e](https://placehold.co/14x14/1a2f6e/1a2f6e.png) **Azul corporativo** | `#1a2f6e` | Texto principal, headers |
| ![#234674](https://placehold.co/14x14/234674/234674.png) **Azul institucional** | `#234674` | Botones primarios, navbar |
| ![#f1f5f9](https://placehold.co/14x14/f1f5f9/f1f5f9.png) **Slate 100** | `#f1f5f9` | Fondos suaves |
| ![#64748b](https://placehold.co/14x14/64748b/64748b.png) **Slate 500** | `#64748b` | Texto secundario |

---

## Política de fidelidad a la BD

Para **FINDRISC**, **Captación** y **Planificación Familiar** el PDF imprime los datos **literales** de la BD. No calcula, no clasifica, no infiere:

- Los rangos / puntajes desglosados que mostraba antes FINDRISC se eliminaron porque eran cálculos en Python — solo se muestra el `Puntaje total` que ya viene calculado de la BD.
- Las banderas (`SI` / vacío / `1` / `0`…) se interpretan estrictamente: `"SI"` → recuadro verde, cualquier otra cosa → no marcado. Excepto en Captación y PlanFami, donde **cualquier valor no vacío** se considera marcado (porque la SQL ya las normaliza con `CASE WHEN ... THEN 'SI' ELSE '' END`).
- Los decimales con coma (`"1,72"`) se almacenan como string para no perder el formato del dato original.

Demanda Inducida es distinto: tiene un catálogo fijo de 124 programas, y el PDF resalta los que la persona tiene asignados.

---

## Módulos disponibles

### Demanda Inducida

Extrae registros de `AVS_REGISTRO_SERAGIL` cruzados con `AVS_PROGRAMA_ASOCIADO_DEMIND`. Genera un PDF por afiliado por día (formato "SOPORTE DEMANDA INDUCIDA") con:

- **Header limpio** consistente con FINDRISC (logo Mutualser + título centrado en azul institucional).
- **Datos del afiliado**: documento, nombre, sexo, edad, contacto, departamento/municipio.
- **Tabla de atenciones del día** con todos los programas, IPS, encuestador y los tres flags (Not. / Urg. / C.Ext.) marcados según lo que trae la BD.
- **Catálogo de 124 programas DI** con los del afiliado resaltados en verde.

> **Flags Not./Urg./C.Ext.** se leen vía `_to_bool(...)` que normaliza correctamente `'SI'/'NO'`/bit/null. Antes había un bug que marcaba como ✓ cualquier valor no nulo (incluyendo `'NO'`) — corregido.

> **Wrap en celdas**: si un nombre largo de programa o IPS no entra en su columna, se parte en varias líneas dentro de la misma celda en vez de derramar al espacio adyacente.

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

### FINDRISC — Encuesta de Riesgo de Diabetes Tipo 2

Extrae registros de `SRG_FORMATO_FINDRISC` y genera un PDF por afiliado replicando el formato oficial impreso de Mutualser ("SOPORTE ENCUESTAS FINDRISC"). El PDF contiene:

- **Header**: logo Mutualser + título centrado, sin colores institucionales agresivos.
- **Datos generales del afiliado**: nombre, sexo, edad, municipio, IPS, documento, teléfonos, correo.
- **8 preguntas FINDRISC**:
  - Preguntas 1–3 (Edad, IMC, Perímetro): muestran el valor literal de la BD.
  - Preguntas 4–8 (Actividad física, Verduras, Medicamentos, Glucosa, Antecedente diabetes): marcan en verde la opción que coincide con el valor de la BD.
- **Recuadro de Puntaje total**: muestra el `VLR_PUNTAJE_OBTENIDO` que ya viene calculado de la BD.

> **Política de fidelidad de datos:** el PDF FINDRISC no inventa, no calcula y no clasifica nada. Cada campo se imprime literal como viene del SELECT (`1,72`, `0`, `NO`, etc.). La clasificación de riesgo (BAJO / MODERADO / etc.) **NO se incluye** porque la BD no la trae.

```
lote_001.zip
├── CC_12345678/
│   └── CC_12345678_2026-05-15.pdf
└── …
```

**Filtro fuente:** `FLG_FORMATO_COLDRISC = 'SI'`
**API:** `/findrisc/extractions/...`

**Columnas que devuelve el SELECT:** 20 campos del reporte (Nombre, Sexo, Edad, Municipio, IPS, Tipo y Nº de identificación, Teléfonos 1 y 2, Correo, Peso, Talla, IMC, Perímetro, Actividad física, Frecuencia de verduras, Medicamento hipertensión, Glucosa alta, Antecedente diabetes, Puntaje total) + 4 columnas internas para agrupar (`SEQ_SERAGIL`, `COD_TIPO_IDENTIFICACION`, `FEC_REGISTRO_INFORMACION`, `NUM_REGISTRO`).

### Gestión Captación Afiliados

Extrae registros de `srg_captacion_afiliados` cruzados con `AVS_AFILIADO_MUTUALSER`. Genera un PDF por afiliado por fecha de captación (formato "SOPORTE GESTIÓN CAPTACIÓN AFILIADOS") con:

- **DATOS DEL AFILIADO**: documento, nombre, sexo, edad, fecha nacimiento, regional/depto/municipio, dirección, 3 teléfonos, correo.
- **CAPTACIÓN**: estado (`EN VALIDACION` / `RECHAZADO` / `APROBADO` / `APROBADO PARCIALMENTE` / `NO FUE CONTACTADO`), funcionario, fuente de captación, IPS prestador.
- **PROGRAMAS ASOCIADOS**: grid de 19 banderas (Gestantes, HTA, Mujer sana, Ser Joven, Salud Mental, Víctimas, EPOC, Amarte, Renal, VIH, Hemofilia, Salud sexual, Cáncer, Tuberculosis, Lepra, Epilepsia, Huérfanas, Desnutrición, Obesidad). Las que la BD trae como `"SI"` se marcan con recuadro verde.

**Filtro fuente:** rango de `a.fec_captacion_afiliado` (sin filtros adicionales).
**API:** `/gestion-captacion/extractions/...`

### Seguimiento Planificación Familiar

Extrae registros de `SRG_POBLACION_RIESGO_REPRODUCTIVO` + `SRG_DETALLE_RIESGO_REPRODUCTIVO`. Genera un PDF por afiliado por fecha de gestión (formato "SOPORTE SEGUIMIENTO PLANIFICACIÓN FAMILIAR") con secciones:

- **Bloques compartidos** (no cambian entre seguimientos del mismo afiliado):
  - DATOS DEL AFILIADO (nombre, sexo, edad, doc, teléfonos, régimen)
  - UBICACIÓN Y PERÍODO (regional, depto, municipio, año, trimestre, tipo de población: ADOLESCENTE / MULTIPARA / COHORTE DE RIESGO)
  - FACTORES CLÍNICOS (grid de 13 banderas FIC: Diabetes, HTA, Artritis, Cáncer, Epilepsia, EPOC, Hemofilia, Huérfanas, Renal, Salud mental, Trasplante, Víctimas, VIH)
- **Bloque por cada seguimiento** (cuando hay varios en la misma fecha, sub-header `SEGUIMIENTO #N DE M`):
  - CAPTACIÓN (encuestador, fecha gestión, estado, tipo seguimiento)
  - PLANIFICACIÓN (¿planifica?, motivo no planifica, método anticonceptivo, etc.)
  - EVENTOS OBSTÉTRICOS (Nº eventos, productos, fechas planificación 202 / Temporal)
  - SEGUIMIENTO (¿contactada?, ¿visita domiciliaria?, ¿cierra?, motivo no contacto)

**Filtro fuente:** rango de `a.fec_gestion_seguimiento` (sin filtros adicionales).
**API:** `/planificacion-familiar/extractions/...`

> Para los 13 FIC: cualquier valor no vacío que traiga la BD se considera marcado (en práctica vienen `"SI"` o cadena vacía).

---

## Vista de Inicio (Dashboard)

Al loguearte aterrizás en la pestaña **Inicio** (no en un módulo específico). Muestra:

- **4 KPIs grandes**: PDFs generados hoy / últimos 7 días / último mes y afiliados procesados último mes.
- **4 cards por módulo** (DI, FINDRISC, Captación, Planificación Familiar) con: en curso · completados · fallidos · timestamp de la última extracción. Click → cambia a esa pestaña.
- **Actividad reciente**: lista de las 8 últimas extracciones de cualquier módulo con badge del módulo, estado coloreado y nº de PDFs. Click → abre el job en su módulo.

Mientras trabajás en cualquier módulo, una **franja de chips** queda visible arriba con: `N en curso · M fallidas 24h · X PDFs hoy · Y PDFs mes · Modo: SQL Server/MOCK`. Se refresca cada 15s.

**Endpoint:** `GET /api/dashboard/summary` (autenticado).

---

## Nombres custom en descargas

Cada extracción acepta un nombre opcional (doble clic en el nombre del job en el sidebar). Si tiene nombre:

| Antes | Después |
|---|---|
| `extraccion_2a3b...zip` | `Mi_extraccion_de_mayo.zip` |
| `planfami_lote_001_2a3b...zip` | `Mi_extraccion_de_mayo_lote_001.zip` |

El nombre se sanitiza vía `safe_filename()` en `domain/models.py`:
- Reemplaza `/ \ : * ? " < > |` por `_`.
- Colapsa espacios y guiones bajos múltiples.
- Recorta a 80 caracteres.
- Si queda vacío, usa el fallback con UUID.

---

## Stack

| Capa | Tecnología |
|---|---|
| **Backend** | FastAPI + Pydantic v2 |
| **PDF** | ReportLab (multiprocessing Pool) |
| **DB** | pyodbc — SQL Server via ODBC Driver 17 |
| **Persistencia jobs** | SQLite WAL — sobrevive reinicios |
| **Frontend** | HTML + Tailwind CDN + Vanilla JS — SPA sin build step |
| **Auth** | HMAC + cookie de sesión |

---

## Instalación

### Requisitos

- Python ≥ 3.10 (fijado en `.python-version`)
- [`uv`](https://docs.astral.sh/uv/) — gestor recomendado de entorno + dependencias
- (Solo para SQL real) ODBC Driver 17 for SQL Server

### Camino recomendado — `uv` (reproducible vía `uv.lock`)

```bash
# 1. Instalar uv (una sola vez por máquina)
# Linux/macOS:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell):
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Clonar y entrar al proyecto
git clone <repo-url> && cd proyecto

# 3. Sincronizar dependencias (crea .venv y resuelve uv.lock)
uv sync --extra dev                    # mock, sin SQL Server real
uv sync --extra dev --extra sqlserver  # con SQL Server real

# 4. Configuración
cp .env.example .env
# Editar .env con tus valores

# 5. Correr cualquier comando dentro del venv
uv run python -m efdi.main
uv run pytest
uv run ruff check .
```

`uv sync` lee `uv.lock` (committeado en el repo) y reproduce el entorno **exacto** — mismas versiones que la última vez que se actualizó el lock. Si alguien agrega o sube una dependencia: editar `pyproject.toml`, correr `uv lock` y commitear el `uv.lock` actualizado.

### Camino alternativo — pip (sin lock, deps resueltas en cada instalación)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -e ".[dev]"                # mock, sin SQL Server
pip install -e ".[dev,sqlserver]"      # con SQL Server real

cp .env.example .env
```

> Con pip las versiones se resuelven según los `>=` declarados en `pyproject.toml` — distintas máquinas pueden recibir versiones distintas. Para reproducibilidad usar `uv sync`.

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
API_PORT=8765
LOG_LEVEL=INFO

LOTE_WORKERS=2              # Lotes procesados en paralelo
PDF_WORKERS=-1              # -1=auto (todos los cores) | 0=secuencial
PDF_PARALLEL_THRESHOLD=100  # Mínimo de afiliados para activar Pool
```

> `.env` está en `.gitignore`. **Nunca lo commitees.**

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

1. Abrir `http://127.0.0.1:8765/` y loguearse.
2. Aterrizás en la pestaña **Inicio** con el dashboard de KPIs y actividad reciente.
3. Pestañas disponibles (en orden):
   - **Inicio** — dashboard cross-módulo
   - **Demanda Inducida**
   - **FINDRISC**
   - **Gestión Captación**
   - **Planificación Familiar**
4. Dentro de un módulo: clic en **Nueva extracción** → elegir rango de fechas → Generar.
5. La vista muestra en tiempo real el progreso de cada lote con su fase actual.
6. Al completar → explorar archivos del árbol o descargar el `.zip`.
6. (Opcional) Hacer doble clic en el nombre del job para asignarle un nombre custom → el `.zip` se descarga con ese nombre.

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
GET    /extractions/count?desde=&hasta=        Preview de registros antes de generar
POST   /extractions                            Crear extracción (202 Accepted)
GET    /extractions                            Listar extracciones
GET    /extractions/{id}                       Estado + métricas
GET    /extractions/{id}/lotes                 Lotes con fase en tiempo real
GET    /extractions/{id}/lotes/{n}/download    ZIP de un lote
GET    /extractions/{id}/download              Mega-ZIP (todos los lotes)
GET    /extractions/{id}/files                 Árbol de archivos
GET    /extractions/{id}/files/{doc}/{file}    PDF individual
POST   /extractions/{id}/cancel                Cancelar
DELETE /extractions/{id}                       Eliminar + borrar disco
```

### Módulo FINDRISC

Misma estructura bajo el prefijo `/findrisc/`:

```
GET    /findrisc/extractions/count?desde=&hasta=
POST   /findrisc/extractions
GET    /findrisc/extractions
GET    /findrisc/extractions/{id}
GET    /findrisc/extractions/{id}/lotes
GET    /findrisc/extractions/{id}/lotes/{n}/download
GET    /findrisc/extractions/{id}/download
GET    /findrisc/extractions/{id}/files
GET    /findrisc/extractions/{id}/files/{doc}/{file}
POST   /findrisc/extractions/{id}/cancel
PATCH  /findrisc/extractions/{id}/nombre
DELETE /findrisc/extractions/{id}
```

### Módulo Gestión Captación

Bajo el prefijo `/gestion-captacion/`. Mismos 11 endpoints que FINDRISC.

### Módulo Planificación Familiar

Bajo el prefijo `/planificacion-familiar/`. Mismos 11 endpoints que FINDRISC.

### Dashboard

```
GET    /api/dashboard/summary    KPIs cross-módulo + cards + actividad reciente
```

Devuelve JSON con `global`, `modulos` (4 módulos) y `recientes` (últimas 8 extracciones de cualquier módulo).

### Ejemplo: crear extracción

```bash
# FINDRISC
curl -X POST http://127.0.0.1:8765/findrisc/extractions \
  -H "Content-Type: application/json" \
  -d '{"desde": "2026-05-01", "hasta": "2026-05-31"}'

# Planificación Familiar
curl -X POST http://127.0.0.1:8765/planificacion-familiar/extractions \
  -H "Content-Type: application/json" \
  -d '{"desde": "2026-05-01", "hasta": "2026-05-31"}'

# Renombrar (para customizar el nombre del .zip al descargar)
curl -X PATCH http://127.0.0.1:8765/planificacion-familiar/extractions/{id}/nombre \
  -H "Content-Type: application/json" \
  -d '{"nombre": "Mi extracción mayo 2026"}'
```

### Estados de extracción y errores comunes

Estados posibles: `pending` · `running` · `completed` · `failed` · `cancelled`. Internamente se usan en inglés, pero los mensajes al usuario van en español (vía `estado_label()`):

| Estado | Etiqueta |
|---|---|
| `pending` | Pendiente |
| `running` | En curso |
| `completed` | Completado |
| `failed` | **Fallido** |
| `cancelled` | Cancelado |

`POST /extractions/{id}/cancel` solo funciona en estados `pending` o `running`. Devuelve `409` con mensaje en español si la extracción ya terminó.

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
curl http://127.0.0.1:8765/db/ping
```

---

## Estructura del proyecto

```
D:\proyecto\
├── pyproject.toml
├── .env / .env.example
├── README.md
├── tests/                              # Tests con pytest (ver sección Testing)
└── src/efdi/
    ├── main.py                         # FastAPI app — registra los 4 routers de módulos + dashboard
    ├── config.py                       # Settings desde .env
    ├── api/
    │   ├── routes.py                   # Endpoints Demanda Inducida (/extractions/...)
    │   ├── routes_findrisc.py          # Endpoints FINDRISC (/findrisc/extractions/...)
    │   ├── routes_captacion.py         # Endpoints Captación (/gestion-captacion/...)
    │   ├── routes_planfami.py          # Endpoints PlanFami (/planificacion-familiar/...)
    │   ├── routes_dashboard.py         # GET /api/dashboard/summary
    │   └── schemas.py                  # Request/response Pydantic
    ├── domain/
    │   ├── models.py                   # Atencion / Registros (FINDRISC, Captación, PlanFami)
    │   │                               # + Afiliado* / Extraccion / Lote / ExtraccionTipo
    │   │                               # + helpers: estado_label, safe_filename
    │   │                               # + constantes: CAPTACION_PROGRAMAS, PLANFAMI_FACTORES_CLINICOS
    │   └── services.py                 # agrupar_por_afiliado_* (uno por módulo)
    ├── infrastructure/
    │   ├── db.py                       # SQLite schema con migraciones
    │   ├── job_store.py                # Persistencia de extracciones y lotes
    │   ├── repository.py               # Consulta Demanda Inducida (SQL Server + mock)
    │   ├── repository_findrisc.py      # Consulta FINDRISC
    │   ├── repository_captacion.py     # Consulta Captación
    │   └── repository_planfami.py      # Consulta Planificación Familiar
    ├── pdf/
    │   ├── generator.py                # PDF Demanda Inducida — catálogo 124 programas
    │   ├── generator_findrisc.py       # PDF FINDRISC — formato SOPORTE ENCUESTAS
    │   ├── generator_captacion.py      # PDF Captación — grid 19 banderas de programas
    │   ├── generator_planfami.py       # PDF PlanFami — grid 13 FIC + bloques por seguimiento
    │   ├── parallel.py                 # Worker multiprocessing Demanda Inducida
    │   ├── parallel_findrisc.py        # Worker multiprocessing FINDRISC
    │   ├── parallel_captacion.py       # Worker multiprocessing Captación
    │   ├── parallel_planfami.py        # Worker multiprocessing PlanFami
    │   └── programas_catalogo.py       # Carga programas.txt (124 programas DI)
    ├── services/
    │   ├── extraction.py               # Orquestador Demanda Inducida
    │   ├── extraction_findrisc.py      # Orquestador FINDRISC
    │   ├── extraction_captacion.py     # Orquestador Captación
    │   └── extraction_planfami.py      # Orquestador PlanFami
    ├── templates/
    │   ├── logo.png                    # Logo Mutualser (usado en headers de los PDFs)
    │   └── programas.txt               # 124 códigos + descripciones de programas DI
    └── web/
        ├── index.html                  # SPA — pestañas: Inicio + 4 módulos
        ├── login.html                  # Pantalla de acceso (HMAC + cookie)
        └── siedfaser_logo.png          # Logo del producto
```

---

## Testing

El proyecto usa **pytest** con `pytest-asyncio` y un mock determinista para correr la suite sin depender de SQL Server.

### Correr toda la suite

```bash
pytest                 # suite completa
pytest -v              # verboso
pytest -k "agrupa"     # solo tests cuyo nombre contiene "agrupa"
pytest --tb=short      # tracebacks compactos
```

Configuración en `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"     # tests async se marcan automáticamente
```

### Tests existentes (17)

| Archivo | Tests | Qué cubre |
|---|---|---|
| `tests/test_agrupacion.py` | 1 | `agrupar_por_afiliado` colapsa atenciones por `(documento, fecha)` correctamente. |
| `tests/test_api.py` | 8 | Endpoints HTTP de Demanda Inducida via `TestClient`: `/health`, `/docs`, flow completo (crear → consultar → descargar → eliminar), multi-lote, errores 400/404, lote inexistente. |
| `tests/test_mock_data.py` | 5 | `MockRepository`: cantidad correcta, determinismo con misma semilla, fechas dentro del rango, atenciones por afiliado, OFFSET genera registros distintos. |
| `tests/test_pdf_parallel.py` | 3 | Generación paralela de PDFs: produce archivos, lista vacía → 0, 1 solo worker funciona. |

### Smoke tests rápidos sin pytest

Cuando vas a tocar un módulo, podés validar el camino completo `Mock → agrupador → PDF` con un one-liner. Por ejemplo, para Planificación Familiar:

```bash
python -c "
import sys; sys.path.insert(0, 'src')
from datetime import date; from pathlib import Path
from efdi.infrastructure.repository_planfami import MockPlanFamiRepository
from efdi.domain.services import agrupar_por_afiliado_planfami
from efdi.pdf.generator_planfami import generar_pdf_planfami

repo = MockPlanFamiRepository()
regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=10, offset=0)
afs = agrupar_por_afiliado_planfami(regs)
out = Path('preview.pdf').resolve()
generar_pdf_planfami(afs[0], out)
print('OK', out.stat().st_size, 'bytes')
"
```

Mismo patrón aplica para `repository_findrisc` / `repository_captacion` / `repository.py` cambiando los imports.

### Verificación del orquestador end-to-end

Para validar el flujo completo de extracción (incluyendo SQLite, paralelismo y empaquetado ZIP) con datos mock:

```bash
python -c "
import sys; sys.path.insert(0, 'src')
from uuid import uuid4
from datetime import datetime, date
from efdi.domain.models import Extraccion, ExtraccionTipo, ModoPdf
from efdi.services.extraction_planfami import ejecutar_extraccion_planfami

job = Extraccion(id=uuid4(), desde=date(2026, 5, 1), hasta=date(2026, 5, 31),
                 limite=50, tamano_lote=25, tipo=ExtraccionTipo.PLANIFICACION_FAMILIAR,
                 modo_pdf=ModoPdf.UNO_POR_ATENCION, creado_en=datetime.now())
ejecutar_extraccion_planfami(job)
print('Estado:', job.estado, 'PDFs:', job.total_pdfs, 'Lotes:', job.total_lotes)
"
```

Esperado: `Estado: completed PDFs: ~50 Lotes: 2`. Requiere `USE_MOCK=true` en `.env`.

### Tests pendientes (deuda técnica)

Los tests actuales cubren bien Demanda Inducida pero **no** los 3 módulos nuevos (FINDRISC, Captación, PlanFami). A mediano plazo conviene replicar `test_api.py` y `test_mock_data.py` para cada uno:

```
tests/
├── test_findrisc_api.py        # pendiente
├── test_findrisc_mock.py       # pendiente
├── test_captacion_api.py       # pendiente
├── test_captacion_mock.py      # pendiente
├── test_planfami_api.py        # pendiente
└── test_planfami_mock.py       # pendiente
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
curl -I http://127.0.0.1:8765/
# Debe responder HTTP 200 text/html
```

**Migración de base de datos:** Al actualizar desde versiones anteriores, la BD SQLite se migra automáticamente al arrancar. El schema actual es v3 (añade `lotes.fase` y `extracciones.tipo`).

**Una extracción falla con error SQL:**
1. Mirá el job en la vista — al expandir, el `mensaje_error` muestra el detalle del fallo SQL Server.
2. Errores comunes:
   - `Invalid column name '…'` → la query SQL referencia una columna que no existe en SQL Server (typo o columna fue renombrada en la BD).
   - `The multi-part identifier "x.Y" could not be bound` → alias de tabla mal usado.
   - `Conversion failed when converting date and/or time` → revisar formato del filtro `fec_*`.
3. Para reproducir el SQL exacto, levantar el server con `LOG_LEVEL=DEBUG` y mirar `planfami.query`, `findrisc.query`, etc.

**"No se puede cancelar — la extracción está en estado 'Fallido'"**:
Comportamiento esperado: `cancel` solo aplica a jobs en `Pendiente` o `En curso`. Si el job ya falló o completó, usá el botón de **eliminar** (🗑) en el sidebar para borrarlo del listado y limpiar el disco.

**El nombre custom no se aplica al `.zip` descargado:**
- Verificar que la extracción tenga `nombre` no vacío vía `GET /{modulo}/extractions/{id}`.
- Asignarlo con `PATCH /{modulo}/extractions/{id}/nombre` con `{"nombre": "..."}`.
- El nombre se sanitiza: chars inválidos para filesystem se reemplazan por `_`.

---

<div align="center">

**SIEDFASER** — desarrollado para Seragil
Sistema Inteligente de Exportación de Datos para Facturación

</div>
