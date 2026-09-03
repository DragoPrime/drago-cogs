import asyncio
import random
import re
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
    "personalitatea ta si de contextul conversatiei de mai jos. Daca nu cunosti "
    "un detaliu concret (nume exacte, cifre, linkuri, denumiri de grupuri etc.), "
    "nu il inventa si nu folosi placeholdere de tipul [Nume] sau [X] - spune "
    "sincer ca nu ai aceasta informatie, in loc sa completezi cu ceva plauzibil."
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
            "jellyfin_enabled": True,
            "jellyfin_servers": [],  # lista de dict: {name, url, api_key, description, restricted}
            "jellyfin_search_limit": 6,  # cate rezultate per server sunt incluse in context
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
    #  Integrare Jellyfin
    # ------------------------------------------------------------------ #

    def _extract_search_candidates(self, text: str) -> list:
        """Extrage termeni probabili de cautare dintr-un mesaj (titluri/nume proprii),
        pentru ca o intrebare intreaga (ex: 'Unde gasesc One Piece?') sa nu fie trimisa
        ca atare catre Jellyfin, unde rareori se potriveste cu nimic.

        Incearca, in ordine: propozitii intre ghilimele, secvente de cuvinte cu majuscula
        (probabil titluri), apoi mesajul intreg curatat, ca ultima solutie.
        """
        cleaned = text.strip().rstrip("?!.").strip()
        candidates = []

        # Text intre ghilimele - de obicei exact titlul cautat
        quoted = re.findall(r'["\u201c\u201e]([^"\u201d]{2,60})["\u201d]', cleaned)
        candidates.extend(q.strip() for q in quoted if q.strip())

        # Secvente de 1-4 cuvinte care incep cu majuscula (nume proprii / titluri probabile)
        romanian_upper = "A-ZĂÂÎȘȚ"
        romanian_lower = r"a-zăâîșț0-9'\-"
        pattern = rf"\b[{romanian_upper}][{romanian_lower}]*(?:\s+[{romanian_upper}][{romanian_lower}]*){{0,3}}\b"
        for match in re.findall(pattern, cleaned):
            if match not in candidates and len(match) > 2:
                candidates.append(match)

        # Mesajul intreg, curatat - ca ultima incercare (fallback)
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

        return candidates[:5]  # limitam numarul de incercari, ca sa nu bombardam Jellyfin

    async def _jellyfin_search_diagnostic(self, server: dict, query: str, limit: int) -> dict:
        """La fel ca _jellyfin_search_one, dar NU ascunde erorile - folosita doar de comanda
        de test, ca sa poata arata utilizatorului exact ce s-a intamplat (status HTTP,
        eroare de conexiune, raspuns brut de la Jellyfin etc.)."""
        url = server["url"].rstrip("/")
        endpoint = f"{url}/Search/Hints"
        params = {
            "searchTerm": query,
            "api_key": server["api_key"],
            "Limit": str(limit),
            "IncludeArtists": "false",
            "IncludeGenres": "false",
            "IncludeStudios": "false",
        }
        result = {
            "ok": False,
            "endpoint": endpoint,
            "status": None,
            "error": None,
            "raw_snippet": None,
            "total_record_count": None,
            "items": [],
        }
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(endpoint, params=params, timeout=timeout) as resp:
                result["status"] = resp.status
                text = await resp.text()
                result["raw_snippet"] = text[:300]
                if resp.status != 200:
                    result["error"] = f"Serverul a raspuns cu status HTTP {resp.status}"
                    return result
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    result["error"] = "Raspunsul nu a putut fi interpretat ca JSON valid."
                    return result
        except asyncio.TimeoutError:
            result["error"] = "Timeout - serverul nu a raspuns in timp util (10s)."
            return result
        except aiohttp.ClientConnectorError as e:
            result["error"] = f"Nu m-am putut conecta la server: {e}"
            return result
        except aiohttp.ClientError as e:
            result["error"] = f"Eroare de retea: {e}"
            return result

        result["ok"] = True
        result["total_record_count"] = data.get("TotalRecordCount")
        for hint in data.get("SearchHints", []):
            name = hint.get("Name")
            if not name:
                continue
            year = hint.get("ProductionYear")
            item_type = hint.get("Type", "")
            piece = name
            if year:
                piece += f" ({year})"
            if item_type:
                piece += f" [{item_type}]"
            result["items"].append(piece)
        return result

    async def _jellyfin_search_one(self, server: dict, query: str, limit: int) -> list:
        """Cauta un termen pe un singur server Jellyfin si returneaza o lista de descrieri scurte."""
        url = server["url"].rstrip("/")
        params = {
            "searchTerm": query,
            "api_key": server["api_key"],
            "Limit": str(limit),
            "IncludeArtists": "false",
            "IncludeGenres": "false",
            "IncludeStudios": "false",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(f"{url}/Search/Hints", params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            return []

        results = []
        for hint in data.get("SearchHints", []):
            name = hint.get("Name")
            if not name:
                continue
            year = hint.get("ProductionYear")
            item_type = hint.get("Type", "")
            piece = name
            if year:
                piece += f" ({year})"
            if item_type:
                piece += f" [{item_type}]"
            results.append(piece)
        return results

    async def _jellyfin_search_server(self, server: dict, message_text: str, limit: int) -> list:
        """Incearca mai multi termeni de cautare candidati pe un singur server, in ordine,
        si returneaza rezultatele primului candidat care gaseste ceva."""
        for term in self._extract_search_candidates(message_text):
            items = await self._jellyfin_search_one(server, term, limit)
            if items:
                return items
        return []

    async def _jellyfin_context(self, guild: discord.Guild, query: str, channel: discord.abc.GuildChannel) -> str:
        """Cauta pe toate serverele Jellyfin configurate si construieste un bloc de context text.

        Serverele marcate ca 'restricted' (continut adult) sunt incluse doar daca
        se cauta dintr-un canal marcat NSFW pe Discord.
        """
        conf = await self.config.guild(guild).all()
        if not conf["jellyfin_enabled"]:
            return ""
        servers = conf["jellyfin_servers"]
        if not servers:
            return ""

        is_nsfw = bool(getattr(channel, "is_nsfw", lambda: False)())
        limit = conf["jellyfin_search_limit"]

        blocks = []
        for server in servers:
            if server.get("restricted") and not is_nsfw:
                continue
            items = await self._jellyfin_search_server(server, query, limit)
            if items:
                lines = "\n".join(f"  - {item}" for item in items)
                blocks.append(
                    f"Server '{server['name']}' ({server.get('description', 'fara descriere')}), "
                    f"adresa: {server['url']}:\n{lines}"
                )

        if not blocks:
            return ""

        return (
            "Informatii disponibile despre continutul de pe serverele Jellyfin ale utilizatorului "
            "(foloseste-le DOAR daca sunt relevante pentru mesaj; nu inventa titluri care nu apar "
            "in aceasta lista si nu pretinde ca stii alte titluri decat cele de mai jos; daca "
            "mentionezi un titlu gasit, poti include si adresa serverului unde se afla. Daca gasesti "
            "mai multe variante ale aceluiasi titlu (ex: sezoane, filme, OVA-uri separate), "
            "enumera-le pe scurt pe toate, cu anul sau tipul, ca utilizatorul sa stie ce optiuni are; "
            "nu alege tu unul singur in locul lui):\n\n"
            + "\n\n".join(blocks)
        )

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

        # Inlocuim numele afisat, folosit de AI in text, cu ping-ul real (@utilizator).
        # Daca AI-ul nu a folosit numele deloc, adaugam ping-ul la inceputul mesajului.
        if member.display_name in reply:
            reply = reply.replace(member.display_name, member.mention)
        elif member.name in reply:
            reply = reply.replace(member.name, member.mention)
        else:
            reply = f"{member.mention} {reply}"

        try:
            await channel.send(reply)
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

            jellyfin_context = await self._jellyfin_context(message.guild, message.content, message.channel)
            if jellyfin_context:
                system_prompt += f"\n\n{jellyfin_context}"

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

        if reply:
            if ctx.author.display_name in reply:
                reply = reply.replace(ctx.author.display_name, ctx.author.mention)
            elif ctx.author.name in reply:
                reply = reply.replace(ctx.author.name, ctx.author.mention)
            else:
                reply = f"{ctx.author.mention} {reply}"

        await ctx.send(reply or "(AI-ul a returnat un raspuns gol)")

    @ollamaset.command(name="testchat")
    async def ollamaset_test_chat(self, ctx: commands.Context, *, mesaj: str):
        """Testeaza direct un raspuns AI, pornind de la un mesaj dat de tine."""
        conf = await self.config.guild(ctx.guild).all()
        system_prompt = f"{conf['personality']}\n\n{conf['chat_instruction']}"

        jellyfin_context = await self._jellyfin_context(ctx.guild, mesaj, ctx.channel)
        if jellyfin_context:
            system_prompt += f"\n\n{jellyfin_context}"

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

    @ollamaset.group(name="jellyfin")
    async def ollamaset_jellyfin(self, ctx: commands.Context):
        """Configureaza serverele Jellyfin despre care AI-ul poate raspunde."""

    @ollamaset_jellyfin.command(name="add")
    async def jellyfin_add(
        self,
        ctx: commands.Context,
        nume: str,
        url: str,
        api_key: str,
        continut_adult: bool,
        *,
        descriere: str = "",
    ):
        """Adauga un server Jellyfin.

        Exemplu: `[p]ollamaset jellyfin add Anime https://jellyfin.exemplu.ro:8096 CHEIE_API false Serverul cu anime`

        `continut_adult` este `true` sau `false` — daca e `true`, rezultatele de pe acest
        server vor fi folosite de AI DOAR in canale marcate NSFW pe Discord.

        Din motive de securitate (cheia API va fi vizibila in mesaj), botul va incerca sa
        stearga mesajul tau imediat dupa ce salveaza configuratia.
        """
        servers = await self.config.guild(ctx.guild).jellyfin_servers()
        if any(s["name"].lower() == nume.lower() for s in servers):
            await ctx.send(f"Exista deja un server numit `{nume}`. Sterge-l intai cu `jellyfin remove {nume}`.")
            return

        servers.append(
            {
                "name": nume,
                "url": url.rstrip("/"),
                "api_key": api_key,
                "description": descriere or "fara descriere",
                "restricted": continut_adult,
            }
        )
        await self.config.guild(ctx.guild).jellyfin_servers.set(servers)

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        confirmare = f"Serverul Jellyfin `{nume}` a fost adaugat"
        confirmare += " (marcat ca **continut adult** — folosit doar in canale NSFW)." if continut_adult else "."
        await ctx.send(confirmare)

    @ollamaset_jellyfin.command(name="remove")
    async def jellyfin_remove(self, ctx: commands.Context, nume: str):
        """Sterge un server Jellyfin dupa nume."""
        servers = await self.config.guild(ctx.guild).jellyfin_servers()
        filtered = [s for s in servers if s["name"].lower() != nume.lower()]
        if len(filtered) == len(servers):
            await ctx.send(f"Nu am gasit niciun server numit `{nume}`.")
            return
        await self.config.guild(ctx.guild).jellyfin_servers.set(filtered)
        await ctx.send(f"Serverul `{nume}` a fost sters.")

    @ollamaset_jellyfin.command(name="list")
    async def jellyfin_list(self, ctx: commands.Context):
        """Afiseaza serverele Jellyfin configurate (fara cheile API)."""
        servers = await self.config.guild(ctx.guild).jellyfin_servers()
        if not servers:
            await ctx.send("Niciun server Jellyfin configurat inca. Foloseste `jellyfin add`.")
            return
        embed = discord.Embed(title="Servere Jellyfin configurate", color=discord.Color.blurple())
        for s in servers:
            tip = "Continut adult (doar canale NSFW)" if s.get("restricted") else "Continut general"
            embed.add_field(
                name=s["name"],
                value=f"URL: `{s['url']}`\nTip: {tip}\nDescriere: {s.get('description', '—')}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @ollamaset_jellyfin.command(name="test")
    async def jellyfin_test(self, ctx: commands.Context, nume: str, *, cautare: str):
        """Testeaza o cautare directa pe un server Jellyfin, dupa nume, cu diagnostic detaliat."""
        servers = await self.config.guild(ctx.guild).jellyfin_servers()
        server = next((s for s in servers if s["name"].lower() == nume.lower()), None)
        if server is None:
            await ctx.send(f"Nu am gasit niciun server numit `{nume}`.")
            return
        limit = await self.config.guild(ctx.guild).jellyfin_search_limit()
        async with ctx.typing():
            r = await self._jellyfin_search_diagnostic(server, cautare, limit)

        embed = discord.Embed(
            title=f"Diagnostic Jellyfin — {server['name']}",
            color=discord.Color.green() if r["ok"] and r["items"] else discord.Color.orange(),
        )
        embed.add_field(name="Endpoint interogat", value=f"`{r['endpoint']}`", inline=False)
        embed.add_field(name="Termen cautat", value=f"`{cautare}`", inline=True)
        embed.add_field(name="Status HTTP", value=str(r["status"]) if r["status"] else "—", inline=True)

        if r["error"]:
            embed.color = discord.Color.red()
            embed.add_field(name="Eroare", value=r["error"], inline=False)
            if r["raw_snippet"]:
                embed.add_field(name="Raspuns brut (primele caractere)", value=f"```{r['raw_snippet']}```", inline=False)
            embed.add_field(
                name="Verifica",
                value=(
                    "- URL-ul e corect si accesibil de pe masina unde ruleaza botul "
                    "(nu doar din reteaua ta locala)?\n"
                    "- Cheia API e valida (Dashboard → API Keys in Jellyfin)?\n"
                    "- Serverul Jellyfin chiar ruleaza si e pornit?"
                ),
                inline=False,
            )
        elif not r["items"]:
            embed.add_field(
                name="Rezultat",
                value=(
                    f"Conexiunea a functionat (status 200), dar cautarea nu a gasit nimic pentru "
                    f"`{cautare}` (TotalRecordCount: {r['total_record_count']}).\n\n"
                    "Verifica:\n"
                    "- Titlul e scris corect si exista efectiv in aceasta biblioteca Jellyfin?\n"
                    "- Biblioteca a fost scanata complet in Jellyfin (Dashboard → Libraries → Scan)?\n"
                    "- Cheia API are acces la biblioteca respectiva (nu doar la cont, ci si la "
                    "permisiunile de biblioteca setate pentru acel user/cheie)?\n"
                    "- Incearca un termen si mai simplu, de-o singura silaba/cuvant comun din titlu."
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name=f"Rezultate ({len(r['items'])})",
                value="\n".join(f"- {item}" for item in r["items"]),
                inline=False,
            )

        await ctx.send(embed=embed)

    @ollamaset_jellyfin.command(name="limita", aliases=["limit"])
    async def jellyfin_limit(self, ctx: commands.Context, numar: int):
        """Seteaza cate rezultate se cauta per server Jellyfin (implicit 6).

        Mareste aceasta valoare daca ai titluri cu multe sezoane/filme separate
        si vrei ca AI-ul sa le vada pe toate intr-o cautare.
        """
        if not 1 <= numar <= 20:
            await ctx.send("Alege o valoare intre 1 si 20.")
            return
        await self.config.guild(ctx.guild).jellyfin_search_limit.set(numar)
        await ctx.send(f"Limita de rezultate per server Jellyfin a fost setata la {numar}.")

    @ollamaset_jellyfin.command(name="toggle")
    async def jellyfin_toggle(self, ctx: commands.Context):
        """Activeaza/dezactiveaza integrarea Jellyfin, global pentru acest server Discord."""
        current = await self.config.guild(ctx.guild).jellyfin_enabled()
        await self.config.guild(ctx.guild).jellyfin_enabled.set(not current)
        stare = "activata" if not current else "dezactivata"
        await ctx.send(f"Integrarea Jellyfin a fost {stare}.")

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
        jellyfin_servers = conf["jellyfin_servers"]
        embed.add_field(
            name="Jellyfin",
            value=f"{'Activat' if conf['jellyfin_enabled'] else 'Dezactivat'} ({len(jellyfin_servers)} servere)",
            inline=True,
        )
        embed.add_field(name="Personalitate", value=conf["personality"][:1024], inline=False)
        await ctx.send(embed=embed)
