from discord.ext import commands
from discord import app_commands, Interaction
import discord
import google.auth
from google.cloud import compute_v1
from google.oauth2 import service_account
import asyncio
import os
import re # For regex validation

from src.core import settings
from src.utils.logger import get_logger
from src.utils import permissions # Import permissions module
from src.cogs.db_cog import DBCog # Import DBCog for rate limiting

logger = get_logger(__name__)

# --- Rate Limiting Check Function ---
async def gcp_rate_limit_check(interaction: discord.Interaction) -> bool:
    """Checks if the user is rate-limited for GCP commands."""
    db_cog: DBCog = interaction.client.get_cog("DBCog")
    if not db_cog:
        logger.error("DBCog not found, cannot perform rate limit check for GcpCog.")
        return True # Fail open if DBCog is missing
    return await db_cog.check_app_command_rate_limit(interaction)

# --- Confirmation View for VM Deletion ---
class ConfirmDeleteVMView(discord.ui.View):
    def __init__(self, original_interaction: Interaction, instance_name: str, zone: str, gcp_cog_instance):
        super().__init__(timeout=60.0)
        self.original_interaction = original_interaction
        self.instance_name = instance_name
        self.zone = zone
        self.gcp_cog = gcp_cog_instance
        self.confirmed = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("You cannot interact with this confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Delete VM", style=discord.ButtonStyle.danger, custom_id="confirm_delete_vm_gcp")
    async def confirm_button(self, interaction: Interaction, button: discord.ui.Button):
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Deletion of VM `{self.instance_name}` in zone `{self.zone}` confirmed. Processing...", view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_delete_vm_gcp")
    async def cancel_button(self, interaction: Interaction, button: discord.ui.Button):
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Deletion of VM `{self.instance_name}` cancelled.", view=self)
        self.stop()

    async def on_timeout(self):
        if self.confirmed is None:
            for item in self.children:
                item.disabled = True
            try:
                await self.original_interaction.edit_original_response(content=f"VM deletion confirmation for `{self.instance_name}` timed out.", view=self)
            except discord.NotFound:
                logger.warning(f"Original interaction message for VM {self.instance_name} delete confirmation not found on timeout.")
            except Exception as e:
                logger.error(f"Error editing message on timeout for VM {self.instance_name} delete confirmation: {e}")

# --- Confirmation View for Firewall Rule Deletion ---
class ConfirmDeleteFirewallRuleView(discord.ui.View):
    def __init__(self, original_interaction: Interaction, rule_name: str, gcp_cog_instance):
        super().__init__(timeout=60.0)
        self.original_interaction = original_interaction
        self.rule_name = rule_name
        self.gcp_cog = gcp_cog_instance
        self.confirmed = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("You cannot interact with this confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Delete Rule", style=discord.ButtonStyle.danger, custom_id="confirm_delete_fw_gcp")
    async def confirm_button(self, interaction: Interaction, button: discord.ui.Button):
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Deletion of firewall rule `{self.rule_name}` confirmed. Processing...", view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_delete_fw_gcp")
    async def cancel_button(self, interaction: Interaction, button: discord.ui.Button):
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Deletion of firewall rule `{self.rule_name}` cancelled.", view=self)
        self.stop()

    async def on_timeout(self):
        if self.confirmed is None:
            for item in self.children:
                item.disabled = True
            try:
                await self.original_interaction.edit_original_response(content=f"Firewall rule deletion confirmation for `{self.rule_name}` timed out.", view=self)
            except discord.NotFound:
                logger.warning(f"Original interaction message for firewall rule {self.rule_name} delete confirmation not found on timeout.")
            except Exception as e:
                logger.error(f"Error editing message on timeout for firewall rule {self.rule_name} delete confirmation: {e}")


