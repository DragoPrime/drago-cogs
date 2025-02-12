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
            identifier=987654321,  # Identificator unic pentru acest cog
            force_registration=True
        )
        
        # Setări implicite
        default_guild = {
            "base_url": None,
            "api_key": None,
            "channel_id": None
        }
        
        self.config.register_guild(**default_guild)
        self.bg_task = None
        self.start_tasks()

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
                    if all(settings.values()):  # Verificăm dacă toate setările sunt configurate
                        guild = self.bot.get_guild(guild_id)
                        if guild:
                            await self.send_recommendation(guild)
            await asyncio.sleep(3600)  # 3600 secunde = 1 oră

    async def send_recommendation(self, guild):
        """Send a recommendation to the configured channel"""
        settings = await self.config.guild(guild).all()
        if not all(settings.values()):
            return

        item = await self.get_random_recommendation(settings['base_url'], settings['api_key'])
        if not item:
            return

        title = item.get('Name', 'Titlu necunoscut')
        year = item.get('ProductionYear', 'An necunoscut')
        item_type = "Film" if item.get('Type') == "Movie" else "Serial"
        
        overview = item.get('Overview', 'Fără descriere disponibilă.')
        if len(overview) > 1000:
            overview = overview[:997] + "..."

        embed = discord.Embed(
            title=f"Recomandarea Săptămânii: {title} ({year})",
            description=overview,
            color=discord.Color.blue()
        )
        
        if genres := item.get('Genres', [])[:3]:
            embed.add_field(name="Genuri", value=", ".join(genres), inline=True)
        
        if community_rating := item.get('CommunityRating'):
            embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

        item_id = item.get('Id')
        if item_id:
            web_url = f"{settings['base_url']}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Detalii", value=f"[Vezi pe Jellyfin]({web_url})", inline=False)

        channel = guild.get_channel(settings['channel_id'])
        if channel:
            await channel.send(f"🎬 Recomandarea de {item_type} pentru săptămâna aceasta:", embed=embed)

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
            name="API Key", 
            value="Setat ✓" if settings['api_key'] else "Nesetat ✗",
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

    @commands.command()
    async def recommend(self, ctx):
        """Manually trigger a random Jellyfin recommendation"""
        settings = await self.config.guild(ctx.guild).all()
        if not all(settings.values()):
            return await ctx.send("Te rog să configurezi mai întâi URL-ul și API-ul Jellyfin.")

        item = await self.get_random_recommendation(settings['base_url'], settings['api_key'])
        if not item:
            return await ctx.send("Nu s-a putut genera o recomandare.")

        title = item.get('Name', 'Titlu necunoscut')
        year = item.get('ProductionYear', 'An necunoscut')
        item_type = "Film" if item.get('Type') == "Movie" else "Serial"
        
        overview = item.get('Overview', 'Fără descriere disponibilă.')
        if len(overview) > 1000:
            overview = overview[:997] + "..."

        embed = discord.Embed(
            title=f"Recomandarea Momentului: {title} ({year})",
            description=overview,
            color=discord.Color.blue()
        )
        
        if genres := item.get('Genres', [])[:3]:
            embed.add_field(name="Genuri", value=", ".join(genres), inline=True)
        
        if community_rating := item.get('CommunityRating'):
            embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

        item_id = item.get('Id')
        if item_id:
            web_url = f"{settings['base_url']}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Detalii", value=f"[Vezi pe Jellyfin]({web_url})", inline=False)

        await ctx.send(f"🎬 Recomandare: {item_type}", embed=embed)
