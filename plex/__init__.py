from .plex import plex


async def setup(bot):
    await bot.add_cog(plex(bot))
