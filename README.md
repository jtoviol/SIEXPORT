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
[![Multi-module](https://img.shields.io/badge/m%C3%B3dulos-7-1a2f6e?style=flat-square)](#módulos-disponibles)
[![Persistence](https://img.shields.io/badge/persistencia-SQLite%20WAL-234674?style=flat-square)](#stack)
[![Concurrency](https://img.shields.io/badge/concurrencia-Pool%20%2B%20Threads-22a84a?style=flat-square)](#procesamiento-por-lotes)
[![Auth](https://img.shields.io/badge/auth-RBAC%20multi--user-234674?style=flat-square)](#autenticación-y-roles)

<br/>

</div>

---

## Resumen

**SIEDFASER** es una plataforma web para extracción y empaquetado masivo de datos clínicos de la base **Seragil** (SQL Server) con destino a facturación. Cada extracción agrupa los registros por afiliado y entrega un `.zip` con un PDF por paciente, listo para radicar como soporte de cuenta médica.

**7 módulos activos** — cada uno con su consulta SQL, su modelo de dominio y su plantilla de PDF:

| Módulo | Tabla origen | Filtro | API |
|---|---|---|---|---|
| Demanda Inducida | `AVS_REGISTRO_SERAGIL` + `AVS_PROGRAMA_ASOCIADO_DEMIND` | `FLG_REGIND_DEMIND = 'SI'` + rango fechas | `/extractions/...` |
| FINDRISC | `SRG_FORMATO_FINDRISC` | `FLG_FORMATO_COLDRISC = 'SI'` + rango fechas | `/findrisc/...` |
| Gestión Captación | `srg_captacion_afiliados` | rango `fec_captacion_afiliado` | `/gestion-captacion/...` |
| Planificación Familiar | `SRG_POBLACION_RIESGO_REPRODUCTIVO` + `SRG_DETALLE_RIESGO_REPRODUCTIVO` | rango `fec_gestion_seguimiento` | `/planificacion-familiar/...` |
| Vacunación | `AVS_REGISTRO_SERAGIL` + `AVS_PROGRAMA_ASOCIADO_DEMIND` (códigos de programa de vacunación) | rango fechas + régimen — sin factura | `/vacunacion/...` |
| Caracterización Familiar | `SBW_PERSONA_CARACTERIZADA` + `SBW_UBICACION_FAMILIA` (**base sibacom**, servidor aparte) | rango `fecha_reg` — sin factura | `/caracterizacion-familiar/...` |
| Educación Grupal | `SRG_EDUCACION_GRUPAL` + `SRG_ASISTENTE_EDUCACION_GRUPAL` | rango `fec_educacion_grupal` — sin factura | `/educacion-grupal/...` |

> Caracterización Familiar agrupa **por familia** (jerarquía geográfica + vivienda + familia + ciuf): 1 PDF por familia con todos sus integrantes. Requiere las variables `DB_*_SIBACOM` en el `.env`.

> Educación Grupal agrupa **por afiliado** (1 PDF por persona con todas las sesiones educativas a las que asistió). Sin factura. Sin Excel.

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

Además de estos acentos de marca, **cada módulo tiene su propio color de identificación** (campo `color` en el registry `MODULES` de `index.html`) usado en badges, bordes de hover de las cards y el ícono del sidebar: `brand` (Demanda Inducida), `emerald` (FINDRISC), `amber` (Gestión Captación), `rose` (Planificación Familiar), `cyan` (Vacunación), `indigo` (Caracterización Familiar), `violet` (Pruebas Rápidas), `teal` (Educación Grupal), `slate` (Soporte Unificado — color neutro, por ser un módulo transversal). Es una decisión de diseño intencional para distinguir módulos a simple vista, no una inconsistencia.

---

## Política de fidelidad a la BD

Para **FINDRISC**, **Captación**, **Planificación Familiar** y **Caracterización Familiar** el PDF imprime los datos **literales** de la BD. No calcula, no clasifica, no infiere:

- Los rangos / puntajes desglosados que mostraba antes FINDRISC se eliminaron porque eran cálculos en Python — solo se muestra el `Puntaje total` que ya viene calculado de la BD.
- Las banderas (`SI` / vacío / `1` / `0`…) se interpretan estrictamente: `"SI"` → recuadro verde, cualquier otra cosa → no marcado. Excepto en Captación y PlanFami, donde **cualquier valor no vacío** se considera marcado (porque la SQL ya las normaliza con `CASE WHEN ... THEN 'SI' ELSE '' END`).
- Los decimales con coma (`"1,72"`) se almacenan como string para no perder el formato del dato original.
- En **Caracterización Familiar** todos los códigos se resuelven a su descripción legible vía LEFT JOIN con catálogos (`AVS_DEPARTAMENTO_SALUD`, `AVS_MUNICIPIO_SALUD`, `parentes`, `AVS_OCUPACION_INGRESO`, `etnia`, `programas`, `SBW_TIPO_DISCAPACIDAD`, `AVS_TIPO_FAMILIA`, `SBW_TIPO_REGIMEN_SGSSS`). Teléfonos `-1` o vacíos se normalizan a `N/A` en el SQL.

Demanda Inducida es distinto: tiene un catálogo fijo de 124 programas, y el PDF resalta los que la persona tiene asignados.

**Vacunación** reutiliza la misma consulta base de Demanda Inducida, acotada a los códigos de programa de vacunación (`COD_PROGRAMA_DEMIND IN (...)`, esquema regular + COVID-19) y filtrada por régimen — igual que Captación/Educación Grupal, sin factura.

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

### Vacunación

Consulta `AVS_REGISTRO_SERAGIL` + `AVS_PROGRAMA_ASOCIADO_DEMIND`, acotada a los códigos de programa de vacunación (esquema regular + COVID-19), igual que Demanda Inducida pero con otro filtro de programas. Agrupa por afiliado (1 PDF por persona = carné de vacunas, no 1 por fecha) y empaqueta el ZIP.

- Filtro principal: **rango de fechas + régimen** (`AVS_AFILIADO_MUTUALSER_HIS.AFIC_REGIMEN`) — mismo patrón que Educación Grupal/Gestión Captación. El usuario solo elige régimen y fechas, no sube nada.
- Sin factura (porque no cruza con `AVS_REGISTROS_AP`).
- 1 PDF por persona con **todas sus vacunas** del rango (formato carné).

**Fuente:** SQL Server, filtro por fecha + régimen (sin Excel, sin factura).
**API:** `/vacunacion/...`

### Caracterización Familiar

Apunta a la base **`sibacom`** (servidor distinto: `DB_*_SIBACOM` en `.env`), no a Seragil. Genera **1 PDF por familia** con todos sus integrantes — no 1 por afiliado como los otros módulos.

**Diferencias estructurales respecto al resto:**

- **Unidad de agrupación = familia.** Llave: jerarquía geográfica completa (`codniv1..6` + `codvivi` + `codfami` + `ciuf`). Cada PDF muestra el área geográfica + ubicación + un bloque INTEGRANTE #N DE M por cada persona.
- **Paginación por familia con `DENSE_RANK`:** cada lote trae familias completas. Una familia nunca queda partida entre dos lotes (evita PDFs parciales/duplicados).
- **Sin factura.** No cruza contra `AVS_REGISTROS_AP`.
- **Filtro de régimen "del jefe":** el régimen vive a nivel persona (`PC.tipousua`). Para poder generar lotes SUB/CONT separados (como los otros módulos), se aplica una regla de negocio: **el régimen de la familia entera es el del JEFE DE FAMILIA** (persona con `parentes='1'`). El resto de integrantes se ignoran para esta decisión.
  - Si hay **varios jefes** en la misma familia (vivienda extensa): gana el de menor `uid` (orden natural BD).
  - Si **no hay ningún jefe**: cae al primer integrante por `uid`.
  - Si el jefe tiene régimen distinto de S/C (`N`=POBRE NO ASEGURADO, `O`=ESPECIAL, `P`=PARTICULAR): la familia queda fuera de ambos lotes.
- **Catálogos resueltos en SQL:** departamento, municipio (vía `codniv1+codniv2`), área (`U`→URBANA), parentesco, ocupación, régimen, EPS/institución, etnia, programa, discapacidad, tipo de familia (`AVS_TIPO_FAMILIA`: NUCLEAR / EXTENSA / MONOPARENTAL). Teléfonos vacíos o `-1` → `N/A`.
- **Orden interno:** dentro de cada familia los integrantes salen ordenados con el **JEFE DE FAMILIA primero**, después cónyuge, hijos…

**Filtro fuente:** rango de `UF.fecha_reg`. Opcional `regimen` (SUBSIDIADO/CONTRIBUTIVO) que filtra familias por el régimen del jefe.
**API:** `/caracterizacion-familiar/...`

### Educación Grupal

Extrae sesiones educativas grupales de `SRG_EDUCACION_GRUPAL` + asistentes de `SRG_ASISTENTE_EDUCACION_GRUPAL`, cruzando con `AVS_AFILIADO_MUTUALSER_HIS` para obtener los datos del afiliado. Genera **1 PDF por afiliado** con todas las sesiones a las que asistió (formato "SOPORTE EDUCACIÓN GRUPAL"):

- **Header**: logo Mutualser + título centrado en azul institucional.
- **Datos del afiliado**: documento, nombre, total de sesiones asistidas.
- **Tabla de sesiones educativas**: # consecutivo, fecha, curso de vida, eje temático, modalidad (PRESENCIAL / VIRTUAL / OTROS), facilitador, ubicación (depto / municipio).
- **Total de sesiones** al pie de la tabla.

```
lote_001.zip
├── CC_12345678/
│   └── CC_12345678_2026-05-15.pdf
├── TI_98765432/
│   └── TI_98765432_2026-05-10.pdf
└── …
```

**Filtro fuente:** rango de `a.fec_educacion_grupal`. Opcional `regimen` (SUBSIDIADO/CONTRIBUTIVO) que filtra por `h.AFIC_REGIMEN`.
**API:** `/educacion-grupal/extractions/...`

---

### Soporte Unificado

Módulo **transversal**: no tiene query ni generador propios. Orquesta los 8 módulos de arriba y reorganiza la salida **por afiliado** en vez de por módulo — una carpeta por documento, con un PDF adentro por cada módulo donde esa persona tenga soportes.

```
lote_001.zip
├── CC_12345678/
│   ├── demanda_inducida_2026-05-15.pdf
│   ├── findrisc_2026-05-10.pdf
│   └── vacunacion.pdf
├── FAM_13|001|1|00|002|03|0001|1|100001/   ← familia sin ningún documento (ver abajo)
│   └── caracterizacion_familiar.pdf
└── …
```

**Universo** = unión de los 8 módulos: una persona entra al índice si aparece en **cualquiera** de ellos. El total de personas **nunca es la suma** de los conteos individuales — si alguien tiene soporte en 2 módulos, ahí cuenta 1 vez (deduplicado), mientras que cada módulo por separado la cuenta 1 vez cada uno. El endpoint de conteo previo lo advierte explícitamente (`"nota"` en la respuesta).

**Filtro según el grupo de módulo** (fecha siempre obligatoria; régimen siempre obligatorio — corrida separada por régimen, igual que los demás módulos):
- **Facturables** (Demanda Inducida, FINDRISC, Planificación Familiar, Pruebas Rápidas): el `regimen` del formulario **no los filtra** (sus repos ni siquiera reciben ese parámetro) — lo único que los filtra es el `numero_factura`, opcional. **Sin factura**: traen su universo **completo** del rango de fechas, mezclando ambos regímenes. **Con factura**: se filtran por `EXISTS ... NRO_FACTURA IN (CAB<n>, FAB<n>)` contra `AVS_REGISTROS_AP` — ambos prefijos siempre, sin importar qué régimen se eligió en el formulario (CAB y FAB son los dos lotes de facturación de una misma factura, uno por régimen).
- **Régimen simple** (Gestión Captación, Educación Grupal, Vacunación) y **Caracterización Familiar**: solo fecha + régimen, nunca factura. Vacunación entra automáticamente por consulta SQL — no requiere ningún upload.

**Caracterización Familiar se ancla al JEFE DE FAMILIA** (mismo criterio que el módulo individual): si nadie tiene parentesco "JEFE DE FAMILIA" explícito, cae al primer integrante con documento; si **nadie** en la familia tiene documento, la familia **igual se incluye**, bajo la carpeta `FAM_<clave_familia>` — idéntico al fallback que ya usa el módulo standalone. (Antes de corregirse, esas familias se descartaban en silencio del unificado, dando un conteo menor al de Caracterización Familiar individual sin que fuera por la deduplicación esperada.)

**API:** `/soporte-unificado/extractions/...`, `/soporte-unificado/extractions/count` (preview con desglose `por_modulo`).

**Permisos:** usa el mismo sistema de roles/módulos que el resto (`"soporte-unificado"` en `MODULOS_VALIDOS`) — un administrador debe habilitarlo explícitamente por usuario desde la gestión de usuarios, igual que cualquier otro módulo.

#### Ajustar Soportes — fusionar en un solo PDF por afiliado

Sobre un job de Soporte Unificado **ya completado**, el botón **"Ajustar soportes"** (panel derecho de detalle) dispara un segundo job que toma todos los PDF sueltos de cada afiliado y los fusiona en **un solo PDF**, renombrado para facturación:

```
HEV_900422757_<FACTURA>_<TIPODOC><NUMERODOC>.pdf
```

Reemplaza el uso manual de un script externo (`unificar_soportes.py`) que corría por fuera del sistema sobre los ZIP ya descargados — acá opera directo sobre los archivos que el propio backend generó, sin descargar ni descomprimir nada.

- **Régimen**: no se pide — se hereda del job de origen (ya es fijo y obligatorio desde que se creó el Soporte Unificado).
- **Factura**: se pide en el momento (pre-llenada con la del job de origen si tenía una, pero siempre editable — cambia cada mes).
- **Identificador de afiliado**: se valida con el mismo criterio `^[A-Za-z]+_\d+$` sobre el `doc_key` que ya arma el sistema — excluye automáticamente carpetas `FAM_<clave>` (familias de Caracterización sin ningún integrante con documento) y documentos con número no puramente numérico (ej. menores sin documento propio, tipo `MS`). Nunca se pierde un afiliado en silencio: todo excluido queda en el resumen.
- **PDF fuente corrupto/ilegible**: se salta ese archivo puntual y sigue con los demás del mismo afiliado; si *todos* los PDF de un afiliado fallan, no se genera nada para él (también reportado).
- **Orden de fusión**: alfabético por nombre de archivo dentro de la carpeta del afiliado — como cada PDF ya se llama `<modulo>_<fecha_iso>.pdf` o `<modulo>.pdf`, esto agrupa por módulo y, dentro del mismo módulo, cronológicamente.
- **Salida**: `job_<id>/lote_NNN/<REGIMEN>/HEV_900422757_<factura>_<tipo><numero>.pdf`, empaquetada en ZIP por lote igual que cualquier otro job — mismos endpoints de descarga (`/download`, `/files`, etc.) que Soporte Unificado, porque comparten tipo de almacenamiento.
- **Resumen**: al completarse, el panel de detalle muestra PDF generados, páginas totales, excluidos por identificador (con ejemplos) y PDFs fuente con error de lectura — guardado en el campo `resumen_json` del job.

**API:** `POST /soporte-unificado/extractions/{job_id}/ajuste-soportes` con `{"numero_factura": "..."}` — crea un job `tipo=ajuste_soportes` enlazado al `origen_job_id`. El resto de endpoints (`/{id}`, `/lotes`, `/download`, `/files`, etc.) son los mismos de Soporte Unificado — aceptan ambos tipos indistintamente.

**Pendiente (deuda técnica):** no se replica la verificación "misma persona en los 2 regímenes" que sí hacía el script externo (exigiría comparar contra OTRO job de régimen distinto — fuera de alcance de esta fase).

---

## Vista de Inicio (Dashboard)

Al loguearte aterrizás en la pestaña **Inicio** (no en un módulo específico). Muestra:

- **4 KPIs grandes**: PDFs generados hoy / últimos 7 días / último mes y afiliados procesados último mes.
- **7 cards por módulo** (DI, FINDRISC, Captación, Planificación Familiar, Vacunación, Caracterización Familiar, Educación Grupal) con: en curso · completados · fallidos · timestamp de la última extracción. Click → cambia a esa pestaña.
- **Actividad reciente**: lista de las 8 últimas extracciones de cualquier módulo con badge del módulo, estado coloreado y nº de PDFs. Click → abre el job en su módulo.

Mientras trabajás en cualquier módulo, una **franja de chips** queda visible arriba con: `N en curso · M fallidas 24h · X PDFs hoy · Y PDFs mes · Modo: SQL Server/MOCK`. Se refresca cada 15s.

**Filtro automático por permisos:** las cards de módulos a los que tu usuario no tiene acceso (RBAC, ver siguiente sección) se ocultan del dashboard, del sidebar y del Cmd+K.

**Endpoint:** `GET /api/dashboard/summary` (autenticado).

---

## Autenticación y roles

Multi-user con bcrypt + RBAC, cookie HMAC stateless (compatible con `--workers N` sin necesidad de Redis):

- **Bootstrap automático**: en el primer arranque, si la tabla `users` está vacía, se crea un admin con las credenciales del `.env` (`AUTH_USER` / `AUTH_PASSWORD`). A partir de ahí, el `.env` queda como referencia: todos los logins van contra DB con bcrypt.
- **3 roles predefinidos**:
  - `ADMIN` — todo, incluyendo CRUD de usuarios.
  - `OPERADOR` — puede generar / cancelar / borrar extracciones de los módulos asignados.
  - `VIEWER` — solo lectura: listar y descargar, no generar.
- **Permisos por módulo:** cada usuario tiene una lista de módulos permitidos (`["demanda-inducida", "findrisc", ...]`). El backend rechaza con 403 si el usuario intenta acceder a un módulo fuera de su lista. El frontend filtra el sidebar/dashboard/Cmd+K según permisos.
- **Anti self-lockout:** el último admin activo no puede borrarse ni desactivarse a sí mismo.

**Endpoints:**

```
POST /auth/login                       Form (username, password) → cookie HMAC
POST /auth/logout                      Borra cookie

GET  /api/me                           Datos del usuario logueado
PUT  /api/me/password                  Cambiar mi password (verifica la actual)

GET    /api/users                      Listar usuarios (solo ADMIN)
POST   /api/users                      Crear usuario
GET    /api/users/{id}                 Detalle
PUT    /api/users/{id}                 Actualizar (rol, módulos, activo, …)
DELETE /api/users/{id}                 Eliminar
POST   /api/users/{id}/reset-password  Resetear password (sin verificar la actual)
GET    /api/users/_meta/modulos        Catálogo de módulos válidos (para UI)
```

**UI**: avatar con dropdown en el header → "Mi perfil" (todos), "Gestionar usuarios" (solo admin), "Cerrar sesión".

### Auditoría — "quién hizo qué"

Cada extracción guarda `created_by_username` (el usuario que disparó el POST) y la lista de jobs muestra **`… · por <usuario>`** en su detalle.

Los eventos críticos sobre usuarios se persisten en la tabla `audit_log`:

| Acción | Cuándo |
|---|---|
| `user.create` | ADMIN creó un usuario (incluye rol y módulos asignados) |
| `user.update` | ADMIN editó un usuario (incluye diff de los campos cambiados antes/después) |
| `user.delete` | ADMIN eliminó un usuario |
| `user.reset_password` | ADMIN reseteó la password de un usuario |
| `me.change_password` | Un usuario cambió su propia password (verificando la actual) |

**Endpoint** (solo ADMIN): `GET /api/users/_audit/log?limit=200&actor=admin&target_id=<uuid>`

Útil para responder "¿quién creó/borró/editó al usuario X?" y para cumplimiento (Habeas Data Colombia). Los registros incluyen `ts`, `actor_username`, `accion`, `target_type/id/label` y un `detalle` JSON con metadata extra (rol, módulos, cambios, etc.). El borrado de un usuario **no elimina** sus registros del audit log: el username se preserva como string histórico.

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
| **DB clínica** | pyodbc — SQL Server (Seragil) via ODBC Driver 17 |
| **DB caracterización** | pyodbc — SQL Server (sibacom, servidor aparte) |
| **Persistencia jobs/users** | SQLite WAL — sobrevive reinicios |
| **Auth** | bcrypt + cookie HMAC (multi-user, RBAC) |
| **Frontend** | HTML + Tailwind (compilado localmente) + Vanilla JS — SPA sin build step en runtime, sidebar lateral + Cmd+K palette |

---

### Regenerar el CSS de Tailwind

El frontend (`src/efdi/web/index.html`, `login.html`) **ya no** carga Tailwind desde `cdn.tailwindcss.com` (ese CDN compila en el navegador en cada carga — provoca un parpadeo sin estilos y depende de red externa; no apto para producción). En su lugar, el CSS se compila una sola vez a `src/efdi/web/dist/app.css` (estático, servido desde `/static/dist/app.css`) usando el **binario standalone de Tailwind CLI** (no requiere Node/npm).

Solo hace falta regenerarlo cuando se agregan clases Tailwind nuevas al HTML:

```bash
# 1. Descargar el binario standalone (una vez; Windows x64 — ver releases de
#    tailwindlabs/tailwindcss para otras plataformas)
curl -sL -o tailwindcss.exe https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-windows-x64.exe

# 2. Compilar (desde la raíz del repo)
./tailwindcss.exe -i src/efdi/web/tailwind-input.css -o src/efdi/web/dist/app.css --minify
```

`src/efdi/web/tailwind-input.css` define la paleta `brand` (antes vivía en un `tailwind.config` inline del CDN) y un **safelist** (`@source inline(...)`) para las pocas clases que el HTML arma dinámicamente en JS (ej. `bg-${m.color}-100`, que el escaneo estático no puede detectar como texto literal). Si se agrega un color de módulo nuevo a `MODULES` en `index.html`, hay que agregar sus shades al safelist de `tailwind-input.css` también.

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

> ⚠️ **`USE_MOCK` define el modo de operación**:
> - **`USE_MOCK=false`** → **PRODUCCIÓN**. Consulta el SQL Server real (Seragil + sibacom). Es el modo del despliegue.
> - **`USE_MOCK=true`** → **DESARROLLO**. Usa datos ficticios deterministas. NO toca SQL Server. Útil para correr la suite de tests, desarrollar la UI y demos sin VPN.

```bash
USE_MOCK=false              # false=SQL Server real (producción) | true=datos ficticios (dev)

# ── SQL Server Seragil (módulos DI, FINDRISC, Captación, PlanFami) ──
DB_HOST=10.244.21.11
DB_PORT=1433
DB_NAME=seragil
DB_USER=sa
DB_PASSWORD=tu-password
DB_DRIVER=ODBC Driver 17 for SQL Server

# ── SQL Server sibacom (solo módulo Caracterización Familiar) ──
DB_HOST_SIBACOM=10.244.21.13
DB_PORT_SIBACOM=1433
DB_NAME_SIBACOM=sibacom
DB_USER_SIBACOM=usuario
DB_PASSWORD_SIBACOM=tu-password

DATA_DIR=./data             # Directorio de salida de ZIPs y PDFs (y SQLite efdi.db)
API_HOST=0.0.0.0
API_PORT=8765
LOG_LEVEL=INFO

LOTE_WORKERS=2              # Lotes procesados en paralelo
PDF_WORKERS=-1              # -1=auto (todos los cores) | 0=secuencial
PDF_PARALLEL_THRESHOLD=100  # Mínimo de afiliados para activar Pool

# ── Auth: solo se usa para BOOTSTRAP del primer admin si users está vacía ──
AUTH_USER=admin
AUTH_PASSWORD=cambiar-en-prod
AUTH_SECRET=                # opcional; si vacío se deriva del user+password
```

> `.env` está en `.gitignore`. **Nunca lo commitees.**

> Una vez creado el primer admin (bootstrap automático al arrancar con la tabla `users` vacía), el `.env` queda como referencia. Cambiar `AUTH_PASSWORD` en `.env` ya **no** cambia la password del admin — eso se hace desde la UI (Mi perfil → cambiar password) o vía `POST /api/users/{id}/reset-password`.

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
3. **Navegación**: sidebar lateral a la izquierda agrupado por categorías (Prevención, Tamizajes, Seguimiento, Caracterización). Atajo `Ctrl+K` / `Cmd+K` abre un buscador rápido.
4. Módulos disponibles (filtrados según los permisos de tu usuario):
   - **Inicio** — dashboard cross-módulo
   - **Demanda Inducida**
   - **FINDRISC**
   - **Gestión Captación**
   - **Planificación Familiar**
   - **Vacunación** — SQL, filtro por fecha + régimen (sin factura)
   - **Caracterización Familiar** — sibacom, 1 PDF por familia
   - **Educación Grupal** — sesiones educativas grupales
5. Dentro de un módulo: clic en **Nueva extracción** → elegir rango de fechas → (opcional) régimen → Generar.
6. La vista muestra en tiempo real el progreso de cada lote con su fase actual.
7. Al completar → explorar archivos del árbol o descargar el `.zip`.
8. (Opcional) Hacer doble clic en el nombre del job para asignarle un nombre custom → el `.zip` se descarga con ese nombre.

El badge superior derecho indica si la conexión es **SQL Server** o **Mock**.

**Filtros de régimen — 2 modos según el módulo:**

| Módulos | Modo | Cómo se ve |
|---|---|---|
| DI, FINDRISC, Captación, PlanFami | Inputs CAB/FAB **requeridos** | Cruza contra `AVS_REGISTROS_AP`. El usuario ingresa el sufijo del código (ej. `11502`) y el backend arma `CAB11502` + `FAB11502`. Genera 1 o 2 jobs (uno por cada régimen ingresado). |
| Caracterización Familiar | Checkboxes SUB/CONT **opcionales** | No usa factura. Filtra familias por el régimen del **JEFE DE FAMILIA** (ver sección del módulo). Sin marcar nada → trae el universo completo. |
| Educación Grupal | Checkboxes SUB/CONT **opcionales** | Filtra sesiones por régimen del afiliado (`h.AFIC_REGIMEN`). Sin marcar nada → trae el universo completo. |
| Vacunación | Checkboxes SUB/CONT **opcionales** | Filtra por régimen del afiliado (`AFIC_REGIMEN`), igual que Educación Grupal. Sin marcar nada → trae el universo completo. |

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

### Módulo Vacunación

Bajo el prefijo `/vacunacion/`. Mismos 11 endpoints que Educación Grupal. El `count` y `POST extractions` aceptan opcionalmente `regimen=SUBSIDIADO|CONTRIBUTIVO` que filtra por `AFIC_REGIMEN`.

```bash
# Conteo previo filtrado por régimen
curl -b cookie.txt "http://127.0.0.1:8765/vacunacion/extractions/count?desde=2026-05-01&hasta=2026-05-31&regimen=SUBSIDIADO"
# → {"total_en_db":...,"limite_efectivo":...,"tamano_lote":...}

# Crear extracción solo de vacunación subsidiada
curl -X POST -b cookie.txt \
  -H "Content-Type: application/json" \
  -d '{"desde":"2026-05-01","hasta":"2026-05-31","regimen":"SUBSIDIADO"}' \
  http://127.0.0.1:8765/vacunacion/extractions
```

### Módulo Caracterización Familiar

Bajo el prefijo `/caracterizacion-familiar/`. Mismos 11 endpoints que FINDRISC. El `count` y `POST extractions` aceptan opcionalmente `regimen=SUBSIDIADO|CONTRIBUTIVO` que filtra familias por régimen del JEFE DE FAMILIA.

```bash
# Conteo previo filtrado por régimen del jefe
curl -b cookie.txt "http://127.0.0.1:8765/caracterizacion-familiar/extractions/count?desde=2026-05-01&hasta=2026-05-31&regimen=SUBSIDIADO"
# → {"total_en_db":2336,"limite_efectivo":2336,"tamano_lote":...}

# Crear extracción solo de familias contributivas
curl -X POST -b cookie.txt \
  -H "Content-Type: application/json" \
  -d '{"desde":"2026-05-01","hasta":"2026-05-31","regimen":"CONTRIBUTIVO"}' \
  http://127.0.0.1:8765/caracterizacion-familiar/extractions
```

### Módulo Educación Grupal

Bajo el prefijo `/educacion-grupal/`. Mismos 11 endpoints que FINDRISC. El `count` y `POST extractions` aceptan opcionalmente `regimen=SUBSIDIADO|CONTRIBUTIVO` que filtra por `h.AFIC_REGIMEN`.

```bash
# Conteo previo filtrado por régimen
curl -b cookie.txt "http://127.0.0.1:8765/educacion-grupal/extractions/count?desde=2026-05-01&hasta=2026-05-31&regimen=SUBSIDIADO"
# → {"total_en_db":1200,"limite_efectivo":1200,"tamano_lote":...}

# Crear extracción solo de sesiones educativas subsidiadas
curl -X POST -b cookie.txt \
  -H "Content-Type: application/json" \
  -d '{"desde":"2026-05-01","hasta":"2026-05-31","regimen":"SUBSIDIADO"}' \
  http://127.0.0.1:8765/educacion-grupal/extractions
```

### Módulo Soporte Unificado

Bajo el prefijo `/soporte-unificado/`. `regimen` es **obligatorio** (corrida separada por régimen); `numero_factura` es **opcional** (solo lo usan los módulos facturables dentro del universo). El conteo (`count`) devuelve además `por_modulo` (desglose) y `total_soportes` (cota superior de personas — ver nota de la respuesta).

```
GET    /soporte-unificado/extractions/count    Preview rápido por módulo, sin deduplicar
POST   /soporte-unificado/extractions          Crear (1 job por régimen)
GET    /soporte-unificado/extractions/...      Mismos endpoints de estado/lotes/descarga que los demás módulos
```

```bash
# Conteo previo: régimen obligatorio, sin factura (no incluye los facturables)
curl -b cookie.txt "http://127.0.0.1:8765/soporte-unificado/extractions/count?desde=2026-05-01&hasta=2026-05-31&regimen=SUBSIDIADO"
# → {"total_soportes":...,"por_modulo":[{"modulo":"gestion-captacion","label":"Gestión Captación","soportes":...}, ...],
#    "nota":"El total es cota superior de personas distintas; el número exacto se sabe al correr."}

# Crear extracción incluyendo los módulos facturables (con factura) + Vacunación (automática, por régimen+fecha)
curl -X POST -b cookie.txt \
  -H "Content-Type: application/json" \
  -d '{"desde":"2026-05-01","hasta":"2026-05-31","regimen":"SUBSIDIADO","numero_factura":"11502"}' \
  http://127.0.0.1:8765/soporte-unificado/extractions

# Ajustar Soportes: fusionar los PDFs de un Soporte Unificado YA COMPLETADO
# (régimen se hereda del job de origen, no se pide de nuevo)
curl -X POST -b cookie.txt \
  -H "Content-Type: application/json" \
  -d '{"numero_factura":"11502"}' \
  http://127.0.0.1:8765/soporte-unificado/extractions/<job_id_del_soporte_unificado>/ajuste-soportes
# → 202, nuevo job con tipo "ajuste_soportes" y origen_job_id=<job_id_del_soporte_unificado>
# Al completarse, GET .../extractions/{nuevo_id} trae resumen_json con el detalle
# (generados, excluidos_identificador, pdfs_fuente_error, paginas_totales, etc.)
```

### Autenticación / Usuarios

```
POST   /auth/login                              Form login → cookie HMAC
POST   /auth/logout                             Borra cookie

GET    /api/me                                  Mi perfil
PUT    /api/me/password                         Cambiar mi password

GET    /api/users                               Listar (ADMIN)
POST   /api/users                               Crear (ADMIN)
GET    /api/users/{id}                          Detalle (ADMIN)
PUT    /api/users/{id}                          Actualizar (ADMIN)
DELETE /api/users/{id}                          Eliminar (ADMIN)
POST   /api/users/{id}/reset-password           Resetear password (ADMIN)
GET    /api/users/_meta/modulos                 Catálogo módulos válidos
GET    /api/users/_audit/log                    Audit log de eventos críticos
```

### Dashboard

```
GET    /api/dashboard/summary    KPIs cross-módulo + cards + actividad reciente
```

Devuelve JSON con `global`, `modulos` (7 módulos) y `recientes` (últimas 8 extracciones de cualquier módulo).

### Ejemplo: crear extracción

```bash
# Primero login (guarda cookie para los siguientes curl)
curl -c cookie.txt -X POST -d "username=admin&password=Admin123123" \
  http://127.0.0.1:8765/auth/login

# FINDRISC con código de régimen
curl -b cookie.txt -X POST http://127.0.0.1:8765/findrisc/extractions \
  -H "Content-Type: application/json" \
  -d '{"desde":"2026-05-01","hasta":"2026-05-31","numero_factura":"11502","regimen":"SUBSIDIADO"}'

# Planificación Familiar
curl -b cookie.txt -X POST http://127.0.0.1:8765/planificacion-familiar/extractions \
  -H "Content-Type: application/json" \
  -d '{"desde":"2026-05-01","hasta":"2026-05-31","numero_factura":"11502","regimen":"CONTRIBUTIVO"}'

# Caracterización Familiar — sin factura, opcional régimen del JEFE
curl -b cookie.txt -X POST http://127.0.0.1:8765/caracterizacion-familiar/extractions \
  -H "Content-Type: application/json" \
  -d '{"desde":"2026-05-01","hasta":"2026-05-31","regimen":"SUBSIDIADO"}'

# Renombrar (para customizar el nombre del .zip al descargar)
curl -b cookie.txt -X PATCH http://127.0.0.1:8765/planificacion-familiar/extractions/{id}/nombre \
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
├── Dockerfile / docker-compose.yml     # Imagen siedfaser con ODBC Driver 17 preinstalado
├── tests/                              # Tests con pytest (ver sección Testing)
└── src/efdi/
    ├── main.py                         # FastAPI app — registra 8 routers + auth/users + dashboard
    ├── config.py                       # Settings desde .env (incluye DB_*_SIBACOM para Caracterización)
    ├── api/
    │   ├── dependencies.py             # Auth/RBAC: current_user, require_admin, require_modulo, …
    │   ├── routes.py                   # Endpoints Demanda Inducida (/extractions/...)
    │   ├── routes_findrisc.py          # Endpoints FINDRISC
    │   ├── routes_captacion.py         # Endpoints Captación
    │   ├── routes_planfami.py          # Endpoints PlanFami
    │   ├── routes_vacunacion.py        # Endpoints Vacunación (consulta SQL por régimen+fecha)
    │   ├── routes_caracterizacion.py   # Endpoints Caracterización Familiar (sibacom)
    │   ├── routes_educacion_grupal.py  # Endpoints Educación Grupal
    │   ├── routes_soporte_unificado.py # Endpoints Soporte Unificado (transversal, por afiliado)
    │   ├── routes_dashboard.py         # GET /api/dashboard/summary
    │   ├── routes_users.py             # /api/users — CRUD (solo ADMIN)
    │   ├── routes_me.py                # /api/me — perfil + cambiar password
    │   └── schemas.py                  # Request/response Pydantic (incluye User schemas)
    ├── domain/
    │   ├── models.py                   # Atencion / Registros (todos los módulos)
    │   │                               # + User / Rol / Extraccion / Lote / ExtraccionTipo
    │   │                               # + helpers: estado_label, safe_filename
    │   │                               # + constantes: CAPTACION_PROGRAMAS, PLANFAMI_FACTORES_CLINICOS,
    │   │                               #   MODULOS_VALIDOS, AFILIADO_*
    │   └── services.py                 # agrupar_por_afiliado_* / agrupar_por_familia_caracterizacion
    ├── infrastructure/
    │   ├── db.py                       # SQLite schema con migraciones (v7 — users + audit_log)
    │   ├── job_store.py                # Persistencia de extracciones y lotes
    │   ├── user_store.py               # Persistencia de usuarios (CRUD)
    │   ├── repository.py               # Consulta Demanda Inducida (SQL Server + mock)
    │   ├── repository_findrisc.py      # Consulta FINDRISC
    │   ├── repository_captacion.py     # Consulta Captación
    │   ├── repository_planfami.py      # Consulta Planificación Familiar
    │   ├── repository_vacunacion.py    # Consulta Vacunación (SQL Server, filtro régimen+fecha)
    │   ├── repository_educacion_grupal.py # Consulta SRG_EDUCACION_GRUPAL + asistentes
    │   └── repository_caracterizacion.py  # Consulta sibacom — paginación por familia + filtro régimen jefe
    ├── pdf/
    │   ├── generator.py                # PDF Demanda Inducida
    │   ├── generator_findrisc.py       # PDF FINDRISC
    │   ├── generator_captacion.py      # PDF Captación
    │   ├── generator_planfami.py       # PDF PlanFami
    │   ├── generator_vacunacion.py     # PDF Vacunación — carné por persona
    │   ├── generator_caracterizacion.py # PDF Caracterización Familiar — 1 por familia con N integrantes
    │   ├── generator_educacion_grupal.py # PDF Educación Grupal — 1 por afiliado con todas sus sesiones
    │   ├── parallel*.py                # Workers multiprocessing (uno por módulo)
    │   └── programas_catalogo.py       # Carga programas.txt (124 programas DI)
    ├── services/
    │   ├── extraction.py               # Orquestador Demanda Inducida
    │   ├── extraction_findrisc.py      # Orquestador FINDRISC
    │   ├── extraction_captacion.py     # Orquestador Captación
    │   ├── extraction_planfami.py      # Orquestador PlanFami
    │   ├── extraction_vacunacion.py    # Orquestador Vacunación
    │   ├── extraction_caracterizacion.py # Orquestador Caracterización Familiar
    │   ├── extraction_educacion_grupal.py # Orquestador Educación Grupal
    │   ├── extraction_soporte_unificado.py # Orquestador transversal: reindexa los 8 módulos por afiliado
    │   ├── extraction_ajuste_soportes.py # Fusiona los PDFs de un Soporte Unificado completado en 1 por afiliado
    │   └── auth_service.py             # bcrypt hash/verify + bootstrap admin + login
    ├── templates/
    │   ├── logo.png                    # Logo Mutualser (usado en headers de los PDFs)
    │   └── programas.txt               # 124 códigos + descripciones de programas DI
    └── web/
        ├── index.html                  # SPA — sidebar + 8 módulos + Cmd+K + modales de usuarios
        ├── login.html                  # Pantalla de acceso
        ├── tailwind-input.css          # Fuente del build de Tailwind (paleta brand + safelist)
        ├── dist/app.css                # CSS de Tailwind compilado (ver "Regenerar el CSS de Tailwind")
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

### Tests existentes

| Archivo | Qué cubre |
|---|---|
| `tests/conftest.py` | Setup global: apunta `DATA_DIR` a un tmp único por sesión antes de cualquier import de `efdi.*` (resuelve DB readonly heredada de Docker en WSL). |
| `tests/test_agrupacion.py` | `agrupar_por_afiliado` colapsa atenciones por `(documento, fecha)` correctamente. |
| `tests/test_api.py` | Endpoints HTTP de Demanda Inducida via `TestClient`: `/health`, `/docs`, flow completo (crear → consultar → descargar → eliminar), multi-lote, errores 400/404, lote inexistente. |
| `tests/test_facturas.py` | Cruce CAB+N/FAB+N de DI contra `AVS_REGISTROS_AP`. |
| `tests/test_mock_data.py` | `MockRepository`: cantidad correcta, determinismo, fechas dentro del rango, OFFSET. |
| `tests/test_pdf_parallel.py` | Generación paralela de PDFs (multiprocessing Pool). |
| `tests/test_caracterizacion.py` (8) | Mock de Caracterización Familiar: paginación por familia con `DENSE_RANK`, filtro por régimen del JEFE, generación de PDF, agrupación intacta entre lotes. |
| `tests/test_findrisc.py` (6) | Mock FINDRISC: cantidad, determinismo, offset, agrupación, generación PDF, filtro facturas. |
| `tests/test_planfami.py` (5) | Mock PlanFami: cantidad, determinismo, agrupación por `(doc, fecha_gestion)`, PDF con `regimen_override`. |
| `tests/test_auth_rbac.py` (23) | **Críticos del sistema multi-user**: bcrypt hash/verify, bootstrap admin con creds del `.env`, login válido/inválido, `GET /api/me` sin auth → 401, RBAC por módulo (403 sin permiso), viewer no puede POST, no-admin no puede `/api/users`, anti self-lockout del último admin, cambio password / reset password, password < 8 chars → 422, audit log captura `user.create` / `user.delete` y es admin-only. |
| `tests/test_soporte_unificado.py` (5) | `_jefe_doc_key` ancla cada familia de Caracterización al mismo `doc_key` que usaría el módulo standalone, **incluyendo el caso de familias sin ningún integrante con documento** (antes se perdían del índice unificado en silencio; ahora usan el fallback `FAM_<clave>`). |
| `tests/test_ajuste_soportes.py` (13) | Ajuste de Soportes: validación de identificador (`CC_...` válido, `FAM_...`/`MS_<alfanumérico>` excluidos), nombre de archivo final, fusión de PDFs con manejo de corruptos (se salta uno, sigue con el resto; si todos fallan no se escribe nada), y `recolectar_afiliados` separando válidos de excluidos sobre una estructura de carpetas real. |
| `tests/test_vacunacion.py` (6) | Mock Vacunación (SQL por régimen+fecha, sin Excel): cantidad, determinismo, filtro por régimen, `get_total` con/sin régimen, agrupación por `doc_key` (1 carné por persona, sin separar por fecha), generación de PDF. |

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

Cobertura actual buena en: DI, FINDRISC, PlanFami, Caracterización, auth/RBAC. Faltan tests propios de:

```
tests/
├── test_captacion.py           # pendiente (smoke como findrisc/planfami)
└── test_educacion_grupal.py    # pendiente (smoke + filtro régimen)
```

`tests/test_soporte_unificado.py` cubre el bug de datos corregido (familias sin
documento) a nivel unitario, pero **falta** cobertura de integración más amplia:
- Endpoints de `routes_soporte_unificado.py` (count/crear/estado) via `TestClient`.
- Comparar, con datos mock, `personas_por_modulo`/`soportes_por_modulo` del
  unificado contra el `get_total()` individual de cada uno de los 8 módulos con
  el mismo filtro — para detectar a futuro si un cambio en cualquier repositorio
  rompe el unificado en silencio.
- `CrearSoporteUnificadoReq` con `numero_factura` ausente (ya es opcional).

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

**Migración de base de datos:** Al actualizar desde versiones anteriores, la BD SQLite se migra automáticamente al arrancar. El schema actual es **v7**:

| Versión | Cambio |
|---|---|
| v2 | `lotes.fase` (texto de la fase actual) |
| v3 | `extracciones.tipo` (qué módulo generó el job) |
| v4 | `extracciones.nombre` (nombre custom del job) |
| v5 | `extracciones.regimen` + `extracciones.facturas` (cruce CAB/FAB Fase 2 DI) |
| v6 | tabla `users` (multi-user + RBAC con bcrypt) |
| v7 | `extracciones.created_by_username` + tabla `audit_log` (auditoría "quién hizo qué") |

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
