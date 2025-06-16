from .hedone_recommendation import HedoneRecommendation

async def setup(bot):
    await bot.add_cog(HedoneRecommendation(bot))
