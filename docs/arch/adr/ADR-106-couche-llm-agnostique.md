# ADR-106 — Couche LLM agnostique : Mistral par défaut, swappable via LiteLLM

**Statut** : Accepté / implémenté (Slice 0, consolidé en R0)
**Date** : 2026-07-05

## Contexte

La souveraineté (modèles européens, self-hosting) est un argument central de la
plateforme, mais le choix de fournisseur ne doit pas être une impasse : la démonstration
vaut aussi par la capacité à changer de modèle sans réécriture. Chaque module utilisera
des appels LLM (embeddings M2, function-calling M3, classification M4) : sans couche
commune, chaque module câblerait son fournisseur.

## Décision

- **Tout appel modèle passe par `app/core/llm.py`**, construit sur **LiteLLM** :
  `complete(prompt)` (chat via `acompletion`) et `embed(text)` (via `aembedding`).
  Aucun module n'importe un SDK de fournisseur directement.
- Les modèles sont de la **configuration**, pas du code : `LLM_MODEL`
  (défaut `mistral/mistral-large-latest`) et `EMBED_MODEL` (défaut `mistral/mistral-embed`)
  dans l'environnement (`app/core/config.py`). Basculer vers Claude =
  `LLM_MODEL=anthropic/claude-sonnet-5`, zéro ligne de code.
- **Mistral par défaut** : souveraineté européenne, cohérente avec le self-hosting.
- Chaque appel remonte son **observabilité** : modèle utilisé, latence (ms) et tokens
  consommés — base de la mesure de coûts. L'endpoint `/llm/ping` prouve la chaîne
  (un chat + un embedding) en conditions réelles.

## Conséquences

- Le fil rouge « souverain mais swappable » est démontrable en une variable d'environnement.
- Les modules futurs héritent gratuitement de l'observabilité (latence, tokens) et du
  swap de fournisseur.
- **Compromis / limites** :
  - la surface actuelle est minimale — un chat simple et un embedding unitaire ; le
    function-calling (M3), le batching d'embeddings et le streaming ne sont pas encore
    exposés et devront étendre cette couche (jamais la contourner) ;
  - dépendance à LiteLLM et à ses conventions de nommage de modèles — assumée : c'est le
    prix de l'agnosticisme, et la lib est remplaçable derrière la même interface ;
  - la clé est passée explicitement (`api_key=settings.mistral_api_key or None`) : le
    swap vers un autre fournisseur suppose d'ajouter la variable de clé correspondante.
