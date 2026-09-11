import re
import logging

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

log = logging.getLogger("red.jellyfinaccess")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-.]{3,32}$")


class JellyfinDetailsModal(discord.ui.Modal, title="Detalii cont Jellyfin"):
    """Modal afisat dupa ce userul alege un server din Select."""

    username = discord.ui.TextInput(
        label="Username dorit",
        placeholder="ex: ion_popescu",
        min_length=3,
        max_length=32,
        required=True,
    )
    password = discord.ui.TextInput(
        label="Parola",
        placeholder="minim 8 caractere",
        style=discord.TextStyle.short,
        min_length=8,
        max_length=64,
        required=True,
    )

    def __init__(self, cog: "JellyfinAccess", server_name: str):
        super().__init__()
        self.cog = cog
        self.server_name = server_name

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        username = str(self.username.value).strip()
        password = str(self.password.value)

        if not USERNAME_RE.match(username):
            await interaction.followup.send(
                "Username invalid. Foloseste doar litere, cifre, `_`, `-`, `.` "
                "(3-32 caractere).",
                ephemeral=True,
            )
            return

        success, message = await self.cog.create_jellyfin_user(
            interaction.guild, self.server_name, username, password
        )

        if success:
            await interaction.followup.send(
                f"✅ Cont creat pe serverul **{self.server_name}** cu username-ul "
                f"**{username}**.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ Cererea a esuat pe serverul **{self.server_name}**: {message}",
                ephemeral=True,
            )

        await self.cog.log_request(interaction, self.server_name, username, success, message)


class ServerSelect(discord.ui.Select):
    """Dropdown cu serverele Jellyfin configurate pentru acest server Discord."""

    def __init__(self, cog: "JellyfinAccess", server_names: list[str]):
        options = [
            discord.SelectOption(label=name, value=name) for name in server_names[:25]
        ]
        super().__init__(
            placeholder="Alege serverul Jellyfin...",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="jfaccess:server_select",
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        chosen_server = self.values[0]
        await interaction.response.send_modal(JellyfinDetailsModal(self.cog, chosen_server))


class ServerSelectView(discord.ui.View):
    def __init__(self, cog: "JellyfinAccess", server_names: list[str]):
        super().__init__(timeout=None)
        self.add_item(ServerSelect(cog, server_names))


class JellyfinAccess(commands.Cog):
    """Cog de test: cere acces Jellyfin printr-un panel Select + Modal, fara comanda text."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x4A46414343, force_registration=True)
        self.config.register_guild(servers={}, log_channel=None)
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    # ---------- Apel catre API-ul Jellyfin ----------

    async def create_jellyfin_user(self, guild: discord.Guild, server_name: str, username: str, password: str):
        servers = await self.config.guild(guild).servers()
        server = servers.get(server_name)
        if not server:
            return False, "Serverul nu mai exista in configuratie."

        url = server["url"]
        headers = {
            "X-Emby-Token": server["api_key"],
            "Content-Type": "application/json",
        }
        payload = {"Name": username, "Password": password}

        try:
            async with self.session.post(f"{url}/Users/New", json=payload, headers=headers) as resp:
                if resp.status in (200, 204):
                    return True, "Cont creat cu succes."
                text = await resp.text()
                return False, f"Eroare API ({resp.status}): {text[:200]}"
        except aiohttp.ClientError as exc:
            log.warning("Eroare conexiune Jellyfin (%s): %s", server_name, exc)
            return False, f"Eroare de conexiune catre server: {exc}"

    async def log_request(self, interaction: discord.Interaction, server_name: str, username: str, success: bool, message: str):
        channel_id = await self.config.guild(interaction.guild).log_channel()
        if not channel_id:
            return
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return

        embed = discord.Embed(
            title="Cerere acces Jellyfin" + (" — Succes" if success else " — Esuat"),
            color=discord.Color.green() if success else discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Utilizator Discord", value=f"{interaction.user} ({interaction.user.id})", inline=False)
        embed.add_field(name="Server Jellyfin", value=server_name, inline=True)
        embed.add_field(name="Username Jellyfin", value=username, inline=True)
        embed.add_field(name="Detalii", value=message, inline=False)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("Nu am putut trimite log-ul: %s", exc)

    # ---------- Comenzi admin ----------

    @commands.group(name="jfaccess")
    @commands.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def jfaccess(self, ctx: commands.Context):
        """Configurare pentru panelul de acces Jellyfin (cog de test)."""

    @jfaccess.command(name="addserver")
    async def jfaccess_addserver(self, ctx: commands.Context, name: str, url: str, api_key: str):
        """Adauga sau actualizeaza un server Jellyfin. Sterge mesajul dupa, contine cheia API."""
        async with self.config.guild(ctx.guild).servers() as servers:
            servers[name] = {"url": url.rstrip("/"), "api_key": api_key}

        await ctx.send(f"Server **{name}** salvat. Sterg mesajul tau (contine cheia API)...")
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @jfaccess.command(name="removeserver")
    async def jfaccess_removeserver(self, ctx: commands.Context, name: str):
        """Sterge un server din configuratie."""
        async with self.config.guild(ctx.guild).servers() as servers:
            if name not in servers:
                await ctx.send("Nu exista un server cu acest nume.")
                return
            del servers[name]
        await ctx.send(f"Server **{name}** sters.")

    @jfaccess.command(name="listservers")
    async def jfaccess_listservers(self, ctx: commands.Context):
        """Listeaza serverele Jellyfin configurate (fara cheile API)."""
        servers = await self.config.guild(ctx.guild).servers()
        if not servers:
            await ctx.send("Niciun server configurat inca.")
            return
        desc = "\n".join(f"**{name}** — `{data['url']}`" for name, data in servers.items())
        embed = discord.Embed(title="Servere Jellyfin configurate", description=desc)
        await ctx.send(embed=embed)

    @jfaccess.command(name="logchannel")
    async def jfaccess_logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Seteaza canalul unde se logheaza fiecare cerere de acces."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Canal de log setat la {channel.mention}.")

    @jfaccess.command(name="panel")
    async def jfaccess_panel(self, ctx: commands.Context):
        """Posteaza panelul cu Select + Modal in canalul curent (ex: canalul de tichet)."""
        servers = await self.config.guild(ctx.guild).servers()
        if not servers:
            await ctx.send("Configureaza mai intai cel putin un server cu `[p]jfaccess addserver`.")
            return

        view = ServerSelectView(self, list(servers.keys()))
        embed = discord.Embed(
            title="Cerere acces Jellyfin",
            description=(
                "Alege serverul dorit din lista de mai jos, apoi completeaza "
                "username-ul si parola in fereastra care apare."
            ),
        )
        await ctx.send(embed=embed, view=view)
