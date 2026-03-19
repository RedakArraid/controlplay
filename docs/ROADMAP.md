## Plan pour terminer le MVP

### Phase 1 — Stabiliser le socle (en cours)

- [x] Docker Compose avec `app`, `worker`, `db`, `redis`.
- [x] FastAPI + Celery + PostgreSQL + Redis configurés.
- [x] Modèles: `Station`, `Offer`, `GameSession`, `EventLog`.
- [x] Admin HTML basique pour créer:
  - [x] des offres (durée, prix, provider)
  - [x] des stations (code, IP Broadlink, codes IR).
- [x] Génération de QR codes par station.
- [x] Simulation de paiement avec redirection interne.
- [x] Tâches Celery pour activer et désactiver une session (en mode Broadlink dry-run).

### Phase 2 — Finaliser le MVP fonctionnel (en cours)

- [x] Ajouter des scripts de démarrage et de migration (commande unique pour init DB).
- [ ] Affiner l’UI HTML (client + admin) pour une meilleure expérience en salle de jeux.
- [ ] Tester le flux complet en local (sans Docker si nécessaire):
  - [ ] Création d’une offre via `/admin/offers`.
  - [ ] Scan QR → sélection offre → simulation paiement.
  - [ ] Vérifier création session + déclenchement des tâches Celery.
- [ ] Consolider les statuts de session (cas d’erreur paiement, annulation, etc.).
- [ ] Ajouter un minimum de logs lisibles (plutôt que uniquement `EventLog` brute).

#### Livrables récents (mars 2026)

- [x] Ajout de `.env.example` pour faciliter l'initialisation locale.
- [x] Ajout d'un `Makefile` (`init-env`, `up`, `down`, `migrate`, `bootstrap`, `revision`).
- [x] Intégration d'Alembic avec migration initiale (`0001_initial_schema`).
- [x] Passage de `AUTO_CREATE_SCHEMA=false` par défaut (migrations d'abord).
- [x] `docker-compose.yml` corrigé (chemins relatifs, ports configurables, commande worker Celery).

### Phase 3 — Intégration réelle des paiements

- [ ] Intégration **Paystack**:
  - [ ] Endpoint d'initialisation transaction (appel API Paystack).
  - [ ] Redirection vers la page de paiement Paystack.
  - [ ] Webhook Paystack complet:
    - [x] Validation de signature `x-paystack-signature` (HMAC SHA512).
    - [ ] Vérification du statut transaction via API Paystack.
    - [ ] Gestion idempotence (pas de double activation).

- [ ] Intégration **CinetPay**:
  - [ ] Appel API de création de paiement.
  - [ ] Gestion du retour / redirection.
  - [ ] Webhook CinetPay:
    - [ ] Vérification `x-token` (HMAC SHA256).
    - [ ] Vérification de la transaction via `payment/check`.
    - [ ] Gestion idempotence.

### Phase 4 — Validation matérielle Broadlink

- [ ] Détection et configuration du RM Mini 3 sur le réseau (IP fixe recommandée).
- [ ] Script de "learn" des codes IR (HDMI1, HDMI2, Power).
- [ ] Injection des codes IR dans:
  - [ ] `.env` pour les valeurs par défaut, ou
  - [ ] la configuration de chaque station via l'admin.
- [ ] Passage de `BROADLINK_DRY_RUN=false` en environnement de test.
- [ ] Batterie de tests:
  - [ ] Bascule HDMI1 → HDMI2.
  - [ ] Retour HDMI2 → HDMI1.
  - [ ] Gestion des échecs (retries, logs clairs).

---

## Évolutions futures possibles

### V1+ — Dashboard et supervision

- [ ] Dashboard temps réel pour l’admin (état de chaque station, temps restant, dernière erreur).
- [ ] Filtrage des sessions par date, station, statut.
- [ ] Export des sessions pour la comptabilité / statistique.

### V2 — Multi-sites et multi-projets

- [ ] Gestion de plusieurs locaux / salles (champ `location` sur les stations).
- [ ] Séparation des configurations Paystack / CinetPay par site.
- [ ] Droits utilisateurs (admin global, manager de salle, opérateur).

### V3 — Durées et offres avancées

- [ ] Offres pack / abonnements.
- [ ] Tarifs variables (heure creuse / pleine).
- [ ] Codes promo ou tokens de jeu.

### V4 — Intégrations externes

- [ ] Intégration `n8n` pour orchestrer des scénarios plus complexes.
- [ ] Webhooks sortants vers d’autres systèmes (CRM, BI, etc.).
- [ ] API publique documentée pour que d’autres apps pilotent les stations.

