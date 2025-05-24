import discord
from discord.ext import commands
from discord import app_commands, Interaction
from src.utils.logger import get_logger # Assuming a logger utility
from src.cogs.db_cog import DBCog # Import DBCog to access its methods

logger = get_logger(__name__)

# This is the check function that will be used with @app_commands.check()
async def global_app_command_rate_limit_check(interaction: Interaction) -> bool:
    """
    Predicate for app_commands.check() to apply rate limiting.
    Retrieves DBCog and calls its rate limit check method.
    """
    db_cog: DBCog = interaction.client.get_cog("DBCog")
    if not db_cog:
        logger.error("DBCog not found. Cannot perform rate limit check for app command.")
        # Fail open if DBCog is missing, or could choose to fail closed (return False)
        return True # Or False, depending on desired behavior if DBCog is missing
    
    # Now call the check method from DBCog instance
    return await db_cog.check_app_command_rate_limit(interaction)

# Check personnalisé pour propriétaire
def is_bot_owner():
    async def predicate(interaction: Interaction) -> bool:
        # Assurez-vous que bot.owner_ids est peuplé.
        # commands.Bot popule bot.owner_id et bot.owner_ids à partir de l'application lors de l'initialisation.
        
        if not interaction.client.owner_ids:
            logger.warning("owner_ids n'est pas défini sur le bot. Tentative de chargement depuis src.core.settings.")
            try:
                from src.core import settings
                owner_ids_config = settings.get_owner_ids()
                if owner_ids_config:
                    interaction.client.owner_ids = set(owner_ids_config)
                    logger.info(f"owner_ids chargés depuis settings: {interaction.client.owner_ids}")
                else:
                    logger.error("La configuration des propriétaires (owner_ids) est manquante dans src.core.settings.")
                    raise app_commands.CheckFailure("La configuration des propriétaires du bot est manquante.")
            except ImportError:
                logger.error("Impossible d'importer src.core.settings pour charger les owner_ids.")
                raise app_commands.CheckFailure("Erreur interne lors de la vérification des permissions (ImportError).")
            except Exception as e:
                logger.error(f"Erreur inattendue lors du chargement des owner_ids: {e}", exc_info=True)
                raise app_commands.CheckFailure(f"Erreur interne lors de la vérification des permissions (Exception: {type(e).__name__}).")


        if interaction.user.id not in interaction.client.owner_ids:
            logger.warning(f"Utilisateur non propriétaire {interaction.user.name} (ID: {interaction.user.id}) a tenté d'utiliser une commande propriétaire. IDs propriétaires connus: {interaction.client.owner_ids}")
            raise app_commands.NotOwner() 
        return True
    return app_commands.check(predicate)

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not bot.owner_ids:
            logger.warning("owner_ids non défini sur le bot lors de l'init de AdminCog. Tentative de chargement.")
            try:
                from src.core import settings 
                owner_ids_config = settings.get_owner_ids()
                if owner_ids_config:
                    self.bot.owner_ids = set(int(oid) for oid in owner_ids_config) # Assurer que les IDs sont des entiers
                    logger.info(f"owner_ids chargés dans AdminCog.__init__: {self.bot.owner_ids}")
                else:
                    logger.warning("Aucun owner_id configuré via src.core.settings pour AdminCog.__init__.")
            except ImportError:
                logger.error("Impossible d'importer src.core.settings dans AdminCog.__init__.")
            except Exception as e:
                logger.error(f"Erreur lors du chargement des owner_ids dans AdminCog.__init__: {e}", exc_info=True)
        logger.info("Cog Admin chargé.")

    @commands.command(name='ping', help='Vérifie la latence du bot (commande préfixée).')
    @commands.is_owner() 
    async def ping(self, ctx: commands.Context):
        latency = self.bot.latency * 1000 # en ms
        await ctx.send(f'Pong! Latence (préfixée): {latency:.2f}ms')

    @app_commands.command(name="admin_test", description="Commande de test admin (slash) avec rate limiting.")
    @app_commands.check(global_app_command_rate_limit_check)
    # Pour rendre cette commande propriétaire uniquement, décommentez la ligne suivante :
    # @is_bot_owner() 
    async def admin_test_slash(self, interaction: Interaction):
        """Un simple slash command de test pour l'admin avec rate limiting."""
        latency = self.bot.latency * 1000 # en ms
        await interaction.response.send_message(f'Pong! Latence (slash): {latency:.2f}ms. Commande admin_test exécutée.', ephemeral=True)

    @admin_test_slash.error
    async def on_admin_test_slash_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        if not interaction.response.is_done():
            # Si la réponse n'a pas été envoyée (par exemple, le rate limiter n'a pas répondu)
            # Il est peu probable ici car global_app_command_rate_limit_check devrait répondre.
            # Mais par sécurité, on s'assure de ne pas essayer de répondre deux fois.
            pass

        if isinstance(error, app_commands.NotOwner): 
            logger.warning(f"Utilisateur non propriétaire {interaction.user.name} a tenté d'utiliser /admin_test.")
            # Si is_bot_owner() a levé NotOwner, il n'aura pas envoyé de message.
            if not interaction.response.is_done():
                await interaction.response.send_message("Désolé, cette commande est réservée au propriétaire du bot.", ephemeral=True)
            else: # Si la réponse est faite (par ex. par un defer implicite ou un autre check)
                await interaction.followup.send("Désolé, cette commande est réservée au propriétaire du bot.", ephemeral=True)
        elif isinstance(error, app_commands.CheckFailure):
            logger.warning(f"CheckFailure pour /admin_test par {interaction.user.name}: {error}")
            # global_app_command_rate_limit_check envoie déjà un message si le rate limit est atteint.
            # Donc, on ne renvoie un message que si la réponse n'est pas déjà faite.
            if not interaction.response.is_done():
                 await interaction.response.send_message("Une condition pour exécuter cette commande n'est pas remplie (ex: rate limit).", ephemeral=True)
        else:
            logger.error(f"Erreur inattendue pour /admin_test par {interaction.user.name}: {error}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("Une erreur est survenue.", ephemeral=True)
            else:
                await interaction.followup.send("Une erreur est survenue (followup).", ephemeral=True)


    @app_commands.command(name="load_cog", description="Charge une extension (cog). (Propriétaire uniquement)")
    @is_bot_owner() 
    @app_commands.describe(cog_name="Le nom de l'extension à charger (ex: src.cogs.admin_cog).")
    async def load_cog(self, interaction: Interaction, cog_name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.load_extension(cog_name)
            logger.info(f"Cog '{cog_name}' chargé par {interaction.user.name}.")
            await interaction.followup.send(f"Extension `{cog_name}` chargée avec succès.", ephemeral=True)
        except commands.ExtensionAlreadyLoaded:
            logger.warning(f"Tentative de chargement du cog '{cog_name}' déjà chargé par {interaction.user.name}.")
            await interaction.followup.send(f"L'extension `{cog_name}` est déjà chargée.", ephemeral=True)
        except commands.ExtensionNotFound:
            logger.error(f"Tentative de chargement du cog introuvable '{cog_name}' par {interaction.user.name}.")
            await interaction.followup.send(f"L'extension `{cog_name}` est introuvable.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'extension '{cog_name}' par {interaction.user.name}: {e}", exc_info=True)
            await interaction.followup.send(f"Erreur lors du chargement de `{cog_name}`: ```{e}```", ephemeral=True)

    @app_commands.command(name="unload_cog", description="Décharge une extension (cog). (Propriétaire uniquement)")
    @is_bot_owner() 
    @app_commands.describe(cog_name="Le nom de l'extension à décharger (ex: src.cogs.admin_cog).")
    async def unload_cog(self, interaction: Interaction, cog_name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.unload_extension(cog_name)
            logger.info(f"Cog '{cog_name}' déchargé par {interaction.user.name}.")
            await interaction.followup.send(f"Extension `{cog_name}` déchargée avec succès.", ephemeral=True)
        except commands.ExtensionNotLoaded:
            logger.warning(f"Tentative de déchargement du cog '{cog_name}' non chargé par {interaction.user.name}.")
            await interaction.followup.send(f"L'extension `{cog_name}` n'est pas chargée.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur lors du déchargement de l'extension '{cog_name}' par {interaction.user.name}: {e}", exc_info=True)
            await interaction.followup.send(f"Erreur lors du déchargement de `{cog_name}`: ```{e}```", ephemeral=True)

    @app_commands.command(name="reload_cog", description="Recharge une extension (cog). (Propriétaire uniquement)")
    @is_bot_owner() 
    @app_commands.describe(cog_name="Le nom de l'extension à recharger (ex: src.cogs.admin_cog).")
    async def reload_cog(self, interaction: Interaction, cog_name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(cog_name)
            logger.info(f"Cog '{cog_name}' rechargé par {interaction.user.name}.")
            await interaction.followup.send(f"Extension `{cog_name}` rechargée avec succès.", ephemeral=True)
        except commands.ExtensionNotLoaded:
            logger.warning(f"Tentative de rechargement du cog '{cog_name}' non chargé par {interaction.user.name}. Tentative de chargement...")
            try:
                await self.bot.load_extension(cog_name)
                logger.info(f"Cog '{cog_name}' chargé (après tentative de rechargement) par {interaction.user.name}.")
                await interaction.followup.send(f"Extension `{cog_name}` (non chargée initialement) chargée avec succès.", ephemeral=True)
            except Exception as e_load:
                logger.error(f"Erreur lors du chargement (après tentative de rechargement) de l'extension '{cog_name}' par {interaction.user.name}: {e_load}", exc_info=True)
                await interaction.followup.send(f"L'extension `{cog_name}` n'était pas chargée et n'a pas pu être chargée: ```{e_load}```", ephemeral=True)
        except commands.ExtensionNotFound:
            logger.error(f"Tentative de rechargement du cog introuvable '{cog_name}' par {interaction.user.name}.")
            await interaction.followup.send(f"L'extension `{cog_name}` est introuvable.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur lors du rechargement de l'extension '{cog_name}' par {interaction.user.name}: {e}", exc_info=True)
            await interaction.followup.send(f"Erreur lors du rechargement de `{cog_name}`: ```{e}```", ephemeral=True)

    @load_cog.error
    @unload_cog.error
    @reload_cog.error
    async def on_cog_management_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        # S'assurer que la réponse est différée si ce n'est pas déjà fait par la commande
        # ou par le check is_bot_owner qui lève une exception avant le defer de la commande.
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if isinstance(error, app_commands.NotOwner):
            logger.warning(f"Utilisateur non propriétaire {interaction.user.name} a tenté d'utiliser une commande de gestion de cog.")
            await interaction.followup.send("Désolé, cette commande est réservée au propriétaire du bot.", ephemeral=True)
        elif isinstance(error, app_commands.CheckFailure): 
            logger.warning(f"CheckFailure pour une commande de gestion de cog par {interaction.user.name}: {error}")
            await interaction.followup.send(f"Une condition pour exécuter cette commande n'est pas remplie: {error}", ephemeral=True)
        else:
            logger.error(f"Erreur inattendue pour une commande de gestion de cog par {interaction.user.name}: {error}", exc_info=True)
            await interaction.followup.send("Une erreur est survenue lors de l'exécution de cette commande.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot)) 
    logger.info("Setup du Cog Admin terminé.")
