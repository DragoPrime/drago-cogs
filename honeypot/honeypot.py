import random
import string
import contextlib
from datetime import datetime, timezone

import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list

CUVINTE_NUME_ALEATORIU = [
    "chat", "discutii", "general", "hangout", "colt", "loc", "zona",
    "spatiu", "camera", "hub", "fara-spam", "vorba", "vibe",
]

MESAJE_WARMER = [
    "Nimic de văzut aici 👀",
    "Doar bifez că sunt activ.",
    "Ssst, e liniște azi.",
    "...",
    "Bună ziua tuturor (nimănui).",
    "Verificare de rutină.",
]


class Honeypot(commands.Cog):
    """
    Prinde și elimină automat boți de spam / conturi compromise prin
    monitorizarea unui canal dedicat "honeypot" (capcană).

    Orice utilizator care postează în canalul honeypot configurat este
    eliminat imediat (kick/softban sau ban), deoarece membrii legitimi
    nu au niciun motiv să scrie vreodată acolo.

    Rescris pentru Red Discord Bot 3.5, pe baza conceptului de la
    https://github.com/RiskyMH/honeypot
    """

    __version__ = "1.1.0"
    __author__ = "Claude (rescriere bazată pe RiskyMH/honeypot)"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=0x0110E7404A5B, force_registration=True
        )

        default_guild = {
            "canal_honeypot": None,
            "canal_log": None,
            "actiune": "kick",  # "kick" (softban) sau "ban"
            "activat": True,
            "sterge_canal_la_declansare": False,
            "numar_eliminati": 0,
            "id_mesaj_avertisment": None,
            "warmer_ultima_trimitere": 0,
            "nume_ultima_rotatie": 0,
            # experimente
            "warmer_activ": False,
            "nume_aleatoriu_activ": False,
            "nume_aleatoriu_haos": False,
            "fara_mesaj_avertisment": False,
            "fara_dm": False,
        }
        self.config.register_guild(**default_guild)

        self.task_warmer.start()
        self.task_nume_aleatoriu.start()

    def cog_unload(self):
        self.task_warmer.cancel()
        self.task_nume_aleatoriu.cancel()

    # ---------------------------------------------------------------
    # Listeners
    # ---------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Creează automat un canal #honeypot la intrarea botului pe un server nou."""
        conf = self.config.guild(guild)
        if await conf.canal_honeypot():
            return
        await self._creeaza_canal_honeypot(guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild = message.guild
        conf = self.config.guild(guild)

        if not await conf.activat():
            return

        id_canal_honeypot = await conf.canal_honeypot()
        if id_canal_honeypot is None or message.channel.id != id_canal_honeypot:
            return

        membru = message.author
        if isinstance(membru, discord.Member):
            # Nu acționăm asupra celor pe care botul nu ar trebui să-i sancționeze
            # (ex. proprietarul botului sau administratori).
            if await self.bot.is_owner(membru) or membru.guild_permissions.administrator:
                return

        await self._gestioneaza_declansare(message)

    # ---------------------------------------------------------------
    # Embed de avertisment (cu contor) din canalul honeypot
    # ---------------------------------------------------------------

    def _construieste_embed_avertisment(self, numar_eliminati: int) -> discord.Embed:
        embed = discord.Embed(
            title="⚠️ Canal Honeypot — Nu posta aici!",
            description=(
                "Acesta este un canal-capcană (honeypot) folosit pentru a detecta "
                "conturi de spam sau compromise.\n\n"
                "**Dacă trimiți un mesaj aici, veți fi eliminat imediat de pe server.**"
            ),
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="🍯 Utilizatori eliminați până acum",
            value=f"**{numar_eliminati}**",
            inline=False,
        )
        embed.set_footer(text="Sistem anti-spam Honeypot")
        return embed

    async def _actualizeaza_mesaj_avertisment(self, guild: discord.Guild, canal: discord.TextChannel = None):
        """Actualizează (sau creează) mesajul embed cu contorul din canalul honeypot."""
        conf = self.config.guild(guild)
        data = await conf.all()

        if canal is None:
            id_canal = data.get("canal_honeypot")
            if id_canal is None:
                return
            canal = guild.get_channel(id_canal)
            if canal is None:
                return

        embed = self._construieste_embed_avertisment(data.get("numar_eliminati", 0))
        id_mesaj = data.get("id_mesaj_avertisment")

        if id_mesaj:
            try:
                mesaj = await canal.fetch_message(id_mesaj)
                await mesaj.edit(embed=embed)
                return
            except (discord.NotFound, discord.HTTPException):
                pass  # mesajul nu mai există, trimitem unul nou mai jos

        with contextlib.suppress(discord.HTTPException):
            mesaj_nou = await canal.send(embed=embed)
            await conf.id_mesaj_avertisment.set(mesaj_nou.id)

    # ---------------------------------------------------------------
    # Gestionarea declanșării capcanei
    # ---------------------------------------------------------------

    async def _gestioneaza_declansare(self, message: discord.Message):
        guild = message.guild
        membru = message.author
        conf = self.config.guild(guild)

        actiune = await conf.actiune()
        fara_dm = await conf.fara_dm()
        id_canal_log = await conf.canal_log()

        # Încearcă întâi să șteargă mesajul care a declanșat capcana
        with contextlib.suppress(discord.HTTPException):
            await message.delete()

        # Trimite DM utilizatorului înainte de acțiune, dacă e permis
        if not fara_dm:
            with contextlib.suppress(discord.HTTPException):
                await membru.send(
                    f"Ai fost eliminat de pe **{guild.name}** pentru că ai postat "
                    f"într-un canal restricționat de tip honeypot (capcană)."
                )

        motiv = "Honeypot declanșat: a postat în canalul honeypot (probabil spam/cont compromis)."
        actiune_reusita = False
        eroare = None

        try:
            if actiune == "ban":
                await guild.ban(membru, reason=motiv, delete_message_seconds=3600)
                actiune_reusita = True
            else:
                # "kick" aici = softban (ban urmat de unban) astfel încât
                # Discord să șteargă mesajele recente ale utilizatorului
                await guild.ban(membru, reason=motiv, delete_message_seconds=3600)
                await guild.unban(membru, reason="Curățare softban honeypot (unban după ban)")
                actiune_reusita = True
        except discord.Forbidden:
            eroare = "Nu am permisiunile necesare pentru a bana/da kick acestui membru."
        except discord.HTTPException as e:
            eroare = f"Eroare HTTP la aplicarea sancțiunii: {e}"

        if actiune_reusita:
            numar_nou = await conf.numar_eliminati()
            numar_nou += 1
            await conf.numar_eliminati.set(numar_nou)
            if not await conf.fara_mesaj_avertisment():
                await self._actualizeaza_mesaj_avertisment(guild, message.channel)

        if id_canal_log:
            canal_log = guild.get_channel(id_canal_log)
            if canal_log:
                embed = discord.Embed(
                    title="🍯 Honeypot Declanșat",
                    color=discord.Color.red() if actiune_reusita else discord.Color.orange(),
                    timestamp=datetime.now(timezone.utc),
                )
                embed.add_field(name="Utilizator", value=f"{membru} ({membru.id})", inline=False)
                embed.add_field(
                    name="Acțiune",
                    value=("Softban (kick)" if actiune == "kick" else "Ban") if actiune_reusita else "Eșuat",
                    inline=True,
                )
                if eroare:
                    embed.add_field(name="Eroare", value=eroare, inline=False)
                if message.content:
                    continut = message.content[:500]
                    embed.add_field(name="Conținutul mesajului", value=box(continut), inline=False)
                with contextlib.suppress(discord.HTTPException):
                    await canal_log.send(embed=embed)

    # ---------------------------------------------------------------
    # Creare / gestionare canal
    # ---------------------------------------------------------------

    async def _creeaza_canal_honeypot(self, guild: discord.Guild, haos: bool = False):
        nume = self._genereaza_nume_canal(haos)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
        }
        try:
            canal = await guild.create_text_channel(
                nume, overwrites=overwrites, reason="Cog Honeypot: configurare canal honeypot"
            )
        except discord.Forbidden:
            return None

        conf = self.config.guild(guild)
        await conf.canal_honeypot.set(canal.id)
        await conf.id_mesaj_avertisment.set(None)

        if not await conf.fara_mesaj_avertisment():
            await self._actualizeaza_mesaj_avertisment(guild, canal)

        return canal

    def _genereaza_nume_canal(self, haos: bool = False) -> str:
        if haos:
            return "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        return random.choice(CUVINTE_NUME_ALEATORIU) + "-" + "".join(random.choices(string.digits, k=3))

    # ---------------------------------------------------------------
    # Task-uri programate (experimente)
    # ---------------------------------------------------------------

    @tasks.loop(hours=1)
    async def task_warmer(self):
        """La fiecare oră verifică dacă au trecut 24h de la ultimul mesaj warmer,
        pentru fiecare server cu warmer activat; dacă da, trimite unul nou.
        Verificarea orară (în loc de buclă directă la 24h) evită trimiterea
        imediată a unui mesaj la fiecare reîncărcare a cog-ului."""
        acum = datetime.now(timezone.utc).timestamp()
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            if not data.get("warmer_activ") or not data.get("activat"):
                continue
            if acum - data.get("warmer_ultima_trimitere", 0) < 24 * 3600:
                continue
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            id_canal = data.get("canal_honeypot")
            if id_canal is None:
                continue
            canal = guild.get_channel(id_canal)
            if canal is None:
                continue
            with contextlib.suppress(discord.HTTPException):
                await canal.send(random.choice(MESAJE_WARMER))
            await self.config.guild(guild).warmer_ultima_trimitere.set(acum)

    @task_warmer.before_loop
    async def before_task_warmer(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def task_nume_aleatoriu(self):
        """La fiecare oră verifică dacă au trecut 24h de la ultima rotație de nume,
        pentru fiecare server cu funcția activată; dacă da, redenumește canalul.
        Verificarea orară evită o redenumire imediată la fiecare reîncărcare."""
        acum = datetime.now(timezone.utc).timestamp()
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            if not data.get("nume_aleatoriu_activ") or not data.get("activat"):
                continue
            if acum - data.get("nume_ultima_rotatie", 0) < 24 * 3600:
                continue
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            id_canal = data.get("canal_honeypot")
            if id_canal is None:
                continue
            canal = guild.get_channel(id_canal)
            if canal is None:
                continue
            nume_nou = self._genereaza_nume_canal(haos=data.get("nume_aleatoriu_haos", False))
            with contextlib.suppress(discord.HTTPException):
                await canal.edit(name=nume_nou, reason="Honeypot: rotație zilnică a numelui canalului")
            await self.config.guild(guild).nume_ultima_rotatie.set(acum)

    @task_nume_aleatoriu.before_loop
    async def before_task_nume_aleatoriu(self):
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------------
    # Comenzi
    # ---------------------------------------------------------------

    @commands.hybrid_group(name="honeypot")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def honeypot(self, ctx: commands.Context):
        """Configurează canalul honeypot anti-spam."""
        if ctx.invoked_subcommand is None:
            await self._afiseaza_setari(ctx)

    async def _afiseaza_setari(self, ctx: commands.Context):
        conf = self.config.guild(ctx.guild)
        data = await conf.all()
        canal_honeypot = ctx.guild.get_channel(data["canal_honeypot"]) if data["canal_honeypot"] else None
        canal_log = ctx.guild.get_channel(data["canal_log"]) if data["canal_log"] else None

        embed = discord.Embed(title="🍯 Setări Honeypot", color=await ctx.embed_color())
        embed.add_field(name="Activat", value=("Da" if data["activat"] else "Nu"), inline=True)
        embed.add_field(
            name="Canal Honeypot", value=canal_honeypot.mention if canal_honeypot else "Nesetat", inline=True
        )
        embed.add_field(
            name="Canal Log", value=canal_log.mention if canal_log else "Nesetat", inline=True
        )
        embed.add_field(name="Acțiune", value=data["actiune"], inline=True)
        embed.add_field(name="Utilizatori eliminați", value=str(data.get("numar_eliminati", 0)), inline=True)
        experimente = []
        if data["warmer_activ"]:
            experimente.append("Warmer canal")
        if data["nume_aleatoriu_activ"]:
            experimente.append("Nume canal aleatoriu")
        if data["nume_aleatoriu_haos"]:
            experimente.append("Nume canal aleatoriu (haos)")
        if data["fara_mesaj_avertisment"]:
            experimente.append("Fără mesaj de avertisment")
        if data["fara_dm"]:
            experimente.append("Fără DM")
        embed.add_field(
            name="Experimente",
            value=humanize_list(experimente) if experimente else "Niciunul activ",
            inline=False,
        )
        await ctx.send(embed=embed)

    @honeypot.command(name="setup")
    async def honeypot_setup(self, ctx: commands.Context):
        """Creează (sau recreează) canalul honeypot pe acest server."""
        canal = await self._creeaza_canal_honeypot(ctx.guild)
        if canal is None:
            await ctx.send("Nu am permisiunea de a crea canale pe acest server.")
            return
        await ctx.send(f"Canal honeypot creat: {canal.mention}")

    @honeypot.command(name="canal")
    async def honeypot_canal(self, ctx: commands.Context, canal: discord.TextChannel):
        """Setează manual un canal existent ca honeypot."""
        await self.config.guild(ctx.guild).canal_honeypot.set(canal.id)
        await ctx.send(f"Canal honeypot setat la {canal.mention}.")

    @honeypot.command(name="canallog")
    async def honeypot_canal_log(self, ctx: commands.Context, canal: discord.TextChannel):
        """Setează canalul unde se trimit jurnalele de declanșare a capcanei."""
        await self.config.guild(ctx.guild).canal_log.set(canal.id)
        await ctx.send(f"Canal de log setat la {canal.mention}.")

    @honeypot.command(name="actiune")
    async def honeypot_actiune(self, ctx: commands.Context, actiune: str):
        """Setează acțiunea aplicată la declanșare: `kick` (softban) sau `ban`."""
        actiune = actiune.lower()
        if actiune not in ("kick", "ban"):
            await ctx.send("Acțiunea trebuie să fie `kick` sau `ban`.")
            return
        await self.config.guild(ctx.guild).actiune.set(actiune)
        await ctx.send(f"Acțiunea honeypot setată la `{actiune}`.")

    @honeypot.command(name="activare")
    async def honeypot_activare(self, ctx: commands.Context, activat: bool = None):
        """Activează sau dezactivează honeypot-ul pe acest server."""
        conf = self.config.guild(ctx.guild)
        if activat is None:
            activat = not await conf.activat()
        await conf.activat.set(activat)
        await ctx.send(f"Honeypot este acum **{'activat' if activat else 'dezactivat'}**.")

    @honeypot.command(name="contor")
    async def honeypot_contor(self, ctx: commands.Context):
        """Afișează numărul de utilizatori eliminați de honeypot pe acest server."""
        numar = await self.config.guild(ctx.guild).numar_eliminati()
        await ctx.send(f"🍯 Honeypot a eliminat până acum **{numar}** utilizatori pe acest server.")

    @honeypot.command(name="reseteazacontor")
    async def honeypot_reseteaza_contor(self, ctx: commands.Context):
        """Resetează la 0 contorul de utilizatori eliminați și actualizează embed-ul din canal."""
        conf = self.config.guild(ctx.guild)
        await conf.numar_eliminati.set(0)
        if not await conf.fara_mesaj_avertisment():
            await self._actualizeaza_mesaj_avertisment(ctx.guild)
        await ctx.send("Contorul a fost resetat la 0.")

    @honeypot.group(name="experiment")
    async def honeypot_experiment(self, ctx: commands.Context):
        """Activează/dezactivează funcții experimentale honeypot."""

    @honeypot_experiment.command(name="warmer")
    async def experiment_warmer(self, ctx: commands.Context, activat: bool):
        """Activează/dezactivează warmer-ul de canal (trimite mesaje zilnice ca să pară activ)."""
        await self.config.guild(ctx.guild).warmer_activ.set(activat)
        await ctx.send(f"Warmer canal: **{'activat' if activat else 'dezactivat'}**.")

    @honeypot_experiment.command(name="numealeatoriu")
    async def experiment_nume_aleatoriu(self, ctx: commands.Context, activat: bool, haos: bool = False):
        """Activează/dezactivează redenumirea zilnică aleatorie a canalului honeypot."""
        await self.config.guild(ctx.guild).nume_aleatoriu_activ.set(activat)
        await self.config.guild(ctx.guild).nume_aleatoriu_haos.set(haos)
        await ctx.send(
            f"Nume canal aleatoriu: **{'activat' if activat else 'dezactivat'}** "
            f"(mod haos: **{'da' if haos else 'nu'}**)."
        )

    @honeypot_experiment.command(name="faraavertisment")
    async def experiment_fara_avertisment(self, ctx: commands.Context, activat: bool):
        """Activează/dezactivează postarea mesajului embed de avertisment (cu contor) în canalul honeypot."""
        conf = self.config.guild(ctx.guild)
        await conf.fara_mesaj_avertisment.set(activat)

        if not activat:
            # Re-activat: (re)trimite embed-ul cu contor în canal, dacă există un canal setat
            await self._actualizeaza_mesaj_avertisment(ctx.guild)
        else:
            # Dezactivat: șterge mesajul embed existent, dacă există
            id_canal = await conf.canal_honeypot()
            id_mesaj = await conf.id_mesaj_avertisment()
            if id_canal and id_mesaj:
                canal = ctx.guild.get_channel(id_canal)
                if canal:
                    with contextlib.suppress(discord.HTTPException):
                        mesaj = await canal.fetch_message(id_mesaj)
                        await mesaj.delete()
                await conf.id_mesaj_avertisment.set(None)

        await ctx.send(f"Fără mesaj de avertisment: **{'activat' if activat else 'dezactivat'}**.")

    @honeypot_experiment.command(name="faradm")
    async def experiment_fara_dm(self, ctx: commands.Context, activat: bool):
        """Activează/dezactivează trimiterea unui DM utilizatorilor înainte de eliminare."""
        await self.config.guild(ctx.guild).fara_dm.set(activat)
        await ctx.send(f"Fără DM la declanșare: **{'activat' if activat else 'dezactivat'}**.")
