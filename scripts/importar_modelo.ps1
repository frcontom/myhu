param(
    [Parameter(Mandatory = $true)]
    [string]$GgufPath,

    [string]$ModelName = "qwen2.5:7b-instruct",
    [string]$Container = "qa-testcase-ollama"
)

<#
IMPORTAR UN MODELO DE OLLAMA OFFLINE (sin descarga desde Cloudflare R2)

Uso (en una máquina con el GGUF descargado en una red permitida):
    powershell -ExecutionPolicy Bypass -File scripts\importar_modelo.ps1 `
        -GgufPath "C:\models\qwen2.5-7b-instruct-q4_k_m.gguf" `
        -ModelName "qwen2.5:7b-instruct"

Dónde conseguir el GGUF (descargarlo en una red SIN el bloqueo):
    - qwen2.5:7b-instruct  -> HuggingFace: Qwen/Qwen2.5-7B-Instruct-GGUF  (qwen2.5-7b-instruct-q4_k_m.gguf)
    - deepseek-r1:7b       -> HuggingFace: deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF

Nota: el modelo queda dentro del volumen persistente ollama_data, así que no se
pierde al reiniciar el contenedor.
#>

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $GgufPath)) {
    Write-Error "No existe el archivo GGUF: $GgufPath"
    exit 1
}

$fileName = Split-Path -Leaf $GgufPath
$mfTmp = Join-Path $env:TEMP "Modelfile.txt"

Write-Host "==> Copiando GGUF al contenedor $Container ..."
docker exec $Container sh -c "mkdir -p /models" | Out-Null
docker cp $GgufPath "${Container}:/models/${fileName}" | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "Fallo al copiar el GGUF"; exit 1 }

Write-Host "==> Creando Modelfile..."
Set-Content -Path $mfTmp -Value "FROM /models/$fileName" -Encoding UTF8
docker cp $mfTmp "${Container}:/models/Modelfile" | Out-Null
Remove-Item -Force $mfTmp

Write-Host "==> Creando el modelo '$ModelName' (esto puede tardar)..."
docker exec $Container ollama create $ModelName -f /models/Modelfile
if ($LASTEXITCODE -ne 0) { Write-Error "No se pudo crear el modelo"; exit 1 }

Write-Host "==> Modelos instalados:"
docker exec $Container ollama list

Write-Host ""
Write-Host "Listo. Reinicia el backend si ya estaba corriendo: docker compose up -d --build"