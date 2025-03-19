from redbot.core import commands, Config
import asyncio
import aiohttp
import discord
from datetime import datetime, timedelta

class JellyfinNewContent(commands.Cog):
    """Announces new movies and TV shows added to Jellyfin"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=273845109,  # Unique identifier for this cog
            force_registration=True
        )
        
        # Default settings
        default_guild = {
            "base_url": None,
            "api_key": None,
            "announcement_channel_id": None,
            "tmdb_api_key": None,
            "check_interval": 6,  # Hours between checks
            "last_check": None    # Timestamp of last check
        }
        
        self.config.register_guild(**default_guild)
        self.bg_task = None
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.poster_base_url = "https://image.tmdb.org/t/p/w500"
        self.start_tasks()

    def start_tasks(self):
        self.bg_task = self.bot.loop.create_task(self.check_new_content_loop())
        
    def cog_unload(self):
        if self.bg_task:
            self.bg_task.cancel()

    async def check_new_content_loop(self):
        """Background loop to check for new content"""
        await self.bot.wait_until_ready()
        while True:
            try:
                all_guilds = await self.config.all_guilds()
                for guild_id, settings in all_guilds.items():
                    if all(k in settings and settings[k] for k in ['base_url', 'api_key', 'announcement_channel_id']):
                        guild = self.bot.get_guild(guild_id)
                        if guild:
                            await self.check_and_announce_new_content(guild)
            except Exception as e:
                print(f"Error in check_new_content_loop: {e}")
            
            # Sleep based on the shortest check interval across all guilds
            min_interval = 6  # Default 6 hours
            for _, settings in all_guilds.items():
                if 'check_interval' in settings and settings['check_interval'] > 0:
                    min_interval = min(min_interval, settings['check_interval'])
            
            # Convert hours to seconds
            await asyncio.sleep(min_interval * 3600)

    async def check_and_announce_new_content(self, guild):
        """Check for new content and announce it"""
        settings = await self.config.guild(guild).all()
        channel = guild.get_channel(settings['announcement_channel_id'])
        if not channel:
            return
            
        # Calculate the time since last check
        last_check = settings.get('last_check')
        now = datetime.utcnow().timestamp()
        
        # If first time running, set last_check to now and return
        if not last_check:
            await self.config.guild(guild).last_check.set(now)
            return
            
        # Find new content added since last check
        new_items = await self.get_new_content(
            settings['base_url'], 
            settings['api_key'], 
            last_check
        )
        
        # Update last check time
        await self.config.guild(guild).last_check.set(now)
        
        if not new_items:
            return
            
        # Process and announce each new item
        for item in new_items:
            try:
                await self.announce_item(channel, item, settings)
                # Add a small delay between messages to avoid rate limits
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Error announcing item: {e}")

    async def get_new_content(self, base_url, api_key, last_check):
        """Get new movies and TV shows added since last check"""
        # Convert last_check timestamp to ISO date format
        date_added = datetime.fromtimestamp(last_check).strftime("%Y-%m-%d")
        
        # Build search URL that excludes episodes
        search_url = (
            f"{base_url}/Items?IncludeItemTypes=Movie,Series&"
            f"AddedDate={date_added}&"
            f"SortBy=DateCreated,SortName&SortOrder=Descending&"
            f"Recursive=true&api_key={api_key}"
        )
        
        # Implement retry system
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(search_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            items = data.get('Items', [])
                            return items
                        else:
                            print(f"Jellyfin API error: Status {response.status}")
            except Exception as e:
                print(f"Error fetching new content on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        return []

    async def search_tmdb(self, title, year, is_movie, tmdb_api_key):
        """Search TMDb for additional media info"""
        if not tmdb_api_key:
            return None
            
        media_type = "movie" if is_movie else "tv"
        search_url = f"{self.tmdb_base_url}/search/{media_type}?api_key={tmdb_api_key}&query={title}&year={year}"
        
        timeout = aiohttp.ClientTimeout(total=30)  # 30 seconds total timeout
        
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(search_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            results = data.get('results', [])
                            if results:
                                tmdb_data = results[0]
                                tmdb_id = tmdb_data.get('id')
                                
                                # Get complete details for more accurate information
                                if tmdb_id:
                                    details_url = f"{self.tmdb_base_url}/{media_type}/{tmdb_id}?api_key={tmdb_api_key}"
                                    async with session.get(details_url) as details_response:
                                        if details_response.status == 200:
                                            details = await details_response.json()
                                            return {
                                                'poster_path': details.get('poster_path'),
                                                'overview': details.get('overview'),
                                                'tmdb_id': tmdb_id
                                            }
                                
                                # If we can't get complete details, use search results
                                return {
                                    'poster_path': tmdb_data.get('poster_path'),
                                    'overview': tmdb_data.get('overview'),
                                    'tmdb_id': tmdb_id
                                }
                        elif response.status == 429:  # Too many requests (rate limit)
                            # Wait longer if rate-limited
                            await asyncio.sleep(retry_delay * (attempt + 2))
                            continue
                        else:
                            print(f"TMDb API error: Status {response.status}")
            except Exception as e:
                print(f"Error searching TMDb on attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        return None

    async def announce_item(self, channel, item, settings):
        """Create and send an announcement for a new item"""
        title = item.get('Name', 'Unknown Title')
        year = item.get('ProductionYear', 'Unknown Year')
        is_movie = item.get('Type') == "Movie"
        
        # Determine media type based on Jellyfin Type
        media_type = "Film" if is_movie else "Serial"
        
        # Get initial description from Jellyfin
        overview = item.get('Overview', 'No description available.')
        
        # Search TMDb for poster and description
        tmdb_data = None
        if 'tmdb_api_key' in settings and settings['tmdb_api_key']:
            tmdb_data = await self.search_tmdb(title, year, is_movie, settings['tmdb_api_key'])
        
        # Use TMDb description if available and not empty
        if tmdb_data and tmdb_data.get('overview'):
            overview = tmdb_data['overview']
        
        # Limit description length
        if len(overview) > 1000:
            overview = overview[:997] + "..."

        # Create embed for the announcement
        embed = discord.Embed(
            title=f"{title} ({year})",
            description=overview,
            color=discord.Color.green()
        )
        
        # Add TMDb poster if available
        if tmdb_data and tmdb_data.get('poster_path'):
            poster_url = f"{self.poster_base_url}{tmdb_data['poster_path']}"
            embed.set_thumbnail(url=poster_url)
        
        # Add type (Movie/Series)
        embed.add_field(name="Tip", value=media_type, inline=True)
        
        if genres := item.get('Genres', [])[:3]:
            embed.add_field(name="Genuri", value=", ".join(genres), inline=True)
        
        if community_rating := item.get('CommunityRating'):
            embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

        item_id = item.get('Id')
        if item_id:
            web_url = f"{settings['base_url']}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Vizionare Online:", value=f"[Freia [SERVER 2]]({web_url})", inline=False)
            
        # Add timestamp for when the item was added
        added_date = item.get('DateCreated')
        if added_date:
            try:
                embed.set_footer(text=f"Adăugat: {added_date}")
            except:
                pass
        
        # Send the announcement
        await channel.send(f"**{media_type} nou adăugat pe Freia:**", embed=embed)

    @commands.group(name="newcontent")
    async def newcontent(self, ctx):
        """Commands to manage Jellyfin new content announcements"""
        if ctx.invoked_subcommand is None:
            help_text = (
                "**Comenzi pentru configurarea anunțurilor de conținut nou:**\n\n"
                f"`{ctx.prefix}newcontent seturl <URL>` - Setează URL-ul serverului Jellyfin\n"
                f"`{ctx.prefix}newcontent setapi <API_KEY>` - Setează cheia API Jellyfin\n"
                f"`{ctx.prefix}newcontent settmdb <API_KEY>` - Setează cheia API TMDb pentru postere (opțional)\n"
                f"`{ctx.prefix}newcontent setchannel <#CANAL>` - Setează canalul pentru anunțuri\n"
                f"`{ctx.prefix}newcontent setinterval <ORE>` - Setează intervalul de verificare (ore)\n"
                f"`{ctx.prefix}newcontent settings` - Arată setările curente\n"
                f"`{ctx.prefix}newcontent check` - Verifică manual conținut nou\n"
                f"`{ctx.prefix}newcontent reset` - Resetează timestamp-ul de verificare"
            )
            await ctx.send(help_text)

    @newcontent.command(name="seturl")
    @commands.admin_or_permissions(administrator=True)
    async def set_url(self, ctx, url: str):
        """Set the Jellyfin server URL"""
        url = url.rstrip('/')
        await self.config.guild(ctx.guild).base_url.set(url)
        await ctx.send(f"URL-ul serverului Jellyfin a fost setat la: {url}")

    @newcontent.command(name="setapi")
    @commands.admin_or_permissions(administrator=True)
    async def set_api(self, ctx, api_key: str):
        """Set the Jellyfin API key"""
        await self.config.guild(ctx.guild).api_key.set(api_key)
        await ctx.send("Cheia API Jellyfin a fost setată.")
        await ctx.message.delete()

    @newcontent.command(name="settmdb")
    @commands.admin_or_permissions(administrator=True)
    async def set_tmdb(self, ctx, api_key: str):
        """Set the TMDb API key for posters and descriptions"""
        await self.config.guild(ctx.guild).tmdb_api_key.set(api_key)
        await ctx.send("Cheia API TMDb pentru postere și descrieri a fost setată.")
        await ctx.message.delete()

    @newcontent.command(name="setchannel")
    @commands.admin_or_permissions(administrator=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for new content announcements"""
        await self.config.guild(ctx.guild).announcement_channel_id.set(channel.id)
        await ctx.send(f"Canalul pentru anunțuri de conținut nou a fost setat la: {channel.mention}")

    @newcontent.command(name="setinterval")
    @commands.admin_or_permissions(administrator=True)
    async def set_interval(self, ctx, hours: int):
        """Set how often to check for new content (in hours)"""
        if hours < 1:
            return await ctx.send("Intervalul trebuie să fie de cel puțin 1 oră.")
        await self.config.guild(ctx.guild).check_interval.set(hours)
        await ctx.send(f"Intervalul de verificare a fost setat la {hours} ore.")

    @newcontent.command(name="settings")
    @commands.admin_or_permissions(administrator=True)
    async def show_settings(self, ctx):
        """Show current new content announcements settings"""
        settings = await self.config.guild(ctx.guild).all()
        channel = ctx.guild.get_channel(settings['announcement_channel_id']) if settings['announcement_channel_id'] else None
        
        last_check_str = "Niciodată"
        if settings.get('last_check'):
            try:
                last_check_time = datetime.fromtimestamp(settings['last_check'])
                last_check_str = last_check_time.strftime("%Y-%m-%d %H:%M:%S")
            except:
                last_check_str = "Eroare la conversie"
        
        embed = discord.Embed(
            title="Setări Anunțuri Conținut Nou Jellyfin",
            color=discord.Color.green()
        )
        embed.add_field(
            name="URL Server", 
            value=settings['base_url'] or "Nesetat",
            inline=False
        )
        embed.add_field(
            name="API Key Jellyfin", 
            value="Setat ✓" if settings['api_key'] else "Nesetat ✗",
            inline=False
        )
        embed.add_field(
            name="API Key TMDb", 
            value="Setat ✓" if settings.get('tmdb_api_key') else "Nesetat ✗",
            inline=False
        )
        embed.add_field(
            name="Canal Anunțuri", 
            value=channel.mention if channel else "Nesetat",
            inline=False
        )
        embed.add_field(
            name="Interval Verificare", 
            value=f"{settings.get('check_interval', 6)} ore",
            inline=False
        )
        embed.add_field(
            name="Ultima Verificare", 
            value=last_check_str,
            inline=False
        )
        
        await ctx.send(embed=embed)

    @newcontent.command(name="check")
    @commands.admin_or_permissions(administrator=True)
    async def manual_check(self, ctx):
        """Manually check for new content"""
        settings = await self.config.guild(ctx.guild).all()
        if not all(k in settings and settings[k] for k in ['base_url', 'api_key', 'announcement_channel_id']):
            help_msg = (
                "⚠️ Configurarea nu este completă. Folosește următoarele comenzi pentru a seta totul:\n\n"
                f"`{ctx.prefix}newcontent seturl <URL>` - Setează URL-ul serverului Jellyfin\n"
                f"`{ctx.prefix}newcontent setapi <API_KEY>` - Setează cheia API Jellyfin\n"
                f"`{ctx.prefix}newcontent setchannel <#CANAL>` - Setează canalul pentru anunțuri\n\n"
                f"Poți verifica setările curente folosind `{ctx.prefix}newcontent settings`"
            )
            return await ctx.send(help_msg)
            
        await ctx.send("Verificare pentru conținut nou în desfășurare...")
        try:
            await self.check_and_announce_new_content(ctx.guild)
            await ctx.send("Verificare completă.")
        except Exception as e:
            await ctx.send(f"Eroare în timpul verificării: {e}")

    @newcontent.command(name="reset")
    @commands.admin_or_permissions(administrator=True)
    async def reset_timestamp(self, ctx):
        """Reset the last check timestamp to force a fresh check"""
        await self.config.guild(ctx.guild).last_check.set(None)
        await ctx.send("Timestamp-ul de verificare a fost resetat. Următoarea verificare va include tot conținutul disponibil.")

async def setup(bot):
    await bot.add_cog(JellyfinNewContent(bot))
