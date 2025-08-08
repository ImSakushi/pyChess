PyChess Online Multiplayer / Multijoueur en ligne
=================================================

Ce projet inclut un petit serveur WebSocket et un mode en ligne optionnel pour le client Pygame. Vous pouvez héberger une partie (obtenir un code) et un ami peut rejoindre avec ce code pour jouer en direct.

Vue d’ensemble
--------------
- Serveur: FastAPI + WebSockets (salles en mémoire) dans `server/server.py`.
- Client: `main.py` accepte `--online` pour créer/rejoindre et relaie les coups via WebSocket.
- Protocole: messages JSON simples; pas de comptes, pas de persistance.

Lancer en local
---------------
1) Démarrer le serveur:
   - `python -m venv venv && source venv/bin/activate` (Windows: `venv\\Scripts\\activate`)
   - `pip install -r server/requirements.txt`
   - `uvicorn server.server:app --host 0.0.0.0 --port 8000`

   Santé du serveur: http://localhost:8000/ et WebSocket: `ws://localhost:8000/ws`.

2) Démarrer l’hôte (Blanc par défaut):
   - Dans un autre terminal: `pip install websockets`
   - `python main.py --online --server ws://localhost:8000/ws`
   - Le client affiche: `Hosting game. Share code: ABC123 ...`

3) Démarrer le client « ami » (rejoindre):
   - `python main.py --online --server ws://localhost:8000/ws --join ABC123`

Notes
-----
- Les Blancs commencent; le client force l’ordre des tours par couleur.
- Si l’adversaire se déconnecte, un message s’affiche; vous pouvez continuer en local ou redémarrer.
- Sans `--online`, le jeu reste strictement local (inchangé).

Hébergement gratuit (Render)
----------------------------
Render.com propose un palier gratuit compatible WebSockets. Deux options:

Option A — Utiliser `render.yaml` (recommandé)
1) Poussez ce dossier sur GitHub.
2) Sur Render, « New + » → « Blueprint » et pointez sur votre repo.
3) Render détecte `render.yaml` et crée le service web.
4) Déployez. L’URL ressemblera à `https://<votre-app>.onrender.com`.
5) Client Web prêt à l’emploi: ouvrez `https://<votre-app>.onrender.com` dans le navigateur (les images sont servies depuis `/images`).
6) Pour jouer sans installer quoi que ce soit:
   - Un joueur clique « Héberger » et partage le code affiché.
   - L’ami entre le code et clique « Rejoindre » — jouez directement dans le navigateur.
7) Pour rester compatible avec l’ancien client desktop, vous pouvez toujours utiliser:
   - Hôte: `python main.py --online --server wss://<votre-app>.onrender.com/ws`
   - Ami:  `python main.py --online --server wss://<votre-app>.onrender.com/ws --join ABC123`

Option B — Créer manuellement le service web
1) « New + » → « Web Service » depuis votre repo GitHub.
2) Paramètres avancés:
   - Root Directory: ce dossier (si vous déployez à la racine du repo, laissez `.`)
   - Build Command: `pip install -r server/requirements.txt`
   - Start Command: `uvicorn server.server:app --host 0.0.0.0 --port $PORT`
3) Déployez, puis utilisez `wss://<votre-app>.onrender.com/ws` côté client.

Astuces pratiques
-----------------
- Variable d’environnement: vous pouvez définir `WS_SERVER_URL` et lancer sans `--server`:
  `WS_SERVER_URL=wss://<votre-app>.onrender.com/ws python main.py --online`
- Production: utilisez `wss://` (TLS) ; en local, `ws://`.
- Dépendances client: `pip install websockets` (le serveur a ses propres deps dans `server/requirements.txt`).

Dépannage
---------
- Erreurs de connexion: assurez-vous que l’URL se termine par `/ws` et que le protocole est correct.
- Démarrage à froid Render: la première connexion après inactivité peut prendre 30–60s.

Sécurité & limites
------------------
- Salles en mémoire et éphémères; pas de BDD ni authentification.
- Codes à 6 caractères (A–Z, 0–9); pas garantis uniques entre redémarrages.
- Pour durcir: base de données, codes plus longs, et rate limiting.
