# GCP Discord Bot pour Serveurs de Jeux

## Introduction
Ce bot Discord avancé permet le provisionnement et la gestion automatisée de machines virtuelles (VMs) sur Google Cloud Platform (GCP), spécifiquement configurées pour héberger divers serveurs de jeux. Il utilise les slash commands Discord pour une interface utilisateur moderne.

## Fonctionnalités Actuelles
- **Gestion de VMs GCP** : Création, listing, description, démarrage, arrêt, suppression.
- **Gestion de Pare-feu GCP** : Ouverture de ports, listing, suppression de règles.
- **Système de Templates de Serveurs de Jeux** : Définissez des modèles pour déployer rapidement des jeux (ex: Minecraft).
- **Gestion Basique des Serveurs de Jeux** : Création de serveurs de jeux basés sur les templates, listing des serveurs, affichage de statut.
- **Journalisation des Actions** : Les actions du bot et les interactions avec l'API GCP sont journalisées.
- **Base de Données** : Suivi de l'utilisation des commandes et des instances de serveurs de jeux.
- **Permissions Basées sur les Rôles** : Contrôle d'accès pour les commandes sensibles (propriétaire du bot, rôles configurables).
- **Configuration Flexible** : Via `config.ini` et variables d'environnement.
- **Déploiement sur Railway** : Prêt pour un déploiement simplifié via Docker.

## Prérequis
- Python 3.10+
- Compte Discord avec les permissions de création de bot.
- Compte Google Cloud Platform avec un projet configuré et la facturation activée.
  - API Compute Engine activée.
  - Un compte de service GCP avec les permissions nécessaires (ex: "Compute Admin", "Service Account User").
- Docker (pour le déploiement ou le développement local).
- `config/game_server_templates.json` configuré avec vos modèles de serveurs de jeux.

