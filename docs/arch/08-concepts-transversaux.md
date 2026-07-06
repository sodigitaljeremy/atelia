# Concepts transversaux

Les principes récurrents, appliqués dans le code aujourd'hui — chaque concept cite son
implémentation réelle.

## 1. Couche LLM agnostique (ADR-106)

Tout appel modèle passe par `app/core/llm.py` (LiteLLM) : `complete()` et `embed()`. Les modèles
sont de la configuration (`LLM_MODEL`, `EMBED_MODEL` — Mistral par défaut, Claude en changeant la
valeur), jamais du code. Chaque appel remonte modèle, latence et tokens ; `/llm/ping` prouve la
chaîne en conditions réelles. Aucun module n'importe un SDK de fournisseur.

## 2. Déterministe d'abord — la bonne technique par problème

Là où la donnée est structurée et normée, pas de LLM : l'extraction Factur-X
(`app/modules/invoices/extraction.py`) lit le XML CII qui fait foi (XPath, `confidence = 1.0`),
et les contrôles (`checks.py`) sont des règles pures — totaux, TVA, dates, doublons. Résultat
exact, testable unitairement, gratuit à l'exécution. Les techniques LLM sont réservées aux
problèmes qui en ont besoin : RAG (Conformité), agent (Fournisseurs), classification (Triage).
Et même là, **le code décide du critique** : score fournisseurs calculé par barème
(`agent.grade`), garde-fou sécurité du triage (`classifier.security_guard`), seuil
hors-corpus du RAG (`rag.SIMILARITY_THRESHOLD`) — le LLM travaille, il ne tranche jamais
seul ce qui engage.

## 3. Human-in-the-loop

Aucune écriture engageante sans opérateur : une facture ingérée reste `en_validation` tant qu'un
humain ne l'a pas validée ou rejetée. Une anomalie **bloquante** (ou un doublon) exige une
confirmation explicite — case à cocher dans l'UI **et** garde côté serveur
(`router.invoice_validate`) : l'UI ne suffit jamais.

## 4. Journal immuable et auditabilité (ADR-107)

Les gains sont un **journal d'événements append-only** (`gain_event`) : un événement par
validation, tarif figé au moment des faits, jamais d'UPDATE/DELETE, total = somme fidèle.
Le tarif runtime (`settings_runtime`) ne vaut que pour l'avenir ; le simulateur est une
projection pure sans écriture. Corollaire : on ne « corrige » pas l'historique — on le vide
entièrement (reset démo, doublement gardé) ou pas du tout.

## 5. Souveraineté

Mistral par défaut (modèles européens), self-hosté sur infra européenne (Hetzner), base de
données locale au déploiement (pgvector dans le même Postgres — ADR-103, le RAG de M2 y
tourne). Le swap de fournisseur reste possible (concept 1) : souverain sans être enfermé.

## 6. Données publiques et synthétiques uniquement (ADR-102, ADR-105)

PME et fournisseurs fictifs, nom porté par `settings.company_name` (une seule source, injectée
partout par le context processor de `core/templates.py`). Factures générées par
`scripts/generate_samples.py` (valides) et `generate_broken_samples.py` (incohérentes exprès,
préfixe `anomalie_`). Relecture d'anonymisation avant chaque déploiement.

## 7. Schémas idempotents, propriété par module (ADR-101)

Chaque module possède ses tables : son `schema.sql` (`CREATE … IF NOT EXISTS`,
`ALTER … ADD COLUMN IF NOT EXISTS`) est appliqué à chaque démarrage par `core/db.py`, suivi du
hook `on_startup` du module pour les migrations de données (ex. backfill des gains, idempotent
par contrainte `UNIQUE`). Pas d'outil de migration séparé tant que le besoin n'existe pas
(anti-over-engineering).
