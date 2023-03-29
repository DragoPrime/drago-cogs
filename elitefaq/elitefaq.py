import discord
from discord.ext import commands

class EliteFAQ(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
@commands.command()
async def hello(self, ctx):
    embed = discord.Embed(title="Hello, {}!".format(ctx.author.name))
    await ctx.send(embed=embed)
    
@commands.command()
async def avatar(self, ctx, user: discord.Member = None):
    if not user:
        user = ctx.author
    embed = discord.Embed(title="{}'s Avatar".format(user.name))
    embed.set_image(url=user.avatar_url)
    await ctx.send(embed=embed)
    
def setup(bot):
    bot.add_cog(EliteFAQ(bot))
