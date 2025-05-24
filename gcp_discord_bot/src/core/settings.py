import configparser
import os
from dotenv import load_dotenv

load_dotenv() # Charge les variables depuis .env s'il existe

config = configparser.ConfigParser()

# Chemin vers le fichier de configuration principal
CONFIG_FILE_PATH = 'config/config.ini'
# Chemin vers le fichier de clé GCP (peut être surchargé par une variable d'env)
GCP_KEY_FILE_PATH = 'config/gcp_key.json'
# Dossier pour la base de données et autres données persistantes
DATA_DIR = 'data/'


def load_config():
    """Charge la configuration depuis config.ini (optionnel) et les variables d'environnement."""
    if os.path.exists(CONFIG_FILE_PATH):
        config.read(CONFIG_FILE_PATH)
        print(f"Fichier de configuration '{CONFIG_FILE_PATH}' chargé.")
        # logger.info(f"Fichier de configuration '{CONFIG_FILE_PATH}' chargé.")
    else:
        print(f"AVERTISSEMENT: Fichier de configuration '{CONFIG_FILE_PATH}' introuvable. Utilisation prioritaire des variables d'environnement et des valeurs par défaut.")
        # logger.warning(f"Fichier de configuration '{CONFIG_FILE_PATH}' introuvable. Utilisation prioritaire des variables d'environnement et des valeurs par défaut.")

    # S'assurer que les sections existent pour les appels .set() et .get() suivants,
    # même si config.ini n'a pas été lu ou était incomplet.
    sections_to_ensure = ['discord', 'gcp', 'database', 'bot_settings', 'abuse_prevention', 'pterodactyl']
    for section_name in sections_to_ensure:
        if not config.has_section(section_name):
            config.add_section(section_name)

    # Surcharger avec les variables d'environnement si elles existent
    # Discord
    config.set('discord', 'token', os.getenv('DISCORD_TOKEN', config.get('discord', 'token', fallback=None)))
    config.set('discord', 'prefix', os.getenv('BOT_PREFIX', config.get('discord', 'prefix', fallback='!')))
    owner_ids_str = os.getenv('OWNER_IDS', config.get('discord', 'owner_ids', fallback=''))
    config.set('discord', 'owner_ids', owner_ids_str)
    config.set('discord', 'game_admin_role_id', os.getenv('GAME_ADMIN_ROLE_ID', config.get('discord', 'game_admin_role_id', fallback='')))
    config.set('discord', 'vm_operator_role_id', os.getenv('VM_OPERATOR_ROLE_ID', config.get('discord', 'vm_operator_role_id', fallback='')))


    # GCP
    config.set('gcp', 'project_id', os.getenv('GCP_PROJECT_ID', config.get('gcp', 'project_id', fallback=None)))
    config.set('gcp', 'default_zone', os.getenv('GCP_DEFAULT_ZONE', config.get('gcp', 'default_zone', fallback='europe-west1-b')))
    # Pour la clé de service, la variable d'env `GCP_SERVICE_ACCOUNT_KEY_JSON` (contenant le JSON)
    # ou `GCP_SERVICE_ACCOUNT_FILE` (contenant le chemin vers le fichier) est souvent préférée.
    # Le fichier config.ini peut spécifier un chemin par défaut.
    config.set('gcp', 'service_account_file', os.getenv('GCP_SERVICE_ACCOUNT_FILE', config.get('gcp', 'service_account_file', fallback=GCP_KEY_FILE_PATH)))

    # Database
    db_path_env = os.getenv('DATABASE_PATH', config.get('database', 'path', fallback=os.path.join(DATA_DIR, 'bot_database.db')))
    config.set('database', 'path', db_path_env)


    # Bot Settings
    config.set('bot_settings', 'log_level', os.getenv('LOG_LEVEL', config.get('bot_settings', 'log_level', fallback='INFO')))
    config.set('bot_settings', 'timezone', os.getenv('TIMEZONE', config.get('bot_settings', 'timezone', fallback='UTC')))

    # Abuse Prevention Settings
    config.add_section('abuse_prevention') # Ensure section exists for set operations
    config.set('abuse_prevention', 'max_commands_per_minute', os.getenv('MAX_COMMANDS_PER_MINUTE', config.get('abuse_prevention', 'max_commands_per_minute', fallback='20')))
    config.set('abuse_prevention', 'max_active_vms_per_user', os.getenv('MAX_ACTIVE_VMS_PER_USER', config.get('abuse_prevention', 'max_active_vms_per_user', fallback='2')))
    config.set('abuse_prevention', 'max_total_vms_managed_per_user', os.getenv('MAX_TOTAL_VMS_MANAGED_PER_USER', config.get('abuse_prevention', 'max_total_vms_managed_per_user', fallback='5')))
    config.set('abuse_prevention', 'vm_creation_cooldown_seconds', os.getenv('VM_CREATION_COOLDOWN_SECONDS', config.get('abuse_prevention', 'vm_creation_cooldown_seconds', fallback='300')))
    config.set('abuse_prevention', 'rate_limit_excluded_commands', os.getenv('RATE_LIMIT_EXCLUDED_COMMANDS', config.get('abuse_prevention', 'rate_limit_excluded_commands', fallback='help,ping,status')))

    # Pterodactyl Settings
    config.add_section('pterodactyl') # Ensure section exists
    config.set('pterodactyl', 'panel_url', os.getenv('PTERODACTYL_PANEL_URL', config.get('pterodactyl', 'panel_url', fallback=None)))
    config.set('pterodactyl', 'api_key', os.getenv('PTERODACTYL_API_KEY', config.get('pterodactyl', 'api_key', fallback=None)))
    config.set('pterodactyl', 'default_node_id', os.getenv('PTERODACTYL_DEFAULT_NODE_ID', config.get('pterodactyl', 'default_node_id', fallback='')))
    config.set('pterodactyl', 'default_pterodactyl_user_id', os.getenv('PTERODACTYL_DEFAULT_USER_ID', config.get('pterodactyl', 'default_pterodactyl_user_id', fallback='')))


    # Créer le dossier data s'il n'existe pas
    db_path_resolved = config.get('database', 'path')
    db_dir = os.path.dirname(db_path_resolved)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        # logger.info(f"Dossier de données '{db_dir}' créé.")
        print(f"Dossier de données '{db_dir}' créé.")


    return config

