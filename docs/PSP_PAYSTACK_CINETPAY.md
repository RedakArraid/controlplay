# Paystack (primaire) et CinetPay (secours)

## Où mettre les jetons et clés

Tout est lu depuis le fichier **`.env`** à la racine du projet (voir **`.env.example`**). Les variables **ne sont pas** dans le code ni dans Git : copier `.env.example` vers `.env` puis remplacer les placeholders.

### Paystack — obligatoires pour un paiement réel

| Variable | Usage |
|---------|--------|
| **`PAYSTACK_SECRET_KEY`** | Clé secrète (**sk_live_…** ou **sk_test_…**) : initialise la transaction (`/transaction/initialize`) et vérifie le paiement (`/transaction/verify`). |
| **`PAYSTACK_PUBLIC_KEY`** | Réservé à un checkout embarqué côté navigateur si vous l’ajoutez plus tard. Le flux actuel **redirection serveur** n’utilise que la **clé secrète**. |

Recommandées en production :

| Variable | Usage |
|---------|--------|
| **`PAYSTACK_WEBHOOK_SECRET`** | Secret du webhook dans le tableau de bord Paystack. Sans lui, **`POST /webhooks/paystack`** accepte les appels sans vérifier la signature (**à éviter en prod**). |

Autres :

- **`PAYSTACK_CURRENCY`** : ex. `XOF`, `NGN`.
- **`PAYSTACK_AMOUNT_MULTIPLIER`** : multiplicateur entier envoyé à Paystack (souvent `100`).
- **`BASE_URL`** : URL publique HTTPS de l’app (sans slash final). Sert aux `callback_url` Paystack et aux liens dans les mails / redirections.

### CinetPay — secours (après échec Paystack ou si Paystack indisponible)

| Variable | Usage |
|---------|--------|
| **`CINETPAY_API_KEY`** | Identifiant API. |
| **`CINETPAY_SITE_ID`** | Identifiant du site / service. |
| **`CINETPAY_SECRET_KEY`** | Sert aussi à **`POST /webhooks/cinetpay`** : si renseigné, validation du header **`x-token`** (HMAC, voir doc CinetPay checkout). |

Les montants CinetPay en XOF doivent être des **multiples de 5** (contrainte actuelle du code).

## URLs à enregistrer chez les PSP

Après avoir fixé **`BASE_URL`** :

- **Paystack** — Webhook :  
  `{BASE_URL}/webhooks/paystack`  
  Retour utilisateur : géré automatiquement via `callback_url` à l’init.

- **CinetPay** — Notification / notify : **`{BASE_URL}/webhooks/cinetpay`** (envoyée à l’API à l’init).  
  Retour utilisateur : **`{BASE_URL}/payments/return/cinetpay`**.

## Comportement applicatif

1. **Ordre utilisé** : tentative **Paystack** en premier (`is_paystack_configured()` : clés valides + Paystack activé en base). En cas d’exception à l’init ou si Paystack n’est pas utilisable → **CinetPay** si configuré.
2. **Flags en base** : table `payment_provider_config` ; interface **SPA super-admin → Providers** (`/super-admin/providers`, formulaire posté vers `/admin/providers`). Vous pouvez désactiver l’un des deux PSP sans retirer les clés du `.env`.

## Implémentation (une seule source de vérité)

La logique partagée (vérif transactions, init, références, lecture des flags PSP) vit dans **`app/payment_utils.py`**. **`main`** et les routes web/API importent depuis ce module pour éviter les doublons.

## Limitations actuelles

- **Extension de temps** après session : flux **Paystack uniquement** ; si seul CinetPay est configuré pour l’extension, l’API renvoie **501** (message explicite).
