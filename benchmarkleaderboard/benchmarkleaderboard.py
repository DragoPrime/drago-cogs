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
        """Benchmark leaderboard management commands"""
        await ctx.send_help(ctx.command)

    @benchmark.command(name="add")
    async def benchmark_add(self, ctx, benchmark_type: str, score: float):
        """Add a benchmark score
        
        Example: [p]benchmark add cpu 95.5
        """
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

    @benchmark.command(name="view")
    async def benchmark_view(self, ctx, benchmark_type: str):
        """View the leaderboard for a specific benchmark type
        
        Example: [p]benchmark view cpu
        """
        if benchmark_type not in self.leaderboards or not self.leaderboards[benchmark_type]:
            await ctx.send(f"No scores found for {benchmark_type} benchmark.")
            return

        # Sort scores in descending order
        sorted_scores = sorted(
            self.leaderboards[benchmark_type].items(), 
            key=lambda x: x[1], 
            reverse=True
        )

        # Create leaderboard embed
        embed = discord.Embed(
            title=f"{benchmark_type.upper()} Benchmark Leaderboard", 
            color=discord.Color.blue()
        )

        for rank, (user_id, score) in enumerate(sorted_scores[:10], 1):
            try:
                user = await self.bot.fetch_user(user_id)
                embed.add_field(
                    name=f"{rank}. {user.name}", 
                    value=f"Score: {score}", 
                    inline=False
                )
            except discord.NotFound:
                # Skip users who have left the server
                continue

        await ctx.send(embed=embed)

    @benchmark.command(name="types")
    async def benchmark_types(self, ctx):
        """List all available benchmark types
        
        Example: [p]benchmark types
        """
        if not self.leaderboards:
            await ctx.send("No benchmark types have been created yet.")
            return

        types_list = "\n".join(sorted(self.leaderboards.keys()))
        await ctx.send(f"Available benchmark types:\n{types_list}")

    @benchmark.command(name="delete")
    @commands.admin()
    async def benchmark_delete(self, ctx, benchmark_type: str, user: Optional[discord.Member] = None):
        """Delete a benchmark type or a user's score
        
        Example: [p]benchmark delete cpu
        Example: [p]benchmark delete cpu @Username
        """
        if benchmark_type not in self.leaderboards:
            await ctx.send(f"No leaderboard found for {benchmark_type}")
            return

        if user:
            # Delete specific user's score
            if user.id in self.leaderboards[benchmark_type]:
                del self.leaderboards[benchmark_type][user.id]
                await self.config.leaderboards.set(self.leaderboards)
                await ctx.send(f"Deleted {user.name}'s score for {benchmark_type} benchmark")
            else:
                await ctx.send(f"{user.name} has no score for {benchmark_type} benchmark")
        else:
            # Delete entire benchmark type
            del self.leaderboards[benchmark_type]
            await self.config.leaderboards.set(self.leaderboards)
            await ctx.send(f"Deleted entire {benchmark_type} benchmark leaderboard")

    async def cog_load(self):
        """Load leaderboard data when the cog is loaded"""
        self.leaderboards = await self.config.leaderboards() or {}
