from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement (.env en local, env_file via compose)."""

    mistral_api_key: str = ""
    database_url: str = "postgresql://atelia:atelia@localhost:5432/atelia"

    # Modèles derrière LiteLLM — swappables vers Claude par simple changement de valeur (ADR-001)
    llm_model: str = "mistral/mistral-large-latest"
    embed_model: str = "mistral/mistral-embed"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
