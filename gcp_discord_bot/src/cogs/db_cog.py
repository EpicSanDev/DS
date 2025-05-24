import discord
from discord.ext import commands
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import json # Add json import
from discord.ext import commands # Ensure commands is imported for Cog.listener and checks
from discord import Interaction # For type hinting
from src.core import settings # Import the settings module
from src.utils.logger import get_logger # Assuming a logger utility exists

logger = get_logger(__name__)

Base = declarative_base()

class UserUsage(Base):
    __tablename__ = 'user_usage'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    command_name = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    details = Column(String, nullable=True) # Optional: for command arguments or context

class GameServerInstance(Base):
    __tablename__ = 'game_server_instances'

    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_user_id = Column(String, nullable=False, index=True) # User who created/owns this server
    gcp_instance_name = Column(String, nullable=False, unique=True, index=True) # Name in GCP
    gcp_instance_id = Column(String, nullable=True, unique=True) # GCP's unique ID for the instance
    gcp_zone = Column(String, nullable=False)
    game_template_name = Column(String, nullable=False) # e.g., "minecraft_vanilla"
    status = Column(String, default="PROVISIONING", nullable=False) # e.g., PROVISIONING, RUNNING, STOPPED, DELETED, ERROR
    ip_address = Column(String, nullable=True)
    ports_info = Column(String, nullable=True) # JSON string of opened ports e.g., [{"port": 25565, "protocol": "TCP"}]
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    last_status_update = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    auto_shutdown_hours = Column(Integer, nullable=True) # Hours after creation/start to auto-shutdown. NULL means no auto-shutdown.
    # For cost tracking or specific game settings
    additional_config = Column(String, nullable=True) # JSON string for extra game-specific config or cost data

