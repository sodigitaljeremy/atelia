# ADR-105 — Données publiques + synthétiques uniquement

**Statut** : Accepté / appliqué sur les 4 modules (synthétique : M1, M4 · publique : M2, M3)
**Date** : 2026-07-05

## Contexte

La plateforme est publique et à vocation de démonstration : elle doit manipuler de la
donnée crédible sans jamais exposer de donnée privée réelle (ni d'une entreprise, ni de
personnes). Deux familles couvrent tous les besoins : les données **publiques
officielles** (textes réglementaires, API d'État) et les données **synthétiques** là où
le réel serait privé (factures, réclamations).

## Décision

Toute donnée de la plateforme est soit **publique**, soit **synthétique**. Jamais de
donnée privée réelle.

État par module :

| Donnée | Type | Module | État |
|---|---|---|---|
| Factures Factur-X EN 16931 (`scripts/generate_samples.py`) | Synthétique | M1 | **En place** |
| Règlement (UE) 1169/2011 consolidé (EUR-Lex, texte officiel) | Publique | M2 | **En place** |
| API Recherche d'entreprises (RNE + Sirene) et BODACC | Publique (live) | M3 | **En place** |
| Messages entrants (réclamations, demandes) | Synthétique | M4 | **En place** |

Les fournisseurs figurant dans les factures synthétiques sont eux-mêmes fictifs
(noms, SIREN et adresses inventés), en cohérence avec ADR-102.

## Conséquences

- La plateforme peut être montrée à n'importe qui sans question de confidentialité,
  et le visiteur peut manipuler les données librement (télécharger les samples, les
  soumettre, les valider).
- **Compromis / limites** :
  - le synthétique ne reproduit pas la variété du réel (factures propres, bien formées) —
    assumé pour le happy path, les cas dégradés seront eux aussi synthétiques ;
  - les SIREN inventés des samples M1 ne correspondent à rien dans les API publiques de
    M3 : une éventuelle passerelle M1→M3 devra utiliser des SIREN réels d'entreprises
    publiques ou gérer le « non trouvé » (passerelle non construite à ce jour) ;
  - le module M3 est volontairement affiché comme **hors de la fiction** Conservia :
    il interroge de vraies entreprises, la séparation est explicite dans l'UI (ADR-102).
