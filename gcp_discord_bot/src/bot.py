import discord
from discord.ext import commands
import os
import configparser
import logging
from src.utils.logger import setup_logging # Import setup_logging

# Configurer le logging dès que possible
setup_logging()
logger = logging.getLogger(__name__) # Obtenir un logger pour ce module

# Charger la configuration
config = configparser.ConfigParser()
# TODO: Gérer le cas où config.ini n'existe pas et guider l'utilisateur
if os.path.exists('config/config.ini'):
    config.read('config/config.ini')
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', config.get('discord', 'token', fallback=None))
    BOT_PREFIX = config.get('discord', 'prefix', fallback='!')
else:
    logger.error("ERREUR: Le fichier config/config.ini est introuvable. Veuillez le créer à partir de config.example.ini.")
    # Potentiellement, charger les variables d'environnement comme fallback principal
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    BOT_PREFIX = os.getenv('BOT_PREFIX', '!')
    if not DISCORD_TOKEN:
        logger.critical("ERREUR: Le token Discord n'est pas configuré. Veuillez le définir dans config/config.ini ou via la variable d'environnement DISCORD_TOKEN.")
        exit() # Quitter si le token n'est pas trouvé

intents = discord.Intents.default()
intents.message_content = True # Nécessaire pour les commandes textuelles, à ajuster si slash commands uniquement
# intents.members = True # Si besoin de suivre les membres

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

@bot.event
async def on_ready():
    logger.info(f'Application Discord connectée en tant que {bot.user.name}')
    logger.info(f'ID de l application: {bot.user.id}')
    # Charger les cogs ici
    await load_cogs()
    try:
        synced = await bot.tree.sync()
        logger.info(f"Nombre de commandes d'application synchronisées : {len(synced)}")
    except Exception as e:
        logger.error(f"Erreur lors de la synchronisation des commandes d'application: {e}")

async def load_cogs():
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    for filename in os.listdir(cogs_dir):
        if filename.endswith(".py") and not filename.startswith("__"): # Ignorer __init__.py etc.
            extension_name = filename[:-3]
            try:
                await bot.load_extension(f"src.cogs.{extension_name}")
                logger.info(f"Cog '{extension_name}' chargé avec succès.")
            except commands.ExtensionAlreadyLoaded:
                logger.info(f"Cog '{extension_name}' est déjà chargé.")
            except Exception as e:
                logger.error(f"Erreur lors du chargement du cog '{extension_name}': {e}", exc_info=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("Le token Discord n'est pas défini. Veuillez vérifier votre configuration.")
    else:
        try:
            logger.info("Démarrage du bot...")
            bot.run(DISCORD_TOKEN)
        except Exception as e:
            logger.critical(f"Erreur critique lors du démarrage du bot: {e}", exc_info=True)
