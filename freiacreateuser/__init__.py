from .freia import FreiaUsers

def setup(bot):
    bot.add_cog(FreiaUsers(bot))