class DBCog(commands.Cog, name="DBCog"): # Added name for clarity
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        db_url = settings.get_database_url()
        if not db_url:
            logger.error("DATABASE_URL n'est pas configuré correctement.")
            raise ValueError("DATABASE_URL is not configured.")
        try:
            self.engine = create_engine(db_url)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            logger.info("Connexion à la base de données et initialisation des tables réussies.")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de la base de données: {e}", exc_info=True)
            raise

        self.max_commands_per_minute = settings.get_max_commands_per_minute()
        self.excluded_commands = settings.get_rate_limit_excluded_commands()

    async def log_usage(self, user_id: int, command_name: str, is_interaction: bool = False):
        session = self.Session()
        try:
            usage = UserUsage(user_id=str(user_id), command_name=command_name)
            session.add(usage)
            session.commit()
            logger.debug(f"Usage logged for user {user_id}: command '{command_name}' (interaction: {is_interaction})")
        except Exception as e:
            logger.error(f"Failed to log usage for user {user_id}, command '{command_name}': {e}", exc_info=True)
            session.rollback() # Important to roll back on error
        finally:
            session.close()

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        """Logs usage for traditional prefixed commands."""
        if ctx.command: # Ensure it's a valid command
            await self.log_usage(ctx.author.id, ctx.command.qualified_name)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        """Logs usage for slash commands and other interactions if they are commands."""
        if interaction.type == discord.InteractionType.application_command:
            # For slash commands, interaction.data usually holds command info
            command_name = interaction.data.get('name')
            if command_name:
                await self.log_usage(interaction.user.id, command_name, is_interaction=True)
            else:
                logger.warning(f"Could not determine command name from interaction: {interaction.data}")


    async def cog_check(self, ctx: commands.Context) -> bool:
        """Global check for rate limiting on prefixed commands."""
        # Bypass for bot owners
        if await self.bot.is_owner(ctx.author):
            return True

        command_name = ctx.command.qualified_name
        if command_name in self.excluded_commands:
            return True

        session = self.Session()
        try:
            one_minute_ago = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
            command_count = session.query(func.count(UserUsage.id)).filter(
                UserUsage.user_id == str(ctx.author.id),
                UserUsage.timestamp >= one_minute_ago
            ).scalar()

            if command_count >= self.max_commands_per_minute:
                await ctx.send(f"Vous exécutez des commandes trop rapidement. Veuillez réessayer dans un instant.", ephemeral=True)
                logger.info(f"User {ctx.author.id} rate limited for command '{command_name}'. Count: {command_count}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error during rate limit check for {ctx.author.id}: {e}", exc_info=True)
            return True # Fail open in case of DB error
        finally:
            session.close()

    async def get_last_command_timestamp(self, user_id: str, command_name: str) -> datetime.datetime | None:
        """Retrieves the timestamp of the last time a user executed a specific command."""
        session = self.Session()
        try:
            last_usage = session.query(UserUsage.timestamp).filter(
                UserUsage.user_id == user_id,
                UserUsage.command_name == command_name
            ).order_by(UserUsage.timestamp.desc()).first()
            
            return last_usage[0] if last_usage else None
        except Exception as e:
            logger.error(f"Error fetching last command timestamp for user {user_id}, command '{command_name}': {e}", exc_info=True)
            return None
        finally:
            session.close()

    # Note: For slash commands, checks are typically implemented within the command definition
    # using @app_commands.check decorator or by handling it in on_interaction if a global check is desired.
    # A global check for interactions similar to cog_check is harder with discord.py's current structure
    # for app_commands. We might need to adapt the on_interaction listener or add checks to each app_command.

    async def check_app_command_rate_limit(self, interaction: Interaction) -> bool:
        """
        Checks if a user is rate-limited for an application command.
        Returns True if the command is allowed, False if rate-limited.
        This method is intended to be used by @app_commands.check() in other cogs.
        """
        # Bypass for bot owners
        # Ensure interaction.user is not None, though it typically shouldn't be for command interactions
        if not interaction.user:
            logger.warning("Interaction received with no user object for rate limit check.")
            return True # Fail open

        if await self.bot.is_owner(interaction.user):
            return True

        command_name = None
        if interaction.command: # interaction.command should be populated in an app_command.check
            command_name = interaction.command.qualified_name
        else: # Fallback if interaction.command is not available for some reason
            command_name = interaction.data.get('name')

        if not command_name:
            logger.warning(f"Could not determine command name for rate limit check from interaction: {interaction.data}")
            return True # Fail open if command name can't be determined

        if command_name in self.excluded_commands:
            return True

        session = self.Session()
        try:
            one_minute_ago = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
            # Count all commands by the user in the last minute for a global rate limit
            command_count = session.query(func.count(UserUsage.id)).filter(
                UserUsage.user_id == str(interaction.user.id),
                UserUsage.timestamp >= one_minute_ago
            ).scalar()

            if command_count >= self.max_commands_per_minute:
                if not interaction.response.is_done():
                    try:
                        await interaction.response.send_message(
                            f"Vous exécutez des commandes trop rapidement ({command_name}). Veuillez réessayer dans un instant.",
                            ephemeral=True
                        )
                    except discord.errors.InteractionResponded:
                        logger.warning(f"Interaction already responded to for user {interaction.user.id} during rate limit message for '{command_name}'.")
                    except Exception as e:
                        logger.error(f"Error sending rate limit message for {interaction.user.id}, command '{command_name}': {e}", exc_info=True)

                logger.info(f"User {interaction.user.id} (Name: {interaction.user.name}) rate limited for app command '{command_name}'. Count: {command_count}")
                return False # Rate limited
            return True # Allowed
        except Exception as e:
            logger.error(f"Error during app command rate limit check for {interaction.user.id} (Name: {interaction.user.name}), command '{command_name}': {e}", exc_info=True)
            return True # Fail open in case of DB error
        finally:
            session.close()


