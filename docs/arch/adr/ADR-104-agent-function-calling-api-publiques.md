# ADR-104 — Agent M3 : function-calling sur API publiques officielles

**Statut** : Accepté, non encore implémenté (prévu Slice M3)
**Date** : 2026-07-05

## Contexte

Le module M3 (enrichissement & fiabilité fournisseurs) doit qualifier un fournisseur à
partir de données **live** : existence légale, état administratif, cohérence. Ces données
existent dans des API publiques officielles. Deux approches possibles : un pipeline fixe
d'appels câblés en dur, ou un **agent** qui décide dynamiquement quels outils appeler —
c'est la technique que M3 a précisément vocation à démontrer (tool-use / orchestration).

## Décision

Implémenter M3 comme un agent LLM en **function-calling**, restreint à des **API
publiques officielles** :

- sources : **API Recherche d'entreprises** (recherche-entreprises.api.gouv.fr) /
  **Sirene INSEE** (existence, NAF, effectifs, état administratif) ; **BODACC**
  (procédures collectives) en option ; **Open Food Facts** pour le volet produit ;
- **pas de scraping** : uniquement des API documentées, dans le respect de leurs
  conditions et **rate limits** ;
- clés et secrets d'API en **variables d'environnement** (pattern existant de
  `app/core/config.py`), jamais commités ;
- **timeouts et repli** : une API indisponible dégrade la fiche (champ « non vérifié »),
  elle ne casse pas le module ;
- les appels LLM (choix d'outils, synthèse, score expliqué) passeront par la couche
  agnostique du socle (`app/core/llm.py`, ADR-106).

## Conséquences

- M3 démontrera l'orchestration multi-API par LLM sur données réelles et publiques,
  en cohérence avec ADR-105.
- Passerelle prévue avec M1 : enrichir le fournisseur d'une facture (SIREN déjà extrait).
- **Compromis / limites** :
  - dépendance à la disponibilité et aux quotas d'API tierces — d'où timeouts et repli
    obligatoires dès la conception ;
  - `app/core/llm.py` n'expose aujourd'hui que `complete` et `embed` : le support du
    function-calling devra y être ajouté (extension de la couche, pas contournement) ;
  - **rien de M3 n'existe à ce jour** : cet ADR fige l'approche et les garde-fous, pas
    une implémentation.