class GcpCog(commands.Cog, name="GCP Management"):
    """Cog for managing Google Cloud Platform resources."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.project_id = settings.get_gcp_project_id()
        self.default_zone = settings.APP_CONFIG.get('gcp', 'default_zone', fallback='europe-west1-b') # Example, refine
        
        # Initialize GCP credentials
        self.credentials = self._initialize_gcp_credentials()
        if self.credentials:
            self.compute_client = compute_v1.InstancesClient(credentials=self.credentials)
            self.firewall_client = compute_v1.FirewallsClient(credentials=self.credentials)
            self.operations_client = compute_v1.ZoneOperationsClient(credentials=self.credentials) # For waiting on operations
            logger.info("GCP Compute clients initialized successfully.")
        else:
            logger.error("Failed to initialize GCP credentials. GCP Cog will be non-functional.")
            self.compute_client = None # Ensure it's None if init fails
            self.firewall_client = None
            self.operations_client = None

        if not self.project_id:
            logger.error("GCP Project ID is not configured. GCP Cog may not function correctly.")

    def _initialize_gcp_credentials(self):
        """Initializes GCP credentials from service account key."""
        try:
            # Option 1: JSON string in environment variable
            gcp_key_json_str = os.getenv('GCP_SERVICE_ACCOUNT_KEY_JSON')
            if gcp_key_json_str:
                logger.info("Loading GCP credentials from GCP_SERVICE_ACCOUNT_KEY_JSON environment variable.")
                import json # Ensure json is imported
                credentials = service_account.Credentials.from_service_account_info(json.loads(gcp_key_json_str))
                return credentials

            # Option 2: Path to service account file in environment variable or config
            key_path = os.getenv('GCP_SERVICE_ACCOUNT_FILE', settings.APP_CONFIG.get('gcp', 'service_account_file', fallback=None))
            if key_path and os.path.exists(key_path):
                logger.info(f"Loading GCP credentials from service account file: {key_path}")
                credentials = service_account.Credentials.from_service_account_file(key_path)
                return credentials
            
            # Option 3: Application Default Credentials (ADC) - useful for local dev or GCE/Cloud Run
            logger.info("Attempting to use Application Default Credentials (ADC) for GCP.")
            credentials, project = google.auth.default()
            if credentials:
                logger.info(f"Successfully loaded Application Default Credentials. Project: {project or 'Not determined by ADC'}")
                if not self.project_id and project:
                    logger.info(f"Setting GCP Project ID from ADC: {project}")
                    self.project_id = project # Use project from ADC if not set
                return credentials

            logger.warning("No GCP service account key JSON, file path, or ADC found. GCP features will be limited.")
            return None
        except Exception as e:
            logger.error(f"Error initializing GCP credentials: {e}", exc_info=True)
            return None

    async def wait_for_operation(self, project: str, zone: str, operation_id: str, timeout_seconds: int = 300):
        """Waits for a GCP operation to complete."""
        if not self.operations_client:
            logger.error("Operations client not initialized.")
            return None # Or raise an exception

        start_time = asyncio.get_event_loop().time()
        while True:
            try:
                operation = self.operations_client.get(project=project, zone=zone, operation=operation_id)
                if operation.status == compute_v1.Operation.Status.DONE:
                    if operation.error:
                        logger.error(f"GCP Operation {operation_id} failed: {operation.error.errors}")
                        # Construct a more detailed error message
                        error_messages = [f"Code: {err.code}, Message: {err.message}" for err in operation.error.errors]
                        raise Exception(f"GCP Operation failed: {'; '.join(error_messages)}")
                    logger.info(f"GCP Operation {operation_id} completed successfully.")
                    return operation
                
                if asyncio.get_event_loop().time() - start_time >= timeout_seconds:
                    logger.error(f"Timeout waiting for GCP operation {operation_id} to complete.")
                    raise TimeoutError(f"Timeout waiting for GCP operation {operation_id}")

                await asyncio.sleep(5)  # Poll every 5 seconds
            except Exception as e:
                logger.error(f"Error checking GCP operation {operation_id}: {e}", exc_info=True)
                raise # Re-raise the exception to be caught by the command handler

    async def _create_vm_logic(self, 
                               instance_name: str, 
                               machine_type: str, 
                               image_project: str, 
                               image_family: str, 
                               disk_size_gb: int, 
                               zone: str, 
                               created_by_user_id: str,
                               metadata_items: list = None, 
                               custom_tags: list = None,
                               custom_labels: dict = None
                               ):
        """Internal logic for creating a VM instance on GCP. Returns instance details on success or raises an exception."""
        if not self.compute_client or not self.project_id:
            raise Exception("GCP client is not initialized or Project ID is missing.")
        if not zone:
            raise ValueError("Zone must be specified for VM creation.")

        logger.info(f"Attempting to create VM '{instance_name}' in zone '{zone}' with machine type '{machine_type}'.")

        image_client = compute_v1.ImagesClient(credentials=self.credentials)
        latest_image = image_client.get_from_family(project=image_project, family=image_family)
        source_image = latest_image.self_link
        logger.info(f"Using source image: {source_image}")

        machine_type_uri = f"projects/{self.project_id}/zones/{zone}/machineTypes/{machine_type}"
        
        final_labels = {"discord-bot-managed": "true", "created-by": created_by_user_id}
        if custom_labels:
            final_labels.update(custom_labels)

        final_tags = ["discord-bot-vm"] # Default tag
        if custom_tags:
            final_tags.extend(custom_tags)
            final_tags = list(set(final_tags)) # Remove duplicates

        instance_config = {
            "name": instance_name,
            "machine_type": machine_type_uri,
            "disks": [
                {
                    "boot": True,
                    "auto_delete": True,
                    "initialize_params": {
                        "source_image": source_image,
                        "disk_size_gb": disk_size_gb,
                    },
                }
            ],
            "network_interfaces": [
                {
                    "network": f"projects/{self.project_id}/global/networks/default",
                    "access_configs": [{"type_": "ONE_TO_ONE_NAT", "name": "External NAT"}],
                }
            ],
            "labels": final_labels,
            "tags": {"items": final_tags},
            "metadata": {"items": metadata_items if metadata_items else []},
        }

        operation = self.compute_client.insert(project=self.project_id, zone=zone, instance_resource=instance_config)
        logger.info(f"VM creation for '{instance_name}' initiated. Operation ID: {operation.name}.")
        
        completed_operation = await self.wait_for_operation(self.project_id, zone, operation.name)

        if completed_operation:
            instance = self.compute_client.get(project=self.project_id, zone=zone, instance=instance_name)
            ip_address = "N/A"
            if instance.network_interfaces and instance.network_interfaces[0].access_configs:
                ip_address = instance.network_interfaces[0].access_configs[0].nat_ip
            logger.info(f"VM '{instance_name}' created. IP: {ip_address}. User: {created_by_user_id}")
            return instance # Return the full instance object
        else:
            # wait_for_operation should raise an exception on failure/timeout
            raise Exception(f"VM creation for '{instance_name}' failed or timed out after operation initiation.")


    @app_commands.command(name="gcp_create_vm", description="Creates a new Virtual Machine on GCP. (VM Operator+)")
    @permissions.has_vm_operator_role()
    @app_commands.check(gcp_rate_limit_check)
    @app_commands.describe(
        instance_name="Name for the new VM (e.g., minecraft-server-prod)",
        machine_type="GCP machine type (e.g., e2-medium)",
        image_project="Project ID for the OS image (e.g., debian-cloud)",
        image_family="OS image family (e.g., debian-11)",
        disk_size_gb="Size of the boot disk in GB (e.g., 20)",
        zone="GCP zone for the VM (e.g., europe-west1-b, defaults to config)",
        startup_script="Optional startup script content (bash or powershell).",
        tags="Comma-separated list of additional network tags (e.g., game-server,mc-java)."
    )
    async def create_vm(self, interaction: Interaction, 
                        instance_name: str, machine_type: str = 'e2-medium', 
                        image_project: str = 'debian-cloud', image_family: str = 'debian-11', 
                        disk_size_gb: int = 20, zone: str = None,
                        startup_script: str = None, tags: str = None):
        """Creates a new VM instance on GCP."""
        
        # Validate instance_name
        if not re.fullmatch(r"[a-z]([-a-z0-9]*[a-z0-9])?", instance_name) or not (1 <= len(instance_name) <= 63):
            await interaction.response.send_message(
                "Nom d'instance invalide. Il doit commencer par une lettre minuscule, contenir uniquement des lettres minuscules, des chiffres ou des tirets, "
                "ne pas se terminer par un tiret, et avoir une longueur de 1 à 63 caractères.",
                ephemeral=True
            )
            return

        target_zone = zone if zone else self.default_zone
        if not target_zone:
            await interaction.response.send_message("GCP zone is not configured. Please specify a zone or configure a default.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False, thinking=True) 

        metadata_items_list = []
        if startup_script:
            # Determine script type based on typical shebang or file extension if it were a file
            # For raw string, assume bash for Linux images unless specified otherwise
            # GCP uses specific metadata keys for startup scripts:
            # 'startup-script' for Linux (bash/sh)
            # 'windows-startup-script-ps1' for PowerShell
            # 'windows-startup-script-cmd' for CMD
            # 'windows-startup-script-bat' for BAT
            # Assuming Linux/debian image_family for now.
            metadata_items_list.append({"key": "startup-script", "value": startup_script})
        
        custom_tags_list = [tag.strip() for tag in tags.split(',')] if tags else []

        try:
            created_instance = await self._create_vm_logic(
                instance_name=instance_name,
                machine_type=machine_type,
                image_project=image_project,
                image_family=image_family,
                disk_size_gb=disk_size_gb,
                zone=target_zone,
                created_by_user_id=str(interaction.user.id),
                metadata_items=metadata_items_list,
                custom_tags=custom_tags_list
            )
            
            ip_address = "N/A"
            if created_instance.network_interfaces and created_instance.network_interfaces[0].access_configs:
                ip_address = created_instance.network_interfaces[0].access_configs[0].nat_ip
            
            await interaction.followup.send(f"VM '{created_instance.name}' created successfully in zone '{target_zone}'. IP: {ip_address}", ephemeral=False)
            # TODO: Log this action to the database (UserUsage or a dedicated VM table)

        except TimeoutError as e:
            logger.error(f"Timeout creating VM '{instance_name}': {e}", exc_info=True)
            await interaction.followup.send(f"Timeout during VM creation for '{instance_name}'. The operation might still be in progress or failed. Details: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating VM '{instance_name}': {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while creating VM '{instance_name}'. Details: {e}", ephemeral=True)

    @app_commands.command(name="gcp_list_vms", description="Lists all VMs in the configured project and zone(s).")
    @app_commands.describe(zone="Specific zone to list VMs from (optional, defaults to all zones in default region or default_zone).")
    async def list_vms(self, interaction: Interaction, zone: str = None):
        if not self.compute_client or not self.project_id:
            await interaction.response.send_message("GCP client is not initialized or Project ID is missing.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            instances_list = []
            
            target_zones = []
            if zone:
                target_zones.append(zone)
            elif self.default_zone: # If a specific default_zone is set
                 target_zones.append(self.default_zone)
            else: # Fallback: list from all zones in a default region (e.g., 'europe-west1') or all project zones (can be slow)
                # For simplicity, let's require default_zone to be set for now if no zone is specified by user.
                # A more advanced version could list regions then zones.
                # For now, if no specific zone and no default_zone, we might have an issue.
                # Let's assume default_zone is usually available from config.
                # If not, we should prompt or error.
                # This part can be expanded to list all zones in the project if desired.
                # For now, we'll stick to the default_zone if no specific zone is given.
                if self.default_zone:
                    target_zones.append(self.default_zone)
                else:
                    # This case should ideally be caught by an earlier check or config validation
                    logger.warning("Default zone not set and no zone provided for list_vms. Attempting to list from all zones (can be slow).")
                    # Fetch all zones (this can be an expensive call and make the command slow)
                    # For now, let's restrict to default_zone or user-specified zone.
                    # If you want to list all zones:
                    # zones_client = compute_v1.ZonesClient(credentials=self.credentials)
                    # project_zones = zones_client.list(project=self.project_id)
                    # for z in project_zones:
                    # target_zones.append(z.name)
                    await interaction.followup.send("Please specify a zone or ensure a default zone is configured in the bot settings.", ephemeral=True)
                    return


            for target_zone_item in target_zones:
                logger.info(f"Listing VMs in project '{self.project_id}', zone '{target_zone_item}'.")
                request = compute_v1.ListInstancesRequest(project=self.project_id, zone=target_zone_item)
                all_instances_in_zone = self.compute_client.list(request=request)
                
                for instance in all_instances_in_zone:
                    ip_address = "N/A"
                    if instance.network_interfaces and instance.network_interfaces[0].access_configs:
                        ip_address = instance.network_interfaces[0].access_configs[0].nat_ip
                    
                    instances_list.append({
                        "name": instance.name,
                        "zone": target_zone_item,
                        "status": instance.status,
                        "machine_type": instance.machine_type.split('/')[-1], # Get just the type name
                        "ip": ip_address,
                        "id": instance.id
                    })

            if not instances_list:
                await interaction.followup.send("No VMs found in the specified zone(s).", ephemeral=True)
                return

            embed = discord.Embed(title=f"GCP Virtual Machines", color=discord.Color.blue())
            if zone:
                embed.description = f"Listing VMs in zone: {zone}"
            elif self.default_zone :
                 embed.description = f"Listing VMs in default zone: {self.default_zone}"
            else:
                 embed.description = "Listing VMs (zone not specified, showing default behavior)"


            for inst_data in instances_list:
                field_value = (
                    f"**Status:** {inst_data['status']}\n"
                    f"**Type:** {inst_data['machine_type']}\n"
                    f"**IP:** {inst_data['ip']}\n"
                    f"**Zone:** {inst_data['zone']}\n"
                    f"**ID:** `{inst_data['id']}`"
                )
                embed.add_field(name=f"🖥️ {inst_data['name']}", value=field_value, inline=False)
            
            if len(embed.fields) == 0: # Should be caught by instances_list check, but as a safeguard
                 await interaction.followup.send("No VMs found or an issue occurred fetching them.", ephemeral=True)
                 return

            # Handle cases where the embed might be too large
            if len(embed) > 6000: # Discord embed total character limit
                logger.warning("VM list embed too large. Sending a summary.")
                await interaction.followup.send(f"Found {len(instances_list)} VMs. The list is too long to display in a single embed. Consider specifying a zone or checking the GCP console.", ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=False) # Send publicly if successful

        except Exception as e:
            logger.error(f"Error listing VMs: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while listing VMs: {e}", ephemeral=True)

    @app_commands.command(name="gcp_describe_vm", description="Describes a specific VM.")
    @app_commands.describe(
        instance_name="Name of the VM to describe.",
        zone="Zone of the VM (defaults to configured default_zone)."
    )
    async def describe_vm(self, interaction: Interaction, instance_name: str, zone: str = None):
        if not self.compute_client or not self.project_id:
            await interaction.response.send_message("GCP client is not initialized or Project ID is missing.", ephemeral=True)
            return

        target_zone = zone if zone else self.default_zone
        if not target_zone:
            await interaction.response.send_message("GCP zone is not configured. Please specify a zone or configure a default.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            logger.info(f"Describing VM '{instance_name}' in zone '{target_zone}'.")
            instance = self.compute_client.get(project=self.project_id, zone=target_zone, instance=instance_name)

            ip_address = "N/A"
            internal_ip = "N/A"
            if instance.network_interfaces:
                if instance.network_interfaces[0].access_configs:
                    ip_address = instance.network_interfaces[0].access_configs[0].nat_ip
                internal_ip = instance.network_interfaces[0].network_ip


            embed = discord.Embed(title=f"VM Details: {instance.name}", color=discord.Color.green())
            embed.add_field(name="ID", value=f"`{instance.id}`", inline=False)
            embed.add_field(name="Status", value=instance.status, inline=True)
            embed.add_field(name="Zone", value=target_zone, inline=True)
            embed.add_field(name="Machine Type", value=instance.machine_type.split('/')[-1], inline=True)
            embed.add_field(name="External IP", value=ip_address, inline=True)
            embed.add_field(name="Internal IP", value=internal_ip, inline=True)
            
            if instance.disks:
                disk_info = []
                for disk in instance.disks:
                    disk_name = disk.device_name
                    disk_type = "Boot" if disk.boot else "Data"
                    disk_size_gb = "N/A" # This info is not directly on disk message, would need separate disk get
                    # To get disk size, you'd typically look at initialize_params during creation or get the disk resource
                    # For simplicity, we'll omit size here or mark as N/A
                    disk_info.append(f"{disk_name} ({disk_type})")
                embed.add_field(name="Disks", value=", ".join(disk_info) if disk_info else "N/A", inline=False)

            if instance.labels:
                labels_str = "\n".join([f"- `{key}`: `{value}`" for key, value in instance.labels.items()])
                embed.add_field(name="Labels", value=labels_str if labels_str else "None", inline=False)
            
            if instance.tags and instance.tags.items:
                tags_str = ", ".join([f"`{tag}`" for tag in instance.tags.items])
                embed.add_field(name="Network Tags", value=tags_str if tags_str else "None", inline=False)

            embed.set_footer(text=f"Creation Timestamp: {instance.creation_timestamp}")

            await interaction.followup.send(embed=embed, ephemeral=False)

        except google.api_core.exceptions.NotFound:
            logger.warning(f"VM '{instance_name}' not found in zone '{target_zone}'.")
            await interaction.followup.send(f"VM '{instance_name}' not found in zone '{target_zone}'.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error describing VM '{instance_name}': {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while describing VM '{instance_name}': {e}", ephemeral=True)

    async def _control_vm(self, interaction: Interaction, instance_name: str, zone: str, action: str):
        """Helper function to start, stop, or delete a VM."""
        if not self.compute_client or not self.project_id:
            await interaction.response.send_message("GCP client is not initialized or Project ID is missing.", ephemeral=True)
            return

        target_zone = zone if zone else self.default_zone
        if not target_zone:
            await interaction.response.send_message("GCP zone is not configured. Please specify a zone or configure a default.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False, thinking=True) # Public thinking for control actions

        action_gerund = ""
        operation_future = None

        try:
            if action == "start":
                action_gerund = "Starting"
                logger.info(f"Attempting to start VM '{instance_name}' in zone '{target_zone}'.")
                operation_future = self.compute_client.start(project=self.project_id, zone=target_zone, instance=instance_name)
            elif action == "stop":
                action_gerund = "Stopping"
                logger.info(f"Attempting to stop VM '{instance_name}' in zone '{target_zone}'.")
                operation_future = self.compute_client.stop(project=self.project_id, zone=target_zone, instance=instance_name)
            elif action == "delete":
                action_gerund = "Deleting"
                logger.info(f"Attempting to delete VM '{instance_name}' in zone '{target_zone}'.")
                operation_future = self.compute_client.delete(project=self.project_id, zone=target_zone, instance=instance_name)
            else:
                await interaction.followup.send(f"Invalid action: {action}", ephemeral=True)
                return

            await interaction.followup.send(f"{action_gerund} VM '{instance_name}' in zone '{target_zone}'. Operation ID: {operation_future.name}. Waiting for completion...", ephemeral=False)
            
            completed_operation = await self.wait_for_operation(self.project_id, target_zone, operation_future.name)

            if completed_operation:
                success_message = f"VM '{instance_name}' in zone '{target_zone}' has been successfully {action}ed."
                await interaction.followup.send(success_message, ephemeral=False)
                logger.info(success_message)
                # TODO: Update VM status in local DB if applicable
            # No explicit else here, as wait_for_operation raises on failure/timeout

        except google.api_core.exceptions.NotFound:
            logger.warning(f"VM '{instance_name}' not found in zone '{target_zone}' for action '{action}'.")
            await interaction.followup.send(f"VM '{instance_name}' not found in zone '{target_zone}'.", ephemeral=True)
        except TimeoutError as e:
            logger.error(f"Timeout {action_gerund.lower()} VM '{instance_name}': {e}", exc_info=True)
            await interaction.followup.send(f"Timeout during VM {action}: '{instance_name}'. The operation might still be in progress or failed. Details: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error {action_gerund.lower()} VM '{instance_name}': {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while {action_gerund.lower()} VM '{instance_name}'. Details: {e}", ephemeral=True)

    @app_commands.command(name="gcp_start_vm", description="Starts a GCP VM. (VM Operator+)")
    @permissions.has_vm_operator_role()
    @app_commands.check(gcp_rate_limit_check)
    @app_commands.describe(instance_name="Name of the VM to start.", zone="Zone of the VM (defaults to configured default_zone).")
    async def start_vm(self, interaction: Interaction, instance_name: str, zone: str = None):
        await self._control_vm(interaction, instance_name, zone, "start")

    @app_commands.command(name="gcp_stop_vm", description="Stops a GCP VM. (VM Operator+)")
    @permissions.has_vm_operator_role()
    @app_commands.check(gcp_rate_limit_check)
    @app_commands.describe(instance_name="Name of the VM to stop.", zone="Zone of the VM (defaults to configured default_zone).")
    async def stop_vm(self, interaction: Interaction, instance_name: str, zone: str = None):
        await self._control_vm(interaction, instance_name, zone, "stop")

    @app_commands.command(name="gcp_delete_vm", description="Deletes a GCP VM. This action is irreversible! (VM Operator+)")
    @permissions.has_vm_operator_role()
    @app_commands.check(gcp_rate_limit_check)
    @app_commands.describe(instance_name="Name of the VM to delete.", zone="Zone of the VM (defaults to configured default_zone).")
    async def delete_vm(self, interaction: Interaction, instance_name: str, zone: str = None):
        target_zone = zone if zone else self.default_zone
        if not target_zone:
            # Send message directly if zone is missing before deferring or sending view
            await interaction.response.send_message("GCP zone is not configured. Please specify a zone or configure a default.", ephemeral=True)
            return

        view = ConfirmDeleteVMView(original_interaction=interaction, instance_name=instance_name, zone=target_zone, gcp_cog_instance=self)
        await interaction.response.send_message(
            f"Are you sure you want to delete the VM `{instance_name}` in zone `{target_zone}`? This action is irreversible.",
            view=view,
            ephemeral=False
        )
        await view.wait()

        if view.confirmed is True:
            logger.info(f"User {interaction.user.name} confirmed deletion for VM {instance_name} in zone {target_zone}.")
            # _control_vm handles its own deferral and followups.
            # The button callback has already edited the original message.
            await self._control_vm(interaction, instance_name, target_zone, "delete")
        elif view.confirmed is False:
            logger.info(f"User {interaction.user.name} cancelled deletion for VM {instance_name} in zone {target_zone}.")
        else: # Timeout
            logger.info(f"VM deletion confirmation for {instance_name} timed out for user {interaction.user.name}.")

    async def _open_port_logic(self, firewall_rule_name: str, target_tag: str, port: int, protocol: str, description: str = None):
        """Internal logic to open a port in GCP firewall."""
        if not self.firewall_client or not self.project_id:
            raise Exception("GCP Firewall client is not initialized or Project ID is missing.")

        protocol_upper = protocol.upper()
        if protocol_upper not in ["TCP", "UDP"]:
            raise ValueError("Invalid protocol. Must be TCP or UDP.")

        logger.info(f"Attempting to create firewall rule '{firewall_rule_name}' for tag '{target_tag}', port {port}/{protocol_upper}.")

        firewall_config = compute_v1.Firewall(
            name=firewall_rule_name,
            description=description or f"Allow {protocol_upper} traffic on port {port} for tag {target_tag}",
            network=f"projects/{self.project_id}/global/networks/default",
            priority=1000,
            direction=compute_v1.Firewall.Direction.INGRESS.name,
            allowed=[compute_v1.Allowed(ip_protocol=protocol_upper, ports=[str(port)])],
            target_tags=[target_tag],
            source_ranges=["0.0.0.0/0"]
        )
        
        operation = self.firewall_client.insert(project=self.project_id, firewall_resource=firewall_config)
        
        global_operations_client = compute_v1.GlobalOperationsClient(credentials=self.credentials)
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = 180
        while True:
            global_op = global_operations_client.get(project=self.project_id, operation=operation.name)
            if global_op.status == compute_v1.Operation.Status.DONE:
                if global_op.error:
                    error_messages = [f"Code: {err.code}, Message: {err.message}" for err in global_op.error.errors]
                    raise Exception(f"GCP Global Operation for firewall rule '{firewall_rule_name}' failed: {'; '.join(error_messages)}")
                logger.info(f"GCP Global Operation {operation.name} for firewall rule '{firewall_rule_name}' completed successfully.")
                return True # Indicate success
            if asyncio.get_event_loop().time() - start_time >= timeout_seconds:
                raise TimeoutError(f"Timeout waiting for GCP global operation {operation.name} for firewall rule '{firewall_rule_name}'")
            await asyncio.sleep(3)

    @app_commands.command(name="gcp_open_port", description="Opens a port in GCP firewall. (VM Operator+)")
    @permissions.has_vm_operator_role()
    @app_commands.check(gcp_rate_limit_check)
    @app_commands.describe(
        firewall_rule_name="Name for the new firewall rule (e.g., allow-minecraft-tcp-25565).",
        target_tag="The network tag on VMs to apply this rule to (e.g., discord-bot-vm).",
        port="Port number to open (e.g., 25565).",
        protocol="Protocol (TCP or UDP, defaults to TCP).",
        description="Description for the firewall rule."
    )
    async def open_port(self, interaction: Interaction, firewall_rule_name: str, target_tag: str, port: app_commands.Range[int, 1, 65535], protocol: str = "tcp", description: str = None):
        await interaction.response.defer(ephemeral=False, thinking=True)
        try:
            await self._open_port_logic(firewall_rule_name, target_tag, port, protocol, description)
            success_message = f"Firewall rule '{firewall_rule_name}' created successfully, opening port {port}/{protocol.upper()} for VMs with tag '{target_tag}'."
            await interaction.followup.send(success_message, ephemeral=False)
        except google.api_core.exceptions.Conflict:
            logger.warning(f"Firewall rule '{firewall_rule_name}' already exists.")
            await interaction.followup.send(f"Firewall rule '{firewall_rule_name}' already exists.", ephemeral=True)
        except TimeoutError as e:
            logger.error(f"Timeout creating firewall rule '{firewall_rule_name}': {e}", exc_info=True)
            await interaction.followup.send(f"Timeout creating firewall rule '{firewall_rule_name}'. The operation might still be in progress or failed. Details: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating firewall rule '{firewall_rule_name}': {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while creating firewall rule '{firewall_rule_name}'. Details: {e}", ephemeral=True)

    @app_commands.command(name="gcp_list_firewall_rules", description="Lists all firewall rules in the project.")
    async def list_firewall_rules(self, interaction: Interaction):
        if not self.firewall_client or not self.project_id:
            await interaction.response.send_message("GCP Firewall client is not initialized or Project ID is missing.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            logger.info(f"Listing firewall rules for project '{self.project_id}'.")
            rules = self.firewall_client.list(project=self.project_id)
            
            if not rules:
                await interaction.followup.send("No firewall rules found in the project.", ephemeral=True)
                return

            embed = discord.Embed(title="GCP Firewall Rules", color=discord.Color.orange())
            
            count = 0
            for rule in rules:
                if count >= 20: # Limit to 20 rules to avoid overly large embeds
                    embed.set_footer(text=f"Showing first 20 rules. {len(list(rules)) - 20} more exist.")
                    break
                
                allowed_ports = []
                if rule.allowed:
                    for allow in rule.allowed:
                        ports_str = ", ".join(allow.ports) if allow.ports else "all"
                        allowed_ports.append(f"{allow.ip_protocol.upper()}: {ports_str}")
                
                target_tags_str = ", ".join(rule.target_tags) if rule.target_tags else "N/A (Applies to all instances)"
                source_ranges_str = ", ".join(rule.source_ranges) if rule.source_ranges else "N/A"

                field_value = (
                    f"**Direction:** {rule.direction.name}\n"
                    f"**Priority:** {rule.priority}\n"
                    f"**Allowed:** {', '.join(allowed_ports) if allowed_ports else 'None'}\n"
                    f"**Target Tags:** {target_tags_str}\n"
                    f"**Source Ranges:** {source_ranges_str}\n"
                    f"**Description:** {rule.description or 'N/A'}"
                )
                embed.add_field(name=f"🛡️ {rule.name}", value=field_value, inline=False)
                count += 1
            
            if len(embed.fields) == 0:
                 await interaction.followup.send("No firewall rules found or an issue occurred fetching them.", ephemeral=True)
                 return

            await interaction.followup.send(embed=embed, ephemeral=False)

        except Exception as e:
            logger.error(f"Error listing firewall rules: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while listing firewall rules: {e}", ephemeral=True)

    async def _list_firewall_rules_by_target_tag(self, target_tag: str) -> list[compute_v1.Firewall]:
        """Lists all firewall rules that include the specified target_tag."""
        if not self.firewall_client or not self.project_id:
            logger.error("GCP Firewall client is not initialized or Project ID is missing for _list_firewall_rules_by_target_tag.")
            return [] # Return empty list or raise an exception

        logger.info(f"Listing firewall rules for project '{self.project_id}' with target tag '{target_tag}'.")
        try:
            all_rules = self.firewall_client.list(project=self.project_id)
            tagged_rules = []
            for rule in all_rules:
                if rule.target_tags and target_tag in rule.target_tags:
                    tagged_rules.append(rule)
            logger.info(f"Found {len(tagged_rules)} firewall rules with target tag '{target_tag}'.")
            return tagged_rules
        except Exception as e:
            logger.error(f"Error listing firewall rules by target tag '{target_tag}': {e}", exc_info=True)
            return [] # Return empty list on error

    async def _delete_firewall_rule_logic(self, firewall_rule_name: str):
        """Internal logic to delete a firewall rule."""
        if not self.firewall_client or not self.project_id:
            raise Exception("GCP Firewall client is not initialized or Project ID is missing.")

        logger.info(f"Attempting to delete firewall rule '{firewall_rule_name}'.")
        operation = self.firewall_client.delete(project=self.project_id, firewall=firewall_rule_name)

        global_operations_client = compute_v1.GlobalOperationsClient(credentials=self.credentials)
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = 180
        while True:
            global_op = global_operations_client.get(project=self.project_id, operation=operation.name)
            if global_op.status == compute_v1.Operation.Status.DONE:
                if global_op.error:
                    error_messages = [f"Code: {err.code}, Message: {err.message}" for err in global_op.error.errors]
                    raise Exception(f"GCP Global Operation for deleting firewall rule '{firewall_rule_name}' failed: {'; '.join(error_messages)}")
                logger.info(f"GCP Global Operation {operation.name} for deleting firewall rule '{firewall_rule_name}' completed successfully.")
                return True # Indicate success
            if asyncio.get_event_loop().time() - start_time >= timeout_seconds:
                raise TimeoutError(f"Timeout waiting for GCP global operation {operation.name} for deleting firewall rule '{firewall_rule_name}'")
            await asyncio.sleep(3)

    @app_commands.command(name="gcp_delete_firewall_rule", description="Deletes a firewall rule. Irreversible! (VM Operator+)")
    @permissions.has_vm_operator_role()
    @app_commands.check(gcp_rate_limit_check)
    @app_commands.describe(firewall_rule_name="Name of the firewall rule to delete.")
    async def delete_firewall_rule(self, interaction: Interaction, firewall_rule_name: str):
        view = ConfirmDeleteFirewallRuleView(original_interaction=interaction, rule_name=firewall_rule_name, gcp_cog_instance=self)
        await interaction.response.send_message(
            f"Are you sure you want to delete the firewall rule `{firewall_rule_name}`? This action is irreversible.",
            view=view,
            ephemeral=False
        )
        await view.wait()

        if view.confirmed is True:
            logger.info(f"User {interaction.user.name} confirmed deletion for firewall rule {firewall_rule_name}.")
            # Original interaction's response was edited by button. Now defer for the actual logic.
            # We need a new "interaction" like object or to handle the response carefully.
            # For simplicity, we'll use a followup from the original interaction for the result of the delete logic.
            # The button callback already edited the message to "Processing..."
            # We need to ensure that the _delete_firewall_rule_logic doesn't try to defer/respond itself.
            # Let's make _delete_firewall_rule_logic purely logic and handle response here.
            
            # The button's interaction.response.edit_message already handled the "Processing..." part.
            # Now we call the logic and then followup on the original interaction.
            try:
                await self._delete_firewall_rule_logic(firewall_rule_name)
                success_message = f"Firewall rule '{firewall_rule_name}' deleted successfully."
                # Use followup on the original interaction that initiated the command
                await interaction.followup.send(success_message, ephemeral=False) 
            except google.api_core.exceptions.NotFound:
                logger.warning(f"Firewall rule '{firewall_rule_name}' not found during confirmed delete.")
                await interaction.followup.send(f"Firewall rule '{firewall_rule_name}' not found.", ephemeral=True)
            except TimeoutError as e_timeout:
                logger.error(f"Timeout deleting firewall rule '{firewall_rule_name}' after confirmation: {e_timeout}", exc_info=True)
                await interaction.followup.send(f"Timeout deleting firewall rule '{firewall_rule_name}'. The operation might still be in progress or failed. Details: {e_timeout}", ephemeral=True)
            except Exception as e_general:
                logger.error(f"Error deleting firewall rule '{firewall_rule_name}' after confirmation: {e_general}", exc_info=True)
                await interaction.followup.send(f"An error occurred while deleting firewall rule '{firewall_rule_name}'. Details: {e_general}", ephemeral=True)

        elif view.confirmed is False:
            logger.info(f"User {interaction.user.name} cancelled deletion for firewall rule {firewall_rule_name}.")
            # Message already updated by button callback
        else: # Timeout
            logger.info(f"Firewall rule deletion for {firewall_rule_name} timed out for user {interaction.user.name}.")
            # Message already updated by on_timeout

    @app_commands.command(name="gcp_get_vm_serial_log", description="Retrieves the serial port output (log) for a VM. (VM Operator+)")
    @permissions.has_vm_operator_role()
    @app_commands.check(gcp_rate_limit_check)
    @app_commands.describe(
        instance_name="Name of the VM.",
        zone="Zone of the VM (defaults to configured default_zone).",
        port_number="Serial port number to retrieve (1-4, default is 1)."
    )
    async def get_vm_serial_log(self, interaction: Interaction, instance_name: str, zone: str = None, port_number: app_commands.Range[int, 1, 4] = 1):
        if not self.compute_client or not self.project_id:
            await interaction.response.send_message("GCP client is not initialized or Project ID is missing.", ephemeral=True)
            return

        target_zone = zone if zone else self.default_zone
        if not target_zone:
            await interaction.response.send_message("GCP zone is not configured. Please specify a zone or configure a default.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            logger.info(f"Retrieving serial port {port_number} output for VM '{instance_name}' in zone '{target_zone}'.")
            
            serial_output_response = self.compute_client.get_serial_port_output(
                project=self.project_id,
                zone=target_zone,
                instance=instance_name,
                port=port_number
            )
            
            log_content = serial_output_response.contents or "No content found in serial port output."

            # Send as a file
            log_file_name = f"{instance_name}_serial_port_{port_number}.log"
            with open(log_file_name, "w", encoding="utf-8") as f:
                f.write(log_content)
            
            discord_file = discord.File(log_file_name)
            await interaction.followup.send(f"Serial port {port_number} output for VM `{instance_name}`:", file=discord_file, ephemeral=True)
            
            os.remove(log_file_name) # Clean up the temporary file

        except google.api_core.exceptions.NotFound:
            logger.warning(f"VM '{instance_name}' not found in zone '{target_zone}' for serial log retrieval.")
            await interaction.followup.send(f"VM '{instance_name}' not found in zone '{target_zone}'.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error retrieving serial log for VM '{instance_name}': {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while retrieving serial log for VM '{instance_name}': {e}", ephemeral=True)


    # Error handler for permission checks in this cog
    @create_vm.error
    @start_vm.error
    @stop_vm.error
    @delete_vm.error
    @open_port.error
    @delete_firewall_rule.error
    @get_vm_serial_log.error # Add error handler for the new command
    async def on_gcp_command_permission_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        await permissions.handle_permission_check_failure(interaction, error)
        # If the error is not a CheckFailure, it might be good to log it or re-raise if not handled by a global handler
        if not isinstance(error, app_commands.CheckFailure):
            logger.error(f"Unhandled error in GcpCog command {interaction.command.name if interaction.command else 'unknown'}: {error}", exc_info=True)
            # Send a generic error if not already responded
            if not interaction.response.is_done():
                await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)
            else:
                try:
                    await interaction.followup.send("An unexpected error occurred.", ephemeral=True)
                except discord.errors.HTTPException:
                    pass # Already responded or cannot respond

async def setup(bot: commands.Bot):
    if not settings.get_gcp_project_id():
        logger.warning("GCP Project ID not found in settings. GCP Cog might not work as expected.")
    
    gcp_cog = GcpCog(bot)
    if gcp_cog.credentials and gcp_cog.project_id: # Only add cog if basic GCP setup is okay
        await bot.add_cog(gcp_cog)
        logger.info("GcpCog loaded and added to bot.")
    else:
        logger.error("GcpCog NOT loaded due to missing credentials or project ID. GCP functionality will be unavailable.")
