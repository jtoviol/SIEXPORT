<#
Unifica los soportes PDF descargados de SIEDFASER (varios programas/lotes) en
una sola carpeta por afiliado, para facilitar la radicación de cuentas médicas
cuando un mismo afiliado tiene soportes de más de un programa.

USO:
    1. Copie este archivo dentro de la carpeta donde descomprimió los ZIP
       (ej. C:\Users\jtoviol\Downloads\DATA).
    2. Clic derecho sobre el archivo -> "Ejecutar con PowerShell".
       (Si PowerShell bloquea la ejecución, corra en su lugar:
        powershell -ExecutionPolicy Bypass -File ".\Unificar-Soportes.ps1")
       Agregue -PorRegimen si además quiere la versión separada por
       SUBSIDIADO/CONTRIBUTIVO (ver más abajo).
    3. La ventana queda abierta esperando ENTER al terminar -- así se ve el
       resumen antes de que se cierre.

ENTRADA ESPERADA (estructura que ya entrega SIEDFASER al descomprimir):
    DATA\<Programa>\<lote_NNN>\<TIPO_DOCUMENTO>\archivo.pdf

SALIDA (modo normal):
    DATA\SOPORTES UNIFICADOS\<TIPO_DOCUMENTO>\<Programa>_archivo.pdf

SALIDA (-PorRegimen):
    DATA\SOPORTES UNIFICADOS POR REGIMEN\<SUBSIDIADO|CONTRIBUTIVO>\<TIPO_DOCUMENTO>\<Programa>_archivo.pdf

    El régimen se detecta buscando las palabras "SUBSIDIADO" o "CONTRIBUTIVO"
    en el nombre de la carpeta de cada programa (ese nombre lo escribe quien
    crea la extracción en SIEDFASER). Si una carpeta no trae ninguna de las
    dos, sus soportes van a una carpeta aparte "SIN_REGIMEN" y se avisa en el
    resumen -- nunca se adivina ni se descarta en silencio.

Los soportes originales NO se tocan ni se borran: el script solo COPIA.
Si el mismo afiliado aparece en varios programas (del mismo régimen, en modo
-PorRegimen), sus PDFs quedan juntos en una única carpeta, cada uno con el
prefijo del programa de origen.
#>

[CmdletBinding()]
param(
    # Carpeta raíz donde están las carpetas de cada programa (por defecto, la carpeta donde está este script)
    [string]$DataRoot = $PSScriptRoot,

    # Nombre de la carpeta de salida (por defecto: "SOPORTES UNIFICADOS", o
    # "SOPORTES UNIFICADOS POR REGIMEN" si se usa -PorRegimen)
    [string]$DestFolderName,

    # Si se pasa, separa el resultado en subcarpetas SUBSIDIADO / CONTRIBUTIVO / SIN_REGIMEN
    [switch]$PorRegimen,

    # Si se pasa, solo muestra qué haría, sin copiar nada
    [switch]$DryRun,

    # Si se pasa, NO espera Enter al final (para uso automatizado/scripts)
    [switch]$NoInteractive
)

$ErrorActionPreference = "Stop"

$SIN_REGIMEN = "SIN_REGIMEN"
$NombresSalidaConocidos = @("SOPORTES UNIFICADOS", "SOPORTES UNIFICADOS POR REGIMEN")

if (-not $DestFolderName) {
    $DestFolderName = if ($PorRegimen) { "SOPORTES UNIFICADOS POR REGIMEN" } else { "SOPORTES UNIFICADOS" }
}

function Get-NombreLimpio {
    param([string]$Nombre)
    $limpio = $Nombre.Trim()
    $limpio = $limpio -replace '[\\/:\*\?"<>\|]', '_'
    $limpio = $limpio -replace '\s+', '_'
    return $limpio
}

function Get-Regimen {
    param([string]$NombrePrograma)
    $mayus = $NombrePrograma.ToUpperInvariant()
    if ($mayus -like "*SUBSIDIADO*")   { return "SUBSIDIADO" }
    if ($mayus -like "*CONTRIBUTIVO*") { return "CONTRIBUTIVO" }
    return $SIN_REGIMEN
}

if (-not (Test-Path -LiteralPath $DataRoot)) {
    throw "No existe la carpeta de origen: $DataRoot"
}
$DataRoot = (Resolve-Path -LiteralPath $DataRoot).Path
$DestRoot = Join-Path $DataRoot $DestFolderName

