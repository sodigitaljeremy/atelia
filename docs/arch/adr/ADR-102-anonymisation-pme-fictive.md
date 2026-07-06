# ADR-102 — Anonymisation : PME fictive paramétrable

**Statut** : Accepté / implémenté (Slice R0)
**Date** : 2026-07-05

## Contexte

La plateforme incarne une PME agroalimentaire pour donner un fil conducteur concret aux
cas d'usage. Le projet est public (déployé sur atel-ia.fr, présenté à plusieurs
recruteurs/clients) : nommer une entreprise réelle poserait un problème de prudence
juridique et rattacherait la démonstration à un seul interlocuteur, alors qu'elle se veut
transposable. Le POC v1 référençait un contexte d'entreprise réel — purgé lors de la
Slice R0.

## Décision

- La PME est **fictive** et son nom vit dans **une seule variable de configuration** :
  `settings.company_name` (`app/core/config.py`), valeur par défaut « Conservia »,
  surchargeable par variable d'environnement.
- L'UI ne contient **aucun nom en dur** : un context processor Jinja
  (`app/core/templates.py`) injecte `company_name` dans tous les templates (topbar,
  hub, page Démarche, pied de page).
- Le générateur de factures d'exemple (`scripts/generate_samples.py`) lit le même
  `settings.company_name` pour l'acheteur embarqué dans le XML Factur-X.
- **Aucune entreprise réelle nommée**, nulle part (code, templates, docs, données).
  Relecture obligatoire avant chaque déploiement : `grep -ri` sur les anciens noms et
  toute référence réelle doit rendre zéro occurrence.

## Conséquences

- Rebrander la PME = changer une variable d'environnement (ou la valeur par défaut).
- Le pied de page affiche explicitement que la PME est fictive et les données
  synthétiques/publiques : pas d'ambiguïté pour un visiteur.
- **Compromis / limites** :
  - le nom est **embarqué dans les PDF de `samples/`** : changer `company_name` impose de
    régénérer les samples (`uv run scripts/generate_samples.py`) et de reconstruire l'image ;
  - le nom reste une valeur de travail : vérifier qu'aucune entreprise réelle ne porte
    ce nom avant toute communication large (sinon en changer — coût : une variable +
    régénération des samples). Déjà renommé deux fois depuis le POC v1 au coût prévu
    (anciens noms volontairement non cités ici — zéro occurrence résiduelle ; voir git) ;
  - l'anonymisation reste une discipline de relecture, pas une garantie outillée (pas de
    contrôle automatique en CI à ce stade).
