from .jellyfin_recommendation import JellyfinRecommendation

async def setup(bot):
    await bot.add_cog(JellyfinRecommendation(bot))
