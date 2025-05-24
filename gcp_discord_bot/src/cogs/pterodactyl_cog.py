import discord
from discord.ext import commands
from pteropy import Client as PterodactylClient # Utiliser l'alias Client
import logging

from src.core import settings # Pour accéder à APP_CONFIG ou aux getters

logger = logging.getLogger(__name__)

class PterodactylCog(commands.Cog, name="Pterodactyl"):
    """Commandes pour interagir avec Pterodactyl."""

    def __init__(self, bot):
        self.bot = bot
        self.ptero_client = None
        try:
            panel_url = settings.get_pterodactyl_panel_url()
            api_key = settings.get_pterodactyl_api_key()
            if panel_url and api_key:
                self.ptero_client = PterodactylClient(panel_url, api_key) # Utiliser l'alias
                logger.info("Client Pterodactyl initialisé.")
            else:
                logger.warning("URL du panel Pterodactyl ou clé API non configurée. Le cog Pterodactyl sera limité.")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du client Pterodactyl: {e}", exc_info=True)

    @commands.command(name="pterolistservers", aliases=["pls"])
    @commands.is_owner() # Ou une permission plus appropriée
    async def list_pterodactyl_servers(self, ctx):
        """Liste les serveurs configurés dans Pterodactyl."""
        if not self.ptero_client:
            await ctx.send("Le client Pterodactyl n'est pas configuré correctement. Vérifiez les logs et la configuration.")
            return

        try:
            servers = self.ptero_client.servers.list_servers()
            if not servers:
                await ctx.send("Aucun serveur trouvé sur Pterodactyl.")
                return

            embed = discord.Embed(title="Serveurs Pterodactyl", color=discord.Color.blue())
            for server_data in servers:
                server = server_data['attributes']
                embed.add_field(
                    name=f"{server['name']} (ID: {server['id']})",
                    value=(
                        f"UUID: {server['uuid']}\n"
                        f"Node: {server['node']}\n"
                        f"Utilisateur: {server['user']}\n"
                        f"Statut: {'Running' if server.get('status') == 'running' else 'Offline/Autre'}" # pteropy peut ne pas donner le statut directement
                    ),
                    inline=False
                )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des serveurs Pterodactyl: {e}", exc_info=True)
            await ctx.send(f"Une erreur est survenue en listant les serveurs Pterodactyl: {e}")

async def setup(bot):
    # S'assurer que la configuration est chargée avant d'initialiser le cog
    if not settings.APP_CONFIG:
        logger.error("La configuration de l'application (APP_CONFIG) n'a pas été chargée. Le cog Pterodactyl ne peut pas démarrer.")
        # Vous pourriez vouloir empêcher le chargement du cog ici si APP_CONFIG est None
        # ou laisser le constructeur du cog gérer le cas où les settings ne sont pas là.
        # Pour l'instant, on logue et on continue, le constructeur loguera aussi.
    
    # Vérifier si les settings Pterodactyl sont présents
    pterodactyl_url = settings.get_pterodactyl_panel_url()
    pterodactyl_api_key = settings.get_pterodactyl_api_key()

    if not pterodactyl_url or not pterodactyl_api_key:
        logger.warning("URL du panel Pterodactyl ou clé API non configurée dans config.ini. Le cog Pterodactyl ne sera pas chargé.")
    else:
        await bot.add_cog(PterodactylCog(bot))
        logger.info("Cog Pterodactyl chargé.")
