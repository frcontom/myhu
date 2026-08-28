from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDERS = {"", "tu-organizacion", "Tu-Proyecto", "tu_pat_aqui", "your-organization", "your-project", "your_pat_here"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_devops_org: str = ""
    azure_devops_project: str = ""
    azure_devops_pat: str = ""

    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:14b-instruct"
    ollama_temperature: float = 0.2
    ollama_max_tokens: int = 8192

    @property
    def api_base(self) -> str:
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