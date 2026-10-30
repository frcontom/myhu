from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDERS = {"", "tu-organizacion", "Tu-Proyecto", "tu_pat_aqui", "your-organization", "your-project", "your_pat_here"}

# Catálogo visible en el front (selector "Modelo Kiro"). Los ids y créditos se
# verificaron contra kiro-cli (`chat --list-models --format json`).
# Se incluyen TODOS los modelos estables; se OMITEN los experimentales
# (description "Experimental preview ...": Opus 5.5, Haiku 5.5, GPT 5.6 Sol,
# Kimi K3, DeepSeek 3.2, MiniMax M2.1, Qwen3 Coder Next).
KIRO_MODELS = [
    {"id": "", "label": "Auto (recomendado)", "credits": "1x", "use": "Elige el modelo por ti", "tier": "auto"},
    {"id": "minimax-m2.5", "label": "MiniMax M2.5", "credits": "0.25x", "use": "Casos rápidos y sencillos", "tier": "regular"},
    {"id": "claude-haiku-4.5", "label": "Claude Haiku 4.5", "credits": "0.4x", "use": "Pruebas simples, lo más veloz", "tier": "regular"},
    {"id": "glm-5", "label": "GLM 5", "credits": "0.5x", "use": "Casos de varios pasos", "tier": "regular"},
    {"id": "gpt-5.6-luna", "label": "GPT 5.6 Luna", "credits": "0.6x", "use": "Uso diario con bajo gasto", "tier": "regular"},
    {"id": "claude-sonnet-5.5", "label": "Claude Sonnet 5.5", "credits": "1.3x", "use": "HU normales, buena calidad", "tier": "bueno"},
    {"id": "claude-sonnet-5", "label": "Claude Sonnet 5", "credits": "1.3x", "use": "HU normales, buena calidad", "tier": "bueno"},
    {"id": "claude-sonnet-4.6", "label": "Claude Sonnet 4.6", "credits": "1.3x", "use": "HU normales, buena calidad", "tier": "bueno"},
    {"id": "claude-sonnet-4.5", "label": "Claude Sonnet 4.5", "credits": "1.3x", "use": "HU normales, buena calidad", "tier": "bueno"},
    {"id": "gpt-5.6-terra", "label": "GPT 5.6 Terra", "credits": "2.2x", "use": "HU complejas, gasta más", "tier": "excelente"},
    {"id": "claude-opus-5", "label": "Claude Opus 5", "credits": "2.2x", "use": "HU difíciles, máxima calidad", "tier": "excelente"},
    {"id": "claude-opus-4.8", "label": "Claude Opus 4.8", "credits": "2.2x", "use": "HU difíciles, máxima calidad", "tier": "excelente"},
    {"id": "claude-opus-4.7", "label": "Claude Opus 4.7", "credits": "2.2x", "use": "HU difíciles, máxima calidad", "tier": "excelente"},
    {"id": "claude-opus-4.6", "label": "Claude Opus 4.6", "credits": "2.2x", "use": "HU difíciles, máxima calidad", "tier": "excelente"},
    {"id": "claude-opus-4.5", "label": "Claude Opus 4.5", "credits": "2.2x", "use": "HU difíciles, máxima calidad", "tier": "excelente"},
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_devops_org: str = ""
    azure_devops_project: str = ""
    azure_devops_pat: str = ""
    azure_devops_url: str = ""
    azure_devops_test_plan_id: str = ""
    azure_devops_test_plan_name: str = "QA Test Case Generator"

    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_temperature: float = 0.2
    ollama_max_tokens: int = 8192
    ollama_num_ctx: int = 8192

    llm_provider: str = "ollama"
    enabled_providers: str = "ollama,gemini,kiro"
    # Mostrar u ocultar cada motor en el selector (true/false por motor en el .env).
    provider_ollama_enabled: bool = True
    provider_gemini_enabled: bool = True
    provider_kiro_enabled: bool = True
    gemini_api_key: str = ""
    gemini_url: str = "https://generativelanguage.googleapis.com"
    gemini_model: str = "gemini-3.7-flash"
    gemini_fallback_models: str = (
        "gemini-3.5-flash,gemini-3.6-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    )
    gemini_temperature: float = 0.2
    gemini_max_tokens: int = 16384

    kiro_api_key: str = ""
    kiro_model: str = ""
    kiro_engine: str = ""
    kiro_timeout: int = 600

    # Multiagente
    agents_enabled: bool = True
    agents_parallel: int = 3
    agent_include_risk: str = "auto"  # auto | always | never
    kiro_agents_parallel: int = 3  # agentes Kiro simultáneos (créditos: 3x a la vez)
    agents_single_threshold: int = 2  # <= N casos -> 1 sola llamada directa (sin agentes)

    # Supervisión por agente
    agent_op_timeout: int = 180  # s por agente (0 = usa el timeout del motor)
    agent_inactivity_timeout: int = 45  # s sin tokens nuevos -> cancelar ese agente
    agent_max_retries: int = 1  # reintentos por agente

    @property
    def agent_include_risk_mode(self) -> str:
        mode = (self.agent_include_risk or "auto").strip().lower()
        return mode if mode in ("auto", "always", "never") else "auto"

    @property
    def gemini_configured(self) -> bool:
        return bool((self.gemini_api_key or "").strip())

    @property
    def kiro_configured(self) -> bool:
        return bool((self.kiro_api_key or "").strip())

    @property
    def enabled_providers_list(self) -> list:
        valid = ("ollama", "gemini", "kiro")
        flags = {
            "ollama": self.provider_ollama_enabled,
            "gemini": self.provider_gemini_enabled,
            "kiro": self.provider_kiro_enabled,
        }
        ordered = [p for p in valid if flags[p]]
        return ordered or list(valid)

    @property
    def default_provider(self) -> str:
        provider = (self.llm_provider or "ollama").strip().lower()
        if provider not in ("ollama", "gemini", "kiro"):
            provider = "ollama"
        enabled = self.enabled_providers_list
        return provider if provider in enabled else enabled[0]

    @property
    def api_base(self) -> str:
        if self.azure_devops_url:
            return self.azure_devops_url.rstrip("/")
        return f"https://dev.azure.com/{self.azure_devops_org}"

    @property
    def is_configured(self) -> bool:
        return all(
            (value or "").strip() not in PLACEHOLDERS
            for value in (
                self.azure_devops_org,
                self.azure_devops_project,
                self.azure_devops_pat,
            )
        )

    @property
    def demo_mode(self) -> bool:
        return not self.is_configured


settings = Settings()