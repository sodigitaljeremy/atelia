from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement (.env en local, env_file via compose)."""

    mistral_api_key: str = ""
    database_url: str = "postgresql://atelia:atelia@localhost:5432/atelia"

    # PME fictive incarnée par la plateforme (ADR-102) — unique source du nom, utilisée partout
    company_name: str = "Conserverie du Val"

    # Hypothèses de gain du module Factures — PARAMÉTRABLES (affichées comme telles dans l'UI).
    # 15 € : ordre de grandeur France Num pour une facture papier entrante (IGF/DGFiP : 14-20 €).
    minutes_saved_per_invoice: int = 5
    cost_avoided_per_invoice_eur: int = 15

    # Mode démo : active les actions destructives de démonstration (reset). À passer
    # à false en prod le jour où la plateforme ne doit plus être réinitialisable.
    demo_mode: bool = True

    # API Recherche d'entreprises (module Fournisseurs) — ouverte, sans clé (ADR-104).
    # Surchargeable : utile en test et pour démontrer la gestion de panne.
    suppliers_api_url: str = "https://recherche-entreprises.api.gouv.fr/search"

    # Modèles derrière LiteLLM — swappables vers Claude par simple changement de valeur (ADR-001)
    llm_model: str = "mistral/mistral-large-latest"
    embed_model: str = "mistral/mistral-embed"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
