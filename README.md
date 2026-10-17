# PokéAlerte

Une page unique + un script qui tourne gratuitement toutes les 15 minutes sur GitHub Actions.
Vous recevez une notification sur votre téléphone (app ntfy) et/ou par email pour :

- les **sorties** Pokémon (rappel J-7, J-1 et jour J),
- les **actus** (flux Google Actualités, filtré sur Pokémon),
- les **restocks** des pages produits que vous surveillez.

## Mise en route (≈ 10 minutes)

1. **Créez un dépôt GitHub** (public pour GitHub Pages gratuit) et déposez-y tout ce dossier.
2. **Choisissez un nom de sujet ntfy secret**, par exemple `pokealerte-k8f3x92` (difficile à deviner : c'est votre « mot de passe »).
   Installez l'app **ntfy** sur votre téléphone et abonnez-vous à ce sujet.
3. Dans le dépôt : *Settings → Secrets and variables → Actions → New repository secret* :
   - `NTFY_TOPIC` : votre nom de sujet (obligatoire pour les notifs push)
   - Optionnel, pour les emails : `SMTP_HOST`, `SMTP_PORT` (465), `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`
     (fonctionne avec Gmail via un « mot de passe d'application », ou avec Brevo / Resend).
4. *Settings → Pages* : source = branche `main`, dossier `/ (root)`. Votre page sera en ligne.
5. Onglet *Actions* : lancez une première fois « Surveillance Pokémon » avec *Run workflow*. Ensuite c'est automatique.

## Personnaliser : `config.json`

- `releases` : ajoutez les dates de sortie (`"date": "AAAA-MM-JJ"`).
- `products` : pour chaque produit, collez le lien de la page et ajustez les phrases qui signalent
  « en stock » / « rupture » (regardez le texte de la page chez l'enseigne).
  Pensez aux pages de retrait en magasin des enseignes proches de chez vous (Clermont-Ferrand, Riom, Issoire, Thiers…).
- `news_feeds` : vous pouvez ajouter d'autres flux RSS.

## Limites à connaître

- Le stock **en rayon** n'est pas publié par la plupart des enseignes : la détection est fiable surtout pour la vente en ligne et le retrait en magasin.
- Certains sites bloquent les robots (la page revient en erreur) : l'état affiché sera alors « Erreur » ou « Inconnu ».
- GitHub Actions peut décaler une exécution de quelques minutes ; l'intervalle réel est donc d'environ 15 à 30 minutes.
- Après 60 jours sans activité sur le dépôt, GitHub peut suspendre les exécutions planifiées ; les commits automatiques du script évitent normalement ce cas.

## Tester en local

```bash
NTFY_TOPIC=votre-sujet python3 monitor.py
```