# Charger la configuration au démarrage du module pour qu'elle soit accessible globalement
# La FileNotFoundError pour config.ini n'est plus levée par load_config.
# APP_CONFIG sera toujours un objet ConfigParser.
APP_CONFIG = load_config()
if APP_CONFIG is None: # Théoriquement, ne devrait plus arriver si load_config retourne toujours config
    print("ERREUR CRITIQUE: APP_CONFIG n'a pas pu être initialisé.")
    # logger.critical("APP_CONFIG n'a pas pu être initialisé.")
    # Initialiser à un ConfigParser vide pour éviter des erreurs AttributeError plus loin,
    # bien que le bot risque de ne pas fonctionner correctement.
    APP_CONFIG = configparser.ConfigParser()
    sections_to_ensure = ['discord', 'gcp', 'database', 'bot_settings', 'abuse_prevention', 'pterodactyl']
    for section_name in sections_to_ensure:
        if not APP_CONFIG.has_section(section_name):
            APP_CONFIG.add_section(section_name)


def get_discord_token():
    if not APP_CONFIG: return os.getenv('DISCORD_TOKEN') # Fallback for critical early load
    return APP_CONFIG.get('discord', 'token', fallback=None) # Added fallback=None

def get_owner_ids():
    if not APP_CONFIG:
        ids_str = os.getenv('OWNER_IDS', '')
    else:
        ids_str = APP_CONFIG.get('discord', 'owner_ids', fallback='')
    return [int(id_str.strip()) for id_str in ids_str.split(',') if id_str.strip().isdigit()]

def get_game_admin_role_id():
    if not APP_CONFIG: return os.getenv('GAME_ADMIN_ROLE_ID')
    role_id_str = APP_CONFIG.get('discord', 'game_admin_role_id', fallback='')
    return int(role_id_str) if role_id_str.isdigit() else None

def get_vm_operator_role_id():
    if not APP_CONFIG: return os.getenv('VM_OPERATOR_ROLE_ID')
    role_id_str = APP_CONFIG.get('discord', 'vm_operator_role_id', fallback='')
    return int(role_id_str) if role_id_str.isdigit() else None


def get_gcp_project_id():
    if not APP_CONFIG: return os.getenv('GCP_PROJECT_ID') # Fallback
    return APP_CONFIG.get('gcp', 'project_id', fallback=None) # Added fallback=None

