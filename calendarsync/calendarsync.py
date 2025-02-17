import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
import pytz
import base64
from typing import Optional

class CalendarSync(commands.Cog):
    """Sync Discord events to Google Calendar"""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "calendar_id": None,
            "credentials": None,  # Stored as base64 encoded string
            "timezone": "UTC"
        }
        self.config.register_guild(**default_guild)
        self._calendar_service_cache = {}  # Cache for calendar service objects
        
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self._calendar_service_cache.clear()

    @commands.group()
    @commands.admin_or_permissions(manage_guild=True)
    async def calendarset(self, ctx):
        """Calendar settings"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @calendarset.command()
    async def setcalendar(self, ctx, calendar_id: str):
        """Set the Google Calendar ID"""
        await self.config.guild(ctx.guild).calendar_id.set(calendar_id)
        await ctx.send(f"Calendar ID set to: {calendar_id}")
        await self.verify_settings(ctx)

    @calendarset.command()
    async def credentials(self, ctx):
        """Set Google service account credentials"""
        await ctx.send("Please send your Google service account credentials JSON as a file attachment in the next message.")
        
        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel and msg.attachments
            
        try:
            msg = await self.bot.wait_for('message', timeout=60.0, check=check)
            if not msg.attachments:
                return await ctx.send("No file attachment found.")
                
            attachment = msg.attachments[0]
            if not attachment.filename.endswith('.json'):
                return await ctx.send("Please provide a JSON file.")
                
            credentials_content = await attachment.read()
            # Encode credentials as base64 for storage
            encoded_credentials = base64.b64encode(credentials_content).decode('utf-8')
            
            # Test the credentials before saving
            try:
                self.get_calendar_service(encoded_credentials)
                await self.config.guild(ctx.guild).credentials.set(encoded_credentials)
                # Delete the message containing the credentials for security
                await msg.delete()
                await ctx.send("Credentials verified and saved successfully!")
                await self.verify_settings(ctx)
            except Exception as e:
                await ctx.send(f"Error validating credentials: {str(e)}")
        except TimeoutError:
            await ctx.send("Timed out waiting for credentials file.")

    @calendarset.command()
    async def settimezone(self, ctx, timezone: str):
        """Set the timezone for events (e.g. 'America/New_York')"""
        try:
            pytz.timezone(timezone)
            await self.config.guild(ctx.guild).timezone.set(timezone)
            await ctx.send(f"Timezone set to: {timezone}")
            await self.verify_settings(ctx)
        except pytz.exceptions.UnknownTimeZoneError:
            await ctx.send("Invalid timezone. Please use a valid timezone name.")

    @calendarset.command()
    async def verify(self, ctx):
        """Verify calendar settings and credentials"""
        await self.verify_settings(ctx)

    @calendarset.command()
    async def settings(self, ctx):
        """Show current calendar settings"""
        config = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(title="Calendar Sync Settings", color=discord.Color.blue())
        embed.add_field(
            name="Calendar ID", 
            value=config['calendar_id'] or "Not set",
            inline=False
        )
        embed.add_field(
            name="Timezone", 
            value=config['timezone'],
            inline=False
        )
        embed.add_field(
            name="Credentials", 
            value="✅ Set" if config['credentials'] else "❌ Not set",
            inline=False
        )
        
        await ctx.send(embed=embed)

    async def verify_settings(self, ctx) -> bool:
        """Verify all settings are correct and working"""
        config = await self.config.guild(ctx.guild).all()
        
        if not config['calendar_id']:
            await ctx.send("❌ Calendar ID not set. Use `calendarset setcalendar` to set it.")
            return False
            
        if not config['credentials']:
            await ctx.send("❌ Credentials not set. Use `calendarset credentials` to set them.")
            return False
            
        try:
            service = self.get_calendar_service(config['credentials'])
            # Test calendar access
            service.calendars().get(calendarId=config['calendar_id']).execute()
            await ctx.send("✅ All settings verified! Calendar sync is ready to use.")
            return True
        except Exception as e:
            await ctx.send(f"❌ Error verifying calendar access: {str(e)}")
            return False

    def get_calendar_service(self, credentials_content: str) -> Optional[object]:
        """Create and return Google Calendar service"""
        try:
            # Check if we have a cached service for these credentials
            if credentials_content in self._calendar_service_cache:
                return self._calendar_service_cache[credentials_content]
            
            # Decode base64 credentials
            credentials_dict = json.loads(base64.b64decode(credentials_content).decode('utf-8'))
            
            credentials = service_account.Credentials.from_service_account_info(
                credentials_dict,
                scopes=[
                    'https://www.googleapis.com/auth/calendar',  # Full access to all calendars
                    'https://www.googleapis.com/auth/calendar.events'  # Access to calendar events
                ]
            )
            
            service = build('calendar', 'v3', credentials=credentials)
            
            # Cache the service
            self._calendar_service_cache[credentials_content] = service
            return service
        except Exception as e:
            print(f"Error creating calendar service: {e}")
            raise

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        """Listen for new Discord scheduled events"""
        guild_config = await self.config.guild(event.guild).all()
        
        if not all([guild_config['calendar_id'], guild_config['credentials']]):
            return
        
        try:
            service = self.get_calendar_service(guild_config['credentials'])
            
            tz = pytz.timezone(guild_config['timezone'])
            start_time = event.start_time.astimezone(tz)
            end_time = event.end_time.astimezone(tz) if event.end_time else start_time + timedelta(hours=1)
            
            calendar_event = {
                'summary': event.name,
                'description': f"{event.description}\n\nDiscord Event: {event.url}",
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': guild_config['timezone'],
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': guild_config['timezone'],
                },
                'location': event.location or "Discord",
                'extendedProperties': {
                    'private': {
                        'discord_event_id': str(event.id)
                    }
                }
            }
            
            created_event = service.events().insert(
                calendarId=guild_config['calendar_id'],
                body=calendar_event
            ).execute()
            
            print(f"Created calendar event: {created_event.get('htmlLink')}")
            
        except Exception as error:
            print(f"An error occurred: {error}")

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent):
        """Handle Discord event updates"""
        guild_config = await self.config.guild(after.guild).all()
        
        if not all([guild_config['calendar_id'], guild_config['credentials']]):
            return
            
        try:
            service = self.get_calendar_service(guild_config['credentials'])
            
            # Search for existing event
            events_result = service.events().list(
                calendarId=guild_config['calendar_id'],
                privateExtendedProperty=f'discord_event_id={str(after.id)}'
            ).execute()
            
            if not events_result.get('items', []):
                return
                
            calendar_event = events_result['items'][0]
            
            # Update event details
            tz = pytz.timezone(guild_config['timezone'])
            start_time = after.start_time.astimezone(tz)
            end_time = after.end_time.astimezone(tz) if after.end_time else start_time + timedelta(hours=1)
            
            calendar_event.update({
                'summary': after.name,
                'description': f"{after.description}\n\nDiscord Event: {after.url}",
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': guild_config['timezone'],
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': guild_config['timezone'],
                },
                'location': after.location or "Discord"
            })
            
            updated_event = service.events().update(
                calendarId=guild_config['calendar_id'],
                eventId=calendar_event['id'],
                body=calendar_event
            ).execute()
            
            print(f"Updated calendar event: {updated_event.get('htmlLink')}")
            
        except Exception as error:
            print(f"An error occurred during update: {error}")

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        """Handle Discord event deletions"""
        guild_config = await self.config.guild(event.guild).all()
        
        if not all([guild_config['calendar_id'], guild_config['credentials']]):
            return
            
        try:
            service = self.get_calendar_service(guild_config['credentials'])
            
            # Search for existing event
            events_result = service.events().list(
                calendarId=guild_config['calendar_id'],
                privateExtendedProperty=f'discord_event_id={str(event.id)}'
            ).execute()
            
            if not events_result.get('items', []):
                return
                
            calendar_event = events_result['items'][0]
            
            # Delete the calendar event
            service.events().delete(
                calendarId=guild_config['calendar_id'],
                eventId=calendar_event['id']
            ).execute()
            
            print(f"Deleted calendar event for Discord event {event.id}")
            
        except Exception as error:
            print(f"An error occurred during deletion: {error}")