Write-Host "Carpeta de origen : $DataRoot"
Write-Host "Carpeta destino   : $DestRoot"
if ($PorRegimen) { Write-Host "Modo: separado por REGIMEN (SUBSIDIADO / CONTRIBUTIVO / SIN_REGIMEN)" }
if ($DryRun) { Write-Host "MODO PRUEBA (-DryRun): no se copiará nada, solo se muestra el conteo." -ForegroundColor Yellow }
Write-Host ""

# Carpetas de "programa" = subcarpetas de primer nivel dentro de DataRoot,
# excluyendo cualquier carpeta de salida conocida (por si el script se corre
# más de una vez, o ya existe la salida del otro modo).
$excluidas = $NombresSalidaConocidos + $DestFolderName
$carpetasPrograma = Get-ChildItem -LiteralPath $DataRoot -Directory |
    Where-Object { $excluidas -notcontains $_.Name }

if (-not $carpetasPrograma) {
    Write-Warning "No se encontraron carpetas de programa dentro de '$DataRoot'."
    return
}

if (-not $DryRun -and -not (Test-Path -LiteralPath $DestRoot)) {
    New-Item -ItemType Directory -Path $DestRoot | Out-Null
}

$totalPdfsCopiados   = 0
$totalPdfsRenombrados = 0
$afiliadosVistos     = @{}   # clave "regimen|nombreAfiliado" -> conjunto de programas distintos que aportaron
$resumenPorPrograma  = @{}
$resumenPorRegimen   = @{}

# ---- Fase 1: explorar. Recorre cada programa y ubica las carpetas de
# afiliado/familia (cualquier carpeta que tenga PDFs directamente adentro).
# Esta fase puede tardar si hay muchos miles de archivos; se muestra barra.
Write-Host "Explorando carpetas (puede tardar unos minutos si hay muchos archivos)..." -ForegroundColor DarkGray
$totalProgramas = $carpetasPrograma.Count
$trabajos = @()
$totalCarpetasHoja = 0
$iPrograma = 0
$programasSinRegimen = @()

foreach ($carpetaPrograma in $carpetasPrograma) {
    $iPrograma++
    Write-Progress -Id 1 -Activity "Explorando carpetas" `
        -Status "$iPrograma de $totalProgramas`: $($carpetaPrograma.Name)" `
        -PercentComplete ([int](($iPrograma / [Math]::Max($totalProgramas,1)) * 100))

    # Cualquier carpeta, a cualquier profundidad bajo el programa, que tenga
    # PDFs directamente adentro se trata como "carpeta de afiliado" (o de
    # familia, en Caracterización Familiar) sin importar cómo esté nombrada.
    $carpetasHoja = Get-ChildItem -LiteralPath $carpetaPrograma.FullName -Directory -Recurse |
        Where-Object { (Get-ChildItem -LiteralPath $_.FullName -File -Filter '*.pdf' -ErrorAction SilentlyContinue) }

    $regimen = Get-Regimen $carpetaPrograma.Name
    if ($PorRegimen -and $regimen -eq $SIN_REGIMEN) { $programasSinRegimen += $carpetaPrograma.Name }

    $trabajos += [PSCustomObject]@{
        Programa     = $carpetaPrograma.Name
        Prefijo      = Get-NombreLimpio $carpetaPrograma.Name
        Regimen      = $regimen
        CarpetasHoja = $carpetasHoja
    }
    $totalCarpetasHoja += $carpetasHoja.Count
}
Write-Progress -Id 1 -Activity "Explorando carpetas" -Completed
Write-Host "Encontradas $totalCarpetasHoja carpetas de afiliado/familia en $totalProgramas programa(s)."

if ($PorRegimen -and $programasSinRegimen.Count -gt 0) {
    Write-Host ""
    Write-Host "ADVERTENCIA: no se pudo detectar el régimen de estas carpetas" -ForegroundColor Yellow
    Write-Host "(no traen 'SUBSIDIADO' ni 'CONTRIBUTIVO' en el nombre); sus soportes" -ForegroundColor Yellow
    Write-Host "van a la carpeta '$SIN_REGIMEN':" -ForegroundColor Yellow
    foreach ($p in $programasSinRegimen) { Write-Host "  - $p" -ForegroundColor Yellow }
}
Write-Host ""

# ---- Fase 2: copiar (o simular, si -DryRun) ----
$carpetasProcesadas = 0

