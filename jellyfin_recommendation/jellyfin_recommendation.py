from redbot.core import commands, Config
import asyncio
import aiohttp
import random
import discord
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator

class JellyfinRecommendation(commands.Cog):
    """Provide random Jellyfin recommendations every Monday"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=983947321,
            force_registration=True
        )
        
        # Setări implicite pentru anime și porn
        default_guild = {
            "anime": {
                "base_url": None,
                "api_key": None,
                "channel_id": None,
                "tmdb_api_key": None,
                "server_name": "Freia [SERVER 2]"
            },
            "porn": {
                "base_url": None,
                "api_key": None,
                "channel_id": None,
                "tmdb_api_key": None,
                "server_name": "Freia [SERVER 2]"
            }
        }
        
        self.config.register_guild(**default_guild)
        self.bg_task = None
        self.start_tasks()
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.poster_base_url = "https://image.tmdb.org/t/p/w500"

    def start_tasks(self):
        self.bg_task = self.bot.loop.create_task(self.monday_recommendation_loop())
        
    def cog_unload(self):
        if self.bg_task:
            self.bg_task.cancel()

    async def translate_to_romanian(self, text):
        """Traduce textul în română folosind Google Translate"""
        if not text or text == 'Fără descriere disponibilă.':
            return text
        
        try:
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(
                None, 
                lambda: GoogleTranslator(source='auto', target='ro').translate(text)
            )
            return translated
        except Exception as e:
            print(f"Eroare la traducere: {e}")
            return text

    async def monday_recommendation_loop(self):
        """Background loop for Monday recommendations"""
        await self.bot.wait_until_ready()
        while True:
            now = datetime.now()
            if now.weekday() == 0 and now.hour == 18:
                all_guilds = await self.config.all_guilds()
                for guild_id, settings in all_guilds.items():
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        # Trimite recomandare anime dacă este configurat
                        if all(k in settings.get('anime', {}) and settings['anime'][k] for k in ['base_url', 'api_key', 'channel_id']):
                            await self.send_recommendation(guild, 'anime')
                        # Trimite recomandare porn dacă este configurat
                        if all(k in settings.get('porn', {}) and settings['porn'][k] for k in ['base_url', 'api_key', 'channel_id']):
                            await self.send_recommendation(guild, 'porn')
            await asyncio.sleep(3600)

    async def search_tmdb(self, title, year, is_movie, tmdb_api_key):
        """Caută pe TMDb și returnează datele filmului/serialului cu retry și timeout extins"""
        if not tmdb_api_key:
            return None
            
        media_type = "movie" if is_movie else "tv"
        search_url = f"{self.tmdb_base_url}/search/{media_type}?api_key={tmdb_api_key}&query={title}&year={year}"
        
        timeout = aiohttp.ClientTimeout(total=30)
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(search_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            results = data.get('results', [])
                            if results:
                                tmdb_data = results[0]
                                tmdb_id = tmdb_data.get('id')
                                
                                if tmdb_id:
                                    details_url = f"{self.tmdb_base_url}/{media_type}/{tmdb_id}?api_key={tmdb_api_key}"
                                    async with session.get(details_url) as details_response:
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
            except asyncio.TimeoutError:
                print(f"TMDb API timeout on attempt {attempt+1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
            except Exception as e:
                print(f"Error searching TMDb on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        print("Failed to get TMDb data after all retry attempts")
        return None

    async def send_recommendation(self, guild, media_type):
        """Send a recommendation to the configured channel"""
        settings = await self.config.guild(guild).get_raw(media_type)
        if not all(k in settings and settings[k] for k in ['base_url', 'api_key', 'channel_id']):
            return

        item = await self.get_random_recommendation(settings['base_url'], settings['api_key'])
        if not item:
            return

        title = item.get('Name', 'Titlu necunoscut')
        year = item.get('ProductionYear', 'An necunoscut')
        is_movie = item.get('Type') == "Movie"
        
        media_display = "Film" if is_movie else "Serial"
        overview = item.get('Overview', 'Fără descriere disponibilă.')
        
        tmdb_data = None
        if settings.get('tmdb_api_key'):
            tmdb_data = await self.search_tmdb(title, year, is_movie, settings['tmdb_api_key'])
        
        if tmdb_data and tmdb_data.get('overview'):
            overview = tmdb_data['overview']
            overview = await self.translate_to_romanian(overview)
        
        if len(overview) > 1000:
            overview = overview[:997] + "..."

        color = discord.Color.blue() if media_type == 'anime' else discord.Color.red()
        embed = discord.Embed(
            title=f"{title} ({year})",
            description=overview,
            color=color
        )
        
        if tmdb_data and tmdb_data.get('poster_path'):
            poster_url = f"{self.poster_base_url}{tmdb_data['poster_path']}"
            embed.set_thumbnail(url=poster_url)
        
        embed.add_field(name="Tip", value=media_display, inline=True)
        
        if genres := item.get('Genres', [])[:3]:
            embed.add_field(name="Genuri", value=", ".join(genres), inline=True)
        
        if community_rating := item.get('CommunityRating'):
            embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

        item_id = item.get('Id')
        if item_id:
            web_url = f"{settings['base_url']}/web/index.html#!/details?id={item_id}"
            server_name = settings.get('server_name', 'Freia [SERVER 2]')
            embed.add_field(name="Vizionare Online:", value=f"[{server_name}]({web_url})", inline=False)
        
        cmd_text = f"`.recomanda {media_type}`"
        embed.add_field(name="Caută mai multe recomandări:", value=f"Folosește comanda {cmd_text} pentru a primi o recomandare personalizată oricând dorești!", inline=False)

        channel = guild.get_channel(settings['channel_id'])
        if channel:
            await channel.send("**Recomandarea de săptămâna aceasta:**", embed=embed)

    # ===== COMENZI ANIME =====
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def animerecseturl(self, ctx, url: str):
        """Set the Jellyfin server URL for anime recommendations"""
        url = url.rstrip('/')
        await self.config.guild(ctx.guild).anime.base_url.set(url)
        await ctx.send(f"URL-ul serverului Jellyfin pentru anime a fost setat la: {url}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def animerecsetapi(self, ctx, api_key: str):
        """Set the Jellyfin API key for anime recommendations"""
        await self.config.guild(ctx.guild).anime.api_key.set(api_key)
        await ctx.send("Cheia API Jellyfin pentru anime a fost setată.")
        await ctx.message.delete()
        
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def animerecsettmdbapi(self, ctx, api_key: str):
        """Setează cheia API pentru TMDb pentru anime"""
        await self.config.guild(ctx.guild).anime.tmdb_api_key.set(api_key)
        await ctx.send("Cheia API TMDb pentru anime a fost setată.")
        await ctx.message.delete()

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setanimerecommendationchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for Monday anime recommendations"""
        await self.config.guild(ctx.guild).anime.channel_id.set(channel.id)
        await ctx.send(f"Canalul pentru recomandări anime a fost setat la: {channel.mention}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setanimeservername(self, ctx, *, server_name: str):
        """Setează numele serverului care va apărea în link-ul de vizionare pentru anime"""
        await self.config.guild(ctx.guild).anime.server_name.set(server_name)
        await ctx.send(f"Numele serverului pentru anime a fost setat la: {server_name}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def showanimesecsettings(self, ctx):
        """Show current anime recommendation settings"""
        settings = await self.config.guild(ctx.guild).anime.all()
        channel = ctx.guild.get_channel(settings['channel_id']) if settings.get('channel_id') else None
        
        embed = discord.Embed(
            title="Setări Recomandări Jellyfin Anime",
            color=discord.Color.blue()
        )
        embed.add_field(name="URL Server", value=settings.get('base_url') or "Nesetat", inline=False)
        embed.add_field(name="API Key Jellyfin", value="Setat ✓" if settings.get('api_key') else "Nesetat ✗", inline=False)
        embed.add_field(name="API Key TMDb", value="Setat ✓" if settings.get('tmdb_api_key') else "Nesetat ✗", inline=False)
        embed.add_field(name="Nume Server", value=settings.get('server_name', 'Freia [SERVER 2]'), inline=False)
        embed.add_field(name="Canal Recomandări", value=channel.mention if channel else "Nesetat", inline=False)
        
        await ctx.send(embed=embed)

    # ===== COMENZI PORN =====
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def pornrecseturl(self, ctx, url: str):
        """Set the Jellyfin server URL for porn recommendations"""
        url = url.rstrip('/')
        await self.config.guild(ctx.guild).porn.base_url.set(url)
        await ctx.send(f"URL-ul serverului Jellyfin pentru porn a fost setat la: {url}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def pornrecsetapi(self, ctx, api_key: str):
        """Set the Jellyfin API key for porn recommendations"""
        await self.config.guild(ctx.guild).porn.api_key.set(api_key)
        await ctx.send("Cheia API Jellyfin pentru porn a fost setată.")
        await ctx.message.delete()
        
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def pornrecsettmdbapi(self, ctx, api_key: str):
        """Setează cheia API pentru TMDb pentru porn"""
        await self.config.guild(ctx.guild).porn.tmdb_api_key.set(api_key)
        await ctx.send("Cheia API TMDb pentru porn a fost setată.")
        await ctx.message.delete()

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setpornrecommendationchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for Monday porn recommendations"""
        await self.config.guild(ctx.guild).porn.channel_id.set(channel.id)
        await ctx.send(f"Canalul pentru recomandări porn a fost setat la: {channel.mention}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setpornservername(self, ctx, *, server_name: str):
        """Setează numele serverului care va apărea în link-ul de vizionare pentru porn"""
        await self.config.guild(ctx.guild).porn.server_name.set(server_name)
        await ctx.send(f"Numele serverului pentru porn a fost setat la: {server_name}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def showpornrecsettings(self, ctx):
        """Show current porn recommendation settings"""
        settings = await self.config.guild(ctx.guild).porn.all()
        channel = ctx.guild.get_channel(settings['channel_id']) if settings.get('channel_id') else None
        
        embed = discord.Embed(
            title="Setări Recomandări Jellyfin Porn",
            color=discord.Color.red()
        )
        embed.add_field(name="URL Server", value=settings.get('base_url') or "Nesetat", inline=False)
        embed.add_field(name="API Key Jellyfin", value="Setat ✓" if settings.get('api_key') else "Nesetat ✗", inline=False)
        embed.add_field(name="API Key TMDb", value="Setat ✓" if settings.get('tmdb_api_key') else "Nesetat ✗", inline=False)
        embed.add_field(name="Nume Server", value=settings.get('server_name', 'Freia [SERVER 2]'), inline=False)
        embed.add_field(name="Canal Recomandări", value=channel.mention if channel else "Nesetat", inline=False)
        
        await ctx.send(embed=embed)

    async def get_random_recommendation(self, base_url, api_key):
        """Fetch a random recommendation"""
        search_url = f"{base_url}/Items?IncludeItemTypes=Movie,Series&Recursive=true&SortBy=Random&Limit=1&api_key={api_key}"

        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(search_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            items = data.get('Items', [])
                            return items[0] if items else None
                        else:
                            print(f"Jellyfin API error: Status {response.status}")
            except Exception as e:
                print(f"Error fetching recommendation on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        return None

    @commands.group(name="recomanda", invoke_without_command=True)
    async def recomanda_group(self, ctx):
        """Comenzi pentru recomandări de pe Jellyfin"""
        await ctx.send("Folosește `.recomanda anime` sau `.recomanda porn` pentru a primi o recomandare!")

    @recomanda_group.command(name="anime")
    async def recomanda_anime(self, ctx):
        """Generează manual o recomandare aleatorie de anime"""
        settings = await self.config.guild(ctx.guild).anime.all()
        if not all(k in settings and settings[k] for k in ['base_url', 'api_key']):
            help_msg = (
                "⚠️ Configurarea anime nu este completă. Folosește următoarele comenzi:\n\n"
                f"`{ctx.prefix}animerecseturl <URL>` - Setează URL-ul serverului\n"
                f"`{ctx.prefix}animerecsetapi <API_KEY>` - Setează cheia API Jellyfin\n"
                f"`{ctx.prefix}animerecsettmdbapi <API_KEY>` - Setează cheia API TMDb (opțional)\n"
                f"`{ctx.prefix}setanimerecommendationchannel <#CANAL>` - Setează canalul\n\n"
                f"Verifică setările: `{ctx.prefix}showanimesecsettings`"
            )
            return await ctx.send(help_msg)

        await self._send_manual_recommendation(ctx, settings, 'anime')

    @recomanda_group.command(name="porn")
    async def recomanda_porn(self, ctx):
        """Generează manual o recomandare aleatorie de porn"""
        settings = await self.config.guild(ctx.guild).porn.all()
        if not all(k in settings and settings[k] for k in ['base_url', 'api_key']):
            help_msg = (
                "⚠️ Configurarea porn nu este completă. Folosește următoarele comenzi:\n\n"
                f"`{ctx.prefix}pornrecseturl <URL>` - Setează URL-ul serverului\n"
                f"`{ctx.prefix}pornrecsetapi <API_KEY>` - Setează cheia API Jellyfin\n"
                f"`{ctx.prefix}pornrecsettmdbapi <API_KEY>` - Setează cheia API TMDb (opțional)\n"
                f"`{ctx.prefix}setpornrecommendationchannel <#CANAL>` - Setează canalul\n\n"
                f"Verifică setările: `{ctx.prefix}showpornrecsettings`"
            )
            return await ctx.send(help_msg)

        await self._send_manual_recommendation(ctx, settings, 'porn')

    async def _send_manual_recommendation(self, ctx, settings, media_type):
        """Helper method to send manual recommendation"""
        waiting_msg = await ctx.send("Se caută o recomandare... Așteptați vă rog.")

        try:
            item = await self.get_random_recommendation(settings['base_url'], settings['api_key'])
            if not item:
                await waiting_msg.delete()
                return await ctx.send("Nu s-a putut genera o recomandare.")

            title = item.get('Name', 'Titlu necunoscut')
            year = item.get('ProductionYear', 'An necunoscut')
            is_movie = item.get('Type') == "Movie"
            
            media_display = "Film" if is_movie else "Serial"
            overview = item.get('Overview', 'Fără descriere disponibilă.')
            
            tmdb_data = None
            if settings.get('tmdb_api_key'):
                tmdb_data = await self.search_tmdb(title, year, is_movie, settings['tmdb_api_key'])
            
            if tmdb_data and tmdb_data.get('overview'):
                overview = tmdb_data['overview']
                overview = await self.translate_to_romanian(overview)
            
            if len(overview) > 1000:
                overview = overview[:997] + "..."

            color = discord.Color.blue() if media_type == 'anime' else discord.Color.red()
            embed = discord.Embed(
                title=f"{title} ({year})",
                description=overview,
                color=color
            )
            
            if tmdb_data and tmdb_data.get('poster_path'):
                poster_url = f"{self.poster_base_url}{tmdb_data['poster_path']}"
                embed.set_thumbnail(url=poster_url)
            
            embed.add_field(name="Tip", value=media_display, inline=True)
            
            if genres := item.get('Genres', [])[:3]:
                embed.add_field(name="Genuri", value=", ".join(genres), inline=True)
            
            if community_rating := item.get('CommunityRating'):
                embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

            item_id = item.get('Id')
            if item_id:
                web_url = f"{settings['base_url']}/web/index.html#!/details?id={item_id}"
                server_name = settings.get('server_name', 'Freia [SERVER 2]')
                embed.add_field(name="Vizionare Online:", value=f"[{server_name}]({web_url})", inline=False)
                
            cmd_text = f"`.recomanda {media_type}`"
            embed.add_field(name="Caută mai multe recomandări:", value=f"Folosește comanda {cmd_text} pentru a primi o recomandare personalizată oricând dorești!", inline=False)

            await waiting_msg.delete()
            await ctx.send(embed=embed)
        except Exception as e:
            await waiting_msg.delete()
            await ctx.send(f"A apărut o eroare în generarea recomandării: {e}")
