from .plex import PlexInvite


async def setup(bot):
    await bot.add_cog(PlexInvite(bot))
