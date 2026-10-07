from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDERS = {"", "tu-organizacion", "Tu-Proyecto", "tu_pat_aqui", "your-organization", "your-project", "your_pat_here"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_devops_org: str = ""
    azure_devops_project: str = ""
    azure_devops_pat: str = ""
    azure_devops_url: str = ""
    azure_devops_test_plan_id: str = ""

    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_temperature: float = 0.2
    ollama_max_tokens: int = 8192
    ollama_num_ctx: int = 4096

    llm_provider: str = "ollama"
    gemini_api_key: str = ""
    gemini_url: str = "https://generativelanguage.googleapis.com"
    gemini_model: str = "gemini-3.8-flash"
    gemini_temperature: float = 0.2
    gemini_max_tokens: int = 8192

    @property
    def gemini_configured(self) -> bool:
        return bool((self.gemini_api_key or "").strip())

    @property
    def default_provider(self) -> str:
        provider = (self.llm_provider or "ollama").strip().lower()
        return provider if provider in ("ollama", "gemini") else "ollama"

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