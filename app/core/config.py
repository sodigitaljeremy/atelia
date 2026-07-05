from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement (.env en local, env_file via compose)."""

    mistral_api_key: str = ""
    database_url: str = "postgresql://atelia:atelia@localhost:5432/atelia"

    # PME fictive incarnée par la plateforme (ADR-102) — unique source du nom, utilisée partout
    company_name: str = "Conserverie du Val"

    # Hypothèses de gain du module Factures — PARAMÉTRABLES (affichées comme telles dans l'UI)
    minutes_saved_per_invoice: int = 5
    cost_avoided_per_invoice_eur: int = 26

    # Modèles derrière LiteLLM — swappables vers Claude par simple changement de valeur (ADR-001)
    llm_model: str = "mistral/mistral-large-latest"
    embed_model: str = "mistral/mistral-embed"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
