from .jellyfinmanager import JellyfinCog

async def setup(bot):
    """Setup function pentru încărcarea cog-ului"""
    cog = JellyfinCog(bot)
    await bot.add_cog(cog)
