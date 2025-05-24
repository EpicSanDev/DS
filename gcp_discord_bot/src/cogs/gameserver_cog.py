from discord.ext import commands, tasks
from discord import app_commands, Interaction
import discord
import datetime # Required for auto-shutdown logic
import json
import os
import asyncio # Add asyncio import
import re # For regex validation

from src.core import settings
from src.utils.logger import get_logger
from src.utils import permissions # Import permissions
from src.cogs.db_cog import DBCog # Import DBCog for rate limiting
# Import GcpCog to use its methods if needed, or interact via bot.get_cog("GcpCog")
# from src.cogs.gcp_cog import GcpCog 

logger = get_logger(__name__)

# --- Rate Limiting Check Function ---
async def gameserv_rate_limit_check(interaction: discord.Interaction) -> bool:
    """Checks if the user is rate-limited for GameServer commands."""
    db_cog: DBCog = interaction.client.get_cog("DBCog")
    if not db_cog:
        logger.error("DBCog not found, cannot perform rate limit check for GameServerCog.")
        return True # Fail open if DBCog is missing
    return await db_cog.check_app_command_rate_limit(interaction)

# Define a simple structure for game server templates
# This could be loaded from a JSON/YAML file in the future
GAME_SERVER_TEMPLATES_PATH = "config/game_server_templates.json"

