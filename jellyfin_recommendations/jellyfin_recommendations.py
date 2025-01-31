import discord
from redbot.core import commands, Config
from discord.ext import tasks
from redbot.core.bot import Red
import jellyfin_apiclient_python
import random
from datetime import datetime, timedelta

class JellyfinRecommendations(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "jellyfin_url": None,
            "jellyfin_username": None,
            "jellyfin_password": None,
            "recommendation_channel": None
        }
        self.config.register_guild(**default_guild)
        self.weekly_recommendation.start()
    
    def cog_unload(self):
        self.weekly_recommendation.cancel()
    
    @commands.group(invoke_without_command=True)
    @commands.admin()
    async def jellyfinrec(self, ctx):
        """Jellyfin Recommendation Configuration"""
        await ctx.send_help()
    
    @jellyfinrec.command()
    async def setup(self, ctx, url: str, username: str, password: str, channel: discord.TextChannel):
        """Setup Jellyfin server details and recommendation channel"""
        await self.config.guild(ctx.guild).jellyfin_url.set(url)
        await self.config.guild(ctx.guild).jellyfin_username.set(username)
        await self.config.guild(ctx.guild).jellyfin_password.set(password)
        await self.config.guild(ctx.guild).recommendation_channel.set(channel.id)
        await ctx.send("Jellyfin recommendation settings configured successfully!")
    
    @commands.command()
    async def recommend(self, ctx):
        """Manually trigger a recommendation"""
        await self._send_recommendation(ctx.guild)
    
    async def _send_recommendation(self, guild):
        # Retrieve configuration
        jellyfin_url = await self.config.guild(guild).jellyfin_url()
        username = await self.config.guild(guild).jellyfin_username()
        password = await self.config.guild(guild).jellyfin_password()
        channel_id = await self.config.guild(guild).recommendation_channel()
        
        if not all([jellyfin_url, username, password, channel_id]):
            return
        
        # Connect to Jellyfin
        client = jellyfin_apiclient_python.JellyfinClient()
        client.config.app_name = 'DiscordRecommendationBot'
        client.config.device_name = 'DiscordBot'
        
        # Authenticate
        try:
            auth_result = await client.authenticate(jellyfin_url, username, password)
        except Exception as e:
            print(f"Authentication error: {e}")
            return
        
        # Fetch items (movies and series)
        try:
            items = await client.get_items(
                user_id=auth_result.user.user_id, 
                include_item_types=['Movie', 'Series']
            )
        except Exception as e:
            print(f"Error fetching items: {e}")
            return
        
        # Select random item
        if not items:
            return
        
        recommendation = random.choice(items)
        
        # Create embed
        embed = discord.Embed(
            title=recommendation.name, 
            description=recommendation.overview or "No description available",
            color=discord.Color.blue()
        )
        embed.add_field(name="Type", value=recommendation.type, inline=True)
        embed.add_field(name="Rating", value=recommendation.community_rating or "N/A", inline=True)
        embed.add_field(name="Link", value=f"{jellyfin_url}/web/index.html#!/details?id={recommendation.id}", inline=False)
        
        # Send to configured channel
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)
    
    @tasks.loop(hours=24)
    async def weekly_recommendation(self):
        """Send recommendation every Monday"""
        for guild in self.bot.guilds:
            # Check if it's Monday
            if datetime.now().weekday() == 0:
                await self._send_recommendation(guild)

def setup(bot: Red):
    bot.add_cog(JellyfinRecommendations(bot))
