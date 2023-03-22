
import discord
from redbot.core import Config, checks, commands

class ImagesOnly(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def images_only(self, ctx):
        """Restrict channel to image-only messages and public thread replies."""
        channel = ctx.channel

        # Set channel permissions to disallow message sending for everyone
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

        # Set channel topic to provide instructions to users
        await channel.edit(topic="Acest canal este acum limitat la mesaje doar cu imagini "
                                 "și răspunsuri publice. Orice mesaje care nu sunt imagini vor fi eliminate. "
                                 "Pentru a răspunde la o imagine, vă rugăm să utilizați butonul <<începe fir>> și "
                                 "postați mesajul dvs. ca răspuns public.")

        # Define a message filter to remove non-image messages
        def image_filter(message):
            return message.author != self.bot.user and not message.attachments

        # Define a thread creation handler to restrict thread replies to public
        async def thread_created(thread):
            overwrite = thread.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = False
            await thread.set_permissions(ctx.guild.default_role, overwrite=overwrite)

        # Start message filter and thread creation handlers
        self.bot.add_message_filter(channel, image_filter)
        self.bot.add_thread_created_handler(channel, thread_created)

        # Confirm the channel update to the user
        await ctx.send("Acest canal a fost actualizat pentru a restricționa mesajele doar cu imagini și răspunsuri doar prin fire publice. "
                       "Pentru a anula acest lucru și a permite mesajele obișnuite, utilizați din nou comanda [p]images_only.")

    def cog_unload(self):
        # Remove message filter and thread creation handlers
        self.bot.remove_message_filter(self.image_filter)
        self.bot.remove_thread_created_handler(self.thread_created)
