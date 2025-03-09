import discord
import anthropic
import asyncio
import logging
from typing import Optional, List
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box

log = logging.getLogger("red.claudeai")

__version__ = "1.0.0"

class ClaudeAI(commands.Cog):
    """Claude AI integration for Red Discord Bot"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8675309, force_registration=True)
        
        default_global = {
            "api_key": None,
            "model": "claude-3-7-sonnet-20250219",
            "max_tokens": 800,  # Reduced from 1000 for more concise responses
            "temperature": 0.7,
            "enabled_channels": [],
            "system_prompt": "You are Claude, an AI assistant created by Anthropic, now helping users in a Discord server. Your responses should be helpful, accurate, and CONCISE. Avoid lengthy explanations unless specifically requested. Keep your answers brief and to the point."
        }
        
        self.config.register_global(**default_global)
        self.client = None
        self.listening_channels = set()
        self._init_task = asyncio.create_task(self._initialize())
        
    async def _initialize(self):
        """Initialize the cog and set up the Anthropic client"""
        api_key = await self.config.api_key()
        if api_key:
            self.client = anthropic.Anthropic(api_key=api_key)
            self.listening_channels = set(await self.config.enabled_channels())
        
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        if self._init_task:
            self._init_task.cancel()
    
    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def claude(self, ctx: commands.Context):
        """Claude AI settings and commands"""
        pass
    
    @claude.command(name="setapikey")
    @checks.is_owner()
    async def set_api_key(self, ctx: commands.Context, api_key: str):
        """Set the Claude API key"""
        await self.config.api_key.set(api_key)
        self.client = anthropic.Anthropic(api_key=api_key)
        
        # Delete the command message for security
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass
            
        await ctx.send("API key set. Run this command in DMs for security.")
    
    @claude.command(name="setmodel")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_model(self, ctx: commands.Context, model_name: str):
        """Set the Claude model to use"""
        await self.config.model.set(model_name)
        await ctx.send(f"Model set to: {model_name}")
    
    @claude.command(name="setprompt")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_prompt(self, ctx: commands.Context, *, system_prompt: str):
        """Set the system prompt for Claude"""
        await self.config.system_prompt.set(system_prompt)
        await ctx.send("System prompt updated.")
    
    @claude.command(name="concise")
    @checks.admin_or_permissions(manage_guild=True)
    async def set_concise(self, ctx: commands.Context, enabled: bool = True):
        """Enable or disable concise response mode"""
        if enabled:
            prompt = "You are Claude, an AI assistant created by Anthropic, now helping users in a Discord server. Your responses should be helpful, accurate, and CONCISE. Avoid lengthy explanations unless specifically requested. Keep your answers brief and to the point."
            max_tokens = 800
            await ctx.send("Concise mode enabled.")
        else:
            prompt = "You are Claude, an AI assistant created by Anthropic, now helping users in a Discord server. Keep responses helpful and friendly."
            max_tokens = 1000
            await ctx.send("Concise mode disabled.")
            
        await self.config.system_prompt.set(prompt)
        await self.config.max_tokens.set(max_tokens)
    
    @claude.command(name="addchannel")
    @checks.admin_or_permissions(manage_guild=True)
    async def add_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Enable Claude AI in a specific channel"""
        channel = channel or ctx.channel
        
        enabled_channels = await self.config.enabled_channels()
        if channel.id in enabled_channels:
            return await ctx.send(f"Claude AI already enabled in {channel.mention}")
        
        enabled_channels.append(channel.id)
        await self.config.enabled_channels.set(enabled_channels)
        self.listening_channels.add(channel.id)
        
        await ctx.send(f"Claude AI enabled in {channel.mention}")
    
    @claude.command(name="removechannel")
    @checks.admin_or_permissions(manage_guild=True)
    async def remove_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Disable Claude AI in a specific channel"""
        channel = channel or ctx.channel
        
        enabled_channels = await self.config.enabled_channels()
        if channel.id not in enabled_channels:
            return await ctx.send(f"Claude AI not enabled in {channel.mention}")
        
        enabled_channels.remove(channel.id)
        await self.config.enabled_channels.set(enabled_channels)
        self.listening_channels.discard(channel.id)
        
        await ctx.send(f"Claude AI disabled in {channel.mention}")
    
    @claude.command(name="listchannels")
    @checks.admin_or_permissions(manage_guild=True)
    async def list_channels(self, ctx: commands.Context):
        """List all channels where Claude AI is enabled"""
        enabled_channels = await self.config.enabled_channels()
        
        if not enabled_channels:
            return await ctx.send("Claude AI not enabled in any channels.")
        
        channel_mentions = []
        for channel_id in enabled_channels:
            channel = self.bot.get_channel(channel_id)
            if channel:
                channel_mentions.append(channel.mention)
            else:
                # Channel no longer exists, remove it from config
                enabled_channels.remove(channel_id)
                
        await self.config.enabled_channels.set(enabled_channels)
        
        if channel_mentions:
            await ctx.send(f"Claude AI enabled in: {', '.join(channel_mentions)}")
        else:
            await ctx.send("Claude AI not enabled in any valid channels.")
    
    @claude.command(name="settings")
    @checks.admin_or_permissions(manage_guild=True)
    async def show_settings(self, ctx: commands.Context):
        """Show current Claude AI settings"""
        settings = {
            "Model": await self.config.model(),
            "Max Tokens": await self.config.max_tokens(),
            "Temperature": await self.config.temperature(),
            "API Key Set": bool(await self.config.api_key()),
            "System Prompt": await self.config.system_prompt()
        }
        
        message = ["**Claude AI Settings:**"]
        for key, value in settings.items():
            if key == "API Key Set":
                message.append(f"{key}: {'Yes' if value else 'No'}")
            elif key == "System Prompt":
                # Truncate long prompts
                if len(str(value)) > 100:
                    message.append(f"{key}: {str(value)[:100]}...")
                else:
                    message.append(f"{key}: {value}")
            else:
                message.append(f"{key}: {value}")
        
        await ctx.send("\n".join(message))
    
    @claude.command(name="ask")
    async def ask_claude(self, ctx: commands.Context, *, question: str):
        """Ask Claude AI a question directly"""
        if not self.client:
            return await ctx.send("Claude API not configured. Set API key first.")
            
        async with ctx.typing():
            try:
                response = await self._get_claude_response(question)
                
                # Split response if it's too long
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    # Split into chunks of 2000 characters
                    chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                    for chunk in chunks:
                        await ctx.send(chunk)
                        await asyncio.sleep(1)  # Avoid rate limits
                        
            except Exception as e:
                log.error(f"Error getting response from Claude: {e}")
                await ctx.send(f"Error: {e}")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Respond to messages in enabled channels"""
        # Ignore messages from bots, including self
        if message.author.bot:
            return
            
        # Check if this is an enabled channel
        if message.channel.id not in self.listening_channels:
            return
            
        # Ignore commands
        if await self.bot.is_command(message):
            return
            
        # Check if we're mentioned or the message starts with "claude"
        bot_mentioned = self.bot.user in message.mentions
        starts_with_claude = message.content.lower().startswith("claude")
        
        if not (bot_mentioned or starts_with_claude):
            return
            
        # Remove bot mention and "claude" prefix from the message
        content = message.content
        if bot_mentioned:
            content = content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "")
        if starts_with_claude:
            content = content.replace("claude", "", 1).replace("Claude", "", 1)
            
        content = content.strip()
        if not content:
            return
            
        # Let the user know we're processing
        async with message.channel.typing():
            try:
                response = await self._get_claude_response(content)
                
                # Split response if it's too long
                if len(response) <= 2000:
                    await message.reply(response)
                else:
                    # Split into chunks of 2000 characters
                    chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                    first = True
                    for chunk in chunks:
                        if first:
                            await message.reply(chunk)
                            first = False
                        else:
                            await message.channel.send(chunk)
                        await asyncio.sleep(1)  # Avoid rate limits
                        
            except Exception as e:
                log.error(f"Error getting response from Claude: {e}")
                await message.reply(f"Error: {e}")
    
    async def _get_claude_response(self, user_message: str) -> str:
        """Get a response from Claude API"""
        if not self.client:
            raise ValueError("Claude API client not initialized")
            
        model = await self.config.model()
        max_tokens = await self.config.max_tokens()
        temperature = await self.config.temperature()
        system_prompt = await self.config.system_prompt()
        
        try:
            # Create a message and get the response
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            
            return response.content[0].text
            
        except Exception as e:
            log.error(f"Error in Claude API call: {e}")
            raise
