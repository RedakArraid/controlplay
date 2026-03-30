# Flux temps de jeu (QR → paiement → session)

## Parcours client

1. Le client scanne le QR de la station et ouvre `GET /s/{station_code}`.
2. Par défaut, cette URL sert la **SPA** (React). La page charge `GET /api/public/stations/{station_code}` pour afficher :
   - les offres dédoublonnées (priorité de provider, alignée sur l’ancienne page HTML),
   - la composition de la station (TV, console, VR),
   - l’indicateur **session active** pour proposer la prolongation.
3. Le client soumet un formulaire (`application/x-www-form-urlencoded`) vers :
   - `POST /checkout` pour démarrer une session, ou
   - `POST /extend/checkout` pour ajouter du temps.
4. Le backend initialise le paiement (Paystack / CinetPay ou simulation), puis redirige vers le PSP.
5. Au retour PSP / webhook, la session est marquée payée / active ; les tâches worker pilotent l’activation matérielle (Broadlink, etc.).

## Garanties techniques

- Les endpoints **POST** historiques sont conservés (compatibilité tunnel).
- La couche SPA ne change pas la logique paiement / RBAC ; elle remplace l’interface de saisie côté navigateur.
- Le dédoublonnage des offres garde une seule offre par couple `(durée, prix)` avec priorité provider.

## Configuration

- **`PUBLIC_STATION_SPA`** (défaut `1` dans le code) : si `0`, `GET /s/{station_code}` redevient la page **HTML serveur** legacy (même rendu qu’avant la migration SPA). Voir `.env.example`.

## Points de contrôle QA

- Ouvrir une station active et vérifier le chargement des offres (SPA + API).
- Vérifier qu’un `POST /checkout` redirige vers PSP ou simulateur.
- Vérifier qu’une station avec session active affiche la zone d’extension.
- Vérifier qu’un `POST /extend/checkout` met à jour la session existante.