# --- Confirmation View for Deletion ---
class ConfirmDeleteView(discord.ui.View):
    def __init__(self, original_interaction: Interaction, instance_name: str, game_server_cog_instance):
        super().__init__(timeout=60.0) # View times out after 60 seconds
        self.original_interaction = original_interaction
        self.instance_name = instance_name
        self.game_server_cog = game_server_cog_instance
        self.confirmed = None # To store the result

    async def interaction_check(self, interaction: Interaction) -> bool:
        # Only allow the original command user to interact
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("You cannot interact with this confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger, custom_id="confirm_delete_server")
    async def confirm_button(self, interaction: Interaction, button: discord.ui.Button):
        self.confirmed = True
        # Disable buttons after click
        for item in self.children:
            item.disabled = True
        # Acknowledge the button click, then the main command will handle the actual deletion
        # The main command will use interaction.edit_original_response to update the message.
        # Here, we just need to acknowledge. The actual deletion logic is in the command.
        # We can update the message here to show "Processing..."
        await interaction.response.edit_message(content=f"Deletion of `{self.instance_name}` confirmed. Processing...", view=self)
        self.stop() # Stop the view from listening to further interactions

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_delete_server")
    async def cancel_button(self, interaction: Interaction, button: discord.ui.Button):
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Deletion of `{self.instance_name}` cancelled.", view=self)
        self.stop()

    async def on_timeout(self):
        # If the view times out, disable buttons and inform the user
        if self.confirmed is None: # Only if no button was pressed
            for item in self.children:
                item.disabled = True
            # Check if original_interaction message can still be edited
            try:
                await self.original_interaction.edit_original_response(content=f"Deletion confirmation for `{self.instance_name}` timed out.", view=self)
            except discord.NotFound:
                logger.warning(f"Original interaction message for {self.instance_name} delete confirmation not found on timeout.")
            except Exception as e:
                logger.error(f"Error editing message on timeout for {self.instance_name} delete confirmation: {e}")


class GameServerCog(commands.Cog, name="Game Server Management"):
    """Cog for managing game servers on GCP VMs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gcp_cog = None # Will be set in cog_load
        self.game_templates = self._load_game_templates()
        logger.info(f"GameServerCog loaded. {len(self.game_templates)} game templates available.")

    async def cog_load(self):
        """Cog-specific setup. Called after the cog is added to the bot."""
        # It's better to get the GcpCog instance here, after all cogs are potentially loaded.
        # This avoids potential circular dependencies or load order issues if GcpCog isn't ready during __init__.
        # We wait a bit to ensure other cogs are loaded. This is a simple approach.
        # A more robust solution might involve an event or a ready state check.
        await asyncio.sleep(1) # Small delay to allow other cogs to load
        self.gcp_cog = self.bot.get_cog("GCP Management")
        if not self.gcp_cog:
            logger.error("GCP Management cog not found. GameServerCog may not function correctly for VM operations.")
        else:
            logger.info("GCP Management cog successfully linked in GameServerCog.")


    def _load_game_templates(self):
        """Loads game server templates from a JSON file."""
        templates = {}
        if not os.path.exists(GAME_SERVER_TEMPLATES_PATH):
            logger.warning(f"Game server templates file not found: {GAME_SERVER_TEMPLATES_PATH}. Creating an empty example.")
            # Create an example file if it doesn't exist
            example_templates = {
                "minecraft_vanilla": {
                    "display_name": "Minecraft (Vanilla Java)",
                    "description": "Serveur Minecraft Java Edition standard. Permet de spécifier la version, RAM, et quelques propriétés serveur.",
                    "image_project": "debian-cloud",
                    "image_family": "debian-11",
                    "machine_type": "e2-medium",
                    "disk_size_gb": 20,
                    "default_ports": [{"port": 25565, "protocol": "TCP", "description": "Minecraft Java Edition"}],
                    "startup_script_template": """#!/bin/bash
# Minecraft Server Startup Script - Template Avancé
# Paramètres attendus (via custom_params_json, avec des valeurs par défaut de config_params):
# server_version, max_ram, min_ram, server_name, difficulty, pvp, online_mode, eula_accepted (doit être true)
# mods_list (array of objects: [{"name": "ModName", "url": "ModURL"}]) - Optionnel
# config_file_url (URL for server.properties) - Optionnel

echo "--- Début du script de démarrage du serveur Minecraft ---"

# Variables (avec valeurs par défaut si non fournies par le template)
SERVER_VERSION="{server_version:-LATEST_VERSION_HERE}" # Remplacer LATEST_VERSION_HERE par une logique de récupération ou une version fixe
MAX_RAM="{max_ram:-2048}"
MIN_RAM="{min_ram:-1024}"
SERVER_NAME_PARAM="{server_name:-A Minecraft Server}"
DIFFICULTY_PARAM="{difficulty:-easy}"
PVP_PARAM="{pvp:-true}"
ONLINE_MODE_PARAM="{online_mode:-true}"
EULA_ACCEPTED="{eula_accepted:-false}" # L'utilisateur DOIT accepter l'EULA via custom_params_json

MODS_JSON='{mods_list_json:-[]}' # Attendre un JSON stringifié pour les mods
CONFIG_FILE_URL="{config_file_url:-}"

if [ "$EULA_ACCEPTED" != "true" ]; then
    echo "ERREUR: L'EULA de Minecraft doit être acceptée. Veuillez mettre eula_accepted=true dans custom_params_json."
    exit 1
fi

echo "Installation des dépendances..."
sudo apt update
sudo apt install -y openjdk-17-jre-headless wget screen curl jq

SERVER_DIR="/srv/minecraft_server"
mkdir -p "$SERVER_DIR/config" "$SERVER_DIR/mods"
cd "$SERVER_DIR"

echo "Téléchargement du JAR du serveur Minecraft (version: $SERVER_VERSION)..."
# Logique pour télécharger le JAR (ex: PaperMC, Fabric, etc.). Ceci est un placeholder.
# Vous devrez adapter cette section pour la source de JAR que vous souhaitez utiliser.
# Exemple pour PaperMC (nécessite de connaître la build pour la version)
# VERSION_URL="https://api.papermc.io/v2/projects/paper/versions/$SERVER_VERSION"
# LATEST_BUILD=$(curl -s $VERSION_URL | jq -r '.builds[-1]')
# if [ "$LATEST_BUILD" != "null" ]; then
#     JAR_URL="https://api.papermc.io/v2/projects/paper/versions/$SERVER_VERSION/builds/$LATEST_BUILD/downloads/paper-$SERVER_VERSION-$LATEST_BUILD.jar"
#     wget "$JAR_URL" -O server.jar
# else
#     echo "Impossible de trouver la build pour PaperMC version $SERVER_VERSION. Utilisation d'un placeholder."
#     echo "java -version" > server.jar # Placeholder
# fi
echo "Placeholder: Téléchargez votre server.jar ici pour la version $SERVER_VERSION"
# wget <URL_DE_VOTRE_SERVER.JAR> -O server.jar

echo "Configuration de server.properties..."
if [ -n "$CONFIG_FILE_URL" ]; then
    echo "Téléchargement de server.properties depuis $CONFIG_FILE_URL..."
    wget -O "$SERVER_DIR/server.properties" "$CONFIG_FILE_URL"
else
    echo "Création de server.properties par défaut..."
    echo "motd=$SERVER_NAME_PARAM" > server.properties
    echo "difficulty=$DIFFICULTY_PARAM" >> server.properties
    echo "pvp=$PVP_PARAM" >> server.properties
    echo "online-mode=$ONLINE_MODE_PARAM" >> server.properties
    # Ajoutez d'autres propriétés par défaut ici
fi

echo "Acceptation de l'EULA..."
echo "eula=true" > eula.txt

echo "Téléchargement des mods (si spécifiés)..."
# Ceci est un exemple basique. Une gestion robuste des mods est complexe.
# jq doit être installé pour parser le JSON.
# MODS_LIST=$(echo "$MODS_JSON" | jq -c '.[]')
# if [ -n "$MODS_LIST" ]; then
#     echo "$MODS_LIST" | while IFS= read -r mod_obj; do
#         mod_name=$(echo "$mod_obj" | jq -r '.name')
#         mod_url=$(echo "$mod_obj" | jq -r '.url')
#         echo "Téléchargement du mod: $mod_name depuis $mod_url"
#         wget "$mod_url" -P "$SERVER_DIR/mods/"
#     done
# else
#     echo "Aucun mod spécifié ou liste de mods vide."
# fi
echo "Placeholder: Logique de téléchargement de mods ici."


echo "Démarrage du serveur Minecraft..."
# Utilisation de screen pour exécuter le serveur en arrière-plan
# Assurez-vous que le nom de screen est unique si plusieurs serveurs peuvent tourner sur la même VM (non recommandé ici)
screen -dmS minecraft java -Xmx${MAX_RAM}M -Xms${MIN_RAM}M -jar server.jar nogui

echo "--- Script de démarrage du serveur Minecraft terminé ---"
# Un fichier de statut peut être utile pour des vérifications externes
echo "Server $SERVER_NAME_PARAM (version $SERVER_VERSION) démarré avec $MAX_RAM MB RAM." > "$SERVER_DIR/status.txt"
""",
                    "config_params": [
                        {"name": "server_version", "description": "Version du serveur Minecraft (ex: 1.20.4).", "default": "1.20.4"},
                        {"name": "max_ram", "description": "RAM maximale pour le serveur en MB (ex: 2048 pour 2GB).", "default": "2048"},
                        {"name": "min_ram", "description": "RAM minimale pour le serveur en MB (ex: 1024 pour 1GB).", "default": "1024"},
                        {"name": "eula_accepted", "description": "Acceptez l'EULA de Minecraft (doit être 'true').", "default": "false"},
                        {"name": "server_name", "description": "Nom du serveur (Message du Jour).", "default": "A Minecraft Server by Discord Bot"},
                        {"name": "difficulty", "description": "Difficulté du jeu (peaceful, easy, normal, hard).", "default": "easy"},
                        {"name": "pvp", "description": "Activer le PvP (true/false).", "default": "true"},
                        {"name": "online_mode", "description": "Mode en ligne (true/false).", "default": "true"},
                        {"name": "mods_list_json", "description": "JSON stringifié d'une liste de mods (ex: '[{\"name\":\"Optifine\",\"url\":\"...\"}]').", "default": "[]"},
                        {"name": "config_file_url", "description": "URL vers un fichier server.properties personnalisé.", "default": ""}
                    ]
                }
            }
            try:
                with open(GAME_SERVER_TEMPLATES_PATH, 'w') as f:
                    json.dump(example_templates, f, indent=4)
                logger.info(f"Example game server templates file created at {GAME_SERVER_TEMPLATES_PATH}")
                return example_templates
            except IOError as e:
                logger.error(f"Could not write example game server templates file: {e}")
                return {} # Return empty if creation fails

        try:
            with open(GAME_SERVER_TEMPLATES_PATH, 'r') as f:
                templates = json.load(f)
            logger.info(f"Successfully loaded {len(templates)} game templates from {GAME_SERVER_TEMPLATES_PATH}.")
        except FileNotFoundError:
            logger.error(f"Game server templates file not found: {GAME_SERVER_TEMPLATES_PATH}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding game server templates file {GAME_SERVER_TEMPLATES_PATH}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while loading game templates: {e}", exc_info=True)
        return templates

    @app_commands.command(name="gameserv_list_templates", description="Lists available game server templates.")
    async def list_game_templates(self, interaction: Interaction):
        if not self.game_templates:
            await interaction.response.send_message("No game server templates are currently loaded.", ephemeral=True)
            return

        embed = discord.Embed(title="Available Game Server Templates", color=discord.Color.purple())
        for key, template in self.game_templates.items():
            embed.add_field(name=template.get("display_name", key), value=f"`{key}`", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gameserv_create", description="Creates a game server on GCP. (VM Operator+)")
    @permissions.has_vm_operator_role() # Requires VM Operator role or higher
    @app_commands.check(gameserv_rate_limit_check)
    @app_commands.describe(
        template_name="The key of the game server template to use (see /gameserv_list_templates).",
        instance_name="A unique name for this game server instance (e.g., my-mc-server).",
        zone="Optional GCP zone for the VM (e.g., europe-west1-b, defaults to GcpCog's default).",
        custom_params_json="Optional JSON string for custom template parameters (e.g., {\"server_version\":\"1.19.4\"}).",
        auto_shutdown_hours="Optional: Number of hours after which the server will automatically shut down. Leave empty for no auto-shutdown."
    )
    async def create_game_server(self, interaction: Interaction, template_name: str, instance_name: str, zone: str = None, custom_params_json: str = None, auto_shutdown_hours: app_commands.Range[int, 1, 720] = None):
        # Validate instance_name
        if not re.fullmatch(r"[a-z]([-a-z0-9]*[a-z0-9])?", instance_name) or not (1 <= len(instance_name) <= 63):
            await interaction.response.send_message(
                "Nom d'instance invalide. Il doit commencer par une lettre minuscule, contenir uniquement des lettres minuscules, des chiffres ou des tirets, "
                "ne pas se terminer par un tiret, et avoir une longueur de 1 à 63 caractères.",
                ephemeral=True
            )
            return

        if not self.gcp_cog:
            await interaction.response.send_message("GCP Cog is not available. Cannot create VM.", ephemeral=True)
            return

        if template_name not in self.game_templates:
            await interaction.response.send_message(f"Template '{template_name}' not found. Use `/gameserv_list_templates` to see available ones.", ephemeral=True)
            return

        template = self.game_templates[template_name]
        
        # Abuse Prevention Checks
        db_cog = self.bot.get_cog("DBCog")
        if not db_cog:
            await interaction.response.send_message("Database service unavailable, cannot perform abuse checks.", ephemeral=True)
            return

        user_id_str = str(interaction.user.id)

        # Check 1: Max active VMs per user
        max_active_vms = settings.get_max_active_vms_per_user()
        if max_active_vms > 0:
            active_user_servers = await db_cog.get_user_active_game_servers(user_id_str)
            if len(active_user_servers) >= max_active_vms:
                await interaction.response.send_message(f"Vous avez atteint la limite de {max_active_vms} serveur(s) actif(s). Veuillez en supprimer un avant d'en créer un nouveau.", ephemeral=True)
                return
        
        # Check 2: Max total VMs managed per user (can be added similarly if needed, querying all non-DELETED)
        # For now, focusing on active VMs and cooldown.

        # Check 3: VM Creation Cooldown
        cooldown_seconds = settings.get_vm_creation_cooldown_seconds()
        if cooldown_seconds > 0:
            # The command name logged by on_interaction is just the base command name.
            # If the slash command is part of a group, it might be different.
            # For /gameserv_create, the logged name should be 'gameserv_create'.
            last_creation_timestamp = await db_cog.get_last_command_timestamp(user_id_str, "gameserv_create")
            if last_creation_timestamp:
                import datetime # Ensure datetime is imported
                time_since_last_creation = datetime.datetime.utcnow() - last_creation_timestamp
                if time_since_last_creation.total_seconds() < cooldown_seconds:
                    remaining_cooldown = cooldown_seconds - time_since_last_creation.total_seconds()
                    await interaction.response.send_message(
                        f"Vous devez attendre encore {remaining_cooldown:.0f} secondes avant de pouvoir créer un nouveau serveur de jeu.",
                        ephemeral=True
                    )
                    return
        
        await interaction.response.defer(ephemeral=False, thinking=True) # Public thinking
        initial_message = await interaction.original_response() # Get the initial response message object to edit later

        progress_message = f"🚀 Création du serveur de jeu `{instance_name}` avec le template `{template_name}` en cours...\n"
        await initial_message.edit(content=progress_message)

        try:
            current_step_message = await interaction.followup.send("Étape 1/5 : Préparation des paramètres...", ephemeral=False)
            # 1. Prepare parameters
            vm_image_project = template.get("image_project", "debian-cloud")
            vm_image_family = template.get("image_family", "debian-11")
            vm_machine_type = template.get("machine_type", "e2-medium") # User could override this via custom_params if we allow
            vm_disk_size_gb = template.get("disk_size_gb", 20)
            
            # Process custom parameters
            startup_params = {}
            if template.get("config_params"):
                for p_info in template["config_params"]:
                    startup_params[p_info["name"]] = p_info.get("default")

            if custom_params_json:
                try:
                    user_params = json.loads(custom_params_json)
                    startup_params.update(user_params) # User params override defaults
                except json.JSONDecodeError:
                    await interaction.followup.send("Invalid JSON format for custom parameters.", ephemeral=True)
                    return
            
            # 2. Prepare startup script
            startup_script = None
            if "startup_script_template" in template:
                try:
                    startup_script = template["startup_script_template"].format(**startup_params)
                except KeyError as e:
                    await interaction.followup.send(f"Missing parameter for startup script: {e}. Check template's config_params.", ephemeral=True)
                    logger.error(f"Startup script formatting error for template {template_name}: missing key {e}")
                    return
            
            # 3. Call gcp_cog.create_vm
            # We need to pass the startup script to the GcpCog's create_vm method.
            # This requires modifying gcp_cog.create_vm to accept metadata for startup scripts.
            # For now, let's assume gcp_cog.create_vm is modified or we pass it some other way.
            # Let's simulate this by logging what would be passed.
            
            logger.info(f"Requesting VM creation from GcpCog for instance '{instance_name}' using template '{template_name}'.")
            logger.info(f"VM Params: ImageProject='{vm_image_project}', ImageFamily='{vm_image_family}', MachineType='{vm_machine_type}', DiskSizeGB='{vm_disk_size_gb}', Zone='{zone or self.gcp_cog.default_zone}'")
            if startup_script:
                 logger.info(f"Startup script to be used (first 100 chars): {startup_script[:100]}...")
            
            # This is where the actual call to a potentially modified gcp_cog.create_vm would go.
            # It needs to accept `metadata_items` for the startup script.
            # Example modification in GcpCog:
            # In create_vm: add `metadata_items: list = None` to params
            # In instance_config: add `"metadata": {"items": metadata_items if metadata_items else []},`
            
            # For now, we'll call the existing create_vm and then handle ports.
            # The startup script part needs GcpCog to be updated.
            # Let's assume for now the GcpCog's create_vm is called and succeeds.
            # We'll need to get the GcpCog's create_vm to return the instance details or at least success.

            # --- SIMULATED GcpCog Interaction (replace with actual calls once GcpCog is updated) ---
            # This part needs to be implemented by calling the actual GcpCog methods.
            # We'll need to modify GcpCog's create_vm to accept startup_script as metadata.
            # For now, let's assume the VM is created and we proceed to open ports.
            
            # Let's make a placeholder call to the existing create_vm.
            # This won't include the startup script yet.
            # We'll need to update GcpCog.create_vm to accept metadata.
            
            # Create a list of metadata items if startup_script exists
            vm_metadata_items = []
            if startup_script:
                vm_metadata_items.append({"key": "startup-script", "value": startup_script})

            # We need to call the actual create_vm method from gcp_cog
            # This requires gcp_cog.create_vm to be an actual method of the GcpCog class
            # and to handle the interaction object correctly for responses.
            # For now, this is a conceptual flow.
            
            # Let's assume gcp_cog.create_vm is updated to accept metadata and returns True/False or instance details
            # For the purpose of this step, we'll directly call the GcpCog's create_vm method.
            vm_metadata_items = []
            if startup_script:
                vm_metadata_items.append({"key": "startup-script", "value": startup_script})

            # Define a unique tag for this game server VM instance
            game_server_specific_tag = f"gameserv-{instance_name.lower().replace('_', '-')}"[:63]
            # Combine with default tags or other tags from template if any
            vm_custom_tags = template.get("additional_tags", [])
            vm_custom_tags.append(game_server_specific_tag)
            # Ensure the base 'discord-bot-vm' tag is present if GcpCog's _create_vm_logic adds it by default,
            # or add it here if it doesn't. Current _create_vm_logic adds 'discord-bot-vm' and extends with custom_tags.

            vm_custom_labels = template.get("labels", {})
            vm_custom_labels.update({"game-template": template_name, "game-instance-name": instance_name})

            target_zone_for_vm = zone if zone else self.gcp_cog.default_zone
            if not target_zone_for_vm:
                # This should ideally be caught earlier or by GcpCog if its default_zone is also None
                await interaction.edit_original_response(content="Error: GCP zone could not be determined. Please specify a zone or configure a default in GcpCog.")
                return
            
            await current_step_message.edit(content=progress_message + f"Étape 2/5 : Lancement de la création de la VM `{instance_name}` dans la zone `{target_zone_for_vm}`...")
            created_instance = await self.gcp_cog._create_vm_logic(
                instance_name=instance_name,
                machine_type=vm_machine_type,
                image_project=vm_image_project,
                image_family=vm_image_family,
                disk_size_gb=vm_disk_size_gb,
                zone=target_zone_for_vm, # Use the resolved zone
                created_by_user_id=str(interaction.user.id),
                metadata_items=vm_metadata_items,
                custom_tags=list(set(vm_custom_tags)), # Ensure unique tags
                custom_labels=vm_custom_labels
            )

            ip_address = "N/A"
            if created_instance.network_interfaces and created_instance.network_interfaces[0].access_configs:
                ip_address = created_instance.network_interfaces[0].access_configs[0].nat_ip
            
            await current_step_message.edit(content=progress_message + f"Étape 3/5 : VM `{created_instance.name}` est CRÉÉE avec IP : `{ip_address}`. Traitement du script de démarrage en cours...")
            # Note: Actual startup script completion isn't directly known here. This is an optimistic message.
            # A more advanced system might have the script signal completion (e.g., writing to a metadata endpoint or log).

            # 4. Open default ports using the specific tag for this game server
            opened_ports_info = []
            if template.get("default_ports"):
                await current_step_message.edit(content=progress_message + f"Étape 4/5 : Configuration des règles de pare-feu pour le tag `{game_server_specific_tag}`...")
                for port_info in template["default_ports"]:
                    port_num = port_info["port"]
                    port_proto = port_info.get("protocol", "TCP").upper()
                    port_desc = port_info.get("description", f"Port for {template.get('display_name', template_name)} on {instance_name}")
                    # Ensure firewall rule name is unique and valid
                    firewall_rule_name = f"allow-{instance_name[:20]}-{port_num}-{port_proto.lower()}"[:62]
                    
                    try:
                        await self.gcp_cog._open_port_logic(
                            firewall_rule_name=firewall_rule_name,
                            target_tag=game_server_specific_tag, # Use the specific tag
                            port=port_num,
                            protocol=port_proto,
                            description=port_desc
                        )
                        opened_ports_info.append(f"{port_num}/{port_proto}")
                        logger.info(f"Successfully opened port {port_num}/{port_proto} via rule '{firewall_rule_name}' for tag '{game_server_specific_tag}'.")
                        # We'll send a summary of firewall rules at the end of this block.
                    except Exception as e:
                        logger.error(f"Failed to open port {port_num}/{port_proto} for {instance_name} (rule: {firewall_rule_name}): {e}", exc_info=True)
                        # We can't send a new followup while editing current_step_message. Log errors, user will see final status.
                        logger.error(f"Error configuring firewall for port {port_num}/{port_proto} on '{instance_name}': {e}")
                
                if opened_ports_info:
                     logger.info(f"Firewall ports configured: {', '.join(opened_ports_info)} for tag `{game_server_specific_tag}`.")
                else:
                    logger.info("No default ports specified in template for firewall configuration.")
            
            await current_step_message.edit(content=progress_message + "Étape 5/5 : Enregistrement du serveur dans la base de données...")
            # 5. Store game server info in DB
            # db_cog = self.bot.get_cog("DBCog") # Assuming DBCog is the class name
            # if db_cog:
            #     await db_cog.log_game_server_deployment(
            #         user_id=interaction.user.id,
            #         instance_name=instance_name,
            #         instance_id=created_instance.id,
            #         zone=target_zone_for_vm,
            #         game_template=template_name,
            #         ip_address=ip_address,
            #         ports_opened=[f"{p['port']}/{p.get('protocol','TCP')}" for p in template.get("default_ports", [])],
            #         status="provisioned" # Or "running" if startup script confirms
            #     )
            
            db_cog = self.bot.get_cog("DBCog")
            if not db_cog:
                logger.error("DBCog not found, cannot register game server in database.")
                # Continue without DB logging for now, or raise an error
            else:
                try:
                    await db_cog.register_game_server(
                        discord_user_id=str(interaction.user.id),
                        gcp_instance_name=created_instance.name,
                        gcp_instance_id=str(created_instance.id),
                        gcp_zone=target_zone_for_vm,
                        game_template_name=template_name,
                        ip_address=ip_address,
                        ports_info=[{"port": p["port"], "protocol": p.get("protocol","TCP").upper()} for p in template.get("default_ports", [])],
                        status="RUNNING" if ip_address != "N/A" else "PROVISIONING_FAILED_IP", # Simplified status
                        additional_config=startup_params, # Store the parameters used
                        auto_shutdown_hours=auto_shutdown_hours
                    )
                    logger.info(f"Game server '{created_instance.name}' (type: {template_name}, auto_shutdown: {auto_shutdown_hours}h) provisioned and registered by user {interaction.user.id}.")
                except Exception as db_exc:
                    logger.error(f"Failed to register game server '{created_instance.name}' in DB: {db_exc}", exc_info=True)
                    # Potentially send a message to user that DB logging failed but VM might be up.

            final_message = f"✅ Serveur de jeu '{instance_name}' (template: '{template.get('display_name', template_name)}') provisionné avec succès sur la VM '{created_instance.name}' (type: `{vm_machine_type}`) dans la zone '{target_zone_for_vm}' avec l'IP : `{ip_address}`."
            if opened_ports_info:
                final_message += f"\nPorts configurés ({', '.join(opened_ports_info)}) avec le tag `{game_server_specific_tag}`."
            else:
                final_message += "\nAucun port par défaut n'a été spécifié dans le template pour être ouvert."
            if auto_shutdown_hours:
                final_message += f"\nℹ️ Ce serveur s'arrêtera automatiquement dans {auto_shutdown_hours} heure(s)."
            
            gcp_price_calculator_url = "https://cloud.google.com/products/calculator"
            final_message += f"\n\n⚠️ **Note sur les coûts** : L'utilisation de cette VM engendre des coûts sur GCP. Type de machine : `{vm_machine_type}`. Consultez le [Calculateur de prix GCP]({gcp_price_calculator_url}) pour une estimation."
            final_message += "\n\nVotre serveur devrait être prêt sous peu une fois le script de démarrage terminé !"
            
            await current_step_message.edit(content=final_message) # Update the step message to be the final success message
            if initial_message.id != current_step_message.id: # If followup was used, delete the original "Creating..." message
                await initial_message.delete()


        except Exception as e:
            logger.error(f"Error creating game server '{instance_name}' with template '{template_name}': {e}", exc_info=True)
            error_message = f"❌ Une erreur est survenue lors de la création du serveur de jeu '{instance_name}':\n`{str(e)}`\nVeuillez vérifier les logs pour plus de détails."
            if current_step_message:
                await current_step_message.edit(content=error_message)
            else: # Should not happen if defer was successful
                await initial_message.edit(content=error_message)
            # If initial_message was already edited by a step, and current_step_message is the one we are editing.
            # No, if an error occurs before current_step_message is defined, we edit initial_message.
            # If current_step_message exists, we edit that.
            # The goal is to have one final message indicating success or failure.


    @app_commands.command(name="gameserv_list", description="Lists your provisioned game servers.")
    async def list_user_game_servers(self, interaction: Interaction):
        db_cog = self.bot.get_cog("DBCog")
        if not db_cog:
            await interaction.response.send_message("Database service is unavailable.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            user_servers = await db_cog.get_user_active_game_servers(str(interaction.user.id))
            if not user_servers:
                await interaction.followup.send("You have no active game servers.", ephemeral=True)
                return

            embed = discord.Embed(title=f"Your Game Servers ({interaction.user.display_name})", color=discord.Color.dark_gold())
            for server in user_servers:
                ports_display = "N/A"
                if server.ports_info:
                    try:
                        ports_list = json.loads(server.ports_info)
                        ports_display = ", ".join([f"{p['port']}/{p['protocol']}" for p in ports_list])
                    except json.JSONDecodeError:
                        ports_display = "Error parsing ports"
                
                value = (
                    f"**GCP Name:** `{server.gcp_instance_name}`\n"
                    f"**Template:** {server.game_template_name}\n"
                    f"**Status:** {server.status}\n"
                    f"**IP:** {server.ip_address or 'N/A'}\n"
                    f"**Zone:** {server.gcp_zone}\n"
                    f"**Ports:** {ports_display}\n"
                    f"**Created:** {server.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
                )
                embed.add_field(name=f"🎮 {server.gcp_instance_name}", value=value, inline=False)
            
            if not embed.fields: # Should be caught by user_servers check
                 await interaction.followup.send("No game servers found for you or an error occurred.", ephemeral=True)
                 return

            await interaction.followup.send(embed=embed, ephemeral=True) # Keep it ephemeral for user's own list

        except Exception as e:
            logger.error(f"Error listing game servers for user {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while listing your game servers: {e}", ephemeral=True)

    @app_commands.command(name="gameserv_status", description="Gets the status of a specific game server.")
    @app_commands.describe(instance_name="The GCP instance name of the game server.")
    async def game_server_status(self, interaction: Interaction, instance_name: str):
        db_cog = self.bot.get_cog("DBCog")
        if not db_cog or not self.gcp_cog:
            await interaction.response.send_message("Required services (DB or GCP) are unavailable.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=False, thinking=True)
        try:
            db_server_info = await db_cog.get_game_server_by_name(instance_name)
            if not db_server_info:
                await interaction.followup.send(f"Game server '{instance_name}' not found in the database.", ephemeral=True)
                return

            # Optionally, query GCP for real-time status if db status is stale or for more details
            # For now, we rely on DB status which should be updated by control commands.
            # A more advanced version would call self.gcp_cog.describe_vm here.
            
            # Placeholder for fetching live GCP status:
            # In a future step, we would add a method like `_get_instance_details` to GcpCog
            # and call it here to get the latest status from GCP, then update the DB.
            # For now, we'll just log that we're using DB status.
            logger.info(f"Displaying status for '{instance_name}' based on database record. Live GCP check can be added later.")

            ports_display = "N/A"
            if db_server_info.ports_info:
                try:
                    ports_list = json.loads(db_server_info.ports_info)
                    ports_display = ", ".join([f"{p['port']}/{p['protocol']}" for p in ports_list])
                except json.JSONDecodeError:
                    ports_display = "Error parsing ports"

            embed = discord.Embed(title=f"Status for Game Server: {db_server_info.gcp_instance_name}", color=discord.Color.blue())
            embed.add_field(name="GCP Instance Name", value=f"`{db_server_info.gcp_instance_name}`", inline=False)
            embed.add_field(name="Owned By (Discord ID)", value=f"`{db_server_info.discord_user_id}`", inline=False)
            embed.add_field(name="Game Template", value=db_server_info.game_template_name, inline=True)
            embed.add_field(name="Current Status (DB)", value=db_server_info.status, inline=True)
            embed.add_field(name="IP Address", value=db_server_info.ip_address or "N/A", inline=True)
            embed.add_field(name="GCP Zone", value=db_server_info.gcp_zone, inline=True)
            embed.add_field(name="Ports Configured", value=ports_display, inline=False)
            embed.add_field(name="Created At", value=db_server_info.created_at.strftime('%Y-%m-%d %H:%M UTC'), inline=True)
            embed.add_field(name="Last Status Update", value=db_server_info.last_status_update.strftime('%Y-%m-%d %H:%M UTC'), inline=True)
            
            # Add a note if live GCP status couldn't be fetched or if it's different
            # embed.set_footer(text="Status based on database record. For live GCP status, use /gcp_describe_vm.")

            await interaction.followup.send(embed=embed, ephemeral=False)

        except Exception as e:
            logger.error(f"Error getting status for game server '{instance_name}': {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while getting status for '{instance_name}': {e}", ephemeral=True)

    async def _control_game_server(self, interaction: Interaction, instance_name: str, action: str):
        """Helper function to start, stop, or delete a game server."""
        db_cog = self.bot.get_cog("DBCog")
        if not db_cog or not self.gcp_cog:
            await interaction.response.send_message("Required services (DB or GCP) are unavailable.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False, thinking=True)
        
        try:
            server_info = await db_cog.get_game_server_by_name(instance_name)
            if not server_info:
                await interaction.followup.send(f"Game server '{instance_name}' not found in the database.", ephemeral=True)
                return

            # Basic ownership check (can be expanded with roles/permissions)
            if str(interaction.user.id) != server_info.discord_user_id and not await self.bot.is_owner(interaction.user):
                await interaction.followup.send(f"You do not have permission to {action} server '{instance_name}'.", ephemeral=True)
                return

            gcp_action_map = {
                "start": ("start", "STARTING", "RUNNING", "started"),
                "stop": ("stop", "STOPPING", "TERMINATED", "stopped"), # GCP status is TERMINATED when stopped
                "delete": ("delete", "DELETING", "DELETED", "deleted")
            }

            if action not in gcp_action_map:
                await interaction.followup.send(f"Invalid server action: {action}.", ephemeral=True)
                return

            gcp_method_name, pending_status, final_status, past_tense_action = gcp_action_map[action]
            
            # Call the GcpCog's internal control method
            # GcpCog._control_vm expects an interaction object for its own responses,
            # but here GameServerCog is managing the interaction.
            # We need to adapt or call a more primitive version from GcpCog if available,
            # or GcpCog._control_vm needs to be callable without sending its own followup if used internally.
            # For now, let's assume GcpCog._control_vm can be called and we handle followup here.
            # This part needs careful review of GcpCog._control_vm's interaction handling.
            # A better GcpCog design would have _start_vm_logic, _stop_vm_logic, _delete_vm_logic.
            # For now, we'll try to use the existing _control_vm and suppress its direct followup if possible,
            # or just let it send its own and we add to it.

            # Let's assume GcpCog._control_vm is refactored to not send its own followup when called internally,
            # or it returns a success/failure that we can use.
            # For simplicity, we'll call it and then update DB.
            
            await db_cog.update_game_server_status(instance_name, pending_status)
            
            # This is a conceptual call. GcpCog._control_vm is an app_command handler.
            # We need to call the actual GCP SDK methods via GcpCog's internal logic.
            # GcpCog has: self.compute_client.start(), .stop(), .delete()
            # We should call these via a refactored GcpCog method.
            # For now, let's simulate the call to the GCP action and wait.

            gcp_op_future = None
            if action == "start":
                gcp_op_future = self.gcp_cog.compute_client.start(project=self.gcp_cog.project_id, zone=server_info.gcp_zone, instance=instance_name)
            elif action == "stop":
                gcp_op_future = self.gcp_cog.compute_client.stop(project=self.gcp_cog.project_id, zone=server_info.gcp_zone, instance=instance_name)
            elif action == "delete":
                gcp_op_future = self.gcp_cog.compute_client.delete(project=self.gcp_cog.project_id, zone=server_info.gcp_zone, instance=instance_name)
            
            await interaction.followup.send(f"Action '{action}' for game server '{instance_name}' initiated with GCP. Operation: {gcp_op_future.name}. Waiting for completion...", ephemeral=False)
            
            completed_gcp_op = await self.gcp_cog.wait_for_operation(self.gcp_cog.project_id, server_info.gcp_zone, gcp_op_future.name)

            if completed_gcp_op:
                new_ip = None
                if action == "start":
                    # Fetch instance to get new IP if it was dynamic
                    instance_details = self.gcp_cog.compute_client.get(project=self.gcp_cog.project_id, zone=server_info.gcp_zone, instance=instance_name)
                    if instance_details.network_interfaces and instance_details.network_interfaces[0].access_configs:
                        new_ip = instance_details.network_interfaces[0].access_configs[0].nat_ip
                elif action == "stop" or action == "delete":
                    new_ip = "" # Clear IP

                await db_cog.update_game_server_status(instance_name, final_status, ip_address=new_ip)
                
                if action == "delete":
                    # Construct the unique tag for the game server
                    game_server_specific_tag = f"gameserv-{instance_name.lower().replace('_', '-')}"[:63]
                    logger.info(f"Attempting to delete firewall rules for tag: {game_server_specific_tag}")
                    
                    try:
                        associated_firewall_rules = await self.gcp_cog._list_firewall_rules_by_target_tag(game_server_specific_tag)
                        if associated_firewall_rules:
                            deleted_rule_names = []
                            failed_to_delete_rules = []
                            for rule in associated_firewall_rules:
                                try:
                                    logger.info(f"Deleting firewall rule '{rule.name}' associated with tag '{game_server_specific_tag}'.")
                                    await self.gcp_cog._delete_firewall_rule_logic(firewall_rule_name=rule.name)
                                    deleted_rule_names.append(rule.name)
                                    # Short delay between deletions if needed, though GCP operations are async
                                    await asyncio.sleep(0.5) 
                                except Exception as fw_del_exc:
                                    logger.error(f"Failed to delete firewall rule '{rule.name}': {fw_del_exc}", exc_info=True)
                                    failed_to_delete_rules.append(rule.name)
                            
                            if deleted_rule_names:
                                await interaction.followup.send(f"Successfully deleted associated firewall rules: {', '.join(deleted_rule_names)}.", ephemeral=True)
                            if failed_to_delete_rules:
                                await interaction.followup.send(f"Warning: Failed to delete some associated firewall rules: {', '.join(failed_to_delete_rules)}. Please check GCP console.", ephemeral=True)
                        else:
                            logger.info(f"No firewall rules found with tag '{game_server_specific_tag}' to delete.")
                            await interaction.followup.send(f"No specific firewall rules found for tag '{game_server_specific_tag}' to delete.", ephemeral=True)
                    except Exception as list_fw_exc:
                        logger.error(f"Error listing firewall rules for tag '{game_server_specific_tag}' during delete: {list_fw_exc}", exc_info=True)
                        await interaction.followup.send(f"Warning: Could not list or delete associated firewall rules due to an error: {list_fw_exc}. Please check GCP console.", ephemeral=True)

                    # Remove from DB permanently
                    await db_cog.remove_game_server(instance_name)
                    logger.info(f"Game server '{instance_name}' removed from DB after deletion.")

                final_message = f"Game server '{instance_name}' has been successfully {past_tense_action}."
                if action == "start" and new_ip:
                    final_message += f" IP: {new_ip}"
                elif action == "delete":
                    final_message += " All associated resources (VM, disk, specific firewall rules) should now be deleted."
                
                await interaction.followup.send(final_message, ephemeral=False)

            # wait_for_operation raises on error, so no explicit else needed here for GCP failure.

        except Exception as e:
            logger.error(f"Error during game server action '{action}' for '{instance_name}': {e}", exc_info=True)
            await db_cog.update_game_server_status(instance_name, "ERROR") # Mark as error in DB
            await interaction.followup.send(f"An error occurred while trying to {action} server '{instance_name}': {e}", ephemeral=True)

    @app_commands.command(name="gameserv_start", description="Starts a game server. (Owner/Game Admin only)")
    @permissions.can_control_game_server()
    @app_commands.check(gameserv_rate_limit_check)
    @app_commands.describe(instance_name="The GCP instance name of the game server to start.")
    async def start_game_server(self, interaction: Interaction, instance_name: str):
        await self._control_game_server(interaction, instance_name, "start")

    @app_commands.command(name="gameserv_stop", description="Stops a game server. (Owner/Game Admin only)")
    @permissions.can_control_game_server()
    @app_commands.check(gameserv_rate_limit_check)
    @app_commands.describe(instance_name="The GCP instance name of the game server to stop.")
    async def stop_game_server(self, interaction: Interaction, instance_name: str):
        await self._control_game_server(interaction, instance_name, "stop")

    @app_commands.command(name="gameserv_delete", description="Deletes a game server. Irreversible! (Owner/Game Admin only)")
    @permissions.can_control_game_server()
    @app_commands.check(gameserv_rate_limit_check)
    @app_commands.describe(instance_name="The GCP instance name of the game server to delete.")
    async def delete_game_server(self, interaction: Interaction, instance_name: str):
        view = ConfirmDeleteView(original_interaction=interaction, instance_name=instance_name, game_server_cog_instance=self)
        
        # Send the confirmation message with buttons
        # We use followup if defer was used, or send_message if not.
        # _control_game_server will defer, so we should use followup here if we call it after confirmation.
        # For now, let's send the initial confirmation.
        await interaction.response.send_message(
            f"Are you sure you want to delete the game server `{instance_name}`? This action is irreversible and will delete the VM and associated firewall rules.",
            view=view,
            ephemeral=False # Make confirmation visible
        )
        
        # Wait for the view to stop (either by button click or timeout)
        await view.wait()

        if view.confirmed is True:
            # User confirmed. Proceed with deletion.
            # The _control_game_server method handles its own deferral and followups.
            # We need to pass a "clean" interaction or handle responses carefully.
            # For simplicity, we'll call _control_game_server.
            # The button callback already edited the original message to "Processing...".
            # _control_game_server will then send further followups.
            logger.info(f"User {interaction.user.name} confirmed deletion for {instance_name}.")
            await self._control_game_server(interaction, instance_name, "delete")
            # The _control_game_server will send the final status message.
            # We might want to edit the original message again if _control_game_server doesn't.
            # For now, assume _control_game_server's followup is sufficient.
        elif view.confirmed is False:
            # User cancelled. Message already sent by button callback.
            logger.info(f"User {interaction.user.name} cancelled deletion for {instance_name}.")
            # No further action needed as the button callback handled the message update.
        else: # Timeout
            logger.info(f"Deletion confirmation for {instance_name} timed out for user {interaction.user.name}.")
            # Message already handled by view.on_timeout if it could edit.
            # If on_timeout failed to edit, we might send a followup here, but it's tricky.
            # For now, assume on_timeout handles it or it's okay if it doesn't.

    # Error handler for permission checks in this cog
    @create_game_server.error
    @start_game_server.error
    @stop_game_server.error
    @delete_game_server.error
    async def on_gameserv_command_permission_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        await permissions.handle_permission_check_failure(interaction, error)
        if not isinstance(error, app_commands.CheckFailure): # Log other errors
            logger.error(f"Unhandled error in GameServerCog command {interaction.command.name if interaction.command else 'unknown'}: {error}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)
            else:
                try:
                    await interaction.followup.send("An unexpected error occurred.", ephemeral=True)
                except discord.errors.HTTPException:
                    pass

    @app_commands.command(name="gameserv_get_log", description="Retrieves the game-specific log for a server (requires serial port setup).")
    @permissions.can_control_game_server() # Or a more specific permission if needed
    @app_commands.check(gameserv_rate_limit_check)
    @app_commands.describe(
        instance_name="The GCP instance name of the game server.",
        log_port_number="Serial port number configured for game logs (e.g., 2, 3, or 4)."
    )
    async def get_game_log(self, interaction: Interaction, instance_name: str, log_port_number: app_commands.Range[int, 2, 4] = 2):
        if not self.gcp_cog:
            await interaction.response.send_message("GCP Cog is not available.", ephemeral=True)
            return
        
        db_cog: DBCog = self.bot.get_cog("DBCog")
        if not db_cog:
            await interaction.response.send_message("Database Cog is not available.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            server_info = await db_cog.get_game_server_by_name(instance_name)
            if not server_info:
                await interaction.followup.send(f"Game server '{instance_name}' not found in the database.", ephemeral=True)
                return

            # Permission check: ensure the user owns the server or is an admin
            if str(interaction.user.id) != server_info.discord_user_id and \
               not permissions.is_bot_owner_check(interaction.user, self.bot) and \
               not await permissions.has_game_admin_role_check(interaction, self.bot): # Assuming a generic check
                await interaction.followup.send(f"You do not have permission to retrieve logs for server '{instance_name}'.", ephemeral=True)
                return

            logger.info(f"User {interaction.user.id} attempting to retrieve game log (serial port {log_port_number}) for VM '{instance_name}' in zone '{server_info.gcp_zone}'.")
            
            # Call GcpCog's get_vm_serial_log directly
            # This reuses the existing functionality in GcpCog
            serial_output_response = await self.gcp_cog.compute_client.get_serial_port_output(
                project=self.gcp_cog.project_id,
                zone=server_info.gcp_zone,
                instance=instance_name,
                port=log_port_number
            )
            
            log_content = serial_output_response.contents or f"No content found in serial port {log_port_number} output for {instance_name}."
            log_content = log_content[-1980:] # Get last ~2000 chars to fit in a message/file

            log_file_name = f"{instance_name}_game_port_{log_port_number}.log"
            with open(log_file_name, "w", encoding="utf-8") as f:
                f.write(log_content)
            
            discord_file = discord.File(log_file_name)
            await interaction.followup.send(
                f"Game log (from serial port {log_port_number}) for server `{instance_name}`:\n"
                f"(Note: This requires the VM's startup script to redirect game logs to serial port {log_port_number} (e.g., /dev/ttyS{log_port_number-1})).",
                file=discord_file, 
                ephemeral=True
            )
            
            os.remove(log_file_name)

        except discord.NotFound: # If the original interaction is gone
            logger.warning(f"Original interaction for gameserv_get_log for {instance_name} not found.")
        except Exception as e:
            logger.error(f"Error retrieving game log for VM '{instance_name}': {e}", exc_info=True)
            if interaction.response.is_done():
                 await interaction.followup.send(f"An error occurred while retrieving game log for VM '{instance_name}': {e}", ephemeral=True)
            else:
                 await interaction.response.send_message(f"An error occurred while retrieving game log for VM '{instance_name}': {e}", ephemeral=True)


    @tasks.loop(minutes=10) # Check every 10 minutes
    async def auto_shutdown_task(self):
        logger.info("Auto-shutdown task running...")
        db_cog: DBCog = self.bot.get_cog("DBCog")
        if not db_cog or not self.gcp_cog:
            logger.error("Auto-shutdown task: DBCog or GcpCog not found. Skipping check.")
            return

        try:
            running_servers = await db_cog.get_all_running_servers()
            if not running_servers:
                logger.info("Auto-shutdown task: No running servers with auto_shutdown_hours configured.")
                return

            for server in running_servers:
                if server.status == "RUNNING" and server.auto_shutdown_hours is not None:
                    # We need to compare against the time the server was last started or created.
                    # For simplicity, let's use created_at for now.
                    # A more robust solution would track last_started_at if servers can be stopped/started.
                    # Current GameServerInstance model has `last_status_update`. If status becomes RUNNING, this is updated.
                    # Let's assume `last_status_update` reflects the start time when status is RUNNING.
                    
                    # If using created_at:
                    # server_uptime = datetime.datetime.utcnow() - server.created_at
                    
                    # If using last_status_update (assuming it's updated when server becomes RUNNING):
                    # This is more accurate if servers can be restarted.
                    # We need to ensure last_status_update is correctly set when a server is started.
                    # The _control_game_server method updates status to "RUNNING" after a start.
                    # So, last_status_update should be the start time.
                    
                    if server.last_status_update: # Ensure it's not None
                        time_since_last_start_or_update = datetime.datetime.utcnow() - server.last_status_update
                        shutdown_threshold = datetime.timedelta(hours=server.auto_shutdown_hours)

                        if time_since_last_start_or_update > shutdown_threshold:
                            logger.info(f"Auto-shutting down server '{server.gcp_instance_name}' as it exceeded {server.auto_shutdown_hours} hours.")
                            try:
                                # We need an interaction object for _control_game_server.
                                # For a background task, we don't have one.
                                # We should call a more direct method in GcpCog or the _control_game_server logic.
                                # Let's call GcpCog's stop method directly (needs to be adapted or use a simpler internal method).
                                
                                # Simplified: directly call GCP stop and update DB
                                op_future = self.gcp_cog.compute_client.stop(
                                    project=self.gcp_cog.project_id, 
                                    zone=server.gcp_zone, 
                                    instance=server.gcp_instance_name
                                )
                                await db_cog.update_game_server_status(server.gcp_instance_name, "STOPPING_AUTO")
                                
                                # Wait for operation (optional for background task, but good for logging)
                                completed_op = await self.gcp_cog.wait_for_operation(
                                    self.gcp_cog.project_id, server.gcp_zone, op_future.name, timeout_seconds=180
                                )
                                if completed_op:
                                    await db_cog.update_game_server_status(server.gcp_instance_name, "TERMINATED", ip_address="") # TERMINATED is GCP's stopped state
                                    logger.info(f"Server '{server.gcp_instance_name}' auto-stopped successfully.")
                                    # Optionally, notify the owner via DM
                                    owner = self.bot.get_user(int(server.discord_user_id))
                                    if owner:
                                        try:
                                            await owner.send(f"Votre serveur de jeu `{server.gcp_instance_name}` a été automatiquement arrêté car il a dépassé la durée configurée de {server.auto_shutdown_hours} heures.")
                                        except discord.Forbidden:
                                            logger.warning(f"Could not DM user {server.discord_user_id} about auto-shutdown of {server.gcp_instance_name}.")
                                else:
                                    # wait_for_operation raises on error, so this path might not be hit often
                                    # unless timeout occurs without an exception from wait_for_operation itself.
                                    await db_cog.update_game_server_status(server.gcp_instance_name, "ERROR_AUTO_STOP")
                                    logger.error(f"Auto-stop operation for '{server.gcp_instance_name}' did not complete successfully (or timed out).")

                            except Exception as e_stop:
                                logger.error(f"Error auto-stopping server '{server.gcp_instance_name}': {e_stop}", exc_info=True)
                                await db_cog.update_game_server_status(server.gcp_instance_name, "ERROR_AUTO_STOP")
                        else:
                            logger.debug(f"Server '{server.gcp_instance_name}' uptime {time_since_last_start_or_update} < {shutdown_threshold}. No auto-shutdown needed.")
                    else:
                        logger.warning(f"Server '{server.gcp_instance_name}' is RUNNING but last_status_update is None. Cannot perform auto-shutdown check.")
        except Exception as e:
            logger.error(f"Error in auto_shutdown_task: {e}", exc_info=True)

    @auto_shutdown_task.before_loop
    async def before_auto_shutdown_task(self):
        await self.bot.wait_until_ready()
        logger.info("Auto-shutdown task is waiting for bot to be ready...")

async def setup(bot: commands.Bot):
    game_server_cog = GameServerCog(bot)
    await bot.add_cog(game_server_cog)
    game_server_cog.auto_shutdown_task.start() # Start the background task
    # cog_load will be called by discord.py after adding the cog
    logger.info("GameServerCog added to bot. Linking to GcpCog will occur in cog_load. Auto-shutdown task started.")
