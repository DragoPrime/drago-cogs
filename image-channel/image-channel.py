import discord
from discord.ext import commands

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
        await channel.edit(topic="This channel is now restricted to image-only messages "
                                 "and public thread replies. Any non-image messages will be removed. "
                                 "To respond to an image, please use the 'start thread' button and "
                                 "post your message as a public reply.")

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
        await ctx.send("This channel has been updated to restrict to image-only messages and public thread replies. "
                       "To undo this and allow regular messages, use !images_only command again.")

    def cog_unload(self):
        # Remove message filter and thread creation handlers
        self.bot.remove_message_filter(self.image_filter)
        self.bot.remove_thread_created_handler(self.thread_created)

def setup(bot):
    bot.add_cog(ImagesOnly(bot))
