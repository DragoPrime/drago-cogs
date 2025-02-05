import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Dict, Optional

class BenchmarkLeaderboard(commands.Cog):
    """A cog to track and display benchmark leaderboards"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        # Define the structure of the configuration
        default_global = {}
        self.config.register_global(**default_global)
        
        # Leaderboard will be stored in memory and periodically saved
        self.leaderboards: Dict[str, Dict[int, float]] = {}

    @commands.group(invoke_without_command=True)
    async def benchmark(self, ctx):
        """Base command for benchmark leaderboards"""
        await ctx.send_help(ctx.command)

    @benchmark.command(name="add")
    async def add_benchmark(self, ctx, benchmark_type: str, score: float):
        """
        Add a benchmark score for the current user
        
        Args:
            benchmark_type: The type of benchmark (e.g., 'cpu', 'gpu', 'memory')
            score: The benchmark score
        """
        # Ensure the leaderboard for this type exists
        if benchmark_type not in self.leaderboards:
            self.leaderboards[benchmark_type] = {}
        
        # Add or update user's score
        user_id = ctx.author.id
        previous_score = self.leaderboards[benchmark_type].get(user_id)
        
        # Determine if this is a new high score
        if previous_score is None or score > previous_score:
            self.leaderboards[benchmark_type][user_id] = score
            await self.save_leaderboard()
            
            if previous_score is None:
                await ctx.send(f"Added new {benchmark_type} benchmark score: {score}")
            else:
                await ctx.send(f"New high score for {benchmark_type}! Updated from {previous_score} to {score}")
        else:
            await ctx.send(f"Your previous score of {previous_score} for {benchmark_type} is higher. Score not updated.")

    @benchmark.command(name="view")
    async def view_leaderboard(self, ctx, benchmark_type: str):
        """
        View the leaderboard for a specific benchmark type
        
        Args:
            benchmark_type: The type of benchmark to view
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
    async def list_benchmark_types(self, ctx):
        """List all available benchmark types"""
        if not self.leaderboards:
            await ctx.send("No benchmark types have been created yet.")
            return

        types_list = "\n".join(sorted(self.leaderboards.keys()))
        await ctx.send(f"Available benchmark types:\n{types_list}")

    @benchmark.command(name="delete")
    @commands.admin()
    async def delete_benchmark(self, ctx, benchmark_type: str, user: Optional[discord.Member] = None):
        """
        Delete a benchmark type or a user's score
        
        Args:
            benchmark_type: The benchmark type to delete
            user: Optional user to remove from the leaderboard
        """
        if benchmark_type not in self.leaderboards:
            await ctx.send(f"No leaderboard found for {benchmark_type}")
            return

        if user:
            # Delete specific user's score
            if user.id in self.leaderboards[benchmark_type]:
                del self.leaderboards[benchmark_type][user.id]
                await self.save_leaderboard()
                await ctx.send(f"Deleted {user.name}'s score for {benchmark_type} benchmark")
            else:
                await ctx.send(f"{user.name} has no score for {benchmark_type} benchmark")
        else:
            # Delete entire benchmark type
            del self.leaderboards[benchmark_type]
            await self.save_leaderboard()
            await ctx.send(f"Deleted entire {benchmark_type} benchmark leaderboard")

    async def save_leaderboard(self):
        """Save the current leaderboard state"""
        await self.config.set(self.leaderboards)

    async def load_leaderboard(self):
        """Load the leaderboard from config"""
        loaded_data = await self.config.get_raw()
        self.leaderboards = loaded_data if loaded_data else {}

    def cog_load(self):
        """Called when the cog is loaded"""
        self.bot.loop.create_task(self.load_leaderboard())

def setup(bot: Red):
    """Add the cog to the bot"""
    bot.add_cog(BenchmarkLeaderboard(bot))
