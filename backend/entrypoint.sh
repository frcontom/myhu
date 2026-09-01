#!/bin/sh
set -e

/bin/ollama serve &
OLLAMA_PID=$!

until /bin/ollama list >/dev/null 2>&1; do
  sleep 2
done

MODEL="${OLLAMA_MODEL:-qwen2.5:7b-instruct}"
HF_MODEL="${OLLAMA_HF_MODEL:-Qwen/Qwen2.5-7B-Instruct-GGUF:q3_K_M}"
SOURCE="${OLLAMA_DOWNLOAD_SOURCE:-auto}"

alias_from_hf() {
  HF_NAME=$(/bin/ollama list 2>/dev/null | awk '{print $1}' | grep -i "^hf.co" | head -1)
  if [ -z "$HF_NAME" ]; then
    echo "==> No se encontró un modelo hf.co en ollama list para crear el alias."
    return 1
  fi
  if /bin/ollama create "$MODEL" --from "$HF_NAME" 2>/dev/null; then
    echo "==> Modelo ${MODEL} creado desde ${HF_NAME}."
  elif /bin/ollama cp "$HF_NAME" "$MODEL" 2>/dev/null; then
    echo "==> Modelo ${MODEL} copiado desde ${HF_NAME}."
  else
    echo "==> No se pudo crear el alias. Ejecuta manualmente: ollama create ${MODEL} --from ${HF_NAME}"
    return 1
  fi
}

if /bin/ollama list 2>/dev/null | grep -q "^${MODEL}[[:space:]]"; then
  echo "==> Modelo ${MODEL} ya instalado."
else
  case "$SOURCE" in
    2|hf|huggingface)
      echo "==> [fuente=$SOURCE] Descargando desde HuggingFace (hf.co/${HF_MODEL})..."
      if /bin/ollama pull "hf.co/${HF_MODEL}"; then
        alias_from_hf
      else
        echo "==> No se pudo descargar desde HuggingFace. Importa el GGUF offline: powershell -File scripts/importar_modelo.ps1"
      fi
      ;;
    1|registry)
      echo "==> [fuente=$SOURCE] Descargando desde registry.ollama.ai..."
      /bin/ollama pull "$MODEL" \
        && echo "==> Modelo ${MODEL} descargado desde registry." \
        || echo "==> No se pudo descargar desde registry (puede estar bloqueado)."
      ;;
    *)
      echo "==> [fuente=auto] Descargando ${MODEL} desde registry.ollama.ai..."
      if command -v timeout >/dev/null 2>&1; then
        timeout 90 /bin/ollama pull "$MODEL"
        REGISTRY_OK=$?
      else
        /bin/ollama pull "$MODEL"
        REGISTRY_OK=$?
      fi
      if [ "$REGISTRY_OK" -eq 0 ]; then
        echo "==> Modelo ${MODEL} descargado desde registry."
      else
        echo "==> registry bloqueado/falló, probando HuggingFace (hf.co/${HF_MODEL})..."
        if /bin/ollama pull "hf.co/${HF_MODEL}"; then
          alias_from_hf
        else
          echo "==> No se pudo descargar (registry y HuggingFace bloqueados). Importa el GGUF offline: scripts/importar_modelo.ps1"
        fi
      fi
      ;;
  esac
fi

echo "==> Ollama listo."
wait "$OLLAMA_PID"