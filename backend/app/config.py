from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDERS = {"", "tu-organizacion", "Tu-Proyecto", "tu_pat_aqui", "your-organization", "your-project", "your_pat_here"}

# Catálogo visible en el front (selector "Modelo Kiro"). Los ids se verificaron
# contra kiro-cli 2.32 (`--model <id>`); credits = multiplicador de créditos Kiro.
# Solo los modelos eficientes (<= 1.3x); los de 2x-4.4x (Opus, GPT Terra/Sol) se omiten.
KIRO_MODELS = [
    {"id": "", "label": "Auto (recomendado)", "credits": "1x", "use": "Selección automática de modelo"},
    {"id": "qwen3-coder-next", "label": "Qwen3 Coder Next", "credits": "0.05x", "use": "Pruebas sencillas y generación repetitiva de código"},
    {"id": "minimax-m2.1", "label": "MiniMax M2.1", "credits": "0.15x", "use": "Experimentos económicos"},
    {"id": "deepseek-3.2", "label": "DeepSeek V3.2", "credits": "0.25x", "use": "Análisis y pruebas de varios pasos"},
    {"id": "minimax-m2.5", "label": "MiniMax M2.5", "credits": "0.25x", "use": "Generación de código y pruebas"},
    {"id": "claude-haiku-4.5", "label": "Claude Haiku 4.5", "credits": "0.4x", "use": "Correcciones rápidas y pruebas unitarias simples"},
    {"id": "glm-5", "label": "GLM 5", "credits": "0.5x", "use": "Análisis de cambios en varios archivos"},
    {"id": "gpt-5.6-luna", "label": "GPT 5.6 Luna", "credits": "0.6x", "use": "Pruebas y programación con bajo consumo"},
    {"id": "claude-sonnet-5.5", "label": "Claude Sonnet 5.5", "credits": "1.3x", "use": "Pruebas integradas y depuración"},
    {"id": "claude-sonnet-5", "label": "Claude Sonnet 5", "credits": "1.3x", "use": "Implementación y revisión de pruebas"},
    {"id": "claude-sonnet-4.6", "label": "Claude Sonnet 4.6", "credits": "1.3x", "use": "Desarrollo y correcciones"},
    {"id": "claude-sonnet-4.5", "label": "Claude Sonnet 4.5", "credits": "1.3x", "use": "Alternativa para tareas de programación"},
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
    kiro_agents_parallel: int = 1  # agentes Kiro simultáneos (control de créditos)

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
        raw = {p.strip() for p in (self.enabled_providers or "").split(",") if p.strip()}
        ordered = [p for p in valid if p in raw]
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