from .plex import PlexCog


async def setup(bot):
    await bot.add_cog(PlexCog(bot))
