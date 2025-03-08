import discord
from discord.ext import commands
import os
import logging
import json
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PRINCIPAL_SERVER_ID = 607066249381543946  # ID del servidor principal
SECUNDARIO_SERVER_ID = 1346226782306832465  # ID del servidor secundario para roles
COMANDOS_SERVER_ID = 1298147393191284736  # ID del servidor donde estarán los comandos
ROLES_FILE = "roles_sincronizados.json"  # Archivo de roles sincronizados

# Funciones para cargar/guardar roles sincronizados
def load_sync_roles():
    try:
        with open(ROLES_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_sync_roles():
    with open(ROLES_FILE, "w") as f:
        json.dump(list(ROLES_SINCRONIZADOS), f)

ROLES_SINCRONIZADOS = load_sync_roles()  # Cargar roles al inicio

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', 
                    filename='sentinelsync.log', filemode='a')
logger = logging.getLogger()

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!!!!sentinelsync!!!!', intents=intents)

@bot.event
async def on_ready():
    """Registra los comandos de barra en el servidor exclusivo de comandos al iniciar el bot."""
    bot.sync_enabled = True  # Inicializar variable de sincronización
    guild = bot.get_guild(COMANDOS_SERVER_ID)
    if guild:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    logger.info("Bot listo y comandos sincronizados en el servidor de comandos.")
    
    # NUEVO: Sincronización automática al iniciar
    logger.info("Iniciando sincronización global tras reinicio...")
    await sync_roles()  # Ejecutar sincronización completa
    logger.info("Sincronización inicial completada.")

def get_role_by_name_fuzzy(guild, role_name):
    for role in guild.roles:
        if role_name.lower().strip() in role.name.lower().strip():
            return role
    return None

@bot.event
async def on_member_update(before, after):
    if before.guild.id != PRINCIPAL_SERVER_ID:
        return

    secundario_guild = bot.get_guild(SECUNDARIO_SERVER_ID)
    if not secundario_guild:
        return

    secundario_member = secundario_guild.get_member(after.id)
    if not secundario_member:
        return

    added_roles = [r for r in after.roles if r not in before.roles and r.id in ROLES_SINCRONIZADOS]
    removed_roles = [r for r in before.roles if r not in after.roles and r.id in ROLES_SINCRONIZADOS]

    for role in added_roles:
        sec_role = get_role_by_name_fuzzy(secundario_guild, role.name)
        if sec_role and sec_role not in secundario_member.roles:
            await secundario_member.add_roles(sec_role)
            logger.info(f"Rol `{role.name}` sincronizado en {secundario_guild.name} para {after.name}.")

    for role in removed_roles:
        sec_role = get_role_by_name_fuzzy(secundario_guild, role.name)
        if sec_role and sec_role in secundario_member.roles:
            await secundario_member.remove_roles(sec_role)
            logger.info(f"Rol `{role.name}` removido en {secundario_guild.name} para {after.name}.")

async def sync_roles():
    logger.info("Sincronización manual global iniciada")
    principal_guild = bot.get_guild(PRINCIPAL_SERVER_ID)
    secundario_guild = bot.get_guild(SECUNDARIO_SERVER_ID)
    
    if not (principal_guild and secundario_guild):
        logger.warning("No se encontraron ambos servidores")
        return

    for member in principal_guild.members:
        sec_member = secundario_guild.get_member(member.id)
        if not sec_member:
            continue

        # Verificar todos los roles sincronizados
        for role_id in ROLES_SINCRONIZADOS:
            primary_role = principal_guild.get_role(role_id)
            if not primary_role:
                continue

            # Buscar rol equivalente en servidor secundario
            sec_role = get_role_by_name_fuzzy(secundario_guild, primary_role.name)
            if not sec_role:
                continue

            # Verificar estado en ambos servidores
            has_primary = primary_role in member.roles
            has_secondary = sec_role in sec_member.roles

            # Sincronizar en ambas direcciones
            if has_primary and not has_secondary:
                await sec_member.add_roles(sec_role)
                logger.info(f"ROL AÑADIDO: {primary_role.name} a {member.name} en {secundario_guild.name}")
            elif not has_primary and has_secondary:
                await sec_member.remove_roles(sec_role)
                logger.info(f"ROL REMOVIDO: {sec_role.name} de {member.name} en {secundario_guild.name}")



@bot.tree.command(name="sync", description="Controla la sincronización de roles")
@discord.app_commands.choices(option=[
    discord.app_commands.Choice(name="now", value="now"),
    discord.app_commands.Choice(name="on", value="on"),
    discord.app_commands.Choice(name="off", value="off")
])

