import discord
from redbot.core import commands
from plexapi.server import PlexServer

class PlexCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.plex_token = "aNqSN_FV6WF-G8_x8ze7"  # Replace with your Plex token
        self.plex_baseurl = "http://192.168.1.12:32400"  # Update if Plex server is running on a different port

    @commands.command()
    async def plex_info(self, ctx):
        """Get information about the Plex server."""
        plex = PlexServer(self.plex_baseurl, self.plex_token)
        if plex:
            info = f"Connected to Plex Server: {plex.friendlyName}\n"
            info += f"Library Sections: {', '.join([section.title for section in plex.library.sections()])}"
        else:
            info = "Unable to connect to Plex server."
        await ctx.send(info)

    @commands.command()
    async def plex_search(self, ctx, query: str):
        """Search for media on Plex server."""
        plex = PlexServer(self.plex_baseurl, self.plex_token)
        if plex:
            results = plex.library.search(query)
            if results:
                media_info = "\n".join([f"{item.title} - {item.TYPE}" for item in results])
                await ctx.send(f"Search Results:\n{media_info}")
            else:
                await ctx.send("No results found.")
        else:
            await ctx.send("Unable to connect to Plex server.")

def setup(bot):
    bot.add_cog(PlexCog(bot))
