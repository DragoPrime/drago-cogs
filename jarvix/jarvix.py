import asyncio
import copy
import json
import re
import time
import unicodedata
from typing import Dict, List, Optional

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

# Comenzi pe care Jarvix nu le va rula NICIODATA implicit (proprietarul botului poate modifica lista
# cu `[p]jarvix blocate ...`). Se blocheaza numele exact SI toate subcomenzile (ex: "set token").
DEFAULT_BLOCKED = [
    "eval", "debug", "repl", "mock", "mockmsg", "bypasscooldowns",
    "load", "unload", "reload", "unloadall",
    "shutdown", "restart", "leave",
    "set token", "set api", "set owner", "set ownernotifications",
    "repo", "cog", "bankset reset",
]

KEYWORD_SYSTEM = (
    "You convert a user's request (usually written in Romanian) into search keywords used to find "
    "a Discord bot command. Return JSON: {\"keywords\": [...]} with 3 to 8 lowercase ENGLISH words "
    "describing the action and the object (examples: rename, channel, name, ban, member, role, "
    "delete, message, create, mute, announce, prefix). No explanations."
)
KEYWORD_SCHEMA = {
    "type": "object",
    "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
    "required": ["keywords"],
}

SELECT_SYSTEM = (
    "You are Jarvix. You map a user's request to exactly ONE Discord bot command taken from the list "
    "you are given.\n"
    "Rules:\n"
    "- Choose ONLY a command from the list and copy its name exactly as written.\n"
    "- `arguments` is exactly what the user would type after the command name: no prefix, and do not "
    "repeat the command name. Copy Discord mentions such as <#123>, <@123> or <@&123> verbatim from the "
    "request. Never invent IDs. 'This channel' means the current channel mention you are given.\n"
    "- Put multi-word values in double quotes ONLY if the usage shows a single-word parameter; if the "
    "usage ends with '...' (takes the rest of the text) do NOT use quotes.\n"
    "- If no command fits, or required information is missing, set `command` to null and explain in "
    "Romanian in `reason`.\n"
    "- `reason`: one short sentence in Romanian saying what the command will do.\n"
    "Return only JSON: {\"command\": string|null, \"arguments\": string, \"reason\": string}."
)
SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {"type": ["string", "null"]},
        "arguments": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["command", "arguments", "reason"],
}


class JarvixError(Exception):
    """Eroare cu mesaj sigur de afisat utilizatorului."""


