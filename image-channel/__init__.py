from .imagechannel import ImagesOnly


def setup(bot):
    bot.add_cog(ImagesOnly(bot))
