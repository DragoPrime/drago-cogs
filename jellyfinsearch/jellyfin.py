from redbot.core import commands, Config
import aiohttp
import urllib.parse
import discord
from datetime import datetime

class JellyfinSearch(commands.Cog):
    """Jellyfin search commands for Red Discord Bot"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=856712356)
        default_global = {
            "base_url": None,
            "api_key": None
        }
        self.config.register_global(**default_global)

    async def get_base_url(self):
        """Get the stored base URL"""
        return await self.config.base_url()

    async def get_api_key(self):
        """Get the stored API key"""
        return await self.config.api_key()

    @commands.command()
    @commands.is_owner()
    async def setjellyfinurl(self, ctx, url: str):
        """Set the Jellyfin server URL"""
        url = url.rstrip('/')
        await self.config.base_url.set(url)
        await ctx.send(f"URL-ul serverului Jellyfin a fost setat la: {url}")

    @commands.command()
    @commands.is_owner()
    async def setjellyfinapi(self, ctx, api_key: str):
        """Set the Jellyfin API key"""
        await self.config.api_key.set(api_key)
        await ctx.send("Cheia API Jellyfin a fost setată.")
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
        base_url = await self.get_base_url()
        api_key = await self.get_api_key()
        
        if not base_url or not api_key:
            return await ctx.send("Te rog să setezi mai întâi URL-ul și cheia API folosind `setjellyfinurl` și `setjellyfinapi`")

        encoded_query = urllib.parse.quote(query)
        search_url = f"{base_url}/Items?searchTerm={encoded_query}&IncludeItemTypes=Movie,Series&Recursive=true&SearchType=String&IncludeMedia=true&Limit=10&api_key={api_key}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(search_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = data.get('Items', [])

                        if not items:
                            return await ctx.send("Nu s-au găsit rezultate. Atenție: căutarea se face după titlul de pe TMDB (cel în engleză, nu japoneză).")

                        embed = discord.Embed(
                            title=f"Rezultate pentru '{query}'",
                            color=discord.Color.blue()
                        )

                        for item in items:
                            title = item.get('Name', 'Titlu necunoscut')
                            if year := item.get('ProductionYear'):
                                title += f" ({year})"

                            details = []
                            
                            item_type = item.get('Type', 'Tip necunoscut')
                            if item_type == "Movie":
                                item_type = "Film"
                            elif item_type == "Series":
                                item_type = "Serial"
                            details.append(f"Tip: {item_type}")
                            
                            runtime = self.format_runtime(item.get('RunTimeTicks'))
                            if runtime != "N/A":
                                details.append(f"Durată: {runtime}")

                            if community_rating := item.get('CommunityRating'):
                                details.append(f"Rating: ⭐ {community_rating:.1f}")

                            if genres := item.get('Genres', [])[:3]:
                                details.append(f"Genuri: {', '.join(genres)}")

                            item_id = item.get('Id')
                            if item_id:
                                web_url = f"{base_url}/web/index.html#!/details?id={item_id}"
                                details.append(f"[Vezi Detalii]({web_url})")

                            embed.add_field(
                                name=title,
                                value="\n".join(details),
                                inline=False
                            )

                        total_results = data.get('TotalRecordCount', 0)
                        embed.set_footer(text=f"S-au găsit {total_results} rezultate în total")

                        await ctx.send(embed=embed)
                    else:
                        error_text = await response.text()
                        await ctx.send(f"Eroare: Nu s-a putut căuta pe serverul Jellyfin (Cod status: {response.status})\nDetalii eroare: {error_text}")
            except Exception as e:
                await ctx.send(f"Eroare la conectarea cu serverul Jellyfin: {str(e)}")
