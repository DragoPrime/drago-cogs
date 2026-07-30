import asyncio
import random
import time
from collections import defaultdict, deque

import aiohttp
import discord
from redbot.core import Config, checks, commands
from redbot.core.bot import Red

DEFAULT_PERSONALITY = (
    "Esti un bot prietenos si glumet de pe un server de Discord romanesc. "
    "Vorbesti exclusiv in limba romana, folosesti un ton cald si informal, "
    "si iti place sa faci mici glume, dar ramai mereu respectuos si util."
)

DEFAULT_WELCOME_INSTRUCTION = (
    "Un utilizator nou pe nume {member_name} tocmai a intrat pe server. "
    "Scrie un mesaj de bun venit scurt (maxim 2-3 propozitii), cald si original, "
    "in limba romana, care sa reflecte personalitatea ta. Nu folosi ghilimele "
    "in jurul mesajului si nu adauga explicatii, scrie doar mesajul de bun venit."
)

DEFAULT_CHAT_INSTRUCTION = (
    "Esti intr-un chat de Discord si tocmai cineva a scris un mesaj. Raspunde "
    "natural, scurt (maxim 1-3 propozitii), in limba romana, tinand cont de "
    "personalitatea ta si de contextul conversatiei de mai jos."
)


class OllamaChat(commands.Cog):
    """Cog care foloseste Ollama (AI local) pentru mesaje de bun venit si chat ocazional, in romana."""

    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x0114A114, force_registration=True)

        default_guild = {
            "ollama_url": "http://localhost:11434",
            "model": "llama3",
            "personality": DEFAULT_PERSONALITY,
            "welcome_instruction": DEFAULT_WELCOME_INSTRUCTION,
            "chat_instruction": DEFAULT_CHAT_INSTRUCTION,
            "welcome_channel": None,
            "chat_channel": None,
            "welcome_enabled": True,
            "chat_enabled": True,
            "chat_chance": 15,  # procent sansa (%) de a raspunde la un mesaj din canalul de chat
            "chat_cooldown": 20,  # secunde minime intre doua raspunsuri automate
            "history_length": 8,  # cate mesaje anterioare tine minte per canal, pentru context
            "timeout": 60,  # secunde, timeout pentru cererile catre Ollama
            "thinking_mode": False,  # pentru modele cu "thinking" (ex: qwen3, deepseek-r1) - dezactivat implicit
        }
        self.config.register_guild(**default_guild)

        self.session: aiohttp.ClientSession = None

        # Memorie in RAM, nu se salveaza pe disc: istoric scurt de conversatie per canal
        # si timestamp-ul ultimului raspuns automat per canal, pentru cooldown.
        self._history = defaultdict(lambda: deque(maxlen=20))
        self._last_reply = {}
        self._locks = defaultdict(asyncio.Lock)

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ------------------------------------------------------------------ #
    #  Comunicarea cu Ollama
    # ------------------------------------------------------------------ #

    async def _ollama_chat(self, guild: discord.Guild, messages: list) -> str:
        """Trimite o cerere catre endpoint-ul /api/chat al Ollama si returneaza textul de raspuns."""
        conf = await self.config.guild(guild).all()
        url = conf["ollama_url"].rstrip("/")
        payload = {
            "model": conf["model"],
            "messages": messages,
            "stream": False,
            # Pentru modele care suporta "thinking mode" (ex: qwen3, deepseek-r1),
            # dezactivam acest mod implicit pentru raspunsuri rapide si curate in chat.
            # Ollama ignora acest parametru la modelele care nu-l suporta.
            "think": conf["thinking_mode"],
        }
        timeout = aiohttp.ClientTimeout(total=conf["timeout"])
        try:
            async with self.session.post(f"{url}/api/chat", json=payload, timeout=timeout) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Ollama a raspuns cu status {resp.status}: {text[:300]}")
                data = await resp.json()
        except asyncio.TimeoutError:
            raise RuntimeError("Cererea catre Ollama a expirat (timeout). Verifica daca serverul Ollama ruleaza.")
        except aiohttp.ClientConnectorError:
            raise RuntimeError(
                "Nu m-am putut conecta la Ollama. Verifica URL-ul configurat si daca serviciul Ollama este pornit."
            )

        message = data.get("message", {})
        content = message.get("content", "")
        return content.strip()

    async def _build_system_prompt(self, guild: discord.Guild, extra_instruction: str) -> str:
        personality = await self.config.guild(guild).personality()
        return f"{personality}\n\n{extra_instruction}"

    # ------------------------------------------------------------------ #
    #  Mesaje de bun venit
    # ------------------------------------------------------------------ #

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        conf = await self.config.guild(guild).all()
        if not conf["welcome_enabled"]:
            return
        channel_id = conf["welcome_channel"]
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            return

        system_prompt = f"{conf['personality']}\n\n{conf['welcome_instruction'].format(member_name=member.display_name)}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Scrie mesajul de bun venit pentru {member.display_name}."},
        ]

        try:
            reply = await self._ollama_chat(guild, messages)
        except RuntimeError:
            # Nu blocam alte functionalitati daca Ollama nu raspunde; esuam silentios la welcome.
            return

        if not reply:
            return

        try:
            await channel.send(f"{member.mention} {reply}")
        except discord.Forbidden:
            pass

    # ------------------------------------------------------------------ #
    #  Chat ocazional pe canalul configurat
    # ------------------------------------------------------------------ #

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        conf = await self.config.guild(message.guild).all()
        if not conf["chat_enabled"]:
            return

        chat_channel_id = conf["chat_channel"]
        if not chat_channel_id or message.channel.id != chat_channel_id:
            return

        # Ignoram comenzile catre bot (orice prefix valid al botului)
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # Retinem mesajul in istoricul scurt, pentru context, indiferent daca raspundem sau nu
        history = self._history[message.channel.id]
        history.append({"role": "user", "content": f"{message.author.display_name}: {message.content}"})

        # Verificam cooldown-ul, ca sa nu spamam canalul
        now = time.monotonic()
        last = self._last_reply.get(message.channel.id, 0)
        if now - last < conf["chat_cooldown"]:
            return

        # Sansa aleatorie de a raspunde
        if random.randint(1, 100) > conf["chat_chance"]:
            return

        lock = self._locks[message.channel.id]
        if lock.locked():
            return

        async with lock:
            system_prompt = f"{conf['personality']}\n\n{conf['chat_instruction']}"
            recent = list(history)[-conf["history_length"]:]
            messages = [{"role": "system", "content": system_prompt}] + recent

            async with message.channel.typing():
                try:
                    reply = await self._ollama_chat(message.guild, messages)
                except RuntimeError:
                    return

            if not reply:
                return

            self._last_reply[message.channel.id] = time.monotonic()
            history.append({"role": "assistant", "content": reply})
            try:
                await message.channel.send(reply)
            except discord.Forbidden:
                pass

    # ------------------------------------------------------------------ #
    #  Comenzi de configurare
    # ------------------------------------------------------------------ #

    @commands.group(name="ollamaset")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def ollamaset(self, ctx: commands.Context):
        """Configureaza cog-ul OllamaChat (AI local, mesaje de bun venit si chat)."""

    @ollamaset.command(name="url")
    async def ollamaset_url(self, ctx: commands.Context, url: str):
        """Seteaza adresa serverului Ollama (implicit: http://localhost:11434)."""
        await self.config.guild(ctx.guild).ollama_url.set(url.rstrip("/"))
        await ctx.send(f"Adresa Ollama a fost setata la: `{url.rstrip('/')}`")

    @ollamaset.command(name="model")
    async def ollamaset_model(self, ctx: commands.Context, model: str):
        """Seteaza numele modelului Ollama folosit (ex: llama3, mistral, gemma2)."""
        await self.config.guild(ctx.guild).model.set(model)
        await ctx.send(f"Modelul a fost setat la: `{model}`")

    @ollamaset.command(name="personalitate", aliases=["personality"])
    async def ollamaset_personality(self, ctx: commands.Context, *, text: str):
        """Seteaza personalitatea AI-ului (descriere in text liber)."""
        await self.config.guild(ctx.guild).personality.set(text)
        await ctx.send("Personalitatea a fost actualizata.")

    @ollamaset.command(name="canalbunvenit", aliases=["welcomechannel"])
    async def ollamaset_welcome_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Seteaza canalul unde se trimit mesajele de bun venit. Fara argument = dezactiveaza."""
        if channel is None:
            await self.config.guild(ctx.guild).welcome_channel.set(None)
            await ctx.send("Canalul de bun venit a fost dezactivat (niciun canal setat).")
            return
        await self.config.guild(ctx.guild).welcome_channel.set(channel.id)
        await ctx.send(f"Canalul de bun venit a fost setat la {channel.mention}.")

    @ollamaset.command(name="canalchat", aliases=["chatchannel"])
    async def ollamaset_chat_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Seteaza canalul unde botul poate discuta ocazional. Fara argument = dezactiveaza."""
        if channel is None:
            await self.config.guild(ctx.guild).chat_channel.set(None)
            await ctx.send("Canalul de chat a fost dezactivat (niciun canal setat).")
            return
        await self.config.guild(ctx.guild).chat_channel.set(channel.id)
        await ctx.send(f"Canalul de chat a fost setat la {channel.mention}.")

    @ollamaset.command(name="sansa", aliases=["chance"])
    async def ollamaset_chance(self, ctx: commands.Context, procent: int):
        """Seteaza sansa (in procente, 1-100) ca botul sa raspunda la un mesaj din canalul de chat."""
        if not 1 <= procent <= 100:
            await ctx.send("Te rog alege un procent intre 1 si 100.")
            return
        await self.config.guild(ctx.guild).chat_chance.set(procent)
        await ctx.send(f"Sansa de raspuns a fost setata la {procent}%.")

    @ollamaset.command(name="cooldown")
    async def ollamaset_cooldown(self, ctx: commands.Context, secunde: int):
        """Seteaza timpul minim (in secunde) intre doua raspunsuri automate consecutive."""
        if secunde < 0:
            await ctx.send("Numarul de secunde trebuie sa fie pozitiv.")
            return
        await self.config.guild(ctx.guild).chat_cooldown.set(secunde)
        await ctx.send(f"Cooldown-ul a fost setat la {secunde} secunde.")

    @ollamaset.command(name="istoric", aliases=["history"])
    async def ollamaset_history(self, ctx: commands.Context, numar_mesaje: int):
        """Seteaza cate mesaje anterioare sa foloseasca AI-ul drept context (implicit 8)."""
        if not 1 <= numar_mesaje <= 20:
            await ctx.send("Alege o valoare intre 1 si 20.")
            return
        await self.config.guild(ctx.guild).history_length.set(numar_mesaje)
        await ctx.send(f"Lungimea istoricului de context a fost setata la {numar_mesaje} mesaje.")

    @ollamaset.command(name="gandire", aliases=["thinking"])
    async def ollamaset_thinking(self, ctx: commands.Context):
        """Activeaza/dezactiveaza modul de 'gandire' (thinking) pentru modelele care il suporta (ex: qwen3).

        Implicit este dezactivat, pentru raspunsuri rapide, potrivite pentru chat live.
        Activarea lui poate imbunatati calitatea raspunsurilor complexe, dar le face mai lente.
        """
        current = await self.config.guild(ctx.guild).thinking_mode()
        await self.config.guild(ctx.guild).thinking_mode.set(not current)
        stare = "activat" if not current else "dezactivat"
        await ctx.send(f"Modul de gandire (thinking) a fost {stare}.")

    @ollamaset.command(name="toggle")
    async def ollamaset_toggle(self, ctx: commands.Context):
        """Activeaza/dezactiveaza functia de chat ocazional."""
        current = await self.config.guild(ctx.guild).chat_enabled()
        await self.config.guild(ctx.guild).chat_enabled.set(not current)
        stare = "activat" if not current else "dezactivat"
        await ctx.send(f"Chat-ul ocazional a fost {stare}.")

    @ollamaset.command(name="togglebunvenit", aliases=["togglewelcome"])
    async def ollamaset_toggle_welcome(self, ctx: commands.Context):
        """Activeaza/dezactiveaza mesajele de bun venit."""
        current = await self.config.guild(ctx.guild).welcome_enabled()
        await self.config.guild(ctx.guild).welcome_enabled.set(not current)
        stare = "activate" if not current else "dezactivate"
        await ctx.send(f"Mesajele de bun venit au fost {stare}.")

    @ollamaset.command(name="testbunvenit", aliases=["testwelcome"])
    async def ollamaset_test_welcome(self, ctx: commands.Context):
        """Genereaza si trimite un mesaj de bun venit de test pentru tine, pe canalul curent."""
        conf = await self.config.guild(ctx.guild).all()
        system_prompt = f"{conf['personality']}\n\n{conf['welcome_instruction'].format(member_name=ctx.author.display_name)}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Scrie mesajul de bun venit pentru {ctx.author.display_name}."},
        ]
        async with ctx.typing():
            try:
                reply = await self._ollama_chat(ctx.guild, messages)
            except RuntimeError as e:
                await ctx.send(f"Eroare la comunicarea cu Ollama: {e}")
                return
        await ctx.send(reply or "(AI-ul a returnat un raspuns gol)")

    @ollamaset.command(name="testchat")
    async def ollamaset_test_chat(self, ctx: commands.Context, *, mesaj: str):
        """Testeaza direct un raspuns AI, pornind de la un mesaj dat de tine."""
        conf = await self.config.guild(ctx.guild).all()
        system_prompt = f"{conf['personality']}\n\n{conf['chat_instruction']}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{ctx.author.display_name}: {mesaj}"},
        ]
        async with ctx.typing():
            try:
                reply = await self._ollama_chat(ctx.guild, messages)
            except RuntimeError as e:
                await ctx.send(f"Eroare la comunicarea cu Ollama: {e}")
                return
        await ctx.send(reply or "(AI-ul a returnat un raspuns gol)")

    @ollamaset.command(name="setari", aliases=["settings", "show"])
    async def ollamaset_settings(self, ctx: commands.Context):
        """Afiseaza configuratia curenta a cog-ului pentru acest server."""
        conf = await self.config.guild(ctx.guild).all()
        welcome_channel = ctx.guild.get_channel(conf["welcome_channel"]) if conf["welcome_channel"] else None
        chat_channel = ctx.guild.get_channel(conf["chat_channel"]) if conf["chat_channel"] else None

        embed = discord.Embed(title="Configuratie OllamaChat", color=discord.Color.blurple())
        embed.add_field(name="URL Ollama", value=f"`{conf['ollama_url']}`", inline=False)
        embed.add_field(name="Model", value=f"`{conf['model']}`", inline=True)
        embed.add_field(name="Chat activat", value=str(conf["chat_enabled"]), inline=True)
        embed.add_field(name="Bun venit activat", value=str(conf["welcome_enabled"]), inline=True)
        embed.add_field(
            name="Canal bun venit",
            value=welcome_channel.mention if welcome_channel else "Nesetat",
            inline=True,
        )
        embed.add_field(
            name="Canal chat",
            value=chat_channel.mention if chat_channel else "Nesetat",
            inline=True,
        )
        embed.add_field(name="Sansa raspuns", value=f"{conf['chat_chance']}%", inline=True)
        embed.add_field(name="Cooldown", value=f"{conf['chat_cooldown']}s", inline=True)
        embed.add_field(name="Lungime istoric", value=str(conf["history_length"]), inline=True)
        embed.add_field(name="Mod gandire (thinking)", value=str(conf["thinking_mode"]), inline=True)
        embed.add_field(name="Personalitate", value=conf["personality"][:1024], inline=False)
        await ctx.send(embed=embed)