# ---------------------------------------------------------------------- #
#  Functii ajutatoare (pure, usor de testat)
# ---------------------------------------------------------------------- #

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _tokens(text: str) -> List[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", _norm(text)) if len(t) > 1]


def _strip_mentions(text: str) -> str:
    """Inlocuieste mentiunile Discord cu cuvinte neutre, pentru cautarea de cuvinte-cheie."""
    text = re.sub(r"<#\d+>", " channel ", text)
    text = re.sub(r"<@&\d+>", " role ", text)
    text = re.sub(r"<@!?\d+>", " user ", text)
    return " ".join(text.split())


def _parse_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    try:
        data = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise JarvixError("Modelul nu a returnat un răspuns JSON valid.")
        try:
            data = json.loads(match.group(0))
        except ValueError:
            raise JarvixError("Modelul nu a returnat un răspuns JSON valid.")
    if not isinstance(data, dict):
        raise JarvixError("Modelul nu a returnat un răspuns JSON valid.")
    return data


def _is_blocked(name: str, blocked: List[str]) -> bool:
    n = name.lower().strip()
    return any(n == b or n.startswith(b + " ") for b in blocked)


def _score_entry(entry: dict, primary: set, secondary: set) -> float:
    score = 0.0
    for weight, tokens in ((1.0, primary), (0.35, secondary)):
        for k in tokens:
            if k in entry["name_tokens"]:
                score += 5 * weight
            elif len(k) >= 4 and any(len(t) >= 4 and (k in t or t in k) for t in entry["name_tokens"]):
                score += 2.5 * weight
            if k in entry["help_tokens"]:
                score += 1 * weight
            if k in entry["cog_tokens"]:
                score += 1.5 * weight
    return score


def _trunc(text: str, n: int) -> str:
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


class Plan:
    """Rezultatul planificarii unei cereri (fara executie)."""

    def __init__(self):
        self.keywords: List[str] = []
        self.candidates: List[dict] = []
        self.result: Optional[dict] = None
        self.entry: Optional[dict] = None
        self.args: str = ""
        self.command_text: str = ""
        self.reason: str = ""
        self.ctx = None
        self.error: Optional[str] = None


class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Doar cel care a făcut cererea o poate confirma.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Execută", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Anulează", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.defer()
        self.stop()


class Jarvix(commands.Cog):
    """Controlează botul în limba naturală: un AI local (Ollama) alege comanda Red potrivită."""

    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x4A415256, force_registration=True)
        self.config.register_global(
            ollama_url="http://localhost:11434",
            model="qwen3:8b",
            thinking_mode=False,
            timeout=90,
            blocked=list(DEFAULT_BLOCKED),
        )
        self.config.register_guild(
            enabled=True,
            require_confirmation=True,
            allowed_channels=[],
            log_channel=None,
            user_cooldown=10,
            shortlist_size=15,
        )
        self.session: Optional[aiohttp.ClientSession] = None
        self._catalog_cache = (0.0, [])
        self._cooldowns: Dict[tuple, float] = {}

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ------------------------------------------------------------------ #
    #  Ollama
    # ------------------------------------------------------------------ #

    async def _ollama_chat(self, messages: list, schema: Optional[dict] = None) -> str:
        conf = await self.config.all()
        url = conf["ollama_url"].rstrip("/")
        payload = {
            "model": conf["model"],
            "messages": messages,
            "stream": False,
            "think": conf["thinking_mode"],
            "options": {"temperature": 0.1},
        }
        if schema is not None:
            payload["format"] = schema
        timeout = aiohttp.ClientTimeout(total=conf["timeout"])
        try:
            async with self.session.post(f"{url}/api/chat", json=payload, timeout=timeout) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise JarvixError(f"Ollama a răspuns cu status {resp.status}: {_trunc(text, 200)}")
                data = await resp.json(content_type=None)
        except asyncio.TimeoutError:
            raise JarvixError("Ollama nu a răspuns în timp util (timeout).")
        except aiohttp.ClientConnectorError:
            raise JarvixError("Nu mă pot conecta la Ollama. Verifică adresa și dacă serviciul rulează.")
        except aiohttp.ClientError as e:
            raise JarvixError(f"Eroare de rețea către Ollama: {e}")
        return ((data.get("message") or {}).get("content") or "").strip()

    # ------------------------------------------------------------------ #
    #  Catalogul de comenzi (construit automat din ce e incarcat in Red)
    # ------------------------------------------------------------------ #

    def _build_catalog(self) -> List[dict]:
        entries = []
        for cmd in self.bot.walk_commands():
            try:
                if cmd.hidden or not cmd.enabled:
                    continue
                if cmd.cog is self:
                    continue  # Jarvix nu isi poate rula propriile comenzi
                if isinstance(cmd, commands.Group) and not cmd.invoke_without_command:
                    continue  # grupurile care doar afiseaza help nu sunt utile
                name = cmd.qualified_name
                try:
                    help_full = cmd.help or ""
                except Exception:
                    help_full = ""
                cog_name = cmd.cog_name or ""
                entries.append(
                    {
                        "name": name,
                        "command": cmd,
                        "signature": cmd.signature or "",
                        "name_tokens": set(_tokens(name)),
                        "help_tokens": set(_tokens(help_full[:500])),
                        "cog_tokens": set(_tokens(cog_name)),
                    }
                )
            except Exception:
                continue
        return entries

    async def _get_catalog(self) -> List[dict]:
        ts, entries = self._catalog_cache
        if time.monotonic() - ts > 30 or not entries:
            entries = self._build_catalog()
            self._catalog_cache = (time.monotonic(), entries)
        return entries

    async def _can_run(self, ctx, cmd) -> bool:
        try:
            return bool(await cmd.can_run(ctx, check_all_parents=True))
        except Exception:
            return False

    async def _get_prefix(self, guild: discord.Guild) -> str:
        prefixes = await self.bot.get_valid_prefixes(guild)
        for p in prefixes:
            if not p.startswith("<@"):
                return p
        return prefixes[0]

    # ------------------------------------------------------------------ #
    #  Planificarea unei cereri (fara executie)
    # ------------------------------------------------------------------ #

    async def _plan(self, message: discord.Message, request: str, gconf: dict) -> Plan:
        plan = Plan()
        try:
            await self._plan_inner(plan, message, request, gconf)
        except JarvixError as e:
            plan.error = str(e)
        return plan

    async def _plan_inner(self, plan: Plan, message: discord.Message, request: str, gconf: dict):
        prefix = await self._get_prefix(message.guild)
        base_ctx = await self.bot.get_context(message)
        blocked = [b.lower() for b in await self.config.blocked()]
        entries = [e for e in await self._get_catalog() if not _is_blocked(e["name"], blocked)]
        simple = _strip_mentions(request)

        # Pasul 1: cuvinte-cheie in engleza (comenzile sunt in engleza, cererea e in romana)
        raw = await self._ollama_chat(
            [{"role": "system", "content": KEYWORD_SYSTEM}, {"role": "user", "content": simple}],
            KEYWORD_SCHEMA,
        )
        data = _parse_json(raw)
        keywords = [str(k) for k in (data.get("keywords") or []) if isinstance(k, str)]
        plan.keywords = keywords[:10]
        primary = set(_tokens(" ".join(plan.keywords)))
        secondary = set(_tokens(simple)) - primary
        if not primary and not secondary:
            plan.error = "Nu am înțeles ce comandă ai nevoie."
            return

        # Scurtlista: cele mai probabile comenzi, doar dintre cele pe care autorul are voie sa le ruleze
        scored = sorted(((_score_entry(e, primary, secondary), e) for e in entries), key=lambda x: -x[0])
        scored = [(s, e) for s, e in scored if s > 0]
        size = gconf["shortlist_size"]
        runnable = []
        for _, entry in scored[: size * 3]:
            if await self._can_run(base_ctx, entry["command"]):
                runnable.append(entry)
                if len(runnable) >= size:
                    break
        plan.candidates = runnable
        if not runnable:
            plan.error = "Nu am găsit nicio comandă potrivită pe care să ai voie să o rulezi."
            return

        # Pasul 2: modelul alege o comanda din scurtlista si scrie argumentele
        lines = []
        for e in runnable:
            try:
                short = e["command"].format_shortdoc_for_context(base_ctx)
            except Exception:
                short = ""
            short = _trunc(" ".join((short or "").split()), 140)
            line = f"- {e['name']}"
            if e["signature"]:
                line += f" {e['signature']}"
            if short:
                line += f" :: {short}"
            lines.append(line)
        user_content = (
            f"Current channel: <#{message.channel.id}>\n"
            f"Requester: <@{message.author.id}>\n\n"
            "Available commands:\n" + "\n".join(lines) + f"\n\nRequest: {request}"
        )
        raw = await self._ollama_chat(
            [{"role": "system", "content": SELECT_SYSTEM}, {"role": "user", "content": user_content}],
            SELECT_SCHEMA,
        )
        result = _parse_json(raw)
        plan.result = result
        reason = str(result.get("reason") or "").strip()
        chosen = result.get("command")
        if not chosen or not isinstance(chosen, str):
            plan.error = reason or "Nu am găsit o comandă potrivită pentru cererea ta."
            return

        name = " ".join(chosen.split())
        if prefix and name.startswith(prefix):
            name = name[len(prefix):].strip()
        entry = {e["name"].lower(): e for e in runnable}.get(name.lower())
        if entry is None:
            plan.error = "Modelul a ales o comandă care nu e în listă. Nu execut nimic."
            return

        args = " ".join(str(result.get("arguments") or "").split())
        low = args.lower()
        if low == entry["name"].lower():
            args = ""
        elif low.startswith(entry["name"].lower() + " "):
            args = args[len(entry["name"]) + 1:]
        args = args[:1500]

        # Verificare finala: construim mesajul real si cerem Red sa-l interpreteze.
        # Daca argumentele ar "scapa" spre alta comanda/subcomanda, respingem.
        command_text = f"{entry['name']} {args}".strip()
        new_msg = copy.copy(message)
        new_msg.content = f"{prefix}{command_text}"
        ctx = await self.bot.get_context(new_msg)
        if not ctx.valid or ctx.command is None or ctx.command.qualified_name.lower() != entry["name"].lower():
            plan.error = "Nu am putut construi o comandă validă din cererea ta."
            return
        if _is_blocked(ctx.command.qualified_name, blocked) or ctx.command.cog is self:
            plan.error = "Această comandă este blocată pentru Jarvix."
            return
        try:
            allowed = await ctx.command.can_run(ctx, check_all_parents=True)
        except Exception:
            allowed = False
        if not allowed:
            plan.error = "Nu ai permisiunea să rulezi această comandă."
            return

        plan.entry = entry
        plan.args = args
        plan.command_text = f"{prefix}{command_text}"
        plan.reason = reason or "Am găsit comanda potrivită."
        plan.ctx = ctx

    # ------------------------------------------------------------------ #
    #  Ascultarea mesajelor: "@Bot <cerere>"
    # ------------------------------------------------------------------ #

    async def _reply(self, message: discord.Message, content: str, **kwargs):
        content = _trunc(content, 1900)
        none = discord.AllowedMentions.none()
        try:
            return await message.reply(content, mention_author=False, allowed_mentions=none, **kwargs)
        except discord.HTTPException:
            try:
                return await message.channel.send(content, allowed_mentions=none, **kwargs)
            except discord.HTTPException:
                return None

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.guild is None or self.bot.user is None:
            return
        match = re.match(rf"^<@!?{self.bot.user.id}>\s*(.+)$", message.content or "", re.S)
        if not match:
            return
        request = match.group(1).strip()[:600]
        if not request:
            return
        if not await self.bot.message_eligible_as_command(message):
            return

        gconf = await self.config.guild(message.guild).all()
        if not gconf["enabled"]:
            return
        if gconf["allowed_channels"] and message.channel.id not in gconf["allowed_channels"]:
            return

        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        if now - self._cooldowns.get(key, 0) < gconf["user_cooldown"]:
            try:
                await message.add_reaction("⏳")
            except discord.HTTPException:
                pass
            return
        self._cooldowns[key] = now

        await self._run_request(message, request, gconf)

    async def _run_request(self, message: discord.Message, request: str, gconf: dict):
        async with message.channel.typing():
            plan = await self._plan(message, request, gconf)
        if plan.error:
            await self._reply(message, plan.error)
            return

        shown = _trunc(plan.command_text.replace("`", "'"), 1500)
        if gconf["require_confirmation"]:
            view = ConfirmView(message.author.id)
            prompt = await self._reply(message, f"{plan.reason}\n\nVrei să rulez: `{shown}` ?", view=view)
            if prompt is None:
                return
            await view.wait()
            if view.value is not True:
                text = "Anulat. Nu am rulat nimic." if view.value is False else "Timp expirat. Nu am rulat nimic."
                try:
                    await prompt.edit(content=text, view=None)
                except discord.HTTPException:
                    pass
                return
            try:
                await prompt.edit(content=f"Rulez: `{shown}`", view=None)
            except discord.HTTPException:
                pass

        # Reverificam lista de comenzi blocate (s-ar fi putut schimba intre timp)
        blocked = [b.lower() for b in await self.config.blocked()]
        if _is_blocked(plan.ctx.command.qualified_name, blocked):
            await self._reply(message, "Această comandă a fost blocată între timp. Nu execut nimic.")
            return

        await self.bot.invoke(plan.ctx)  # se aplica toate verificarile normale Red (permisiuni etc.)
        failed = bool(getattr(plan.ctx, "command_failed", False))
        try:
            await message.add_reaction("❌" if failed else "✅")
        except discord.HTTPException:
            pass
        await self._log(message, gconf, request, plan, failed)

    async def _log(self, message: discord.Message, gconf: dict, request: str, plan: Plan, failed: bool):
        channel_id = gconf.get("log_channel")
        channel = message.guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        embed = discord.Embed(
            title="Jarvix a rulat o comandă" + (" (eșuată)" if failed else ""),
            color=discord.Color.red() if failed else discord.Color.green(),
        )
        embed.add_field(name="Utilizator", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Cerere", value=_trunc(request, 1000), inline=False)
        embed.add_field(name="Comandă", value=f"`{_trunc(plan.command_text.replace('`', chr(39)), 1000)}`", inline=False)
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------ #
    #  Comenzi de configurare
    # ------------------------------------------------------------------ #

    @commands.group(name="jarvix")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def jarvix(self, ctx: commands.Context):
        """Configurează Jarvix (comenzi în limba naturală, cu AI local)."""

    @jarvix.command(name="toggle")
    async def jarvix_toggle(self, ctx: commands.Context):
        """Activează/dezactivează Jarvix pe acest server."""
        current = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not current)
        await ctx.send(f"Jarvix a fost {'activat' if not current else 'dezactivat'}.")

    @jarvix.command(name="confirmare")
    async def jarvix_confirm(self, ctx: commands.Context):
        """Activează/dezactivează confirmarea cu butoane înainte de executare (recomandat: activată)."""
        current = await self.config.guild(ctx.guild).require_confirmation()
        await self.config.guild(ctx.guild).require_confirmation.set(not current)
        if current:
            await ctx.send("Confirmarea a fost **dezactivată**: comenzile vor rula imediat, fără întrebare.")
        else:
            await ctx.send("Confirmarea a fost activată.")

    @jarvix.command(name="cooldown")
    async def jarvix_cooldown(self, ctx: commands.Context, secunde: int):
        """Timpul minim (în secunde) între două cereri ale aceluiași utilizator."""
        if not 0 <= secunde <= 3600:
            await ctx.send("Alege o valoare între 0 și 3600.")
            return
        await self.config.guild(ctx.guild).user_cooldown.set(secunde)
        await ctx.send(f"Cooldown setat la {secunde} secunde.")

    @jarvix.command(name="candidati")
    async def jarvix_candidates(self, ctx: commands.Context, numar: int):
        """Câte comenzi candidate primește modelul la alegere (5-30, implicit 15)."""
        if not 5 <= numar <= 30:
            await ctx.send("Alege o valoare între 5 și 30.")
            return
        await self.config.guild(ctx.guild).shortlist_size.set(numar)
        await ctx.send(f"Numărul de comenzi candidate a fost setat la {numar}.")

    @jarvix.command(name="logcanal")
    async def jarvix_logchannel(self, ctx: commands.Context, canal: discord.TextChannel = None):
        """Canalul unde Jarvix notează ce comenzi a rulat. Fără argument = dezactivează."""
        await self.config.guild(ctx.guild).log_channel.set(canal.id if canal else None)
        await ctx.send(f"Canal de log: {canal.mention}." if canal else "Jurnalul a fost dezactivat.")

    @jarvix.group(name="canale", invoke_without_command=True)
    async def jarvix_channels(self, ctx: commands.Context):
        """Limitează Jarvix la anumite canale (implicit: toate). Fără subcomandă = listează."""
        ids = await self.config.guild(ctx.guild).allowed_channels()
        if not ids:
            await ctx.send("Jarvix răspunde în **toate** canalele.")
            return
        mentions = [f"<#{i}>" for i in ids]
        await ctx.send("Jarvix răspunde doar în: " + ", ".join(mentions), allowed_mentions=discord.AllowedMentions.none())

    @jarvix_channels.command(name="adauga")
    async def jarvix_channels_add(self, ctx: commands.Context, canal: discord.TextChannel):
        """Adaugă un canal în lista celor permise."""
        async with self.config.guild(ctx.guild).allowed_channels() as ids:
            if canal.id not in ids:
                ids.append(canal.id)
        await ctx.send(f"{canal.mention} a fost adăugat.")

    @jarvix_channels.command(name="sterge")
    async def jarvix_channels_remove(self, ctx: commands.Context, canal: discord.TextChannel):
        """Scoate un canal din lista celor permise."""
        async with self.config.guild(ctx.guild).allowed_channels() as ids:
            if canal.id in ids:
                ids.remove(canal.id)
        await ctx.send(f"{canal.mention} a fost scos.")

    @jarvix_channels.command(name="toate")
    async def jarvix_channels_all(self, ctx: commands.Context):
        """Șterge restricția: Jarvix răspunde din nou în toate canalele."""
        await self.config.guild(ctx.guild).allowed_channels.set([])
        await ctx.send("Jarvix răspunde acum în toate canalele.")

    # ---- setari globale (doar proprietarul botului) ---- #

    @jarvix.command(name="url")
    @commands.is_owner()
    async def jarvix_url(self, ctx: commands.Context, url: str):
        """(Owner) Adresa serverului Ollama."""
        await self.config.ollama_url.set(url.rstrip("/"))
        await ctx.send(f"Adresa Ollama: `{url.rstrip('/')}`")

    @jarvix.command(name="model")
    @commands.is_owner()
    async def jarvix_model(self, ctx: commands.Context, model: str):
        """(Owner) Modelul Ollama folosit de Jarvix (ex: qwen3:8b)."""
        await self.config.model.set(model)
        await ctx.send(f"Model: `{model}`")

    @jarvix.command(name="gandire", aliases=["thinking"])
    @commands.is_owner()
    async def jarvix_thinking(self, ctx: commands.Context):
        """(Owner) Activează/dezactivează modul 'thinking' (mai precis, dar mai lent)."""
        current = await self.config.thinking_mode()
        await self.config.thinking_mode.set(not current)
        await ctx.send(f"Modul de gândire a fost {'activat' if not current else 'dezactivat'}.")

    @jarvix.command(name="timeout")
    @commands.is_owner()
    async def jarvix_timeout(self, ctx: commands.Context, secunde: int):
        """(Owner) Timeout-ul (secunde) pentru fiecare cerere către Ollama."""
        if not 10 <= secunde <= 600:
            await ctx.send("Alege o valoare între 10 și 600.")
            return
        await self.config.timeout.set(secunde)
        await ctx.send(f"Timeout setat la {secunde} secunde.")

    @jarvix.group(name="blocate", invoke_without_command=True)
    @commands.is_owner()
    async def jarvix_blocked(self, ctx: commands.Context):
        """(Owner) Comenzile interzise pentru Jarvix. Fără subcomandă = listează."""
        blocked = await self.config.blocked()
        await ctx.send("Comenzi blocate (inclusiv subcomenzile lor):\n" + (", ".join(f"`{b}`" for b in blocked) or "—"))

    @jarvix_blocked.command(name="adauga")
    async def jarvix_blocked_add(self, ctx: commands.Context, *, comanda: str):
        """(Owner) Blochează o comandă (și subcomenzile ei), ex: `ban` sau `set prefix`."""
        name = " ".join(comanda.strip().strip("`").lower().split())
        async with self.config.blocked() as blocked:
            if name and name not in blocked:
                blocked.append(name)
        self._catalog_cache = (0.0, [])
        await ctx.send(f"`{name}` a fost adăugată la comenzile blocate.")

    @jarvix_blocked.command(name="sterge")
    async def jarvix_blocked_remove(self, ctx: commands.Context, *, comanda: str):
        """(Owner) Scoate o comandă din lista blocată. Atenție: o face disponibilă pentru AI!"""
        name = " ".join(comanda.strip().strip("`").lower().split())
        async with self.config.blocked() as blocked:
            if name in blocked:
                blocked.remove(name)
                await ctx.send(f"`{name}` a fost deblocată.")
            else:
                await ctx.send("Comanda nu era în listă.")

    @jarvix_blocked.command(name="reseteaza")
    async def jarvix_blocked_reset(self, ctx: commands.Context):
        """(Owner) Revine la lista implicită de comenzi blocate."""
        await self.config.blocked.set(list(DEFAULT_BLOCKED))
        await ctx.send("Lista de comenzi blocate a revenit la cea implicită.")

    # ---- unelte de diagnostic ---- #

    @jarvix.command(name="test")
    async def jarvix_test(self, ctx: commands.Context, *, cerere: str):
        """Simulează o cerere FĂRĂ să execute nimic și arată cum a decis Jarvix."""
        gconf = await self.config.guild(ctx.guild).all()
        async with ctx.typing():
            plan = await self._plan(ctx.message, cerere.strip()[:600], gconf)

        embed = discord.Embed(
            title="Jarvix — simulare (nu s-a executat nimic)",
            color=discord.Color.red() if plan.error else discord.Color.green(),
        )
        embed.add_field(name="Cuvinte-cheie (EN)", value=", ".join(plan.keywords) or "—", inline=False)
        names = ", ".join(f"`{e['name']}`" for e in plan.candidates) or "—"
        embed.add_field(name=f"Comenzi candidate ({len(plan.candidates)})", value=_trunc(names, 1000), inline=False)
        if plan.result is not None:
            r = plan.result
            embed.add_field(
                name="Alegerea modelului",
                value=_trunc(
                    f"comandă: `{r.get('command')}`\nargumente: `{r.get('arguments')}`\nmotiv: {r.get('reason')}", 1000
                ),
                inline=False,
            )
        if plan.error:
            embed.add_field(name="Rezultat", value=_trunc(plan.error, 1000), inline=False)
        else:
            embed.add_field(
                name="Ar rula",
                value=f"`{_trunc(plan.command_text.replace('`', chr(39)), 900)}`",
                inline=False,
            )
        await ctx.send(embed=embed)

    @jarvix.command(name="comenzi")
    async def jarvix_commands(self, ctx: commands.Context, *, cautare: str = ""):
        """Arată câte comenzi vede Jarvix; opțional, caută după nume (ex: `channel`)."""
        blocked = [b.lower() for b in await self.config.blocked()]
        entries = [e for e in self._build_catalog() if not _is_blocked(e["name"], blocked)]
        text = f"Jarvix vede **{len(entries)}** comenzi disponibile (fără cele blocate)."
        if cautare:
            q = cautare.strip().lower()
            found = [e["name"] for e in entries if q in e["name"].lower()][:30]
            text += "\n" + (", ".join(f"`{n}`" for n in found) if found else "Nicio potrivire în nume.")
        await ctx.send(_trunc(text, 1900))

    @jarvix.command(name="setari", aliases=["settings", "show"])
    async def jarvix_settings(self, ctx: commands.Context):
        """Afișează configurația curentă."""
        g = await self.config.guild(ctx.guild).all()
        c = await self.config.all()
        embed = discord.Embed(title="Configurație Jarvix", color=discord.Color.blurple())
        embed.add_field(name="Activ", value=str(g["enabled"]), inline=True)
        embed.add_field(name="Confirmare", value=str(g["require_confirmation"]), inline=True)
        embed.add_field(name="Cooldown", value=f"{g['user_cooldown']}s", inline=True)
        embed.add_field(name="Candidați", value=str(g["shortlist_size"]), inline=True)
        chans = ", ".join(f"<#{i}>" for i in g["allowed_channels"]) or "toate"
        embed.add_field(name="Canale permise", value=chans, inline=True)
        embed.add_field(name="Canal log", value=f"<#{g['log_channel']}>" if g["log_channel"] else "—", inline=True)
        embed.add_field(name="Ollama", value=f"`{c['ollama_url']}` / `{c['model']}`", inline=False)
        embed.add_field(name="Mod gândire", value=str(c["thinking_mode"]), inline=True)
        embed.add_field(name="Comenzi blocate", value=str(len(c["blocked"])), inline=True)
        await ctx.send(embed=embed)
