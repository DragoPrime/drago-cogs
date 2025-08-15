from .gemini_cog import GeminiCog

async def setup(bot):
    await bot.add_cog(GeminiCog(bot))
