from .jellyfin_new_content import JellyfinNewContent

async def setup(bot):
    await bot.add_cog(JellyfinNewContent(bot))
