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

        # URL encode the search query
        encoded_query = urllib.parse.quote(query)
        
        # Construct the search URL with more fields
        search_url = f"{self.base_url}/Items?searchTerm={encoded_query}&Limit=5&api_key={self.api_key}&Fields=Overview,Path,Runtime,Genres,Studios,PremiereDate,CommunityRating,OfficialRating"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(search_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = data.get('Items', [])

                        if not items:
                            return await ctx.send("No results found.")

                        # Process each item in detail
                        for item in items:
                            embed = discord.Embed(
                                title=item.get('Name', 'Unknown Title'),
                                color=discord.Color.blue()
                            )

                            # Add year to title if available
                            if year := item.get('ProductionYear'):
                                embed.title += f" ({year})"

                            # Basic information
                            item_type = item.get('Type', 'Unknown Type')
                            embed.add_field(name="Type", value=item_type, inline=True)
                            
                            # Runtime
                            runtime = self.format_runtime(item.get('RunTimeTicks'))
                            embed.add_field(name="Runtime", value=runtime, inline=True)

                            # Rating information
                            rating = item.get('OfficialRating', 'N/A')
                            community_rating = item.get('CommunityRating')
                            if community_rating:
                                rating += f" | ⭐ {community_rating:.1f}"
                            embed.add_field(name="Rating", value=rating, inline=True)

                            # Genres
                            if genres := item.get('Genres'):
                                embed.add_field(name="Genres", value=", ".join(genres[:3]), inline=True)

                            # Studios/Network
                            if studios := item.get('Studios'):
                                studio_names = [studio.get('Name') for studio in studios]
                                if studio_names:
                                    embed.add_field(name="Studio", value=", ".join(studio_names[:2]), inline=True)

                            # Premiere date
                            if premiere_date := item.get('PremiereDate'):
                                try:
                                    date_obj = datetime.fromisoformat(premiere_date.replace('Z', '+00:00'))
                                    formatted_date = date_obj.strftime("%B %d, %Y")
                                    embed.add_field(name="Release Date", value=formatted_date, inline=True)
                                except ValueError:
                                    pass

                            # Overview/Plot
                            if overview := item.get('Overview'):
                                if len(overview) > 1024:
                                    overview = overview[:1021] + "..."
                                embed.add_field(name="Overview", value=overview, inline=False)

                            # Direct links
                            item_id = item.get('Id')
                            if item_id:
                                web_url = f"{self.base_url}/web/index.html#!/details?id={item_id}"
                                play_url = f"{self.base_url}/web/index.html#!/details?id={item_id}&serverId=1&autoplay=true"
                                links = f"[View Details]({web_url})\n[Play Now]({play_url})"
                                embed.add_field(name="Links", value=links, inline=False)

                            # Footer with item ID
                            embed.set_footer(text=f"ID: {item_id}")

                            await ctx.send(embed=embed)
                    else:
                        await ctx.send(f"Error: Unable to search Jellyfin server (Status code: {response.status})")
            except Exception as e:
                await ctx.send(f"Error connecting to Jellyfin server: {str(e)}")

async def setup(bot):
    await bot.add_cog(JellyfinSearch(bot))
