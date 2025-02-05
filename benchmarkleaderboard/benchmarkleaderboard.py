from redbot.core import commands, Config
import discord
from typing import Dict, Optional

class BenchmarkLeaderboard(commands.Cog):
    """A cog to track and display benchmark leaderboards"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_global(leaderboards={})
        self.leaderboards: Dict[str, Dict[int, float]] = {}

    @commands.group(invoke_without_command=True)
    async def benchmark(self, ctx):
        """Base command for benchmark leaderboards"""
        await ctx.send_help(ctx.command)

    @benchmark.command(name="add")
    async def add_benchmark(self, ctx, benchmark_type: str, score: float):
        """Add a benchmark score"""
        if benchmark_type not in self.leaderboards:
            self.leaderboards[benchmark_type] = {}
        
        user_id = ctx.author.id
        previous_score = self.leaderboards[benchmark_type].get(user_id)
        
        if previous_score is None or score > previous_score:
            self.leaderboards[benchmark_type][user_id] = score
            await self.config.leaderboards.set(self.leaderboards)
            
            response = (f"Added new {benchmark_type} benchmark score: {score}" 
                        if previous_score is None 
                        else f"New high score for {benchmark_type}! Updated from {previous_score} to {score}")
            await ctx.send(response)
        else:
            await ctx.send(f"Your previous score of {previous_score} for {benchmark_type} is higher. Score not updated.")

    async def cog_load(self):
        """Load leaderboard data when the cog is loaded"""
        self.leaderboards = await self.config.leaderboards() or {}

def setup(bot):
    return bot.add_cog(BenchmarkLeaderboard(bot))