def get_database_url():
    """
    Constructs the database URL.
    Prioritizes DATABASE_URL environment variable (for services like Railway with managed DBs).
    Then checks for 'database.url' in config (for user-defined full URLs).
    Finally, constructs an SQLite URL from 'database.path' in config.
    """
    # 1. Prioritize DATABASE_URL environment variable
    env_db_url = os.getenv('DATABASE_URL')
    if env_db_url:
        return env_db_url

    if not APP_CONFIG:
        raise ValueError("Application configuration (APP_CONFIG) not loaded and DATABASE_URL environment variable not set.")

    # 2. Check for an explicit 'url' in the 'database' section of the config
    explicit_config_url = APP_CONFIG.get('database', 'url', fallback=None)
    if explicit_config_url:
        return explicit_config_url

    # 3. Construct SQLite URL from 'path'
    db_path = APP_CONFIG.get('database', 'path', fallback=None)
    if not db_path:
        # This should ideally not happen if load_config has proper fallbacks
        raise ValueError("Database path ('database.path') is not configured in config.ini and DATABASE_URL env var is not set.")

    # Ensure the path is absolute for SQLite connection string
    # The load_config function already handles creating the DATA_DIR
    # and resolves a default path if not specified.
    absolute_db_path = os.path.abspath(db_path)
    return f"sqlite:///{absolute_db_path}"

# Getters for Abuse Prevention Settings
def get_max_commands_per_minute():
    if not APP_CONFIG: return int(os.getenv('MAX_COMMANDS_PER_MINUTE', 20)) # Fallback
    return APP_CONFIG.getint('abuse_prevention', 'max_commands_per_minute')

def get_max_active_vms_per_user():
    if not APP_CONFIG: return int(os.getenv('MAX_ACTIVE_VMS_PER_USER', 2)) # Fallback
    return APP_CONFIG.getint('abuse_prevention', 'max_active_vms_per_user')

def get_max_total_vms_managed_per_user():
    if not APP_CONFIG: return int(os.getenv('MAX_TOTAL_VMS_MANAGED_PER_USER', 5)) # Fallback
    return APP_CONFIG.getint('abuse_prevention', 'max_total_vms_managed_per_user')

def get_vm_creation_cooldown_seconds():
    if not APP_CONFIG: return int(os.getenv('VM_CREATION_COOLDOWN_SECONDS', 300)) # Fallback
    return APP_CONFIG.getint('abuse_prevention', 'vm_creation_cooldown_seconds')

def get_rate_limit_excluded_commands():
    if not APP_CONFIG:
        excluded_str = os.getenv('RATE_LIMIT_EXCLUDED_COMMANDS', 'help,ping,status') # Fallback
    else:
        excluded_str = APP_CONFIG.get('abuse_prevention', 'rate_limit_excluded_commands')
    return [cmd.strip() for cmd in excluded_str.split(',') if cmd.strip()]

# Getters for Pterodactyl Settings
def get_pterodactyl_panel_url():
    if not APP_CONFIG: return os.getenv('PTERODACTYL_PANEL_URL')
    return APP_CONFIG.get('pterodactyl', 'panel_url', fallback=None)

def get_pterodactyl_api_key():
    if not APP_CONFIG: return os.getenv('PTERODACTYL_API_KEY')
    return APP_CONFIG.get('pterodactyl', 'api_key', fallback=None)

def get_pterodactyl_default_node_id():
    if not APP_CONFIG: return os.getenv('PTERODACTYL_DEFAULT_NODE_ID')
    node_id_str = APP_CONFIG.get('pterodactyl', 'default_node_id', fallback='')
    return int(node_id_str) if node_id_str.isdigit() else None

def get_pterodactyl_default_user_id():
    if not APP_CONFIG: return os.getenv('PTERODACTYL_DEFAULT_USER_ID')
    user_id_str = APP_CONFIG.get('pterodactyl', 'default_pterodactyl_user_id', fallback='')
    return int(user_id_str) if user_id_str.isdigit() else None


# Ajoutez d'autres getters pour les configurations fréquemment utilisées

if __name__ == '__main__':
    # Pour tester le chargement de la configuration
    if APP_CONFIG:
        print("Configuration chargée avec succès.")
        print(f"Token Discord: {'Présent' if get_discord_token() else 'Absent'}")
        print(f"Projet GCP ID: {get_gcp_project_id()}")
        print(f"Chemin DB: {APP_CONFIG.get('database', 'path')}")
        print(f"Pterodactyl Panel URL: {get_pterodactyl_panel_url()}")
        print(f"Pterodactyl API Key: {'Présent' if get_pterodactyl_api_key() else 'Absent'}")
    else:
        print("Échec du chargement de la configuration.")
