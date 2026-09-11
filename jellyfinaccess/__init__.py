from .jellyfinaccess import JellyfinAccess


async def setup(bot):
    await bot.add_cog(JellyfinAccess(bot))
