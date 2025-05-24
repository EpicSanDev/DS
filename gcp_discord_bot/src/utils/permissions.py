import discord
from discord import app_commands, Interaction
from discord.ext import commands
from functools import wraps

from src.core import settings # To get role IDs
from src.utils.logger import get_logger

logger = get_logger(__name__)

def is_bot_owner():
    """Check if the user is one of the bot owners."""
    async def predicate(interaction: Interaction) -> bool:
        owner_ids = settings.get_owner_ids()
        if not owner_ids: # If no owner IDs are configured, perhaps only allow if guild owner? Or deny all.
            logger.warning("is_bot_owner check failed: No owner_ids configured in settings.")
            return False # Safer to deny if not configured
        return interaction.user.id in owner_ids
    return app_commands.check(predicate)

def has_game_admin_role():
    """Check if the user has the 'Game Admin' role or is a bot owner."""
    async def predicate(interaction: Interaction) -> bool:
        if await is_bot_owner().predicate(interaction): # Owners bypass role checks
            return True
        
        game_admin_role_id = settings.get_game_admin_role_id()
        if not game_admin_role_id:
            logger.warning("has_game_admin_role check failed: game_admin_role_id not configured.")
            return False # Deny if role not configured

        if not isinstance(interaction.user, discord.Member): # Check if in a guild context
            logger.debug("has_game_admin_role: User is not a discord.Member (e.g., in DM). Denying.")
            return False

        user_role_ids = [role.id for role in interaction.user.roles]
        if game_admin_role_id in user_role_ids:
            return True
        
        logger.debug(f"User {interaction.user.name} lacks Game Admin role ({game_admin_role_id}). Roles: {user_role_ids}")
        return False
    return app_commands.check(predicate)

def has_vm_operator_role():
    """Check if the user has the 'VM Operator' role, or 'Game Admin' role, or is a bot owner."""
    async def predicate(interaction: Interaction) -> bool:
        if await is_bot_owner().predicate(interaction): # Owners bypass
            return True
        if await has_game_admin_role().predicate(interaction): # Game Admins are also VM Operators
            return True

        vm_operator_role_id = settings.get_vm_operator_role_id()
        if not vm_operator_role_id:
            logger.warning("has_vm_operator_role check failed: vm_operator_role_id not configured.")
            return False

        if not isinstance(interaction.user, discord.Member):
            return False
            
        user_role_ids = [role.id for role in interaction.user.roles]
        if vm_operator_role_id in user_role_ids:
            return True
        
        logger.debug(f"User {interaction.user.name} lacks VM Operator role ({vm_operator_role_id}). Roles: {user_role_ids}")
        return False
    return app_commands.check(predicate)

def can_control_game_server(instance_name_param: str = "instance_name"):
    """
    Check if the user owns the game server or has Game Admin role or is a bot owner.
    `instance_name_param` is the name of the command parameter that holds the game server's instance name.
    """
    async def predicate(interaction: Interaction) -> bool:
        if await is_bot_owner().predicate(interaction):
            return True
        if await has_game_admin_role().predicate(interaction): # Game Admins can control any server
            return True

        # Check for server ownership
        db_cog = interaction.client.get_cog("DBCog")
        if not db_cog:
            logger.error("can_control_game_server check failed: DBCog not found.")
            return False # Cannot verify ownership

        # Get the instance name from the command arguments
        # This assumes the command parameter for instance name is `instance_name_param`
        try:
            # For slash commands, arguments are in interaction.namespace
            game_server_gcp_name = getattr(interaction.namespace, instance_name_param, None)
            if game_server_gcp_name is None:
                 # Fallback for different interaction types or if namespace isn't populated as expected
                if interaction.data and 'options' in interaction.data:
                    for option in interaction.data['options']:
                        if option['name'] == instance_name_param:
                            game_server_gcp_name = option['value']
                            break
            if not game_server_gcp_name:
                logger.error(f"can_control_game_server: Could not find instance name parameter '{instance_name_param}' in interaction.")
                return False
        except Exception as e:
            logger.error(f"can_control_game_server: Error accessing instance name parameter '{instance_name_param}': {e}", exc_info=True)
            return False


        server_info = await db_cog.get_game_server_by_name(game_server_gcp_name)
        if not server_info:
            # If server not in DB, can't verify ownership.
            # We might allow Game Admins to proceed if the server exists in GCP but not DB.
            # For now, if not in DB, only admins (already checked) can proceed.
            logger.warning(f"can_control_game_server: Server '{game_server_gcp_name}' not found in DB for ownership check by {interaction.user.name}.")
            # Send a message here? Or let the command handle "not found".
            # Let command handle "not found", this check is purely for permission.
            # If it's not found, they can't be the owner.
            return False 

        if str(interaction.user.id) == server_info.discord_user_id:
            return True # User is the owner

        logger.debug(f"User {interaction.user.name} is not owner of server '{game_server_gcp_name}' and not Game Admin.")
        return False
    return app_commands.check(predicate)

# Generic error handler for these permission checks
async def handle_permission_check_failure(interaction: Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        logger.warning(f"Permission check failed for user {interaction.user.name} ({interaction.user.id}) on command {interaction.command.name if interaction.command else 'unknown'}: {error}")
        # Avoid sending multiple messages if response already started (e.g., by rate limiter)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Vous n'avez pas les permissions nécessaires pour exécuter cette commande.", 
                ephemeral=True
            )
        else:
            try: # Try followup if response was deferred
                await interaction.followup.send(
                    "Vous n'avez pas les permissions nécessaires pour exécuter cette commande.", 
                    ephemeral=True
                )
            except discord.errors.HTTPException as e: # e.g. Interaction has already been responded to
                 logger.warning(f"Could not send permission error followup for {interaction.command.name if interaction.command else 'unknown'}: {e}")

    # else: # Re-raise other errors or handle them if needed
    # logger.error(f"Unexpected error in command decorated with permission check: {error}", exc_info=True)
    # if not interaction.response.is_done():
    # await interaction.response.send_message("Une erreur inattendue est survenue.", ephemeral=True)
