from redbot.core import commands, Config
import asyncio
import aiohttp
import discord
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

class JellyfinNewContent(commands.Cog):
    """Announces new movies and TV shows added to multiple Jellyfin servers"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=273845109,
            force_registration=True
        )
        
        default_guild = {
            "servers": [],
            "check_interval": 6,
            "enable_translation": True,
        }
        
        self.config.register_guild(**default_guild)
        self.bg_task = None
        self._session: aiohttp.ClientSession = None  # FIX #4: sesiune reutilizabilă
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.poster_base_url = "https://image.tmdb.org/t/p/w500"
        self.MAX_ANNOUNCEMENTS_PER_RUN = 20  # FIX #8: limită anti-spam

    # FIX #10: folosim on_ready în loc de start_tasks() în __init__
    @commands.Cog.listener()
    async def on_ready(self):
        if self.bg_task is None or self.bg_task.done():
            self.bg_task = self.bot.loop.create_task(self.check_new_content_loop())

    async def _get_session(self) -> aiohttp.ClientSession:
        """FIX #4: returnează sesiunea existentă sau creează una nouă"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def cog_unload(self):
        if self.bg_task:
            self.bg_task.cancel()
        # Închide sesiunea aiohttp la unload
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    async def check_new_content_loop(self):
        """Background loop to check for new content"""
        await self.bot.wait_until_ready()
        while True:
            min_interval = 6  # default
            try:
                all_guilds = await self.config.all_guilds()
                
                # FIX #1: calculăm intervalul în același try block
                for guild_id, settings in all_guilds.items():
                    if 'check_interval' in settings and settings['check_interval'] > 0:
                        min_interval = min(min_interval, settings['check_interval'])

                for guild_id, settings in all_guilds.items():
                    guild = self.bot.get_guild(guild_id)
                    if guild and settings.get('servers'):
                        for server in settings['servers']:
                            if self._is_server_configured(server):
                                await self.check_and_announce_new_content(guild, server, settings)
            except Exception as e:
                print(f"Error in check_new_content_loop: {e}")
            finally:
                # FIX #1: sleep-ul se execută întotdeauna, indiferent de erori
                await asyncio.sleep(min_interval * 3600)

    def _is_server_configured(self, server):
        """Check if a server has all required settings"""
        return all(k in server and server[k] for k in ['name', 'base_url', 'api_key', 'announcement_channel_id'])

    async def check_and_announce_new_content(self, guild, server, guild_settings):
        """Check for new content and announce it for a specific server"""
        channel = guild.get_channel(server['announcement_channel_id'])
        if not channel:
            return
            
        last_check = server.get('last_check')
        # FIX #7: folosim datetime cu timezone în loc de utcnow() deprecated
        now = datetime.now(timezone.utc).timestamp()
        
        if not last_check or not server.get('initialized', False):
            server['last_check'] = now
            server['initialized'] = True
            await self._update_server_in_config(guild, server)
            return
            
        new_items = await self.get_new_content(
            server['base_url'], 
            server['api_key'], 
            last_check
        )
        
        server['last_check'] = now
        await self._update_server_in_config(guild, server)
        
        if not new_items:
            return

        # FIX #8: limităm numărul de anunțuri per run pentru a evita spam-ul
        if len(new_items) > self.MAX_ANNOUNCEMENTS_PER_RUN:
            print(f"[JellyfinNewContent] {server['name']}: {len(new_items)} iteme găsite, limitat la {self.MAX_ANNOUNCEMENTS_PER_RUN}.")
            new_items = new_items[:self.MAX_ANNOUNCEMENTS_PER_RUN]
            
        for item in new_items:
            try:
                await self.announce_item(channel, item, server, guild_settings)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Error announcing item: {e}")

    async def _update_server_in_config(self, guild, updated_server):
        """Update a specific server in the config"""
        servers = await self.config.guild(guild).servers()
        for i, server in enumerate(servers):
            if server.get('name') == updated_server.get('name'):
                servers[i] = updated_server
                break
        await self.config.guild(guild).servers.set(servers)

    async def get_new_content(self, base_url, api_key, last_check):
        """Get new movies and TV shows added since last check"""
        # FIX #2: folosim parametrul corect pentru Jellyfin API
        # MinDateLastSavedForUser nu există global; folosim StartIndex + filtrare manuală
        # Parametrul corect este MinDateLastSaved (pentru conținut adăugat recent)
        search_url = (
            f"{base_url}/Items?"
            f"IncludeItemTypes=Movie,Series&"
            f"SortBy=DateCreated,SortName&SortOrder=Descending&"
            f"Recursive=true&"
            f"api_key={api_key}"
        )
        
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                session = await self._get_session()  # FIX #4: sesiune reutilizabilă
                async with session.get(search_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = data.get('Items', [])
                        
                        # Filtrare precisă după timestamp
                        filtered_items = []
                        for item in items:
                            date_created = item.get('DateCreated')
                            if date_created:
                                try:
                                    item_date = datetime.fromisoformat(date_created.replace('Z', '+00:00'))
                                    item_timestamp = item_date.timestamp()
                                    if item_timestamp > last_check:
                                        filtered_items.append(item)
                                    else:
                                        # FIX #2: itemele sunt sortate descrescător după dată,
                                        # deci putem opri când găsim primul item mai vechi
                                        break
                                except (ValueError, TypeError) as e:
                                    print(f"Error parsing date for item '{item.get('Name')}': {e}")
                                    # Nu includem itemele cu dată invalidă pentru a evita duplicate
                            
                        return filtered_items
                    else:
                        print(f"Jellyfin API error: Status {response.status}")
            except Exception as e:
                print(f"Error fetching new content on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        return []

    async def translate_text(self, text, target_lang="ro"):
        """Translate text using Google Translate via deep-translator"""
        if not text or text == 'No description available.':
            return text
        
        # FIX #5: nu traducem dacă textul pare deja în română
        # (detecție simplă după caractere specifice)
        romanian_chars = set('ăâîșțĂÂÎȘȚ')
        if any(c in romanian_chars for c in text):
            return text
        
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                loop = asyncio.get_event_loop()
                translator = GoogleTranslator(source='auto', target=target_lang)
                translated = await loop.run_in_executor(None, translator.translate, text)
                return translated
            except Exception as e:
                print(f"Error translating text on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        return text

    async def search_tmdb(self, title, year, is_movie, tmdb_api_key):
        """Search TMDb for additional media info"""
        if not tmdb_api_key:
            return None
            
        media_type = "movie" if is_movie else "tv"
        search_url = f"{self.tmdb_base_url}/search/{media_type}?api_key={tmdb_api_key}&query={title}&year={year}"
        
        timeout = aiohttp.ClientTimeout(total=30)
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                session = await self._get_session()  # FIX #4: sesiune reutilizabilă
                async with session.get(search_url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get('results', [])
                        if results:
                            tmdb_data = results[0]
                            tmdb_id = tmdb_data.get('id')
                            
                            if tmdb_id:
                                details_url = f"{self.tmdb_base_url}/{media_type}/{tmdb_id}?api_key={tmdb_api_key}"
                                async with session.get(details_url, timeout=timeout) as details_response:
                                    if details_response.status == 200:
                                        details = await details_response.json()
                                        return {
                                            'poster_path': details.get('poster_path'),
                                            'overview': details.get('overview'),
                                            'tmdb_id': tmdb_id
                                        }
                            
                            return {
                                'poster_path': tmdb_data.get('poster_path'),
                                'overview': tmdb_data.get('overview'),
                                'tmdb_id': tmdb_id
                            }
                    elif response.status == 429:
                        await asyncio.sleep(retry_delay * (attempt + 2))
                        continue
                    else:
                        print(f"TMDb API error: Status {response.status}")
            except Exception as e:
                print(f"Error searching TMDb on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        return None

    async def announce_item(self, channel, item, server, guild_settings):
        """Create and send an announcement for a new item"""
        title = item.get('Name', 'Unknown Title')
        year = item.get('ProductionYear', 'Unknown Year')
        is_movie = item.get('Type') == "Movie"
        media_type = "Film" if is_movie else "Serial"
        
        overview = item.get('Overview', 'No description available.')
        
        tmdb_data = None
        if server.get('tmdb_api_key'):
            tmdb_data = await self.search_tmdb(title, year, is_movie, server['tmdb_api_key'])
        
        if tmdb_data and tmdb_data.get('overview'):
            overview = tmdb_data['overview']
        
        enable_translation = guild_settings.get('enable_translation', True)
        if enable_translation and overview and overview != 'No description available.':
            overview = await self.translate_text(overview, target_lang="ro")
        
        if len(overview) > 1000:
            overview = overview[:997] + "..."

        embed = discord.Embed(
            title=f"{title} ({year})",
            description=overview,
            color=discord.Color.green()
        )
        
        if tmdb_data and tmdb_data.get('poster_path'):
            poster_url = f"{self.poster_base_url}{tmdb_data['poster_path']}"
            embed.set_thumbnail(url=poster_url)
        
        embed.add_field(name="Tip", value=media_type, inline=True)
        
        if genres := item.get('Genres', [])[:3]:
            embed.add_field(name="Genuri", value=", ".join(genres), inline=True)
        
        if community_rating := item.get('CommunityRating'):
            embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

        item_id = item.get('Id')
        if item_id:
            web_url = f"{server['base_url']}/web/index.html#!/details?id={item_id}"
            server_name = server.get('name', 'Server')
            embed.add_field(name="Vizionare Online:", value=f"[{server_name}]({web_url})", inline=False)
            
        added_date = item.get('DateCreated')
        if added_date:
            # FIX #9: try/except cu log în loc de except gol
            try:
                # Formatăm data mai frumos
                parsed_date = datetime.fromisoformat(added_date.replace('Z', '+00:00'))
                formatted_date = parsed_date.strftime("%d.%m.%Y %H:%M")
                embed.set_footer(text=f"Adăugat: {formatted_date}")
            except Exception as e:
                print(f"Error formatting date '{added_date}': {e}")
        
        server_name = server.get('name', 'Server')
        await channel.send(f"**{media_type} nou adăugat pe {server_name}:**", embed=embed)

    # -------------------------------------------------------------------------
    # COMENZI
    # -------------------------------------------------------------------------

    @commands.group(name="newcontent")
    async def newcontent(self, ctx):
        """Commands to manage Jellyfin new content announcements"""
        if ctx.invoked_subcommand is None:
            help_text = (
                "**Comenzi pentru configurarea anunțurilor de conținut nou:**\n\n"
                "**Gestionare servere:**\n"
                f"`{ctx.prefix}newcontent addserver <NUME>` - Adaugă un server Jellyfin nou\n"
                f"`{ctx.prefix}newcontent removeserver <NUME>` - Șterge un server\n"
                f"`{ctx.prefix}newcontent listservers` - Listează toate serverele\n"
                f"`{ctx.prefix}newcontent serverinfo <NUME>` - Arată detalii despre un server\n\n"
                "**Configurare server:**\n"
                f"`{ctx.prefix}newcontent seturl <NUME> <URL>` - Setează URL-ul serverului\n"
                f"`{ctx.prefix}newcontent setapi <NUME> <API_KEY>` - Setează cheia API Jellyfin\n"
                f"`{ctx.prefix}newcontent settmdb <NUME> <API_KEY>` - Setează cheia API TMDb\n"
                f"`{ctx.prefix}newcontent setchannel <NUME> <#CANAL>` - Setează canalul pentru anunțuri\n\n"
                "**Configurare traducere:**\n"
                f"`{ctx.prefix}newcontent toggletranslation` - Activează/dezactivează traducerea automată\n\n"
                "**Configurare globală:**\n"
                f"`{ctx.prefix}newcontent setinterval <ORE>` - Setează intervalul de verificare\n"
                f"`{ctx.prefix}newcontent settings` - Arată setările globale\n\n"
                "**Utilitare:**\n"
                f"`{ctx.prefix}newcontent check <NUME>` - Verifică manual conținut nou pe un server\n"
                f"`{ctx.prefix}newcontent reset <NUME>` - Resetează timestamp-ul de verificare\n"
                f"`{ctx.prefix}newcontent forceinit <NUME>` - Forțează inițializarea fără anunțuri"
            )
            await ctx.send(help_text)

    @newcontent.command(name="addserver")
    @commands.admin_or_permissions(administrator=True)
    async def add_server(self, ctx, name: str):
        """Add a new Jellyfin server"""
        servers = await self.config.guild(ctx.guild).servers()
        
        if any(s.get('name') == name for s in servers):
            return await ctx.send(f"❌ Un server cu numele `{name}` există deja!")
        
        new_server = {
            'name': name,
            'base_url': None,
            'api_key': None,
            'tmdb_api_key': None,
            'announcement_channel_id': None,
            'last_check': None,
            'initialized': False
        }
        
        servers.append(new_server)
        await self.config.guild(ctx.guild).servers.set(servers)
        await ctx.send(f"✅ Serverul `{name}` a fost adăugat! Acum configurează-l folosind comenzile `seturl`, `setapi`, `settmdb`, și `setchannel`.")

    @newcontent.command(name="removeserver")
    @commands.admin_or_permissions(administrator=True)
    async def remove_server(self, ctx, name: str):
        """Remove a Jellyfin server"""
        servers = await self.config.guild(ctx.guild).servers()
        updated_servers = [s for s in servers if s.get('name') != name]
        
        if len(updated_servers) == len(servers):
            return await ctx.send(f"❌ Nu există niciun server cu numele `{name}`!")
        
        await self.config.guild(ctx.guild).servers.set(updated_servers)
        await ctx.send(f"✅ Serverul `{name}` a fost șters.")

    @newcontent.command(name="listservers")
    @commands.admin_or_permissions(administrator=True)
    async def list_servers(self, ctx):
        """List all configured Jellyfin servers"""
        servers = await self.config.guild(ctx.guild).servers()
        
        if not servers:
            return await ctx.send("📝 Nu există servere configurate. Folosește `addserver` pentru a adăuga unul.")
        
        embed = discord.Embed(
            title="🎬 Servere Jellyfin Configurate",
            color=discord.Color.blue()
        )
        
        for server in servers:
            channel = ctx.guild.get_channel(server.get('announcement_channel_id'))
            status = "✅ Configurat complet" if self._is_server_configured(server) else "⚠️ Configurare incompletă"
            
            value = (
                f"**Status:** {status}\n"
                f"**Canal:** {channel.mention if channel else 'Nesetat'}\n"
                f"**Inițializat:** {'Da' if server.get('initialized') else 'Nu'}"
            )
            
            embed.add_field(
                name=f"📺 {server['name']}",
                value=value,
                inline=False
            )
        
        await ctx.send(embed=embed)

    @newcontent.command(name="serverinfo")
    @commands.admin_or_permissions(administrator=True)
    async def server_info(self, ctx, name: str):
        """Show detailed information about a server"""
        servers = await self.config.guild(ctx.guild).servers()
        server = next((s for s in servers if s.get('name') == name), None)
        
        if not server:
            return await ctx.send(f"❌ Nu există niciun server cu numele `{name}`!")
        
        channel = ctx.guild.get_channel(server.get('announcement_channel_id'))
        
        last_check_str = "Niciodată"
        if server.get('last_check'):
            try:
                last_check_time = datetime.fromtimestamp(server['last_check'])
                last_check_str = last_check_time.strftime("%d.%m.%Y %H:%M:%S")
            except Exception as e:
                print(f"Error converting timestamp: {e}")
                last_check_str = "Eroare la conversie"
        
        embed = discord.Embed(
            title=f"📺 Informații Server: {name}",
            color=discord.Color.green()
        )
        embed.add_field(name="URL Server", value=server.get('base_url') or "Nesetat", inline=False)
        embed.add_field(name="API Key Jellyfin", value="Setat ✓" if server.get('api_key') else "Nesetat ✗", inline=True)
        embed.add_field(name="API Key TMDb", value="Setat ✓" if server.get('tmdb_api_key') else "Nesetat ✗", inline=True)
        embed.add_field(name="Canal Anunțuri", value=channel.mention if channel else "Nesetat", inline=False)
        embed.add_field(name="Ultima Verificare", value=last_check_str, inline=True)
        embed.add_field(name="Inițializat", value="Da ✓" if server.get('initialized') else "Nu ✗", inline=True)
        
        await ctx.send(embed=embed)

    @newcontent.command(name="seturl")
    @commands.admin_or_permissions(administrator=True)
    async def set_url(self, ctx, name: str, url: str):
        """Set the Jellyfin server URL"""
        servers = await self.config.guild(ctx.guild).servers()
        server = next((s for s in servers if s.get('name') == name), None)
        
        if not server:
            return await ctx.send(f"❌ Nu există niciun server cu numele `{name}`!")
        
        url = url.rstrip('/')
        server['base_url'] = url
        await self._update_server_in_config(ctx.guild, server)
        await ctx.send(f"✅ URL-ul pentru serverul `{name}` a fost setat la: {url}")

    @newcontent.command(name="setapi")
    @commands.admin_or_permissions(administrator=True)
    async def set_api(self, ctx, name: str, api_key: str):
        """Set the Jellyfin API key"""
        servers = await self.config.guild(ctx.guild).servers()
        server = next((s for s in servers if s.get('name') == name), None)
        
        if not server:
            return await ctx.send(f"❌ Nu există niciun server cu numele `{name}`!")
        
        server['api_key'] = api_key
        await self._update_server_in_config(ctx.guild, server)
        await ctx.send(f"✅ Cheia API Jellyfin pentru serverul `{name}` a fost setată.")
        
        # FIX #6: try/except la ștergerea mesajului
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            print(f"[JellyfinNewContent] Nu am permisiunea să șterg mesajul cu API key.")
        except discord.HTTPException as e:
            print(f"[JellyfinNewContent] Eroare la ștergerea mesajului: {e}")

    @newcontent.command(name="settmdb")
    @commands.admin_or_permissions(administrator=True)
    async def set_tmdb(self, ctx, name: str, api_key: str):
        """Set the TMDb API key for a server"""
        servers = await self.config.guild(ctx.guild).servers()
        server = next((s for s in servers if s.get('name') == name), None)
        
        if not server:
            return await ctx.send(f"❌ Nu există niciun server cu numele `{name}`!")
        
        server['tmdb_api_key'] = api_key
        await self._update_server_in_config(ctx.guild, server)
        await ctx.send(f"✅ Cheia API TMDb pentru serverul `{name}` a fost setată.")
        
        # FIX #6: try/except la ștergerea mesajului
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            print(f"[JellyfinNewContent] Nu am permisiunea să șterg mesajul cu TMDb key.")
        except discord.HTTPException as e:
            print(f"[JellyfinNewContent] Eroare la ștergerea mesajului: {e}")

    @newcontent.command(name="setchannel")
    @commands.admin_or_permissions(administrator=True)
    async def set_channel(self, ctx, name: str, channel: discord.TextChannel):
        """Set the announcement channel for a server"""
        servers = await self.config.guild(ctx.guild).servers()
        server = next((s for s in servers if s.get('name') == name), None)
        
        if not server:
            return await ctx.send(f"❌ Nu există niciun server cu numele `{name}`!")
        
        server['announcement_channel_id'] = channel.id
        await self._update_server_in_config(ctx.guild, server)
        await ctx.send(f"✅ Canalul pentru anunțuri pe serverul `{name}` a fost setat la: {channel.mention}")

    @newcontent.command(name="toggletranslation")
    @commands.admin_or_permissions(administrator=True)
    async def toggle_translation(self, ctx):
        """Toggle automatic translation on/off"""
        current = await self.config.guild(ctx.guild).enable_translation()
        new_value = not current
        await self.config.guild(ctx.guild).enable_translation.set(new_value)
        status = "activată" if new_value else "dezactivată"
        await ctx.send(f"✅ Traducerea automată a fost {status}.")

    @newcontent.command(name="setinterval")
    @commands.admin_or_permissions(administrator=True)
    async def set_interval(self, ctx, hours: int):
        """Set how often to check for new content (in hours)"""
        if hours < 1:
            return await ctx.send("❌ Intervalul trebuie să fie de cel puțin 1 oră.")
        await self.config.guild(ctx.guild).check_interval.set(hours)
        await ctx.send(f"✅ Intervalul de verificare a fost setat la {hours} ore.")

    @newcontent.command(name="settings")
    @commands.admin_or_permissions(administrator=True)
    async def show_settings(self, ctx):
        """Show current global settings"""
        settings = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(title="⚙️ Setări Globale", color=discord.Color.blue())
        embed.add_field(name="Interval Verificare", value=f"{settings.get('check_interval', 6)} ore", inline=True)
        embed.add_field(
            name="Traducere Automată",
            value="Activată ✓" if settings.get('enable_translation', True) else "Dezactivată ✗",
            inline=True
        )
        embed.add_field(name="Număr Servere", value=str(len(settings.get('servers', []))), inline=True)
        embed.add_field(name="Limită Anunțuri/Run", value=str(self.MAX_ANNOUNCEMENTS_PER_RUN), inline=True)
        
        await ctx.send(embed=embed)

    @newcontent.command(name="check")
    @commands.admin_or_permissions(administrator=True)
    async def manual_check(self, ctx, name: str):
        """Manually check for new content on a specific server"""
        servers = await self.config.guild(ctx.guild).servers()
        server = next((s for s in servers if s.get('name') == name), None)
        
        if not server:
            return await ctx.send(f"❌ Nu există niciun server cu numele `{name}`!")
        
        if not self._is_server_configured(server):
            return await ctx.send(f"⚠️ Serverul `{name}` nu este configurat complet. Verifică cu `serverinfo {name}`.")
        
        guild_settings = await self.config.guild(ctx.guild).all()
        await ctx.send(f"🔍 Verificare pentru conținut nou pe `{name}` în desfășurare...")
        try:
            await self.check_and_announce_new_content(ctx.guild, server, guild_settings)
            await ctx.send("✅ Verificare completă.")
        except Exception as e:
            await ctx.send(f"❌ Eroare în timpul verificării: {e}")

    @newcontent.command(name="reset")
    @commands.admin_or_permissions(administrator=True)
    async def reset_timestamp(self, ctx, name: str):
        """Reset the last check timestamp for a server"""
        servers = await self.config.guild(ctx.guild).servers()
        server = next((s for s in servers if s.get('name') == name), None)
        
        if not server:
            return await ctx.send(f"❌ Nu există niciun server cu numele `{name}`!")
        
        server['last_check'] = None
        server['initialized'] = False
        await self._update_server_in_config(ctx.guild, server)
        await ctx.send(f"✅ Timestamp-ul pentru serverul `{name}` a fost resetat.")

    @newcontent.command(name="forceinit")
    @commands.admin_or_permissions(administrator=True)
    async def force_init(self, ctx, name: str):
        """Force initialization for a server without announcing existing content"""
        servers = await self.config.guild(ctx.guild).servers()
        server = next((s for s in servers if s.get('name') == name), None)
        
        if not server:
            return await ctx.send(f"❌ Nu există niciun server cu numele `{name}`!")
        
        # FIX #7: folosim datetime cu timezone
        now = datetime.now(timezone.utc).timestamp()
        server['last_check'] = now
        server['initialized'] = True
        await self._update_server_in_config(ctx.guild, server)
        await ctx.send(f"✅ Serverul `{name}` a fost inițializat fără a anunța conținutul existent.")
