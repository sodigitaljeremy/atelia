# ADR-107 — Journal de gains immuable (append-only) et tarif runtime non rétroactif

**Statut** : Accepté / implémenté (Slices 3-4)
**Date** : 2026-07-06

## Contexte

À l'origine, les gains du dashboard étaient **recalculés depuis l'état courant** des factures
(`count(status='validee') × tarif`). Deux défauts :

1. rejeter une facture déjà validée faisait **redescendre** les gains affichés, alors que le
   temps de saisie avait réellement été économisé au moment de la validation ;
2. changer le tarif (5 min / X € par facture, hypothèses paramétrables — ADR à la Slice 4)
   aurait **réécrit le passé** : le total ne correspondait plus à ce qui avait été constaté.

## Décision

- **Table `gain_event` append-only** (`app/modules/invoices/schema.sql`) : un événement inséré à
  chaque validation (`repository.record_gain`), **jamais mis à jour ni supprimé**. Aucun `UPDATE`
  ni `DELETE` sur cette table nulle part dans le code.
- **Le tarif est figé dans l'événement** : `minutes_saved` et `cost_avoided_eur` sont écrits avec
  les valeurs **en vigueur au moment de la validation**. Le total affiché est une somme fidèle
  (`SUM` sur le journal), pas un produit recalculé.
- **`UNIQUE (invoice_id)` + `ON CONFLICT DO NOTHING`** : idempotence structurelle — pas de double
  gain pour une même facture, backfill relançable (`repository.backfill_gain_events`, exécuté au
  démarrage via le hook `on_startup` du contrat de module).
- **Tarif runtime pour la suite seulement** : la table `settings_runtime` (clé/valeur) porte le
  tarif des **prochaines** validations (`repository.get_rates` / `set_rates`, bouton « Appliquer
  comme tarif par défaut »). Jamais appliqué rétroactivement.
- Le **simulateur** du dashboard (`/dashboard/simulate`) est une projection pure à la volée
  (`gains.projection`) : il n'écrit rien.

## Conséquences

- **Auditabilité** : chaque euro affiché se justifie par un événement daté, au tarif de l'époque —
  le journal se relit comme un livre comptable.
- **Cohabitation de tarifs** : des événements à 5 min / 26 € et à 8 min / 22 € coexistent dans le
  même historique ; c'est voulu et visible (colonne tarif dans « Derniers gains actés »).
- Rejeter une facture validée fait baisser le compteur de factures validées, **pas** le cumul de
  gains — comportement documenté dans l'UI.
- **Repartir propre = reset, pas réécriture** : la remise à zéro de démo (`repository.reset_demo`,
  gardée par `settings.demo_mode` + confirmation explicite) **tronque** les tables du module ;
  on ne corrige jamais l'historique, on le vide entièrement ou pas du tout.
- Compromis : un gain acté sur une validation erronée (puis rejetée) reste compté — assumé, c'est
  la contrepartie de l'immutabilité ; le cas est marginal et le reset existe pour la démo.