## Installation
1. Clonez le dépôt : `git clone <URL_DU_DEPOT>`
2. Naviguez dans le dossier : `cd gcp_discord_bot`
3. Créez un environnement virtuel : `python -m venv venv`
4. Activez l'environnement :
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`
5. Installez les dépendances : `pip install -r requirements.txt`

## Configuration
1.  **Fichier de Configuration Principal** :
    *   Copiez `config/config.example.ini` vers `config/config.ini`.
    *   Remplissez `config/config.ini` avec vos informations :
        *   `[discord]`: `token`, `owner_ids`, `game_admin_role_id`, `vm_operator_role_id`.
            *   Les `owner_ids` sont les IDs Discord des propriétaires du bot.
            *   Les `*_role_id` sont les IDs des rôles Discord pour les permissions. Obtenez-les via Discord (Server Settings -> Roles -> Clic droit sur le rôle -> Copy ID).
        *   `[gcp]`: `project_id`, `default_zone`.
        *   `[database]`: Chemin pour la base de données SQLite ou URL pour d'autres DBs.
        *   `[bot_settings]`: `log_level`, `timezone`.
        *   `[abuse_prevention]`: Configurez les limites pour prévenir les abus.
2.  **Clé de Compte de Service GCP** :
    *   Option A (Recommandé pour Railway/variables d'environnement) :
        1.  Créez un compte de service dans GCP IAM & Admin.
        2.  Donnez-lui les rôles nécessaires (ex: Compute Admin).
        3.  Créez une clé JSON pour ce compte de service.
        4.  Définissez la variable d'environnement `GCP_SERVICE_ACCOUNT_KEY_JSON` avec le **contenu complet** du fichier JSON.
    *   Option B (Fichier local) :
        1.  Copiez `config/gcp_key.example.json` vers `config/gcp_key.json`.
        2.  Collez le contenu de votre clé de compte de service GCP (format JSON) dans `config/gcp_key.json`.
        3.  Assurez-vous que `service_account_file` dans `config.ini` pointe vers ce fichier, ou définissez `GCP_SERVICE_ACCOUNT_FILE` comme variable d'environnement.
    *   Option C (Application Default Credentials) : Si vous exécutez le bot dans un environnement GCP (ex: GCE, Cloud Run) ou avez configuré ADC localement (`gcloud auth application-default login`), le bot tentera de les utiliser.
3.  **Templates de Serveurs de Jeux** :
    *   Copiez `config/game_server_templates.example.json` (s'il existe, sinon créez `config/game_server_templates.json` basé sur l'exemple dans `GameServerCog`).
    *   Modifiez `config/game_server_templates.json` pour définir les jeux que vous voulez supporter. Chaque template inclut des détails GCP (image, type de machine) et un script de démarrage.
4.  **Configuration du Logging** :
    *   Modifiez `config/logging_config.ini` pour ajuster les niveaux de log, les handlers, etc. Par défaut, les logs sont créés dans le dossier `logs/`.

## Utilisation
Exécutez le bot : `python src/bot.py`
Invitez le bot sur votre serveur Discord. Assurez-vous qu'il a les permissions nécessaires pour lire les messages, envoyer des messages, et gérer les slash commands.

## Déploiement sur Railway
Le projet est configuré pour un déploiement facile sur Railway via le `Dockerfile` et `railway.json`.
1. Poussez votre code sur un dépôt GitHub.
2. Créez un nouveau projet sur Railway et connectez-le à votre dépôt GitHub.
3. Railway devrait détecter le `Dockerfile` et construire/déployer l'application.
4. Configurez les variables d'environnement nécessaires sur Railway :
   - `DISCORD_TOKEN`
   - `GCP_PROJECT_ID`
   - `GCP_SERVICE_ACCOUNT_KEY_JSON` (recommandé de coller le contenu JSON directement)
   - `OWNER_IDS`
   - `GAME_ADMIN_ROLE_ID`
   - `VM_OPERATOR_ROLE_ID`
   - `DATABASE_URL` (si vous utilisez une base de données managée par Railway, sinon le bot utilisera SQLite dans le volume persistant)
   - Autres configurations de `config.ini` peuvent aussi être passées en variables d'environnement (ex: `LOG_LEVEL`).

## Déploiement sur Railway
Le projet est configuré pour un déploiement facile sur Railway via le `Dockerfile` et `railway.json`.
1. Poussez votre code sur un dépôt GitHub.
2. Créez un nouveau projet sur Railway et connectez-le à votre dépôt GitHub.
3. Railway devrait détecter le `Dockerfile` et construire/déployer l'application.
4. Configurez les variables d'environnement nécessaires sur Railway :
   - `DISCORD_TOKEN`
   - `GCP_PROJECT_ID`
   - `GCP_SERVICE_ACCOUNT_KEY_JSON` (recommandé de coller le contenu JSON directement)
   - `OWNER_IDS`
   - `GAME_ADMIN_ROLE_ID`
   - `VM_OPERATOR_ROLE_ID`
   - `DATABASE_URL` (si vous utilisez une base de données managée par Railway, sinon le bot utilisera SQLite dans le volume persistant)
   - Autres configurations de `config.ini` peuvent aussi être passées en variables d'environnement (ex: `LOG_LEVEL`).

## Personnalisation Avancée des Serveurs de Jeux

Le système de templates de serveurs de jeux (`config/game_server_templates.json`) permet une personnalisation poussée via le `startup_script_template` et les `config_params`.

### `config_params`
Chaque template peut définir une liste de `config_params`. Ce sont les paramètres que les utilisateurs peuvent surcharger via l'option `custom_params_json` de la commande `/gameserv_create`.
Chaque `config_param` devrait avoir :
- `name`: Le nom de la variable (utilisé comme clé dans `custom_params_json` et dans le `startup_script_template`).
- `description`: Une description pour l'utilisateur.
- `default`: Une valeur par défaut utilisée si l'utilisateur ne fournit pas ce paramètre.

### `startup_script_template`
C'est un script (généralement bash) qui s'exécute au premier démarrage de la VM. Il est responsable de l'installation et de la configuration du serveur de jeu.
- **Utilisation des paramètres** : Vous pouvez injecter les valeurs des `config_params` (ou celles fournies par `custom_params_json`) dans votre script en utilisant la syntaxe de formatage Python, par exemple `{nom_du_parametre}`. Il est recommandé d'utiliser des valeurs par défaut robustes dans le script lui-même au cas où un paramètre ne serait pas fourni (ex: `VARIABLE="{nom_du_parametre:-valeur_par_defaut_script}"`).
- **Exemple de fonctionnalités avancées à implémenter dans le script**:
    - **Téléchargement de version spécifique du jeu**: Utiliser `wget` ou `curl` avec une URL construite à partir d'un paramètre `game_version`.
    - **Installation de mods/plugins**: Si `custom_params_json` contient une liste d'URLs de mods (ex: `{"mods_list_json": "[{\"name\":\"Mod1\",\"url\":\"http://...\"}]"}`), le script peut parser ce JSON (avec `jq` par exemple) et télécharger chaque mod.
    - **Application de configurations serveur**: Télécharger un fichier de configuration complet (ex: `server.properties`) depuis une URL fournie via `custom_params_json`, ou générer le fichier dynamiquement en utilisant les `config_params`.
    - **Gestion de l'EULA**: Forcer l'acceptation de l'EULA via un paramètre (ex: `eula_accepted=true`).

### Exemple `custom_params_json` pour `/gameserv_create`
Pour un template Minecraft qui utilise les `config_params` de l'exemple enrichi :
`{"server_version":"1.19.4", "max_ram":"4096", "eula_accepted":"true", "server_name":"Mon Super Serveur!", "mods_list_json":"[{\"name\":\"Optifine\",\"url\":\"https://optifine.net/downloads\"}, {\"name\":\"JourneyMap\",\"url\":\"https://journeymap.info/downloads\"}]"}`
*(Note: Les URLs des mods sont des exemples et doivent pointer vers des fichiers JAR directs.)*

En combinant intelligemment les `config_params`, `custom_params_json`, et la logique dans `startup_script_template`, vous pouvez offrir un déploiement très flexible et personnalisé pour divers serveurs de jeux.

## Structure du Projet
- `src/`: Code source du bot.
  - `bot.py`: Point d'entrée principal, chargement des cogs.
  - `cogs/`: Modules (Cogs) contenant les commandes.
    - `admin_cog.py`: Commandes d'administration du bot.
    - `gcp_cog.py`: Commandes pour la gestion directe des ressources GCP.
    - `gameserver_cog.py`: Commandes pour la gestion des serveurs de jeux.
    - `db_cog.py`: Gestion de la base de données et des tables (SQLAlchemy).
  - `core/`: Logique principale et configuration.
    - `settings.py`: Chargement et accès aux configurations.
  - `utils/`: Utilitaires.
    - `logger.py`: Configuration du logging.
    - `permissions.py`: Décorateurs et fonctions pour la gestion des permissions.
- `config/`: Fichiers de configuration.
  - `config.ini`: Configuration principale.
  - `logging_config.ini`: Configuration du logging.
  - `gcp_key.json`: (Optionnel) Clé de compte de service GCP.
  - `game_server_templates.json`: Définitions des templates de serveurs de jeux.
- `data/`: (Créé par le bot) Pour la base de données SQLite et autres données.
- `logs/`: (Créé par le bot) Fichiers de log.
- `Dockerfile`: Pour la conteneurisation.
- `railway.json`: Configuration pour le déploiement sur Railway.
- `requirements.txt`: Dépendances Python.
- `docs/`: Documentation additionnelle (ex: `PROJECT_ARCHITECTURE.md`).

## Commandes Disponibles (Slash Commands)

### Administration du Bot (`AdminCog`)
- `/ping` (préfixée, propriétaire uniquement): Vérifie la latence du bot.
- `/admin_test`: Commande de test pour admin avec rate limiting.
- `/load_cog <cog_name>` (Propriétaire uniquement): Charge une extension.
- `/unload_cog <cog_name>` (Propriétaire uniquement): Décharge une extension.
- `/reload_cog <cog_name>` (Propriétaire uniquement): Recharge une extension.

### Gestion GCP (`GcpCog`)
- `/gcp_create_vm <instance_name> [machine_type] [image_project] [image_family] [disk_size_gb] [zone] [startup_script] [tags]` (VM Operator+): Crée une nouvelle VM.
- `/gcp_list_vms [zone]`: Liste les VMs.
- `/gcp_describe_vm <instance_name> [zone]`: Décrit une VM spécifique.
- `/gcp_start_vm <instance_name> [zone]` (VM Operator+): Démarre une VM.
- `/gcp_stop_vm <instance_name> [zone]` (VM Operator+): Arrête une VM.
- `/gcp_delete_vm <instance_name> [zone]` (VM Operator+): Supprime une VM (irréversible!).
- `/gcp_open_port <firewall_rule_name> <target_tag> <port> [protocol] [description]` (VM Operator+): Ouvre un port dans le pare-feu.
- `/gcp_list_firewall_rules`: Liste les règles de pare-feu.
- `/gcp_delete_firewall_rule <firewall_rule_name>` (VM Operator+): Supprime une règle de pare-feu (irréversible!).

### Gestion des Serveurs de Jeux (`GameServerCog`)
- `/gameserv_list_templates`: Liste les templates de serveurs de jeux disponibles.
- `/gameserv_create <template_name> <instance_name> [zone] [custom_params_json]` (VM Operator+): Crée un nouveau serveur de jeu basé sur un template.
- `/gameserv_list`: Liste vos serveurs de jeux provisionnés.
- `/gameserv_status <instance_name>`: Affiche le statut d'un serveur de jeu spécifique.
- `/gameserv_start <instance_name>` (Propriétaire du serveur/Game Admin+): Démarre un serveur de jeu.
- `/gameserv_stop <instance_name>` (Propriétaire du serveur/Game Admin+): Arrête un serveur de jeu.
- `/gameserv_delete <instance_name>` (Propriétaire du serveur/Game Admin+): Supprime un serveur de jeu et sa VM (irréversible!).

*(Note: "VM Operator+" signifie que le rôle VM Operator, Game Admin, ou propriétaire du bot peut utiliser la commande. "Propriétaire du serveur/Game Admin+" signifie que le créateur du serveur, un Game Admin, ou un propriétaire du bot peut utiliser la commande.)*

## Contribution
Les contributions sont les bienvenues. Veuillez ouvrir une issue pour discuter des changements majeurs ou soumettre une Pull Request pour les corrections et améliorations.

## Licence
Ce projet est sous licence MIT.
