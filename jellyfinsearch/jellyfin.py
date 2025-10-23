from redbot.core import commands, Config
import aiohttp
import urllib.parse
import discord
from datetime import datetime
from typing import List, Dict, Any
import asyncio

class TMDBSelectionView(discord.ui.View):
    """View for selecting from TMDB search results"""
    
    def __init__(self, cog, ctx, results: List[Dict[Any, Any]], query: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.results = results
        self.query = query
        self.selected_item = None
        
        # Adăugăm butoane pentru fiecare rezultat (max 5 pentru a nu depăși limita Discord)
        for idx, result in enumerate(results[:5]):
            button = discord.ui.Button(
                label=f"{idx + 1}. {result['title'][:80]}",
                style=discord.ButtonStyle.primary,
                custom_id=f"select_{idx}"
            )
            button.callback = self.create_callback(idx)
            self.add_item(button)
    
    def create_callback(self, index: int):
        """Creează un callback pentru fiecare buton"""
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                await interaction.response.send_message(
                    "Doar persoana care a inițiat comanda poate selecta rezultatul.",
                    ephemeral=True
                )
                return
            
            self.selected_item = self.results[index]
            
            # Dezactivăm toate butoanele
            for child in self.children:
                child.disabled = True
            
            await interaction.response.edit_message(
                content=f"✅ Ai selectat: **{self.selected_item['title']}**\n\nSe caută pe serverul Jellyfin...",
                embed=None,
                view=self
            )
            
            # Căutăm pe Jellyfin
            await self.cog.search_jellyfin_by_tmdb(self.ctx, self.selected_item, self.query)
            
            self.stop()
        
        return callback
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifică dacă utilizatorul care interacționează este cel care a inițiat comanda"""
        return interaction.user == self.ctx.author
    
    async def on_timeout(self):
        """Dezactivează butoanele după timeout"""
        for child in self.children:
            child.disabled = True
        
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(
                    content="⏱️ Timpul de selecție a expirat.",
                    view=self
                )
        except (discord.NotFound, discord.HTTPException):
            pass


class JellyfinSearchView(discord.ui.View):
    """View for paginated Jellyfin search results"""
    
    def __init__(self, cog, ctx, items: List[Dict[Any, Any]], query: str, total_results: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.items = items
        self.query = query
        self.total_results = total_results
        self.current_page = 0
        self.total_pages = len(items)
        
        self._update_buttons()
    
    def _update_buttons(self):
        """Actualizează starea butoanelor în funcție de pagina curentă"""
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page >= self.total_pages - 1
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifică dacă utilizatorul care interacționează este cel care a inițiat comanda"""
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "Doar persoana care a inițiat comanda poate naviga prin rezultate.", 
                ephemeral=True
            )
            return False
        return True
    
    def get_current_page_embed(self) -> discord.Embed:
        """Creează un embed pentru un singur rezultat (pagina curentă)"""
        item = self.items[self.current_page]
        
        title = item.get('Name', 'Titlu necunoscut')
        if year := item.get('ProductionYear'):
            title += f" ({year})"
            
        embed = discord.Embed(
            title=f"Rezultatul {self.current_page + 1} pentru '{self.query}'",
            description=title,
            color=discord.Color.blue()
        )
        
        item_type = item.get('Type', 'Tip necunoscut')
        if item_type == "Movie":
            item_type = "Film"
        elif item_type == "Series":
            item_type = "Serial"
        embed.add_field(name="Tip", value=item_type, inline=True)
        
        runtime = self.cog.format_runtime(item.get('RunTimeTicks'))
        if runtime != "N/A":
            embed.add_field(name="Durată", value=runtime, inline=True)

        if community_rating := item.get('CommunityRating'):
            embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

        if overview := item.get('Overview'):
            if len(overview) > 300:
                overview = overview[:297] + "..."
            embed.add_field(name="Descriere", value=overview, inline=False)

        if item.get('TMDBOverview'):
            tmdb_overview = item.get('TMDBOverview')
            if len(tmdb_overview) > 300:
                tmdb_overview = tmdb_overview[:297] + "..."
            embed.add_field(name="Descriere TMDB", value=tmdb_overview, inline=False)

        if genres := item.get('Genres'):
            embed.add_field(name="Genuri", value=", ".join(genres[:4]), inline=False)
            
        if item.get('TMDBPosterPath'):
            thumbnail_url = f"https://image.tmdb.org/t/p/w342{item['TMDBPosterPath']}"
            embed.set_thumbnail(url=thumbnail_url)
        elif item.get('Id'):
            thumbnail_url = f"{self.cog.base_url}/Items/{item['Id']}/Images/Primary?maxHeight=400&maxWidth=266&quality=90&api_key={self.cog.api_key}"
            embed.set_thumbnail(url=thumbnail_url)
        
        item_id = item.get('Id')
        if item_id:
            web_url = f"{self.cog.base_url}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Vizionare Online:", value=f"[Freia [SERVER 2]]({web_url})", inline=False)
        
        embed.set_footer(text=f"Pagina {self.current_page + 1}/{self.total_pages} • S-au găsit {self.total_results} rezultate în total")
        
        return embed
    
    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Buton pentru navigarea la pagina anterioară"""
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_current_page_embed(), view=self)
    
    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Buton pentru navigarea la pagina următoare"""
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_current_page_embed(), view=self)
        
    @discord.ui.button(emoji="🔍", style=discord.ButtonStyle.secondary)
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Buton pentru afișarea mai multor detalii despre titlul curent"""
        item = self.items[self.current_page]
        item_id = item.get('Id')
        
        if not item_id:
            await interaction.response.send_message("Nu sunt disponibile informații suplimentare pentru acest titlu.", ephemeral=True)
            return
            
        item_name = item.get('Name', 'Titlu necunoscut')
        web_url = f"{self.cog.base_url}/web/index.html#!/details?id={item_id}"
        
        await interaction.response.send_message(
            f"**{item_name}**\nPoți accesa direct acest titlu din Freia folosind link-ul: {web_url}", 
            ephemeral=True
        )
    
    async def on_timeout(self):
        """Dezactivează butoanele după timeout"""
        for child in self.children:
            child.disabled = True
            
        try:
            message = self.message
            if message:
                await message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class JellyfinSearch(commands.Cog):
    """Jellyfin search commands for Red Discord Bot"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=856712356)
        default_global = {
            "base_url": None,
            "api_key": None,
            "tmdb_api_key": None
        }
        self.config.register_global(**default_global)
        self.base_url = None
        self.api_key = None
        self.tmdb_api_key = None
    
    async def cog_load(self):
        """Load cached settings when cog loads"""
        self.base_url = await self.config.base_url()
        self.api_key = await self.config.api_key()
        self.tmdb_api_key = await self.config.tmdb_api_key()

    async def get_base_url(self):
        """Get the stored base URL"""
        return self.base_url or await self.config.base_url()

    async def get_api_key(self):
        """Get the stored API key"""
        return self.api_key or await self.config.api_key()
    
    async def get_tmdb_api_key(self):
        """Get the stored TMDB API key"""
        return self.tmdb_api_key or await self.config.tmdb_api_key()

    @commands.command()
    @commands.is_owner()
    async def setjellyfinurl(self, ctx, url: str):
        """Set the Jellyfin server URL"""
        url = url.rstrip('/')
        await self.config.base_url.set(url)
        self.base_url = url
        await ctx.send(f"URL-ul serverului Jellyfin a fost setat la: {url}")

    @commands.command()
    @commands.is_owner()
    async def setjellyfinapi(self, ctx, api_key: str):
        """Set the Jellyfin API key"""
        await self.config.api_key.set(api_key)
        self.api_key = api_key
        await ctx.send("Cheia API Jellyfin a fost setată.")
        await ctx.message.delete()
    
    @commands.command()
    @commands.is_owner()
    async def freiatmdb(self, ctx, api_key: str):
        """Set the TMDB API key"""
        await self.config.tmdb_api_key.set(api_key)
        self.tmdb_api_key = api_key
        await ctx.send("Cheia API TMDB a fost setată.")
        await ctx.message.delete()

    def format_runtime(self, runtime_ticks):
        """Convert runtime ticks to hours and minutes"""
        if not runtime_ticks:
            return "N/A"
        minutes = int(runtime_ticks / (10000000 * 60))
        hours = minutes // 60
        remaining_minutes = minutes % 60
        if hours > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{remaining_minutes}m"
    
    async def search_tmdb(self, query: str):
        """Search TMDB for movies and TV shows"""
        if not self.tmdb_api_key:
            return None
        
        results = []
        
        # Căutăm atât filme cât și seriale
        for media_type in ['movie', 'tv']:
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://api.themoviedb.org/3/search/{media_type}?api_key={self.tmdb_api_key}&query={encoded_query}&language=ro-RO"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(search_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            for item in data.get('results', [])[:5]:  # Limităm la primele 5 rezultate per tip
                                # Obținem și titlurile alternative
                                tmdb_id = item.get('id')
                                item['media_type'] = media_type
                                item['title'] = item.get('title') if media_type == 'movie' else item.get('name')
                                item['alternative_titles'] = await self.get_alternative_titles(tmdb_id, media_type)
                                results.append(item)
                except Exception as e:
                    pass
        
        return results[:10]  # Returnăm maximum 10 rezultate totale
    
    async def get_alternative_titles(self, tmdb_id: int, media_type: str):
        """Get alternative titles from TMDB"""
        if not self.tmdb_api_key:
            return []
        
        titles = []
        endpoint = "alternative_titles" if media_type == "movie" else "alternative_titles"
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/{endpoint}?api_key={self.tmdb_api_key}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        results_key = "titles" if media_type == "movie" else "results"
                        
                        for item in data.get(results_key, []):
                            if media_type == "movie":
                                titles.append(item.get('title'))
                            else:
                                titles.append(item.get('name'))
            except Exception as e:
                pass
        
        return titles
    
    async def search_jellyfin_by_tmdb(self, ctx, tmdb_item: Dict[Any, Any], original_query: str):
        """Search Jellyfin using TMDB titles"""
        # Creăm o listă de titluri de căutat
        search_titles = [tmdb_item['title']]
        
        # Adăugăm titlul original dacă există
        if 'original_title' in tmdb_item and tmdb_item['original_title'] != tmdb_item['title']:
            search_titles.append(tmdb_item['original_title'])
        if 'original_name' in tmdb_item and tmdb_item['original_name'] != tmdb_item['title']:
            search_titles.append(tmdb_item['original_name'])
        
        # Adăugăm titlurile alternative
        search_titles.extend(tmdb_item.get('alternative_titles', []))
        
        # Eliminăm duplicatele
        search_titles = list(dict.fromkeys([t for t in search_titles if t]))
        
        all_items = []
        seen_ids = set()
        
        async with ctx.typing():
            for title in search_titles[:10]:  # Limităm la primele 10 titluri pentru a nu supraîncărca
                encoded_query = urllib.parse.quote(title)
                search_url = f"{self.base_url}/Items?searchTerm={encoded_query}&IncludeItemTypes=Movie,Series&Recursive=true&SearchType=String&IncludeMedia=true&IncludeOverview=true&Limit=50&api_key={self.api_key}"
                
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get(search_url) as response:
                            if response.status == 200:
                                data = await response.json()
                                items = data.get('Items', [])
                                
                                # Adăugăm doar itemele noi (fără duplicate)
                                for item in items:
                                    item_id = item.get('Id')
                                    if item_id and item_id not in seen_ids:
                                        seen_ids.add(item_id)
                                        all_items.append(item)
                    except Exception as e:
                        pass
                
                # Adăugăm un mic delay între cereri
                await asyncio.sleep(0.3)
        
        if not all_items:
            await ctx.send(f"❌ Nu s-au găsit rezultate pe serverul Jellyfin pentru **{tmdb_item['title']}**.")
            return
        
        # Procesăm primele 10 rezultate pentru a obține informații TMDB îmbogățite
        enhanced_items = []
        for item in all_items[:10]:
            enhanced_item = await self.get_tmdb_info(item)
            enhanced_items.append(enhanced_item)
            await asyncio.sleep(0.5)
        
        if len(all_items) > 10:
            enhanced_items.extend(all_items[10:])
        
        # Creăm view-ul pentru paginare
        view = JellyfinSearchView(self, ctx, enhanced_items, tmdb_item['title'], len(all_items))
        embed = view.get_current_page_embed()
        message = await ctx.send(embed=embed, view=view)
        view.message = message
    
    async def get_tmdb_info(self, item):
        """Get additional information from TMDB API"""
        if not self.tmdb_api_key:
            return item
        
        media_type = "movie" if item.get('Type') == "Movie" else "tv"
        
        tmdb_id = None
        if providers := item.get('ProviderIds', {}):
            tmdb_id = providers.get('Tmdb')
        
        if not tmdb_id:
            name = item.get('Name')
            year = item.get('ProductionYear', '')
            
            if not name:
                return item
                
            search_query = f"{name}"
            if year:
                search_query += f" {year}"
                
            encoded_query = urllib.parse.quote(search_query)
            search_url = f"https://api.themoviedb.org/3/search/{media_type}?api_key={self.tmdb_api_key}&query={encoded_query}&language=ro-RO"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(search_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            results = data.get('results', [])
                            
                            if results:
                                tmdb_id = results[0].get('id')
                                
                                if poster_path := results[0].get('poster_path'):
                                    item['TMDBPosterPath'] = poster_path
                                
                                if overview := results[0].get('overview'):
                                    item['TMDBOverview'] = overview
                except Exception as e:
                    pass
        
        if tmdb_id:
            details_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={self.tmdb_api_key}&language=ro-RO"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(details_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if overview := data.get('overview'):
                                item['TMDBOverview'] = overview
                            
                            if poster_path := data.get('poster_path'):
                                item['TMDBPosterPath'] = poster_path
                except Exception as e:
                    pass
        
        return item

    @commands.command(name="freia")
    async def freia(self, ctx, *, query: str):
        """Search for content on your Jellyfin server"""
        self.base_url = await self.get_base_url()
        self.api_key = await self.get_api_key()
        self.tmdb_api_key = await self.get_tmdb_api_key()
        
        if not self.base_url or not self.api_key:
            return await ctx.send("Te rog să setezi mai întâi URL-ul și cheia API folosind `setjellyfinurl` și `setjellyfinapi`")
        
        if not self.tmdb_api_key:
            return await ctx.send("Te rog să setezi mai întâi cheia API TMDB folosind `freiatmdb`")
        
        # Căutăm mai întâi pe TMDB
        async with ctx.typing():
            wait_msg = await ctx.send("🔍 Se caută pe TMDB...")
            tmdb_results = await self.search_tmdb(query)
            
            if not tmdb_results:
                await wait_msg.edit(content="❌ Nu s-au găsit rezultate pe TMDB.")
                return
            
            # Dacă avem un singur rezultat, căutăm direct pe Jellyfin
            if len(tmdb_results) == 1:
                await wait_msg.edit(content=f"✅ S-a găsit un rezultat pe TMDB: **{tmdb_results[0]['title']}**\n\nSe caută pe serverul Jellyfin...")
                await self.search_jellyfin_by_tmdb(ctx, tmdb_results[0], query)
                return
            
            # Dacă avem mai multe rezultate, afișăm lista pentru selecție
            await wait_msg.delete()
            
            # Creăm embed cu rezultatele TMDB
            embed = discord.Embed(
                title=f"🎬 Rezultate TMDB pentru '{query}'",
                description="Selectează titlul pe care îl cauți:",
                color=discord.Color.gold()
            )
            
            for idx, result in enumerate(tmdb_results[:5]):
                media_type = "🎬 Film" if result['media_type'] == 'movie' else "📺 Serial"
                year = result.get('release_date', result.get('first_air_date', ''))[:4] if result.get('release_date') or result.get('first_air_date') else 'N/A'
                
                embed.add_field(
                    name=f"{idx + 1}. {result['title']} ({year})",
                    value=f"{media_type}",
                    inline=False
                )
            
            # Creăm view-ul pentru selecție
            view = TMDBSelectionView(self, ctx, tmdb_results, query)
            message = await ctx.send(embed=embed, view=view)
            view.message = message
