from .jellyfincog import JellyfinCog

def setup(bot):
    bot.add_cog(JellyfinCog(bot))
