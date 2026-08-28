# ROADMAP

Estado del proyecto y próximos pasos.

## Estado actual (v1.0)

Funcional de punta a punta:

- [x] Front vanilla (HTML/CSS/JS) con input de HU, cantidad e instrucciones.
- [x] Lectura de la HU desde Azure DevOps (`GET /api/hu/{id}`).
- [x] Generación de casos con LLM local (Ollama, `qwen2.5:7b-instruct`, `format=json`).
- [x] Tabla editable de casos (título, prioridad, tipo, precondiciones, pasos).
- [x] Creación de `Test Case` en Azure DevOps enlazados a la HU (`POST /api/create`).
- [x] **Modo demo**: funciona sin Azure DevOps (HU de ejemplo + creación simulada), con banner en el front.
- [x] Manejo de errores con `detail` legible (front usa `alert`).
- [x] `docker-compose.yml` (backend + ollama), `.env.example`, README, AGENTS.md.

## Pruebas realizadas

- `python -m py_compile` sobre los 4 módulos del backend: OK.
- `docker compose config --quiet`: OK.
- Lógica pura de `steps_to_tcm_html` y `_parse_json` verificada con un script standalone: OK.
- **Pendiente:** prueba end-to-end contra Azure DevOps real y contra Ollama (requiere `.env` con PAT real y la descarga del modelo).

## Próximos pasos sugeridos

### Calidad del LLM
- [ ] Probar con HU reales y ajustar el prompt (ej. pedir tipos de prueba específicos).
- [ ] Ajustar `OLLAMA_TEMPERATURE`/`OLLAMA_MAX_TOKENS` si los casos salen repetidos o truncados.
- [ ] Evaluar `qwen2.5:3b` como fallback rápido cuando la RAM esté justa.

### Funcionalidad
- [ ] Exportar casos a JSON/CSV.
- [ ] Verificar si el work item ya existe (evitar duplicados) antes de crear.
- [ ] Batch: crear casos en paralelo o en una sola llamada (hoy es secuencial, `main.py:create`).
- [ ] Marcar en el front qué casos se crearon OK vs fallaron (hoy solo devuelve error global a mitad).
- [ ] Soporte para conectar a Azure DevOps Server (on-prem) cambiando la URL base.

### Tests automatizados
- [ ] Suite `pytest` para `azure_client` (mock httpx) y `llm_client` (mock respuesta de Ollama).
- [ ] Test del prompt builder y del normalizador con muestras realistas del modelo.

### Infra / DX
- [ ] Script `run.ps1` que cree el `.env`, levante compose y abra el navegador.
- [ ] Healthcheck de Ollama en el compose para que el backend arranque solo cuando el modelo esté listo.
- [ ] Considerar modelos más grandes (`qwen2.5:14b`) solo si el usuario sube a 16 GB de RAM.

## Regla importante

Antes de tocar el formato TCM (`steps_to_tcm_html`) o el tipo de relación (`Microsoft.VSTS.Common.Tests`), probar contra Azure DevOps real, porque son los puntos que romperían la creación de casos en la plataforma.