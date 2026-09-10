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
    3. Al terminar, revise la carpeta "SOPORTES UNIFICADOS" dentro de esa misma
       carpeta.

ENTRADA ESPERADA (estructura que ya entrega SIEDFASER al descomprimir):
    DATA\<Programa>\<lote_NNN>\<TIPO_DOCUMENTO>\archivo.pdf

SALIDA:
    DATA\SOPORTES UNIFICADOS\<TIPO_DOCUMENTO>\<Programa>_archivo.pdf

Los soportes originales NO se tocan ni se borran: el script solo COPIA.
Si el mismo afiliado aparece en varios programas, sus PDFs quedan juntos en
una única carpeta, cada uno con el prefijo del programa de origen.
#>

[CmdletBinding()]
param(
    # Carpeta raíz donde están las carpetas de cada programa (por defecto, la carpeta donde está este script)
    [string]$DataRoot = $PSScriptRoot,

    # Nombre de la carpeta de salida
    [string]$DestFolderName = "SOPORTES UNIFICADOS",

    # Si se pasa, solo muestra qué haría, sin copiar nada
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Get-NombreLimpio {
    param([string]$Nombre)
    $limpio = $Nombre.Trim()
    $limpio = $limpio -replace '[\\/:\*\?"<>\|]', '_'
    $limpio = $limpio -replace '\s+', '_'
    return $limpio
}

if (-not (Test-Path -LiteralPath $DataRoot)) {
    throw "No existe la carpeta de origen: $DataRoot"
}
$DataRoot = (Resolve-Path -LiteralPath $DataRoot).Path
$DestRoot = Join-Path $DataRoot $DestFolderName

Write-Host "Carpeta de origen : $DataRoot"
Write-Host "Carpeta destino   : $DestRoot"
if ($DryRun) { Write-Host "MODO PRUEBA (-DryRun): no se copiará nada, solo se muestra el conteo." -ForegroundColor Yellow }
Write-Host ""

# Carpetas de "programa" = subcarpetas de primer nivel dentro de DataRoot,
# excluyendo la carpeta destino (por si el script se corre más de una vez).
$carpetasPrograma = Get-ChildItem -LiteralPath $DataRoot -Directory |
    Where-Object { $_.Name -ne $DestFolderName }

if (-not $carpetasPrograma) {
    Write-Warning "No se encontraron carpetas de programa dentro de '$DataRoot'."
    return
}

if (-not $DryRun -and -not (Test-Path -LiteralPath $DestRoot)) {
    New-Item -ItemType Directory -Path $DestRoot | Out-Null
}

$totalPdfsCopiados   = 0
$totalPdfsRenombrados = 0
$afiliadosVistos     = @{}   # nombre de carpeta afiliado -> cuántos programas distintos aportaron
$resumenPorPrograma  = @{}

foreach ($carpetaPrograma in $carpetasPrograma) {
    $programaPrefijo = Get-NombreLimpio $carpetaPrograma.Name
    $pdfsDeEstePrograma = 0

    # Cualquier carpeta, a cualquier profundidad bajo el programa, que tenga
    # PDFs directamente adentro se trata como "carpeta de afiliado" (o de
    # familia, en Caracterización Familiar) sin importar cómo esté nombrada.
    $carpetasHoja = Get-ChildItem -LiteralPath $carpetaPrograma.FullName -Directory -Recurse |
        Where-Object { (Get-ChildItem -LiteralPath $_.FullName -File -Filter '*.pdf' -ErrorAction SilentlyContinue) }

    foreach ($carpetaAfiliado in $carpetasHoja) {
        $nombreAfiliado = $carpetaAfiliado.Name
        $destAfiliadoDir = Join-Path $DestRoot $nombreAfiliado

        if (-not $afiliadosVistos.ContainsKey($nombreAfiliado)) {
            $afiliadosVistos[$nombreAfiliado] = New-Object System.Collections.Generic.HashSet[string]
        }
        [void]$afiliadosVistos[$nombreAfiliado].Add($carpetaPrograma.Name)

        if (-not $DryRun -and -not (Test-Path -LiteralPath $destAfiliadoDir)) {
            New-Item -ItemType Directory -Path $destAfiliadoDir | Out-Null
        }

        $pdfs = Get-ChildItem -LiteralPath $carpetaAfiliado.FullName -File -Filter '*.pdf'
        foreach ($pdf in $pdfs) {
            $nombreDestino = "${programaPrefijo}_$($pdf.Name)"
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

    $resumenPorPrograma[$carpetaPrograma.Name] = $pdfsDeEstePrograma
}

$afiliadosConVariosProgramas = ($afiliadosVistos.GetEnumerator() | Where-Object { $_.Value.Count -gt 1 }).Count

Write-Host ""
Write-Host "===== Resumen =====" -ForegroundColor Cyan
foreach ($p in $resumenPorPrograma.GetEnumerator() | Sort-Object Name) {
    Write-Host ("  {0,-30} {1,5} PDF" -f $p.Key, $p.Value)
}
Write-Host "-------------------------------------------"
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
