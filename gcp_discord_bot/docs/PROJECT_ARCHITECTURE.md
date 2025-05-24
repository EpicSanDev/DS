# Architecture du Projet : Bot Discord GCP pour Serveurs de Jeux

## 1. Vue d'ensemble

Ce document décrit l'architecture du bot Discord conçu pour le provisionnement et la gestion automatisée de machines virtuelles (VMs) sur Google Cloud Platform (GCP), spécifiquement pour l'hébergement de serveurs de jeux. Le bot utilise les slash commands Discord et est prévu pour un déploiement sur Railway.

## 2. Structure du Projet

Le projet est structuré de la manière suivante :

-   `src/`: Contient le code source principal du bot.
    -   `bot.py`: Point d'entrée de l'application, initialisation du bot et chargement des Cogs.
    -   `cogs/`: Modules (Cogs) contenant la logique des commandes et des fonctionnalités.
        -   `admin_cog.py`: Commandes d'administration du bot (gestion des Cogs, ping, etc.).
        -   `gcp_cog.py`: Commandes et logique pour interagir directement avec l'API GCP (VMs, pare-feu).
        -   `gameserver_cog.py`: Commandes et logique pour la gestion de haut niveau des serveurs de jeux (utilisation de templates, orchestration des opérations GCP).
        -   `db_cog.py`: Gestion de la base de données (SQLAlchemy), définition des tables et méthodes d'accès.
    -   `core/`: Composants centraux.
        -   `settings.py`: Chargement et gestion de la configuration (depuis `config.ini` et variables d'environnement).
    -   `utils/`: Utilitaires.
        -   `logger.py`: Configuration et initialisation du logging.
        -   `permissions.py`: Décorateurs et fonctions pour la gestion des permissions basées sur les rôles Discord.
-   `config/`: Fichiers de configuration.
    -   `config.ini`: Configuration principale du bot (tokens, IDs GCP, paramètres de la DB, limites d'abus).
    -   `logging_config.ini`: Configuration détaillée du logging (handlers, formateurs, niveaux).
    -   `gcp_key.example.json`: Exemple de fichier pour la clé de compte de service GCP (si utilisée localement).
    -   `game_server_templates.json`: Définitions des modèles de serveurs de jeux.
-   `data/`: (Créé par le bot) Contient la base de données SQLite par défaut et potentiellement d'autres données persistantes.
-   `logs/`: (Créé par le bot) Contient les fichiers de log générés.
-   `docs/`: Documentation du projet.
-   `Dockerfile`: Instructions pour construire l'image Docker du bot pour le déploiement.
-   `railway.json`: Configuration spécifique pour le déploiement sur Railway.
-   `requirements.txt`: Dépendances Python du projet.

## 3. Composants Principaux (Cogs)

### 3.1. `AdminCog`
-   Responsable des commandes d'administration du bot.
-   Permet de charger, décharger, et recharger dynamiquement d'autres Cogs.
-   Inclut des commandes de diagnostic de base (ex: `/ping`).
-   Accès généralement restreint aux propriétaires du bot.

### 3.2. `GcpCog`
-   Fournit une abstraction pour les interactions directes avec les APIs Google Cloud.
-   Utilise la bibliothèque `google-cloud-compute`.
-   Fonctionnalités :
    -   Création, listage, description, démarrage, arrêt, suppression de VMs Compute Engine.
    -   Gestion des règles de pare-feu GCP (création, listage, suppression).
    -   Récupération des logs du port série des VMs.
-   Gère l'initialisation des clients GCP et l'authentification (via compte de service).
-   Implémente la logique d'attente pour les opérations GCP de longue durée.

### 3.3. `GameServerCog`
-   Orchestre la création et la gestion des serveurs de jeux.
-   S'appuie sur `GcpCog` pour les opérations sur les VMs et les pare-feux.
-   S'appuie sur `DBCog` pour enregistrer et suivre l'état des serveurs de jeux.
-   Fonctionnalités :
    -   Listage des templates de serveurs de jeux disponibles (depuis `config/game_server_templates.json`).
    -   Création de serveurs de jeux :
        -   Provisionnement de la VM via `GcpCog` en utilisant les spécifications du template.
        -   Application d'un script de démarrage (`startup-script`) pour installer et configurer le jeu.
        -   Configuration automatique des règles de pare-feu nécessaires pour le jeu, en utilisant des tags spécifiques à l'instance.
    -   Listage des serveurs de jeux actifs pour un utilisateur.
    -   Obtention du statut d'un serveur de jeu.
    -   Démarrage, arrêt, et suppression d'un serveur de jeu (incluant la VM et les règles de pare-feu associées).
-   Intègre des vues de confirmation pour les actions destructrices.

### 3.4. `DBCog`
-   Gère toutes les interactions avec la base de données.
-   Utilise SQLAlchemy comme ORM.
-   Définit les modèles de données :
    -   `UserUsage`: Pour tracer l'utilisation des commandes par les utilisateurs (utile pour le rate limiting et l'analyse d'abus).
    -   `GameServerInstance`: Pour stocker les détails de chaque serveur de jeu provisionné (propriétaire, nom GCP, ID GCP, zone, template, statut, IP, ports, dates, configuration additionnelle).
-   Fonctionnalités :
    -   Initialisation de la base de données et création des tables.
    -   Journalisation de l'utilisation des commandes.
    -   Mécanisme de rate limiting pour les commandes (basé sur `UserUsage`).
    -   CRUD (Create, Read, Update, Delete) pour les `GameServerInstance`.
    -   Récupération des serveurs actifs par utilisateur.

## 4. Gestion de la Configuration (`settings.py`)

-   Centralise l'accès aux paramètres de configuration.
-   Charge la configuration depuis `config/config.ini`.
-   Permet la surcharge des paramètres via des variables d'environnement (prioritaire), ce qui est crucial pour les déploiements sur des plateformes comme Railway.
-   Fournit des fonctions d'assistance (getters) pour récupérer les valeurs de configuration de manière typée et avec des valeurs par défaut.
-   Gère la construction dynamique de l'URL de la base de données (priorité à `DATABASE_URL` pour les DB managées, sinon SQLite local).
-   Initialise les paramètres de prévention des abus (limites de commandes, nombre de VMs, cooldowns).

## 5. Interaction avec GCP

-   **Authentification**: Principalement via un fichier de clé de compte de service GCP (JSON). Le chemin du fichier ou le contenu JSON lui-même peut être spécifié via `config.ini` ou des variables d'environnement (`GCP_SERVICE_ACCOUNT_FILE`, `GCP_SERVICE_ACCOUNT_KEY_JSON`). Application Default Credentials (ADC) est également une option.
-   **Bibliothèques Client**: `google-cloud-compute` pour interagir avec l'API Compute Engine.
-   **Clients API**:
    -   `InstancesClient`: Pour la gestion des VMs.
    -   `FirewallsClient`: Pour la gestion des règles de pare-feu.
    -   `ZoneOperationsClient` / `GlobalOperationsClient`: Pour suivre l'état des opérations asynchrones de GCP.
    -   `ImagesClient`: Pour récupérer les dernières images OS à partir d'une famille d'images.
-   **Ressources Gérées**:
    -   Instances Compute Engine (VMs).
    -   Disques persistants (implicitement, attachés aux VMs et généralement configurés pour suppression automatique avec la VM).
    -   Règles de pare-feu VPC.
    -   Tags réseau (utilisés pour appliquer les règles de pare-feu aux bonnes VMs).

## 6. Gestion des Données (`DBCog` et SQLAlchemy)

-   **ORM**: SQLAlchemy est utilisé pour mapper les objets Python aux tables de la base de données.
-   **Base de Données Supportée**: Configuré pour SQLite par défaut (fichier local dans `data/bot_database.db`), mais peut utiliser toute base de données supportée par SQLAlchemy si une `DATABASE_URL` est fournie (ex: PostgreSQL sur Railway).
-   **Tables Principales**:
    -   `UserUsage`:
        -   `id` (PK), `user_id` (Discord), `command_name`, `timestamp`, `details`.
    -   `GameServerInstance`:
        -   `id` (PK), `discord_user_id`, `gcp_instance_name` (unique), `gcp_instance_id` (unique), `gcp_zone`, `game_template_name`, `status`, `ip_address`, `ports_info` (JSON), `created_at`, `last_status_update`, `additional_config` (JSON).
-   **Fonctionnalités du `DBCog`**:
    -   Enregistrement de chaque serveur de jeu créé avec ses métadonnées.
    -   Mise à jour du statut des serveurs (ex: RUNNING, STOPPED, DELETED).
    -   Suivi de l'utilisateur Discord propriétaire de chaque serveur.
    -   Suppression (logique ou physique) des enregistrements de serveurs.
    -   Comptage des serveurs actifs par utilisateur pour les limites d'abus.
    -   Enregistrement de l'utilisation des commandes pour le rate limiting.

## 7. Flux de Commande Important : Création d'un Serveur de Jeu (`/gameserv_create`)

1.  L'utilisateur exécute `/gameserv_create <template_name> <instance_name> [options]`.
2.  `GameServerCog` reçoit la commande.
3.  **Vérifications initiales**:
    -   Validité du template.
    -   Permissions de l'utilisateur (via décorateur `@permissions.has_vm_operator_role()`).
    -   Limites d'abus (nombre max de VMs actives, cooldown de création - nécessite `DBCog`).
4.  Le bot répond avec un message de "thinking" ou "processing".
5.  `GameServerCog` charge les détails du template depuis `game_server_templates.json`.
6.  Prépare les paramètres pour la VM GCP (type de machine, image, disque, script de démarrage formaté avec les `custom_params_json`).
7.  Appelle `GcpCog._create_vm_logic()` pour provisionner la VM.
    -   `GcpCog` construit la configuration de l'instance GCP.
    -   `GcpCog` initie l'opération de création de VM et attend sa complétion.
8.  Une fois la VM créée et démarrée, `GameServerCog` récupère son adresse IP.
9.  `GameServerCog` configure les règles de pare-feu nécessaires (via `GcpCog._open_port_logic()`) en utilisant un tag réseau unique pour cette instance (ex: `gameserv-<instance_name>`).
10. `GameServerCog` enregistre les informations du nouveau serveur (nom de l'instance GCP, ID utilisateur Discord, template, IP, statut "RUNNING", etc.) dans la base de données via `DBCog.register_game_server()`.
11. Le bot envoie un message de confirmation à l'utilisateur avec les détails du serveur (IP, ports).
12. Le script de démarrage s'exécute sur la VM pour installer et configurer le serveur de jeu.

## 8. Sécurité et Permissions

-   **Permissions Basées sur les Rôles Discord**:
    -   Le module `src/utils/permissions.py` définit des décorateurs de vérification (ex: `@has_vm_operator_role()`, `@can_control_game_server()`).
    -   Ces décorateurs sont utilisés sur les commandes slash pour restreindre l'accès en fonction des rôles Discord configurés dans `config.ini` (ex: `owner_ids`, `game_admin_role_id`, `vm_operator_role_id`).
-   **Protection des Secrets**:
    -   Le token Discord et la clé de service GCP sont gérés via `config.ini` et peuvent être surchargés par des variables d'environnement, ce qui est la méthode recommandée pour le déploiement.
-   **Prévention des Abus**:
    -   **Rate Limiting**: `DBCog` implémente un rate limiting global pour les commandes (configurable via `max_commands_per_minute` dans `settings.py`). Une méthode `check_app_command_rate_limit` est disponible pour être utilisée avec les commandes slash.
    -   **Limites de Ressources**:
        -   `max_active_vms_per_user`: Limite le nombre de serveurs de jeux qu'un utilisateur peut avoir actifs simultanément. Vérifié dans `GameServerCog` avant la création.
        -   `vm_creation_cooldown_seconds`: Impose un délai minimum entre les créations de VMs par un même utilisateur. (À implémenter complètement dans `GameServerCog` en utilisant `DBCog`).
    -   **Validation des Entrées**: Les types de paramètres des commandes slash sont spécifiés (ex: `app_commands.Range` pour les ports). Une validation supplémentaire pour les chaînes (noms d'instance, etc.) est nécessaire pour correspondre aux contraintes GCP.

## 9. Déploiement (Railway)

-   **Dockerfile**: Définit l'environnement d'exécution du bot (Python, installation des dépendances depuis `requirements.txt`, copie du code source, point d'entrée `src/bot.py`).
-   **`railway.json`**: Peut contenir des configurations spécifiques à Railway pour le build et le déploiement (ex: commandes de démarrage, variables d'environnement de build).
-   **Variables d'Environnement**: La configuration du bot est conçue pour être largement pilotée par des variables d'environnement sur Railway (Token Discord, ID Projet GCP, Clé de service GCP JSON, URL de la base de données managée par Railway, etc.).

## 10. Logging

-   Un module `src/utils/logger.py` configure le logging pour l'application.
-   La configuration détaillée du logging (format, niveau, handlers pour console/fichier) est dans `config/logging_config.ini`.
-   Les logs sont écrits dans le dossier `logs/` par défaut.
-   Différents niveaux de log (INFO, WARNING, ERROR, DEBUG) sont utilisés à travers le code pour tracer l'exécution et diagnostiquer les problèmes.

## 11. Templates de Serveurs de Jeux

-   Le fichier `config/game_server_templates.json` définit les modèles pour différents types de serveurs de jeux.
-   Chaque template spécifie :
    -   `display_name`: Nom affiché à l'utilisateur.
    -   `image_project`, `image_family`: Image OS GCP à utiliser.
    -   `machine_type`, `disk_size_gb`: Spécifications de la VM.
    -   `default_ports`: Liste des ports à ouvrir (avec protocole et description) pour ce jeu.
    -   `startup_script_template`: Modèle de script bash qui sera exécuté au premier démarrage de la VM pour installer et configurer le jeu. Peut utiliser des placeholders (ex: `{max_ram}`) qui sont remplis à partir des `config_params`.
    -   `config_params`: Liste des paramètres configurables par l'utilisateur pour ce template (avec nom, description, valeur par défaut).
-   Ce système permet d'étendre facilement le support à de nouveaux jeux en ajoutant des entrées à ce fichier JSON.

---

Ce document fournit une base. Il pourra être enrichi avec des diagrammes (Mermaid) et plus de détails au fur et à mesure de l'implémentation des fonctionnalités restantes.
