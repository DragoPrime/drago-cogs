from .plex import Plex


async def setup(bot):
    await bot.add_cog(plex(bot))