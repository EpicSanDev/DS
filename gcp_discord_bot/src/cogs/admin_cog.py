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


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Cog Admin chargé.")

    @commands.command(name='ping', help='Vérifie la latence du bot (commande préfixée).')
    @commands.is_owner() 
    async def ping(self, ctx: commands.Context):
        latency = self.bot.latency * 1000 # en ms
        await ctx.send(f'Pong! Latence (préfixée): {latency:.2f}ms')

    @app_commands.command(name="admin_test", description="Commande de test admin (slash) avec rate limiting.")
    @app_commands.check(global_app_command_rate_limit_check)
    # @app_commands.checks.is_owner() # Example: if you want owner only for this too
    async def admin_test_slash(self, interaction: Interaction):
        """Un simple slash command de test pour l'admin avec rate limiting."""
        latency = self.bot.latency * 1000 # en ms
        await interaction.response.send_message(f'Pong! Latence (slash): {latency:.2f}ms. Commande admin_test exécutée.', ephemeral=True)

    @admin_test_slash.error
    async def on_admin_test_slash_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            # The rate limit message is already sent by check_app_command_rate_limit if interaction not responded
            # So, we might not need to send another message here if it's specifically our rate limit check.
            # However, if the check_app_command_rate_limit failed to send (e.g. interaction already responded),
            # or if it's another check failure, this is a fallback.
            logger.warning(f"CheckFailure pour /admin_test par {interaction.user.name}: {error}")
            if not interaction.response.is_done():
                 await interaction.response.send_message("Une condition pour exécuter cette commande n'est pas remplie (ex: rate limit).", ephemeral=True)
        else:
            logger.error(f"Erreur inattendue pour /admin_test par {interaction.user.name}: {error}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("Une erreur est survenue.", ephemeral=True)


    @app_commands.command(name="load_cog", description="Charge une extension (cog). (Propriétaire uniquement)")
    @app_commands.checks.is_owner()
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
    @app_commands.checks.is_owner()
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
    @app_commands.checks.is_owner()
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
        if isinstance(error, app_commands.NotOwner):
            logger.warning(f"Utilisateur non propriétaire {interaction.user.name} a tenté d'utiliser une commande de gestion de cog.")
            await interaction.followup.send("Désolé, cette commande est réservée au propriétaire du bot.", ephemeral=True)
        elif isinstance(error, app_commands.CheckFailure): # Autre check failure
            logger.warning(f"CheckFailure pour une commande de gestion de cog par {interaction.user.name}: {error}")
            if not interaction.response.is_done(): # Check if response already sent by rate limiter
                 await interaction.response.send_message("Une condition pour exécuter cette commande n'est pas remplie.", ephemeral=True)
            else: # If rate limiter (or other check) already responded, followup might be needed if it was thinking
                 await interaction.followup.send("Une condition pour exécuter cette commande n'est pas remplie (followup).", ephemeral=True)
        else:
            logger.error(f"Erreur inattendue pour une commande de gestion de cog par {interaction.user.name}: {error}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("Une erreur est survenue lors de l'exécution de cette commande.", ephemeral=True)
            else:
                await interaction.followup.send("Une erreur est survenue lors de l'exécution de cette commande (followup).", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
    logger.info("Setup du Cog Admin terminé.")
