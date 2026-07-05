# Introduction et objectifs

## But

AtelIA est une **plateforme portfolio de démonstration AI Engineering**. Elle incarne une PME
agroalimentaire fictive (« Conserverie du Val », ADR-102) et résout ses problèmes métier un par
un, chacun avec la technique appropriée. Le message à prouver : *savoir diagnostiquer un besoin
et choisir la bonne approche IA — déterministe, RAG, agent, classification — plutôt que plaquer
un LLM partout.*

## Ce que la plateforme démontre

| Démonstration | Où (aujourd'hui) |
|---|---|
| Déterminisme assumé quand la donnée est structurée | Module Factures : extraction Factur-X (`extraction.py`) et contrôles (`checks.py`) — zéro LLM |
| Contrôle humain sur toute décision engageante | Écran de validation, confirmation explicite sur anomalie bloquante |
| Mesure honnête de la valeur | Journal de gains append-only, hypothèses sourcées et paramétrables (ADR-107) |
| Architecture évolutive | Socle + modules enfichables via registre (ADR-101) |
| Souveraineté sans enfermement | Couche LLM agnostique, Mistral ↔ Claude en config (ADR-106) |
| RAG, agent, classification | *À venir* — M2/M3/M4, cadrés dans le brief v2, non construits |

## Exigences clés

1. **Souveraineté** : modèles Mistral par défaut, self-hosté, aucun service tiers imposé.
2. **Human-in-the-loop** : aucune écriture sans validation d'un opérateur.
3. **Données publiques ou synthétiques uniquement** ; PME fictive, zéro entreprise réelle nommée
   (ADR-102, ADR-105).
4. **Toujours démontrable** : chaque tranche livrée est déployée sur atel-ia.fr ; la plateforme
   n'est jamais un chantier.
5. **Anti-over-engineering** : MVP démontrable d'abord, raffinement ensuite.
