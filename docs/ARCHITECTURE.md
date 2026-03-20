## Architecture technique

### Composants principaux

- **FastAPI (`app`)**
  - Expose :
    - pages publiques: `/`, `/salle/{salle_code}`, `/s/{station_code}`, `/qr/{station_code}.png`
    - admin: `/admin`, `/admin/offers`, `/admin/stations`, `/admin/sessions`
      - toggles : `/admin/providers`
      - utilitaire : `/admin/stations/{station_id}/reset-sessions`
      - dashboard : `/admin/dashboard`
      - utilitaire salle : `/admin/salles/{salle_id}/reset-sessions`
    - paiements: `/checkout`, `/simulate/pay/{reference}`
    - retours paiements:
      - `/payments/return/paystack/{reference}`
      - `/payments/return/cinetpay`
    - webhooks: `/webhooks/paystack`, `/webhooks/cinetpay`
    - santé: `/health`
  - Gère:
    - la création des sessions de jeu
    - la génération de QR codes
    - l’interface d’administration (offres + stations)

- **Celery / `worker`**
  - Tâches:
    - `tasks.activate_session(session_id)`
      - marque la session comme active
      - envoie la commande IR HDMI2 à la station
      - planifie la fin de session (`deactivate_session`)
    - `tasks.deactivate_session(session_id)`
      - renvoie la TV sur HDMI1
      - clôt la session

- **Alembic (migrations)**
  - Config dans `app/alembic.ini`.
  - Scripts dans `app/alembic/versions`.
  - Exécution via `make migrate` ou `make bootstrap` (dans le conteneur `app`).

- **Broadlink RM Mini 3**
  - Piloté via `broadlink_service.send_ir_command(ip, ir_code)`.
  - Mode dry-run contrôlé par `BROADLINK_DRY_RUN` :
    - `true`: log uniquement (développement / sans matériel)
    - `false`: envoie réel des codes IR.

### Modèle de données (résumé)

- `salles`
  - `code` (optionnel mais pratique pour admin)
  - `name`
  - `latitude`, `longitude`
  - regroupe des `stations`
  - gérant / responsable via la liaison `salle_users` (avec rôles)

- `users` / RBAC
  - `users` (email/phone + `password_hash`, `is_active`)
  - `roles` (admin/manager/responsable/joueur)
  - `user_roles` (rôles globaux, ex: `admin`)
  - `salle_users` (rôles par salle : gérant / responsable)

- `stations`
  - `code` (pour le QR)
  - `name`
  - `broadlink_ip`
  - `ir_code_hdmi1`, `ir_code_hdmi2`
  - `is_active`
  - `salle_id` (nullable)

- `offers`
  - `name`
  - `duration_minutes`
  - `price_xof`
  - `provider` (`paystack` ou `cinetpay`) : choisi **en interne** (priorité Paystack, fallback CinetPay)
  - `is_active`

- tables de liaisons (rattachement des templates aux scopes)
  - `station_offers` : relie `offers` <-> `stations` (une offre peut être attachée à plusieurs stations)
  - `salle_offers` : relie `offers` <-> `salles` (une offre peut être attachée à plusieurs salles)

- `game_sessions`
  - `station_id`, `offer_id`
  - `payment_provider`
  - `payment_reference`
  - `customer_email` (optionnel)
  - `customer_phone` (obligatoire côté UI, stocké pour le suivi PSP / audits)
  - `payment_status` (`pending`, `paid`, `failed`)
  - `status` (`pending`, `active`, `expired`, `failed`)
  - `started_at`, `end_at`

- `event_logs`
  - logs techniques (activation session, erreurs, etc.)

### Variables d'environnement clés

Voir `.env` à la racine :

- Application / infra:
  - `APP_ENV`, `APP_SECRET_KEY`, `BASE_URL`
  - `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
  - `AUTO_CREATE_SCHEMA` (`false` recommandé quand Alembic est utilisé)
- Admin (HTTP Basic):
  - `ADMIN_USERNAME` / `ADMIN_PASSWORD` : bootstrap (création d’un admin dans `users` si aucun admin n’existe)

- Broadlink:
  - `BROADLINK_IP`
  - `BROADLINK_DRY_RUN`
  - `IR_CODE_HDMI1`, `IR_CODE_HDMI2`, `IR_CODE_POWER`

- Paystack:
  - `PAYSTACK_PUBLIC_KEY` (front / futur checkout embarqué)
  - `PAYSTACK_SECRET_KEY` (**obligatoire** pour init + vérification transaction)
  - `PAYSTACK_WEBHOOK_SECRET` (recommandé en prod pour signer les webhooks ; optionnel pour tester l’init seul)
  - `PAYSTACK_CURRENCY` (défaut `XOF`)
  - `PAYSTACK_AMOUNT_MULTIPLIER` (défaut `1` pour XOF ; `100` pour NGN en kobo)

- CinetPay:
  - `CINETPAY_API_KEY`
  - `CINETPAY_SITE_ID`
  - `CINETPAY_SECRET_KEY`
  - `CINETPAY_WEBHOOK_SECRET`

### État actuel (mars 2026)

- Environnement local validé avec Docker (`app`, `worker`, `db`, `redis`).
- Endpoints FastAPI opérationnels (incluant `/health`).
- Migrations Alembic initiales appliquées (`0001_initial_schema`).