async def sync(interaction: discord.Interaction, option: discord.app_commands.Choice[str]):
    if option.value != 'now':
        await interaction.response.send_message("❌ Este comando no está disponible", ephemeral=True)
        return
    
    if option.value == 'now':
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Necesitas permisos de administrador para usar este comando.",
                ephemeral=True
            )

    if option.value == 'now':
        # Diferir la respuesta inmediatamente
        await interaction.response.defer(ephemeral=True)
        try:
            await sync_roles()  # Ejecutar sincronización
            # Enviar mensaje de confirmación
            await interaction.followup.send("✅ Sincronización de roles completada.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error en sincronización manual: {e}")
            await interaction.followup.send("❌ Ocurrió un error durante la sincronización.", ephemeral=True)
    
    elif option.value == 'on':
        bot.sync_enabled = True
        await interaction.response.send_message("✅ Sincronización automática activada.", ephemeral=True)
    
    elif option.value == 'off':
        bot.sync_enabled = False
        await interaction.response.send_message("✅ Sincronización automática desactivada.", ephemeral=True)

# Autocompletado para miembros del servidor principal
async def member_autocomplete(interaction: discord.Interaction, current: str):
    principal_guild = bot.get_guild(PRINCIPAL_SERVER_ID)
    if not principal_guild:
        return []
    return [
        discord.app_commands.Choice(name=member.name, value=str(member.id))
        for member in principal_guild.members if current.lower() in member.name.lower()
    ][:25]

# Autocompletado para roles del servidor principal
async def role_autocomplete(interaction: discord.Interaction, current: str):
    principal_guild = bot.get_guild(PRINCIPAL_SERVER_ID)
    if not principal_guild:
        return []
    return [
        discord.app_commands.Choice(name=role.name, value=str(role.id))
        for role in principal_guild.roles if current.lower() in role.name.lower()
    ][:25]

@bot.tree.command(name="give", description="Asigna un rol a un usuario manualmente")
@discord.app_commands.autocomplete(member=member_autocomplete, role=role_autocomplete)
async def give(interaction: discord.Interaction, member: str, role: str):
    principal_guild = bot.get_guild(PRINCIPAL_SERVER_ID)
    if not principal_guild:
        return
    member = principal_guild.get_member(int(member))
    role = principal_guild.get_role(int(role))
    
    if not member or not role:
        await interaction.response.send_message("❌ Usuario o rol no válido.", ephemeral=True)
        return
    
    await member.add_roles(role)
    await interaction.response.send_message(f"✅ Se ha asignado el rol `{role.name}` a {member.mention}.", ephemeral=True)
    logger.info(f"Rol `{role.name}` asignado a {member.name}.")

@bot.tree.command(name="remove", description="Remueve un rol de un usuario manualmente")
@discord.app_commands.autocomplete(member=member_autocomplete, role=role_autocomplete)
async def remove(interaction: discord.Interaction, member: str, role: str):
    principal_guild = bot.get_guild(PRINCIPAL_SERVER_ID)
    if not principal_guild:
        return
    member = principal_guild.get_member(int(member))
    role = principal_guild.get_role(int(role))
    
    if not member or not role:
        await interaction.response.send_message("❌ Usuario o rol no válido.", ephemeral=True)
        return
    
    await member.remove_roles(role)
    await interaction.response.send_message(f"✅ Se ha removido el rol `{role.name}` de {member.mention}.", ephemeral=True)
    logger.info(f"Rol `{role.name}` removido de {member.name}.")

@bot.tree.command(name="addsyncrole", description="Añade un rol a la lista de roles sincronizados")
async def addsyncrole(interaction: discord.Interaction, role_id: str):
    global ROLES_SINCRONIZADOS
    try:
        role_id = int(role_id)
        if role_id in ROLES_SINCRONIZADOS:
            await interaction.response.send_message("❌ El rol ya está en la lista de sincronización.", ephemeral=True)
            return
        ROLES_SINCRONIZADOS.add(role_id)
        save_sync_roles()
        await interaction.response.send_message(f"✅ Rol `{role_id}` añadido a la lista de sincronización.", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ ID de rol inválido.", ephemeral=True)

@bot.tree.command(name="removesyncrole", description="Elimina un rol de la lista de roles sincronizados")
async def removesyncrole(interaction: discord.Interaction, role_id: str):
    global ROLES_SINCRONIZADOS
    try:
        role_id = int(role_id)
        if role_id not in ROLES_SINCRONIZADOS:
            await interaction.response.send_message("❌ El rol no está en la lista de sincronización.", ephemeral=True)
            return
        ROLES_SINCRONIZADOS.remove(role_id)
        save_sync_roles()
        await interaction.response.send_message(f"✅ Rol `{role_id}` eliminado de la lista de sincronización.", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ ID de rol inválido.", ephemeral=True)

bot.run(TOKEN)
