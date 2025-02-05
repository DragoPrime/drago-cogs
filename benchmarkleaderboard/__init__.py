from .benchmarkleaderboard import BenchmarkLeaderboard

def setup(bot):
    bot.add_cog(BenchmarkLeaderboard(bot))
