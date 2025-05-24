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
    # Helper pour s'assurer que les valeurs sont des strings pour config.set
    def get_env_or_config_str(section, key, env_var, default_value=''):
        # Priorité: variable d'environnement, puis config.ini, puis valeur par défaut
        value = os.getenv(env_var, config.get(section, key, fallback=default_value))
        return str(value) if value is not None else default_value

    # Discord
    config.set('discord', 'token', get_env_or_config_str('discord', 'token', 'DISCORD_TOKEN', default_value='')) # Default '' car critique
    config.set('discord', 'prefix', get_env_or_config_str('discord', 'prefix', 'BOT_PREFIX', default_value='!'))
    config.set('discord', 'owner_ids', get_env_or_config_str('discord', 'owner_ids', 'OWNER_IDS'))
    config.set('discord', 'game_admin_role_id', get_env_or_config_str('discord', 'game_admin_role_id', 'GAME_ADMIN_ROLE_ID'))
    config.set('discord', 'vm_operator_role_id', get_env_or_config_str('discord', 'vm_operator_role_id', 'VM_OPERATOR_ROLE_ID'))

    # GCP
    config.set('gcp', 'project_id', get_env_or_config_str('gcp', 'project_id', 'GCP_PROJECT_ID'))
    config.set('gcp', 'default_zone', get_env_or_config_str('gcp', 'default_zone', 'GCP_DEFAULT_ZONE', default_value='europe-west1-b'))
    config.set('gcp', 'service_account_file', get_env_or_config_str('gcp', 'service_account_file', 'GCP_SERVICE_ACCOUNT_FILE', default_value=GCP_KEY_FILE_PATH))

    # Database
    default_db_path = os.path.join(DATA_DIR, 'bot_database.db')
    config.set('database', 'path', get_env_or_config_str('database', 'path', 'DATABASE_PATH', default_value=default_db_path))
    # Pour 'url', si elle est définie, elle sera utilisée par get_database_url(), pas besoin de la forcer ici.

    # Bot Settings
    config.set('bot_settings', 'log_level', get_env_or_config_str('bot_settings', 'log_level', 'LOG_LEVEL', default_value='INFO'))
    config.set('bot_settings', 'timezone', get_env_or_config_str('bot_settings', 'timezone', 'TIMEZONE', default_value='UTC'))

    # Abuse Prevention Settings
    config.set('abuse_prevention', 'max_commands_per_minute', get_env_or_config_str('abuse_prevention', 'max_commands_per_minute', 'MAX_COMMANDS_PER_MINUTE', default_value='20'))
    config.set('abuse_prevention', 'max_active_vms_per_user', get_env_or_config_str('abuse_prevention', 'max_active_vms_per_user', 'MAX_ACTIVE_VMS_PER_USER', default_value='2'))
    config.set('abuse_prevention', 'max_total_vms_managed_per_user', get_env_or_config_str('abuse_prevention', 'max_total_vms_managed_per_user', 'MAX_TOTAL_VMS_MANAGED_PER_USER', default_value='5'))
    config.set('abuse_prevention', 'vm_creation_cooldown_seconds', get_env_or_config_str('abuse_prevention', 'vm_creation_cooldown_seconds', 'VM_CREATION_COOLDOWN_SECONDS', default_value='300'))
    config.set('abuse_prevention', 'rate_limit_excluded_commands', get_env_or_config_str('abuse_prevention', 'rate_limit_excluded_commands', 'RATE_LIMIT_EXCLUDED_COMMANDS', default_value='help,ping,status'))

    # Pterodactyl Settings
    config.set('pterodactyl', 'panel_url', get_env_or_config_str('pterodactyl', 'panel_url', 'PTERODACTYL_PANEL_URL'))
    config.set('pterodactyl', 'api_key', get_env_or_config_str('pterodactyl', 'api_key', 'PTERODACTYL_API_KEY'))
    config.set('pterodactyl', 'default_node_id', get_env_or_config_str('pterodactyl', 'default_node_id', 'PTERODACTYL_DEFAULT_NODE_ID'))
    config.set('pterodactyl', 'default_pterodactyl_user_id', get_env_or_config_str('pterodactyl', 'default_pterodactyl_user_id', 'PTERODACTYL_DEFAULT_USER_ID'))


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
