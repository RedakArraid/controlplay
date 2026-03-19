## Architecture technique

### Composants principaux

- **FastAPI (`app`)**
  - Expose :
    - pages publiques: `/`, `/s/{station_code}`, `/qr/{station_code}.png`
    - admin: `/admin`, `/admin/offers`, `/admin/stations`, `/admin/sessions`
    - paiements: `/checkout`, `/simulate/pay/{reference}`
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

- **Broadlink RM Mini 3**
  - Piloté via `broadlink_service.send_ir_command(ip, ir_code)`.
  - Mode dry-run contrôlé par `BROADLINK_DRY_RUN` :
    - `true`: log uniquement (développement / sans matériel)
    - `false`: envoie réel des codes IR.

### Modèle de données (résumé)

- `stations`
  - `code` (pour le QR)
  - `name`
  - `broadlink_ip`
  - `ir_code_hdmi1`, `ir_code_hdmi2`
  - `is_active`

- `offers`
  - `name`
  - `duration_minutes`
  - `price_xof`
  - `provider` (`paystack` ou `cinetpay`)
  - `is_active`

- `game_sessions`
  - `station_id`, `offer_id`
  - `payment_provider`
  - `payment_reference`
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

- Broadlink:
  - `BROADLINK_IP`
  - `BROADLINK_DRY_RUN`
  - `IR_CODE_HDMI1`, `IR_CODE_HDMI2`, `IR_CODE_POWER`

- Paystack:
  - `PAYSTACK_PUBLIC_KEY`
  - `PAYSTACK_SECRET_KEY`
  - `PAYSTACK_WEBHOOK_SECRET`

- CinetPay:
  - `CINETPAY_API_KEY`
  - `CINETPAY_SITE_ID`
  - `CINETPAY_SECRET_KEY`
  - `CINETPAY_WEBHOOK_SECRET`