async def setup(bot: commands.Bot):
    cog = DBCog(bot)
    await bot.add_cog(cog)
    # For prefixed commands, this cog_check will apply.
    # For slash commands, rate limiting needs to be handled differently,
    # potentially by adapting the on_interaction listener or adding checks to each command.
    # A simple way for slash commands is to perform the check inside on_interaction
    # before logging, and if it fails, don't proceed with the command logic (though this is tricky
    # as on_interaction is post-factum for the library's command dispatch).
    # A more robust way for slash commands is to use `Interaction.check` within each slash command definition.
    # For now, the cog_check handles prefixed commands. We will enhance on_interaction for slash command checks.

    # Let's refine on_interaction to include a check.
    # We need to be careful as on_interaction is broad.
    # The current on_interaction logs *after* the interaction.
    # To prevent execution, the check must happen earlier.
    # This might require modifying how commands are registered or using a global interaction check if available.

    # For now, let's assume that slash command checks will be added individually to slash commands.
    # The logging part is covered. The `cog_check` covers prefixed commands.
    logger.info("DBCog loaded. UserUsage and GameServerInstance tables initialized. Rate limiting active for prefixed commands.")

    # --- Game Server Instance Management ---
    async def register_game_server(self, discord_user_id: str, gcp_instance_name: str, gcp_zone: str, 
                                   game_template_name: str, gcp_instance_id: str = None, 
                                   ip_address: str = None, ports_info: list = None, 
                                   status: str = "PROVISIONING", additional_config: dict = None,
                                   auto_shutdown_hours: int = None) -> GameServerInstance:
        session = self.Session()
        try:
            new_server = GameServerInstance(
                discord_user_id=str(discord_user_id),
                gcp_instance_name=gcp_instance_name,
                gcp_instance_id=gcp_instance_id,
                gcp_zone=gcp_zone,
                game_template_name=game_template_name,
                status=status,
                ip_address=ip_address,
                ports_info=json.dumps(ports_info) if ports_info else None,
                additional_config=json.dumps(additional_config) if additional_config else None,
                auto_shutdown_hours=auto_shutdown_hours
            )
            session.add(new_server)
            session.commit()
            logger.info(f"Game server '{gcp_instance_name}' registered in DB for user {discord_user_id}.")
            return new_server
        except Exception as e:
            logger.error(f"Error registering game server '{gcp_instance_name}' in DB: {e}", exc_info=True)
            session.rollback()
            raise
        finally:
            session.close()

    async def update_game_server_status(self, gcp_instance_name: str, status: str, 
                                        ip_address: str = None, gcp_instance_id: str = None,
                                        ports_info: list = None) -> bool:
        session = self.Session()
        try:
            server = session.query(GameServerInstance).filter_by(gcp_instance_name=gcp_instance_name).first()
            if server:
                server.status = status
                if ip_address is not None: # Allow clearing IP if VM is stopped
                    server.ip_address = ip_address
                if gcp_instance_id:
                    server.gcp_instance_id = gcp_instance_id
                if ports_info is not None:
                    server.ports_info = json.dumps(ports_info)
                server.last_status_update = datetime.datetime.utcnow()
                session.commit()
                logger.info(f"Status of game server '{gcp_instance_name}' updated to '{status}' in DB.")
                return True
            else:
                logger.warning(f"Game server '{gcp_instance_name}' not found in DB for status update.")
                return False
        except Exception as e:
            logger.error(f"Error updating status for game server '{gcp_instance_name}' in DB: {e}", exc_info=True)
            session.rollback()
            return False
        finally:
            session.close()

    async def get_game_server_by_name(self, gcp_instance_name: str) -> GameServerInstance | None:
        session = self.Session()
        try:
            server = session.query(GameServerInstance).filter_by(gcp_instance_name=gcp_instance_name).first()
            return server
        except Exception as e:
            logger.error(f"Error fetching game server '{gcp_instance_name}' from DB: {e}", exc_info=True)
            return None
        finally:
            session.close()

    async def get_user_active_game_servers(self, discord_user_id: str) -> list[GameServerInstance]:
        session = self.Session()
        try:
            # Active means not DELETED or ERROR, for example
            active_statuses = ["PROVISIONING", "RUNNING", "STOPPING", "STARTING"] 
            servers = session.query(GameServerInstance).filter(
                GameServerInstance.discord_user_id == str(discord_user_id),
                GameServerInstance.status.in_(active_statuses)
            ).all()
            return servers
        except Exception as e:
            logger.error(f"Error fetching active game servers for user {discord_user_id} from DB: {e}", exc_info=True)
            return []
        finally:
            session.close()

    async def get_all_running_servers(self) -> list[GameServerInstance]:
        """Retrieves all game servers currently in 'RUNNING' or 'PROVISIONING' state."""
        session = self.Session()
        try:
            # Servers that might need auto-shutdown
            relevant_statuses = ["RUNNING", "PROVISIONING", "STARTING"]
            servers = session.query(GameServerInstance).filter(
                GameServerInstance.status.in_(relevant_statuses),
                GameServerInstance.auto_shutdown_hours.isnot(None) # Only those with auto-shutdown configured
            ).all()
            return servers
        except Exception as e:
            logger.error(f"Error fetching all running/provisioning servers from DB: {e}", exc_info=True)
            return []
        finally:
            session.close()
            
    async def remove_game_server(self, gcp_instance_name: str) -> bool:
        """Marks a game server as DELETED or physically removes the record."""
        # Option 1: Mark as DELETED
        # return await self.update_game_server_status(gcp_instance_name, "DELETED", ip_address="") 
        # Option 2: Physically delete (more permanent)
        session = self.Session()
        try:
            server = session.query(GameServerInstance).filter_by(gcp_instance_name=gcp_instance_name).first()
            if server:
                session.delete(server)
                session.commit()
                logger.info(f"Game server '{gcp_instance_name}' removed from DB.")
                return True
            logger.warning(f"Game server '{gcp_instance_name}' not found in DB for removal.")
            return False
        except Exception as e:
            logger.error(f"Error removing game server '{gcp_instance_name}' from DB: {e}", exc_info=True)
            session.rollback()
            return False
        finally:
            session.close()
