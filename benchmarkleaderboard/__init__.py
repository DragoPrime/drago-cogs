async def setup(bot):
    from .benchmarkleaderboard import BenchmarkLeaderboard
    await bot.add_cog(BenchmarkLeaderboard(bot))
