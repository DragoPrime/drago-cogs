from redbot.core import commands
import aiohttp
import urllib.parse
import discord
from datetime import datetime

class JellyfinSearch(commands.Cog):
    """Jellyfin search commands for Red Discord Bot"""

    def __init__(self, bot):
        self.bot = bot
        self.base_url = None
        self.api_key = None

    @commands.command()
    @commands.is_owner()
    async def setjellyfinurl(self, ctx, url: str):
        """Set the Jellyfin server URL"""
        self.base_url = url.rstrip('/')
        await ctx.send(f"Jellyfin server URL set to: {self.base_url}")

    @commands.command()
    @commands.is_owner()
    async def setjellyfinapi(self, ctx, api_key: str):
        """Set the Jellyfin API key"""
        self.api_key = api_key
        await ctx.send("Jellyfin API key has been set.")
        # Delete the message containing the API key for security
        await ctx.message.delete()

    def format_runtime(self, runtime_ticks):
        """Convert runtime ticks to hours and minutes"""
        if not runtime_ticks:
            return "N/A"
        minutes = int(runtime_ticks / (10000000 * 60))
        hours = minutes // 60
        remaining_minutes = minutes % 60
        if hours > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{remaining_minutes}m"

    @commands.command(name="freia")
    async def freia(self, ctx, *, query: str):
        """Search for content on your Jellyfin server"""
        if not self.base_url or not self.api_key:
            return await ctx.send("Please set up the Jellyfin URL and API key first using `setjellyfinurl` and `setjellyfinapi`")

        encoded_query = urllib.parse.quote(query)
        search_url = f"{self.base_url}/Items?searchTerm={encoded_query}&Limit=10&api_key={self.api_key}&Fields=Overview,Runtime,Genres,Studios,PremiereDate,CommunityRating,OfficialRating"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(search_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = data.get('Items', [])

                        if not items:
                            return await ctx.send("No results found.")

                        # Create a single embed for all results
                        embed = discord.Embed(
                            title=f"Search Results for '{query}'",
                            color=discord.Color.blue()
                        )

                        for item in items:
                            # Create title with year if available
                            title = item.get('Name', 'Unknown Title')
                            if year := item.get('ProductionYear'):
                                title += f" ({year})"

                            # Compile item details
                            details = []
                            
                            # Type and Runtime
                            runtime = self.format_runtime(item.get('RunTimeTicks'))
                            details.append(f"Runtime: {runtime}")

                            # Rating information
                            if community_rating := item.get('CommunityRating'):
                                details.append(f"Rating: ⭐ {community_rating:.1f}")

                            # Genres (limited to 3)
                            if genres := item.get('Genres', [])[:3]:
                                details.append(f"Genres: {', '.join(genres)}")

                            # Create direct links
                            item_id = item.get('Id')
                            if item_id:
                                web_url = f"{self.base_url}/web/index.html#!/details?id={item_id}"
                                play_url = f"{self.base_url}/web/index.html#!/details?id={item_id}&serverId=1&autoplay=true"
                                details.append(f"[View Details]({web_url}) | [Play Now]({play_url})")

                            # Add field for this item
                            embed.add_field(
                                name=title,
                                value="\n".join(details),
                                inline=False
                            )

                        await ctx.send(embed=embed)
                    else:
                        await ctx.send(f"Error: Unable to search Jellyfin server (Status code: {response.status})")
            except Exception as e:
                await ctx.send(f"Error connecting to Jellyfin server: {str(e)}")
