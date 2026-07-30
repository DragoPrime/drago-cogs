from .ollamachat import OllamaChat


async def setup(bot):
    cog = OllamaChat(bot)
    await bot.add_cog(cog)
