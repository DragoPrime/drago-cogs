from .plex import plexinvite


async def setup(bot):
    await bot.add_cog(plexinvite(bot))
