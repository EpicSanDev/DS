import logging
import logging.config
import os
# from core.settings import APP_CONFIG # Attention aux imports circulaires

LOGGING_CONFIG_FILE = 'config/logging_config.ini'
LOG_DIR = 'logs' # Assurez-vous que ce dossier existe ou est créé

def setup_logging():
    """Configure le logging pour l'application."""
    # Créer le dossier de logs s'il n'existe pas
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        print(f"Dossier de logs '{LOG_DIR}' créé.")

    if os.path.exists(LOGGING_CONFIG_FILE):
        logging.config.fileConfig(LOGGING_CONFIG_FILE, disable_existing_loggers=False)
        # logger = logging.getLogger(__name__) # Ou un nom plus générique comme 'app_logger'
        # logger.info("Logging configuré à partir de logging_config.ini.")
        print("Logging configuré à partir de logging_config.ini.")
    else:
        # Configuration de logging basique si le fichier .ini n'est pas trouvé
        # log_level_str = APP_CONFIG.get('bot_settings', 'log_level', fallback='INFO') if APP_CONFIG else 'INFO'
        log_level_str = os.getenv('LOG_LEVEL', 'INFO') # Fallback simple
        numeric_level = getattr(logging, log_level_str.upper(), logging.INFO)

        logging.basicConfig(
            level=numeric_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.StreamHandler(), # Vers la console
                logging.FileHandler(os.path.join(LOG_DIR, 'bot_fallback.log')) # Vers un fichier
            ]
        )
        # logger = logging.getLogger(__name__)
        # logger.warning(f"Fichier logging_config.ini non trouvé. Utilisation de la configuration de logging basique (Niveau: {log_level_str}).")
        print(f"Fichier {LOGGING_CONFIG_FILE} non trouvé. Utilisation de la configuration de logging basique (Niveau: {log_level_str}).")
    # return logger # Optionnel, si vous voulez retourner le logger principal

# Appeler setup_logging() au chargement du module pour que le logging soit actif dès le début.
# Cependant, cela peut être délicat avec les dépendances de configuration.
# Il est souvent préférable d'appeler setup_logging() explicitement au début de bot.py.
# Pour l'instant, ne l'appelons pas ici pour éviter les problèmes d'ordre d'initialisation.

def get_logger(name: str) -> logging.Logger:
    """Récupère un logger configuré."""
    return logging.getLogger(name)
