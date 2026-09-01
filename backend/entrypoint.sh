#!/bin/sh
set -e

/bin/ollama serve &
OLLAMA_PID=$!

until /bin/ollama list >/dev/null 2>&1; do
  sleep 2
done

MODEL="${OLLAMA_MODEL:-qwen2.5:7b-instruct}"
if ! /bin/ollama list 2>/dev/null | grep -q "^${MODEL}[[:space:]]"; then
  echo "==> Descargando modelo ${MODEL} ..."
  /bin/ollama pull "$MODEL" \
    || echo "==> No se pudo descargar ${MODEL} (la red puede bloquear registry/R2). Importa el modelo offline: powershell -File scripts/importar_modelo.ps1 -GgufPath <archivo.gguf> -ModelName ${MODEL}"
else
  echo "==> Modelo ${MODEL} ya instalado."
fi

echo "==> Ollama listo."
wait "$OLLAMA_PID"