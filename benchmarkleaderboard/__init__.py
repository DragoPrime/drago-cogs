def setup(bot):
    from .benchmarkleaderboard import BenchmarkLeaderboard
    return bot.add_cog(BenchmarkLeaderboard(bot))