foreach ($trabajo in $trabajos) {
    $pdfsDeEstePrograma = 0
    $carpetaRegimen = if ($PorRegimen) { $trabajo.Regimen } else { "" }

    foreach ($carpetaAfiliado in $trabajo.CarpetasHoja) {
        $carpetasProcesadas++
        if ($carpetasProcesadas % 25 -eq 0 -or $carpetasProcesadas -eq $totalCarpetasHoja) {
            $pct = [int](($carpetasProcesadas / [Math]::Max($totalCarpetasHoja,1)) * 100)
            Write-Progress -Id 2 -Activity "Unificando soportes" `
                -Status "$carpetasProcesadas de $totalCarpetasHoja carpetas - $totalPdfsCopiados PDFs copiados - $($trabajo.Programa)" `
                -PercentComplete $pct
        }

        $nombreAfiliado = $carpetaAfiliado.Name
        $destAfiliadoDir = if ($PorRegimen) { Join-Path (Join-Path $DestRoot $carpetaRegimen) $nombreAfiliado } else { Join-Path $DestRoot $nombreAfiliado }

        $claveAfiliado = "$carpetaRegimen|$nombreAfiliado"
        if (-not $afiliadosVistos.ContainsKey($claveAfiliado)) {
            $afiliadosVistos[$claveAfiliado] = New-Object System.Collections.Generic.HashSet[string]
        }
        [void]$afiliadosVistos[$claveAfiliado].Add($trabajo.Programa)

        if (-not $DryRun -and -not (Test-Path -LiteralPath $destAfiliadoDir)) {
            New-Item -ItemType Directory -Path $destAfiliadoDir -Force | Out-Null
        }

        $pdfs = Get-ChildItem -LiteralPath $carpetaAfiliado.FullName -File -Filter '*.pdf'
        foreach ($pdf in $pdfs) {
            $nombreDestino = "$($trabajo.Prefijo)_$($pdf.Name)"
            $rutaDestino   = Join-Path $destAfiliadoDir $nombreDestino

            if (Test-Path -LiteralPath $rutaDestino) {
                # Choque de nombre (mismo programa + mismo nombre de archivo ya copiado): se agrega consecutivo.
                $base = [System.IO.Path]::GetFileNameWithoutExtension($nombreDestino)
                $ext  = [System.IO.Path]::GetExtension($nombreDestino)
                $contador = 2
                do {
                    $nombreDestino = "${base}_$contador$ext"
                    $rutaDestino   = Join-Path $destAfiliadoDir $nombreDestino
                    $contador++
                } while (Test-Path -LiteralPath $rutaDestino)
                $totalPdfsRenombrados++
            }

            if (-not $DryRun) {
                Copy-Item -LiteralPath $pdf.FullName -Destination $rutaDestino
            }
            $totalPdfsCopiados++
            $pdfsDeEstePrograma++
        }
    }

    $resumenPorPrograma[$trabajo.Programa] = $pdfsDeEstePrograma
    if ($PorRegimen) {
        if (-not $resumenPorRegimen.ContainsKey($trabajo.Regimen)) { $resumenPorRegimen[$trabajo.Regimen] = 0 }
        $resumenPorRegimen[$trabajo.Regimen] += $pdfsDeEstePrograma
    }
}
Write-Progress -Id 2 -Activity "Unificando soportes" -Completed

$afiliadosConVariosProgramas = ($afiliadosVistos.GetEnumerator() | Where-Object { $_.Value.Count -gt 1 }).Count

Write-Host ""
Write-Host "===== Resumen =====" -ForegroundColor Cyan
foreach ($p in $resumenPorPrograma.GetEnumerator() | Sort-Object Name) {
    Write-Host ("  {0,-45} {1,6} PDF" -f $p.Key, $p.Value)
}
Write-Host "-------------------------------------------"
if ($PorRegimen) {
    foreach ($r in $resumenPorRegimen.GetEnumerator() | Sort-Object Name) {
        Write-Host ("  Total {0,-20} : {1,6} PDF" -f $r.Key, $r.Value)
    }
    Write-Host "-------------------------------------------"
}
Write-Host "Afiliados/familias unificados : $($afiliadosVistos.Count)"
Write-Host "  - con soportes de 2+ programas: $afiliadosConVariosProgramas"
Write-Host "PDFs copiados                 : $totalPdfsCopiados"
if ($totalPdfsRenombrados -gt 0) {
    Write-Host "PDFs con consecutivo agregado (choque de nombre): $totalPdfsRenombrados"
}
if ($DryRun) {
    Write-Host ""
    Write-Host "Esto fue una PRUEBA. Corra sin -DryRun para copiar de verdad." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "Listo. Revise: $DestRoot" -ForegroundColor Green
}

if (-not $NoInteractive) {
    Write-Host ""
    Read-Host "Presione ENTER para cerrar esta ventana"
}
