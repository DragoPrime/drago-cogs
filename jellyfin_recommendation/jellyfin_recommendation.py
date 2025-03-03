from redbot.core import commands, Config
import asyncio
import aiohttp
import random
import discord
from datetime import datetime, timedelta

class JellyfinRecommendation(commands.Cog):
    """Provide random Jellyfin recommendations every Monday"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=983947321,  # Identificator unic pentru acest cog
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
        """Caută pe TMDb și returnează datele filmului/serialului"""
        if not tmdb_api_key:
            return None
            
        media_type = "movie" if is_movie else "tv"
        search_url = f"{self.tmdb_base_url}/search/{media_type}?api_key={tmdb_api_key}&query={title}&year={year}"
        
        async with aiohttp.ClientSession() as session:
            try:
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
            except Exception as e:
                print(f"Error searching TMDb: {e}")
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
            tmdb_data = await self.search_tmdb(title, year, is_movie, settings['tmdb_api_key'])
        
        # Folosește descrierea TMDb dacă există și nu este goală
        if tmdb_data and tmdb_data.get('overview'):
            overview = tmdb_data['overview']
        
        # Limitează lungimea descrierii
        if len(overview) > 1000:
            overview = overview[:997] + "..."

        embed = discord.Embed(
            title=f"{title} ({year})",
            description=overview,
            color=discord.Color.blue()
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
        embed.add_field(name="Caută mai multe recomandări:", value="Folosește comanda `.recomanda` pentru a primi o recomandare personalizată oricând dorești!", inline=False)

        channel = guild.get_channel(settings['channel_id'])
        if channel:
            # Adăugare text "Recomandarea Săptămânii:" înainte de embed
            await channel.send("**Recomandarea Domnișoarei Freia de săptămâna aceasta:**", embed=embed)

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def recseturl(self, ctx, url: str):
        """Set the Jellyfin server URL for recommendations"""
        url = url.rstrip('/')
        await self.config.guild(ctx.guild).base_url.set(url)
        await ctx.send(f"URL-ul serverului Jellyfin pentru recomandări a fost setat la: {url}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def recsetapi(self, ctx, api_key: str):
        """Set the Jellyfin API key for recommendations"""
        await self.config.guild(ctx.guild).api_key.set(api_key)
        await ctx.send("Cheia API Jellyfin pentru recomandări a fost setată.")
        await ctx.message.delete()
        
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def recsettmdbapi(self, ctx, api_key: str):
        """Setează cheia API pentru TMDb pentru a obține postere"""
        await self.config.guild(ctx.guild).tmdb_api_key.set(api_key)
        await ctx.send("Cheia API TMDb pentru postere și descrieri a fost setată.")
        await ctx.message.delete()

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setrecommendationchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for Monday recommendations"""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"Canalul pentru recomandări a fost setat la: {channel.mention}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def showrecsettings(self, ctx):
        """Show current recommendation settings"""
        settings = await self.config.guild(ctx.guild).all()
        channel = ctx.guild.get_channel(settings['channel_id']) if settings['channel_id'] else None
        
        embed = discord.Embed(
            title="Setări Recomandări Jellyfin",
            color=discord.Color.blue()
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

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(search_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = data.get('Items', [])
                        return items[0] if items else None
            except Exception as e:
                print(f"Error fetching recommendation: {e}")
                return None

    @commands.command(name="recomanda")
    async def recomanda(self, ctx):
        """Generează manual o recomandare aleatorie de film sau serial"""
        settings = await self.config.guild(ctx.guild).all()
        if not all(k in settings and settings[k] for k in ['base_url', 'api_key']):
            help_msg = (
                "⚠️ Configurarea nu este completă. Folosește următoarele comenzi pentru a seta totul:\n\n"
                f"`{ctx.prefix}recseturl <URL>` - Setează URL-ul serverului Jellyfin\n"
                f"`{ctx.prefix}recsetapi <API_KEY>` - Setează cheia API Jellyfin\n"
                f"`{ctx.prefix}recsettmdbapi <API_KEY>` - Setează cheia API TMDb pentru postere și descrieri (opțional)\n"
                f"`{ctx.prefix}setrecommendationchannel <#CANAL>` - Setează canalul pentru recomandări\n\n"
                f"Poți verifica setările curente folosind `{ctx.prefix}showrecsettings`"
            )
            return await ctx.send(help_msg)

        item = await self.get_random_recommendation(settings['base_url'], settings['api_key'])
        if not item:
            return await ctx.send("Nu s-a putut genera o recomandare.")

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
            tmdb_data = await self.search_tmdb(title, year, is_movie, settings['tmdb_api_key'])
        
        # Folosește descrierea TMDb dacă există și nu este goală
        if tmdb_data and tmdb_data.get('overview'):
            overview = tmdb_data['overview']
        
        # Limitează lungimea descrierii
        if len(overview) > 1000:
            overview = overview[:997] + "..."

        embed = discord.Embed(
            title=f"{title} ({year})",
            description=overview,
            color=discord.Color.blue()
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
        embed.add_field(name="Caută mai multe recomandări:", value="Folosește comanda `.recomanda` pentru a primi o recomandare personalizată oricând dorești!", inline=False)

        await ctx.send(embed=embed)
