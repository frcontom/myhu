#!/bin/sh
set -e

/bin/ollama serve &
OLLAMA_PID=$!

until /bin/ollama list >/dev/null 2>&1; do
  sleep 2
done

MODEL="${OLLAMA_MODEL:-qwen2.5:7b-instruct}"
HF_MODEL="${OLLAMA_HF_MODEL:-Qwen/Qwen2.5-7B-Instruct-GGUF:q3_K_M}"

if /bin/ollama list 2>/dev/null | grep -q "^${MODEL}[[:space:]]"; then
  echo "==> Modelo ${MODEL} ya instalado."
else
  echo "==> Descargando ${MODEL} desde registry.ollama.ai..."
  if ! /bin/ollama pull "$MODEL"; then
    echo "==> registry bloqueado/falló, probando HuggingFace (hf.co/${HF_MODEL})..."
    if /bin/ollama pull "hf.co/${HF_MODEL}"; then
      /bin/ollama create "$MODEL" --from "hf.co/${HF_MODEL}" \
        && echo "==> Modelo ${MODEL} creado desde HuggingFace."
    else
      echo "==> No se pudo descargar (la red bloquea registry y HuggingFace)."
      echo "==> Importa el modelo offline: powershell -File scripts/importar_modelo.ps1 -GgufPath <archivo.gguf> -ModelName ${MODEL}"
    fi
  else
    echo "==> Modelo ${MODEL} descargado desde registry."
  fi
fi

echo "==> Ollama listo."
wait "$OLLAMA_PID"