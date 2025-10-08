from redbot.core import commands, Config
import asyncio
import aiohttp
import random
import discord
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator

class JellyfinPornRecommendation(commands.Cog):
    """Provide random Jellyfin porn recommendations every Monday"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=983947322,  # Identificator unic diferit pentru acest cog
            force_registration=True
        )
        
        # Setări implicite
        default_guild = {
            "base_url": None,
            "api_key": None,
            "channel_id": None,
            "tmdb_api_key": None
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
            # Rulăm traducerea într-un executor pentru a nu bloca event loop-ul
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(
                None, 
                lambda: GoogleTranslator(source='auto', target='ro').translate(text)
            )
            return translated
        except Exception as e:
            print(f"Eroare la traducere: {e}")
            # Returnăm textul original dacă traducerea eșuează
            return text

    async def monday_recommendation_loop(self):
        """Background loop for Monday recommendations"""
        await self.bot.wait_until_ready()
        while True:
            now = datetime.now()
            if now.weekday() == 0 and now.hour == 18:
                # Iterăm prin toate guild-urile configurate
                all_guilds = await self.config.all_guilds()
                for guild_id, settings in all_guilds.items():
                    if all(k in settings and settings[k] for k in ['base_url', 'api_key', 'channel_id']):  # Verificăm setările esențiale
                        guild = self.bot.get_guild(guild_id)
                        if guild:
                            await self.send_recommendation(guild)
            await asyncio.sleep(3600)  # 3600 secunde = 1 oră

    async def search_tmdb(self, title, year, is_movie, tmdb_api_key):
        """Caută pe TMDb și returnează datele filmului/serialului cu retry și timeout extins"""
        if not tmdb_api_key:
            return None
            
        media_type = "movie" if is_movie else "tv"
        search_url = f"{self.tmdb_base_url}/search/{media_type}?api_key={tmdb_api_key}&query={title}&year={year}"
        
        # Setăm un timeout mai mare pentru a permite procesarea lentă
        timeout = aiohttp.ClientTimeout(total=30)  # 30 secunde timeout total
        
        # Implementăm un sistem de retry
        max_retries = 3
        retry_delay = 2  # secunde
        
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
                                
                                # Obține detalii complete pentru a avea informații mai precise
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
                                
                                # Dacă nu putem obține detalii complete, folosim rezultatele din căutare
                                return {
                                    'poster_path': tmdb_data.get('poster_path'),
                                    'overview': tmdb_data.get('overview'),
                                    'tmdb_id': tmdb_id
                                }
                        elif response.status == 429:  # Prea multe cereri (rate limit)
                            # Așteptăm mai mult dacă suntem rate-limited
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
        
        # Dacă am epuizat toate încercările și tot nu avem rezultate
        print("Failed to get TMDb data after all retry attempts")
        return None

    async def send_recommendation(self, guild):
        """Send a recommendation to the configured channel"""
        settings = await self.config.guild(guild).all()
        if not all(k in settings and settings[k] for k in ['base_url', 'api_key', 'channel_id']):
            return

        item = await self.get_random_recommendation(settings['base_url'], settings['api_key'])
        if not item:
            return

        title = item.get('Name', 'Titlu necunoscut')
        year = item.get('ProductionYear', 'An necunoscut')
        is_movie = item.get('Type') == "Movie"
        
        # Determinarea tipului bazat pe Type din Jellyfin
        media_type = "Film" if is_movie else "Serial"
        
        # Descriere inițială din Jellyfin
        overview = item.get('Overview', 'Fără descriere disponibilă.')
        
        # Căutare pe TMDb pentru poster și descriere
        tmdb_data = None
        if 'tmdb_api_key' in settings and settings['tmdb_api_key']:
            # Folosim un timeout mai mare pentru această operațiune
            tmdb_data = await self.search_tmdb(title, year, is_movie, settings['tmdb_api_key'])
        
        # Folosește descrierea TMDb dacă există și nu este goală
        if tmdb_data and tmdb_data.get('overview'):
            overview = tmdb_data['overview']
            # Traducem descrierea în română
            overview = await self.translate_to_romanian(overview)
        
        # Limitează lungimea descrierii
        if len(overview) > 1000:
            overview = overview[:997] + "..."

        embed = discord.Embed(
            title=f"{title} ({year})",
            description=overview,
            color=discord.Color.red()
        )
        
        # Adaugă posterul TMDb dacă există
        if tmdb_data and tmdb_data.get('poster_path'):
            poster_url = f"{self.poster_base_url}{tmdb_data['poster_path']}"
            embed.set_thumbnail(url=poster_url)
        
        # Adăugare tip (Film/Serial)
        embed.add_field(name="Tip", value=media_type, inline=True)
        
        if genres := item.get('Genres', [])[:3]:
            embed.add_field(name="Genuri", value=", ".join(genres), inline=True)
        
        if community_rating := item.get('CommunityRating'):
            embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

        item_id = item.get('Id')
        if item_id:
            web_url = f"{settings['base_url']}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Vizionare Online:", value=f"[Freia [SERVER 2]]({web_url})", inline=False)
        
        # Adăugare text informativ despre comanda manuală
        embed.add_field(name="Caută mai multe recomandări:", value="Folosește comanda `.recomanda porn` pentru a primi o recomandare personalizată oricând dorești!", inline=False)

        channel = guild.get_channel(settings['channel_id'])
        if channel:
            # Adăugare text "Recomandarea Săptămânii:" înainte de embed
            await channel.send("**Recomandarea Domnișoarei Freia de săptămâna aceasta:**", embed=embed)

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def pornrecseturl(self, ctx, url: str):
        """Set the Jellyfin server URL for porn recommendations"""
        url = url.rstrip('/')
        await self.config.guild(ctx.guild).base_url.set(url)
        await ctx.send(f"URL-ul serverului Jellyfin pentru recomandări porn a fost setat la: {url}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def pornrecsetapi(self, ctx, api_key: str):
        """Set the Jellyfin API key for porn recommendations"""
        await self.config.guild(ctx.guild).api_key.set(api_key)
        await ctx.send("Cheia API Jellyfin pentru recomandări porn a fost setată.")
        await ctx.message.delete()
        
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def pornrecsettmdbapi(self, ctx, api_key: str):
        """Setează cheia API pentru TMDb pentru a obține postere pentru porn"""
        await self.config.guild(ctx.guild).tmdb_api_key.set(api_key)
        await ctx.send("Cheia API TMDb pentru postere și descrieri porn a fost setată.")
        await ctx.message.delete()

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setpornrecommendationchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for Monday porn recommendations"""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"Canalul pentru recomandări porn a fost setat la: {channel.mention}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def showpornrecsettings(self, ctx):
        """Show current porn recommendation settings"""
        settings = await self.config.guild(ctx.guild).all()
        channel = ctx.guild.get_channel(settings['channel_id']) if settings['channel_id'] else None
        
        embed = discord.Embed(
            title="Setări Recomandări Jellyfin Porn",
            color=discord.Color.red()
        )
        embed.add_field(
            name="URL Server", 
            value=settings['base_url'] or "Nesetat",
            inline=False
        )
        embed.add_field(
            name="API Key Jellyfin", 
            value="Setat ✓" if settings['api_key'] else "Nesetat ✗",
            inline=False
        )
        embed.add_field(
            name="API Key TMDb", 
            value="Setat ✓" if settings.get('tmdb_api_key') else "Nesetat ✗",
            inline=False
        )
        embed.add_field(
            name="Canal Recomandări", 
            value=channel.mention if channel else "Nesetat",
            inline=False
        )
        
        await ctx.send(embed=embed)

    async def get_random_recommendation(self, base_url, api_key):
        """Fetch a random recommendation"""
        search_url = f"{base_url}/Items?IncludeItemTypes=Movie,Series&Recursive=true&SortBy=Random&Limit=1&api_key={api_key}"

        # Implementăm un sistem de retry
        max_retries = 3
        retry_delay = 2  # secunde
        
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
        """Comenzi pentru recomandări"""
        pass
    
    @recomanda_group.command(name="porn")
    async def recomanda_porn(self, ctx):
        """Generează manual o recomandare aleatorie de porn"""
        
        settings = await self.config.guild(ctx.guild).all()
        if not all(k in settings and settings[k] for k in ['base_url', 'api_key']):
            help_msg = (
                "⚠️ Configurarea nu este completă. Folosește următoarele comenzi pentru a seta totul:\n\n"
                f"`{ctx.prefix}pornrecseturl <URL>` - Setează URL-ul serverului Jellyfin\n"
                f"`{ctx.prefix}pornrecsetapi <API_KEY>` - Setează cheia API Jellyfin\n"
                f"`{ctx.prefix}pornrecsettmdbapi <API_KEY>` - Setează cheia API TMDb pentru postere și descrieri (opțional)\n"
                f"`{ctx.prefix}setpornrecommendationchannel <#CANAL>` - Setează canalul pentru recomandări\n\n"
                f"Poți verifica setările curente folosind `{ctx.prefix}showpornrecsettings`"
            )
            return await ctx.send(help_msg)

        # Adaugă un mesaj de "așteptare" pentru a informa utilizatorul
        waiting_msg = await ctx.send("Se caută o recomandare... Așteptați vă rog.")

        try:
            # Obținem recomandarea de la Jellyfin
            item = await self.get_random_recommendation(settings['base_url'], settings['api_key'])
            if not item:
                await waiting_msg.delete()
                return await ctx.send("Nu s-a putut genera o recomandare.")

            title = item.get('Name', 'Titlu necunoscut')
            year = item.get('ProductionYear', 'An necunoscut')
            is_movie = item.get('Type') == "Movie"
            
            # Determinarea tipului bazat pe Type din Jellyfin
            media_type = "Film" if is_movie else "Serial"
            
            # Descriere inițială din Jellyfin
            overview = item.get('Overview', 'Fără descriere disponibilă.')
            
            # Căutare pe TMDb pentru poster și descriere - wait for it
            tmdb_data = None
            if 'tmdb_api_key' in settings and settings['tmdb_api_key']:
                tmdb_data = await self.search_tmdb(title, year, is_movie, settings['tmdb_api_key'])
            
            # Folosește descrierea TMDb dacă există și nu este goală
            if tmdb_data and tmdb_data.get('overview'):
                overview = tmdb_data['overview']
                # Traducem descrierea în română
                overview = await self.translate_to_romanian(overview)
            
            # Limitează lungimea descrierii
            if len(overview) > 1000:
                overview = overview[:997] + "..."

            embed = discord.Embed(
                title=f"{title} ({year})",
                description=overview,
                color=discord.Color.red()
            )
            
            # Adaugă posterul TMDb dacă există
            if tmdb_data and tmdb_data.get('poster_path'):
                poster_url = f"{self.poster_base_url}{tmdb_data['poster_path']}"
                embed.set_thumbnail(url=poster_url)
            
            # Adăugare tip (Film/Serial)
            embed.add_field(name="Tip", value=media_type, inline=True)
            
            if genres := item.get('Genres', [])[:3]:
                embed.add_field(name="Genuri", value=", ".join(genres), inline=True)
            
            if community_rating := item.get('CommunityRating'):
                embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

            item_id = item.get('Id')
            if item_id:
                web_url = f"{settings['base_url']}/web/index.html#!/details?id={item_id}"
                embed.add_field(name="Vizionare Online:", value=f"[Freia [SERVER 2]]({web_url})", inline=False)
                
            # Adăugare text informativ despre comanda manuală
            embed.add_field(name="Caută mai multe recomandări:", value="Folosește comanda `.recomanda porn` pentru a primi o recomandare personalizată oricând dorești!", inline=False)

            # Ștergem mesajul de așteptare
            await waiting_msg.delete()
            
            # Trimitem recomandarea
            await ctx.send(embed=embed)
        except Exception as e:
            # În caz de eroare, ștergem mesajul de așteptare și trimitem mesaj de eroare
            await waiting_msg.delete()
            await ctx.send(f"A apărut o eroare în generarea recomandării: {e}")
