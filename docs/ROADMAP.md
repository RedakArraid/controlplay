# Roadmap ControlPlay

Document de référence : **où en est le projet** et **par quoi enchaîner**. Dernière mise à jour : mars 2026.

---

## État actuel (résumé)

| Domaine | Statut |
|--------|--------|
| Socle Docker, FastAPI, Celery, Postgres, Redis, Alembic | OK |
| Paiements Paystack / CinetPay (init, retours, webhooks avec vérifs) | OK (affiner cas limites en prod) |
| Parcours client QR → `/s/{station}` → checkout | **SPA React** (données `GET /api/public/stations/{code}`) ; `POST /checkout` et `POST /extend/checkout` inchangés |
| Admin opérationnel | **SPA React** (`/admin`, `/super-admin`) + **`/api`** + POST formulaires legacy pour partie CRUD |
| Vitrine publique | **SPA** : `/`, `/location`, `/boutique`, `/carte`, `/jeux` + carte OSM si GPS salles |
| Connexion | Un seul bouton **Se connecter** → `/login` (session cookie ; droits selon RBAC) |
| Dev front | `make frontend-dev` → **:5173** (HMR) ; API proxifiée vers **:8000** |
| Build prod / Docker volume | `make frontend-build` → `app/static/spa/` |

---

## Phase 1 — Stabiliser le socle (**terminé**)

- [x] Docker Compose (`app`, `worker`, `db`, `redis`)
- [x] Modèles `Station`, `Offer`, `GameSession`, `EventLog`, RBAC, salles, offres liées
- [x] QR par station, simulation paiement, Celery activate/deactivate (Broadlink dry-run)
- [x] Makefile, `.env.example`, migrations Alembic, `/health`

---

## Phase 2 — MVP fonctionnel (**en cours**)

- [x] Scripts de démarrage et migration (`make bootstrap`, `migrate`, …)
- [x] **Admin & vitrine en SPA React** (liste / dashboard / navigation bootstrap, marketing location · boutique · carte · jeux)
- [x] API JSON **`/api`** (auth, bootstrap, listes, options session manuelle, salles publiques + lat/lon)
- [x] **Parcours client station** (`/s/{code}`) : **SPA** (vitrine) ; tunnel paiement toujours via `POST /checkout` et `POST /extend/checkout`. Détails : `docs/FLOW_TEMPS_DE_JEU.md`. Désactivation possible : `PUBLIC_STATION_SPA=0` (retour page HTML serveur legacy).
- [ ] **Checklist QA manuelle** (à refaire après chaque grosse release) :
  - [ ] Créer une offre (POST admin existant ou futur écran SPA complet)
  - [ ] QR → choix offre → paiement simulé ou test PSP
  - [ ] Session créée + tâche Celery (logs worker)
- [ ] Consolider statuts session (annulation, timeouts, messages utilisateur)
- [ ] Logs opérationnels lisibles (agrégation / niveaux, pas seulement `EventLog` brute)

---

## Phase 2 bis — Vitrine & expérience marque (**terminé**)

- [x] Identité visuelle (Syne / Outfit, thème sombre gaming / VR)
- [x] Pages marketing et **une seule** entrée **Se connecter**
- [x] Carte des salles (iframe OSM + liste) si coordonnées GPS renseignées

---

## Phase 3 — Paiements en production (**à consolider**)

- [x] Init Paystack / CinetPay, retours, webhooks (signature + vérif API + idempotence)
- [ ] Passes de recette **prod** (montants réels, relances webhook, rejouabilité)
- [ ] Tableau de bord minimal des échecs / sessions bloquées « pending »

---

## Phase 4 — Matériel Broadlink (**à faire**)

- [ ] IP fixe RM Mini 3, script d’apprentissage IR
- [ ] Codes IR par station (ou défaut `.env`)
- [ ] `BROADLINK_DRY_RUN=false` sur environnement pilote
- [ ] Tests manuels HDMI1 ↔ HDMI2 + journalisation

---

## Plan pour la suite (**priorisé**)

Ordre recommandé pour les prochaines itérations produit / tech :

### P0 — Cohérence parcours utilisateur

1. [x] **Aligner les pages HTML client** (`/s/{code}`, `/salle/…`) sur la charte sombre + polices Syne/Outfit (`controlplay.css` + `ui_theme.py` : fonts injectées pour `theme-public`).
2. [x] **Tunnel checkout** : migration progressive vers React (optionnel) — les formulaires POST vers `/checkout` restent inchangés.
3. [x] **Documenter le flux « temps de jeu »** avec schéma ou captures si besoin (`docs/FLOW_TEMPS_DE_JEU.md`).

### P1 — Admin 100 % exploitable depuis la SPA

3. [x] **Endpoints JSON** : stations (`/api/admin/stations`), offres templates (`/api/admin/offers`), salles (`/api/admin/salles`) + **offres rattachées à une salle** (`/api/admin/salles/{id}/offers`).
4. [x] **Formulaires React** : édition SPA des salles (CRUD), stations (CRUD) et offres (templates).
5. [x] Gestion des **offres par salle** : attacher/détacher depuis la SPA (`/admin/salles/:salleId/offers`).

6. [x] Gestion des **users rattachés à une salle** (gérants / responsables) : attach/detach via (`/api/admin/salles/{id}/users`).
7. [x] Page React dédiée : (`/admin/salles/:salleId/users`).

8. [x] Gestion des **offres rattachées à une station** : attach/detach via (`/api/admin/stations/{id}/offers`).
9. [x] Page React dédiée : (`/admin/stations/:stationId/offers`).

### P2 — Données « jeu » et catalogue

10. Modèle **`Game`** (ou équivalent) optionnel + liaison offre / station / tags.
11. [x] **`GET /api/public/jeux`** (ou par salle) pour alimenter `/jeux` au lieu du contenu statique.

### P3 — Boutique

12. Modèles **produit / stock / commande** (ou intégration outil tiers).
13. Parcours panier + paiement (réutiliser PSP ou tunnel dédié).

### P4 — Compte joueur (optionnel)

14. Auth **client** (téléphone / OTP ou email) si vous voulez historique, fidélité, réservations — **hors scope** du login admin actuel.

### P5 — Qualité continue

15. `npm run typecheck` dans CI (ou job parallèle léger).
16. Étendre **Playwright** (parcours marketing + login admin + une station simulée si possible).
17. OpenAPI **`/docs`** : documenter explicitement le préfixe **`/api`** pour intégrations externes.

---

## Évolutions plus lointaines (V1+)

- Dashboard temps réel (WebSocket ou polling) — une partie est déjà dans `/api/admin/dashboard/summary`
- Filtres / export sessions (compta, stats)
- Multi-sites, PSP par site, RBAC affiné
- Offres pack, heures creuses, promos
- Webhooks sortants, n8n, API publique documentée

---

## Comment utiliser ce document

- Cocher les cases au fil des merges.
- Déplacer ou recréer une **issue / epic** par bloc **P0…P5** si vous utilisez un outil de suivi.
- En fin de sprint : mettre à jour le **tableau « État actuel »** en haut.
