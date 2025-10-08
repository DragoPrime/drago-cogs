from .jellyfin_porn_recommendation import JellyfinPornRecommendation

async def setup(bot):
    await bot.add_cog(JellyfinPornRecommendation(bot))
