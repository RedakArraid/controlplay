## Vue d'ensemble du projet ControlPlay

ControlPlay permet de contrôler des TV de stations de jeu via des requêtes HTTP et des paiements en ligne.
Un client scanne un QR code affiché sur la TV, choisit une offre (durée + prix), paie (Paystack ou CinetPay),
et le système bascule la TV sur l'entrée HDMI de la console pendant la durée achetée, puis revient à l'écran d'accueil.

### Stack technique

- **Backend / Web**: FastAPI (Python)
- **Workers**: Celery (tâches asynchrones)
- **Base de données**: PostgreSQL
- **Queue / timers**: Redis
- **Contrôle TV**: Broadlink RM Mini 3 (IR) via librairie `broadlink` (mode dry-run possible)
- **Conteneurisation**: Docker Compose

### Services Docker

- `app`: API + pages HTML (client + admin) sur le port 8000
- `worker`: worker Celery pour activer/désactiver les sessions de jeu
- `db`: PostgreSQL (stockage des stations, offres, sessions, logs)
- `redis`: broker / backend Celery

### Flux fonctionnel simplifié

1. La TV affiche la page d'accueil de la station avec un QR unique.
2. Le client scanne le QR, arrive sur `/s/{station_code}` et choisit une offre (durée + prix).
3. Le backend crée une session de jeu et redirige vers le paiement (MVP: simulation, ensuite Paystack/CinetPay).
4. À la confirmation de paiement (webhook PSP ou simulation), une tâche worker active la session :
   - envoie la commande IR pour passer la TV sur HDMI 2 (console)
   - programme la désactivation à la fin du temps (retour HDMI 1).

