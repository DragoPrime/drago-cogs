from redbot.core import commands
import asyncio
import aiohttp
import random
import discord
from datetime import datetime, timedelta

class JellyfinRecommendation(commands.Cog):
    """Provide random Jellyfin recommendations every Monday"""

    def __init__(self, bot):
        self.bot = bot
        self.base_url = None
        self.api_key = None
        self.channel_id = None
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
            # Verifică dacă este luni și ora 18:00
            if now.weekday() == 0 and now.hour == 18:
                await self.send_recommendation()
            # Așteaptă o oră înainte de următoarea verificare
            await asyncio.sleep(3600)  # 3600 secunde = 1 oră

    async def send_recommendation(self):
        """Send a recommendation to the configured channel"""
        if not all([self.base_url, self.api_key, self.channel_id]):
            return

        item = await self.get_random_recommendation()
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
            web_url = f"{self.base_url}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Detalii", value=f"[Vezi pe Jellyfin]({web_url})", inline=False)

        channel = self.bot.get_channel(self.channel_id)
        if channel:
            await channel.send(f"🎬 Recomandarea de {item_type} pentru săptămâna aceasta:", embed=embed)

    @commands.command()
    @commands.is_owner()
    async def setjellyfinurl(self, ctx, url: str):
        """Set the Jellyfin server URL"""
        self.base_url = url.rstrip('/')
        await ctx.send(f"URL-ul serverului Jellyfin a fost setat la: {self.base_url}")

    @commands.command()
    @commands.is_owner()
    async def setjellyfinapi(self, ctx, api_key: str):
        """Set the Jellyfin API key"""
        self.api_key = api_key
        await ctx.send("Cheia API Jellyfin a fost setată.")
        await ctx.message.delete()

    @commands.command()
    @commands.is_owner()
    async def setrecommendationchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for Monday recommendations"""
        self.channel_id = channel.id
        await ctx.send(f"Canalul pentru recomandări a fost setat la: {channel.mention}")

    async def get_random_recommendation(self):
        """Fetch a random recommendation"""
        if not all([self.base_url, self.api_key]):
            return None

        search_url = f"{self.base_url}/Items?IncludeItemTypes=Movie,Series&Recursive=true&SortBy=Random&Limit=1&api_key={self.api_key}"

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
        if not all([self.base_url, self.api_key]):
            return await ctx.send("Te rog să configurezi mai întâi URL-ul și API-ul Jellyfin.")

        item = await self.get_random_recommendation()
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
            web_url = f"{self.base_url}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Detalii", value=f"[Vezi pe Jellyfin]({web_url})", inline=False)

        await ctx.send(f"🎬 Recomandare: {item_type}", embed=embed)
