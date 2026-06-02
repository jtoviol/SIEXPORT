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

Soporta múltiples módulos de extracción — cada módulo tiene su consulta, su modelo de dominio y su plantilla de PDF.

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

1. Abrir `http://127.0.0.1:8765/`
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
DELETE /findrisc/extractions/{id}
```

### Ejemplo: crear extracción FINDRISC

```bash
curl -X POST http://127.0.0.1:8765/findrisc/extractions \
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
curl http://127.0.0.1:8765/db/ping
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
    │   ├── repository.py               # Consulta Demanda Inducida (SQL Server + mock)
    │   └── repository_findrisc.py      # Consulta FINDRISC (SQL Server + mock)
    ├── pdf/
    │   ├── generator.py                # PDF Demanda Inducida — catálogo 124 programas
    │   ├── generator_findrisc.py       # PDF FINDRISC — formato SOPORTE ENCUESTAS, fiel a la BD
    │   ├── parallel.py                 # Worker multiprocessing Demanda Inducida
    │   ├── parallel_findrisc.py        # Worker multiprocessing FINDRISC
    │   └── programas_catalogo.py       # Carga programas.txt (124 programas)
    ├── services/
    │   ├── extraction.py               # Orquestador Demanda Inducida
    │   └── extraction_findrisc.py      # Orquestador FINDRISC
    ├── templates/
    │   ├── logo.png
    │   └── programas.txt               # 124 códigos + descripciones de programas DI
    └── web/
        ├── index.html                  # SPA — pestañas por módulo, progreso en tiempo real
        ├── login.html                  # Pantalla de acceso (HMAC + cookie)
        └── siedfaser_logo.png          # Logo oficial
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

---

<div align="center">

**SIEDFASER** — desarrollado para Seragil
Sistema Inteligente de Exportación de Datos para Facturación

</div>
