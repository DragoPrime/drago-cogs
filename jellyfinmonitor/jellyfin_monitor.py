import json
import datetime
from typing import Dict, List, Optional
import aiohttp
import asyncio
import discord

from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

class JellyfinMonitor(commands.Cog):
    """Monitor Jellyfin user activity and send notifications for inactive users."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5349763482, force_registration=True)
        
        default_guild = {
            "jellyfin_url": "",
            "api_key": "",
            "notification_channel": None,
            "check_interval_hours": 24,  # Check once per day by default
            "last_check": None,
            "inactive_user_records": {}  # To store when users were first detected as inactive
        }
        
        self.config.register_guild(**default_guild)
        self.task = self.bot.loop.create_task(self.check_inactive_users_loop())
    
    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        if self.task:
            self.task.cancel()
    
    @commands.group(name="jellyfinmon")
    @checks.admin_or_permissions(manage_guild=True)
    async def _jellyfinmon(self, ctx: commands.Context):
        """Commands to configure the Jellyfin monitor."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()
    
    @_jellyfinmon.command(name="setup")
    async def _setup(self, ctx: commands.Context, jellyfin_url: str, api_key: str, notification_channel: discord.TextChannel = None):
        """
        Set up the Jellyfin monitor.
        
        Parameters:
        - jellyfin_url: Your Jellyfin server URL (e.g., http://192.168.1.100:8096)
        - api_key: Your Jellyfin API key
        - notification_channel: The channel to send notifications to (optional)
        """
        # Store configuration
        await self.config.guild(ctx.guild).jellyfin_url.set(jellyfin_url.rstrip("/"))
        await self.config.guild(ctx.guild).api_key.set(api_key)
        
        if notification_channel:
            await self.config.guild(ctx.guild).notification_channel.set(notification_channel.id)
        
        await ctx.send(f"Jellyfin monitor configured. Server: {jellyfin_url}")
        
        # Test connection
        async with aiohttp.ClientSession() as session:
            try:
                result = await self._test_jellyfin_connection(ctx.guild, session)
                if result:
                    await ctx.send("Connection to Jellyfin server is working! 🎉")
                else:
                    await ctx.send("Failed to connect to Jellyfin server. Please check your URL and API key.")
            except Exception as e:
                await ctx.send(f"Error connecting to Jellyfin server: {str(e)}")
    
    @_jellyfinmon.command(name="channel")
    async def _set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the notification channel."""
        await self.config.guild(ctx.guild).notification_channel.set(channel.id)
        await ctx.send(f"Notification channel set to {channel.mention}")
    
    @_jellyfinmon.command(name="interval")
    async def _set_interval(self, ctx: commands.Context, hours: int):
        """Set how often to check for inactive users (in hours)."""
        if hours < 1:
            await ctx.send("Interval must be at least 1 hour.")
            return
        
        await self.config.guild(ctx.guild).check_interval_hours.set(hours)
        await ctx.send(f"Check interval set to {hours} hours.")
    
    @_jellyfinmon.command(name="check")
    async def _check_now(self, ctx: commands.Context):
        """Manually check for inactive Jellyfin users now."""
        # Get guild config
        config_data = await self.config.guild(ctx.guild).all()
        
        if not config_data["jellyfin_url"] or not config_data["api_key"]:
            await ctx.send("Jellyfin monitor is not configured. Use `[p]jellyfinmon setup` first.")
            return
        
        await ctx.send("Checking for inactive Jellyfin users...")
        
        try:
            inactive_users = await self._check_inactive_users(ctx.guild)
            
            if not inactive_users["30_days"] and not inactive_users["60_days"]:
                await ctx.send("No inactive users found.")
                return
            
            # Send report to the current channel
            await self._send_inactive_report(ctx.channel, inactive_users)
            
        except Exception as e:
            await ctx.send(f"Error checking inactive users: {str(e)}")
    
    @_jellyfinmon.command(name="status")
    async def _status(self, ctx: commands.Context):
        """Show current Jellyfin monitor configuration."""
        config_data = await self.config.guild(ctx.guild).all()
        
        if not config_data["jellyfin_url"] or not config_data["api_key"]:
            await ctx.send("Jellyfin monitor is not configured. Use `[p]jellyfinmon setup` first.")
            return
        
        # Create embed
        embed = discord.Embed(
            title="Jellyfin Monitor Status",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Jellyfin Server", 
            value=config_data["jellyfin_url"],
            inline=False
        )
        
        channel_id = config_data["notification_channel"]
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        embed.add_field(
            name="Notification Channel",
            value=channel.mention if channel else "Not set",
            inline=True
        )
        
        embed.add_field(
            name="Check Interval",
            value=f"{config_data['check_interval_hours']} hours",
            inline=True
        )
        
        last_check = config_data["last_check"]
        if last_check:
            last_check_time = datetime.datetime.fromtimestamp(last_check)
            embed.add_field(
                name="Last Check",
                value=f"{last_check_time.strftime('%Y-%m-%d %H:%M:%S')}",
                inline=True
            )
        else:
            embed.add_field(
                name="Last Check", 
                value="Never", 
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    async def _test_jellyfin_connection(self, guild, session):
        """Test connection to Jellyfin server."""
        config_data = await self.config.guild(guild).all()
        
        url = f"{config_data['jellyfin_url']}/Users"
        headers = {
            "X-MediaBrowser-Token": config_data["api_key"]
        }
        
        async with session.get(url, headers=headers) as response:
            return response.status == 200
    
    async def _get_jellyfin_users(self, guild, session):
        """Get all users from Jellyfin server."""
        config_data = await self.config.guild(guild).all()
        
        url = f"{config_data['jellyfin_url']}/Users"
        headers = {
            "X-MediaBrowser-Token": config_data["api_key"]
        }
        
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                users = await response.json()
                return users
            else:
                return None
    
    async def _check_inactive_users(self, guild):
        """Check for inactive users and return results."""
        config_data = await self.config.guild(guild).all()
        inactive_records = config_data["inactive_user_records"] or {}
        
        now = datetime.datetime.now()
        thirty_days_ago = now - datetime.timedelta(days=30)
        sixty_days_ago = now - datetime.timedelta(days=60)
        
        # Store users that are inactive for different thresholds
        inactive_results = {
            "30_days": [],
            "60_days": []
        }
        
        # Get all users from Jellyfin
        async with aiohttp.ClientSession() as session:
            users = await self._get_jellyfin_users(guild, session)
            
            if not users:
                return inactive_results
            
            for user in users:
                user_id = user["Id"]
                name = user["Name"]
                
                # Check last activity date
                last_activity_date = None
                if "LastActivityDate" in user:
                    last_activity_date = datetime.datetime.fromisoformat(
                        user["LastActivityDate"].replace("Z", "+00:00")
                    )
                
                if not last_activity_date:
                    # If no activity date, check if we've already recorded them
                    if user_id in inactive_records:
                        first_noticed = datetime.datetime.fromtimestamp(inactive_records[user_id])
                        days_inactive = (now - first_noticed).days + 30  # Add 30 days since that's when we first noticed
                        
                        if days_inactive >= 60:
                            inactive_results["60_days"].append({
                                "id": user_id,
                                "name": name,
                                "last_activity": None,
                                "days_inactive": days_inactive
                            })
                        elif days_inactive >= 30:
                            inactive_results["30_days"].append({
                                "id": user_id,
                                "name": name,
                                "last_activity": None,
                                "days_inactive": days_inactive
                            })
                    else:
                        # First time seeing this user inactive, record them
                        inactive_records[user_id] = now.timestamp()
                        
                        # Add to 30-day list
                        inactive_results["30_days"].append({
                            "id": user_id,
                            "name": name,
                            "last_activity": None,
                            "days_inactive": "Unknown (30+)"
                        })
                else:
                    # If there is activity date, check against our thresholds
                    if last_activity_date <= sixty_days_ago:
                        days_inactive = (now - last_activity_date).days
                        inactive_results["60_days"].append({
                            "id": user_id,
                            "name": name,
                            "last_activity": last_activity_date,
                            "days_inactive": days_inactive
                        })
                    elif last_activity_date <= thirty_days_ago:
                        days_inactive = (now - last_activity_date).days
                        inactive_results["30_days"].append({
                            "id": user_id,
                            "name": name,
                            "last_activity": last_activity_date,
                            "days_inactive": days_inactive
                        })
                    else:
                        # User is active, remove from inactive records if present
                        if user_id in inactive_records:
                            del inactive_records[user_id]
        
        # Update inactive records
        await self.config.guild(guild).inactive_user_records.set(inactive_records)
        await self.config.guild(guild).last_check.set(now.timestamp())
        
        return inactive_results
    
    async def _send_inactive_report(self, channel, inactive_users):
        """Send a report of inactive users to the specified channel."""
        if not inactive_users["30_days"] and not inactive_users["60_days"]:
            return
        
        embed = discord.Embed(
            title="Jellyfin Inactive Users Report",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now()
        )
        
        # Add 60+ days inactive users (more critical)
        if inactive_users["60_days"]:
            users_list = ""
            for user in inactive_users["60_days"]:
                if user["last_activity"]:
                    last_activity = user["last_activity"].strftime("%Y-%m-%d")
                    users_list += f"• **{user['name']}** - {user['days_inactive']} days (Last: {last_activity})\n"
                else:
                    users_list += f"• **{user['name']}** - {user['days_inactive']} days\n"
            
            embed.add_field(
                name="⚠️ Inactive for 60+ days",
                value=users_list,
                inline=False
            )
        
        # Add 30-60 days inactive users
        thirty_day_users = [u for u in inactive_users["30_days"] if u["id"] not in [u2["id"] for u2 in inactive_users["60_days"]]]
        if thirty_day_users:
            users_list = ""
            for user in thirty_day_users:
                if user["last_activity"]:
                    last_activity = user["last_activity"].strftime("%Y-%m-%d")
                    users_list += f"• **{user['name']}** - {user['days_inactive']} days (Last: {last_activity})\n"
                else:
                    users_list += f"• **{user['name']}** - {user['days_inactive']} days\n"
            
            embed.add_field(
                name="ℹ️ Inactive for 30+ days",
                value=users_list,
                inline=False
            )
        
        await channel.send(embed=embed)
    
    async def check_inactive_users_loop(self):
        """Background loop to check for inactive users periodically."""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                # Check all guilds where this cog is active
                for guild_id in await self.config.all_guilds():
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue
                    
                    config_data = await self.config.guild(guild).all()
                    
                    # Skip if not configured
                    if not config_data["jellyfin_url"] or not config_data["api_key"]:
                        continue
                    
                    # Skip if no notification channel set
                    channel_id = config_data["notification_channel"]
                    if not channel_id:
                        continue
                    
                    # Check if it's time to run again
                    last_check = config_data["last_check"]
                    interval_hours = config_data["check_interval_hours"]
                    
                    now = datetime.datetime.now().timestamp()
                    if last_check and (now - last_check) < (interval_hours * 3600):
                        continue  # Not time to check yet
                    
                    # Check for inactive users
                    inactive_users = await self._check_inactive_users(guild)
                    
                    # Send notifications if there are inactive users
                    if inactive_users["30_days"] or inactive_users["60_days"]:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            await self._send_inactive_report(channel, inactive_users)
            
            except Exception as e:
                # Log errors but don't halt the loop
                print(f"Error in Jellyfin monitor task: {str(e)}")
            
            # Sleep before next check
            await asyncio.sleep(3600)  # Check every hour if it's time to run

# Această funcție este acum în __init__.py pentru a fi compatibilă cu Red v3.5
# def setup(bot):
#     """Add the cog to the bot."""
#     bot.add_cog(JellyfinMonitor(bot))
