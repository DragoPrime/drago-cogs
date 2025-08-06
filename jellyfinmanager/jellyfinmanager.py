import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, Optional

import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify

log = logging.getLogger("red.jellyfincog")

class JellyfinCog(commands.Cog):
    """Cog pentru gestionarea utilizatorilor pe servere Jellyfin multiple"""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        
        default_global = {
            "servers": {}
        }
        
        default_guild = {
            "enabled": False
        }
        
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        
    async def _get_jellyfin_auth_token(self, server_url: str, username: str, password: str) -> Optional[str]:
        """Obține token-ul de autentificare pentru serverul Jellyfin"""
        auth_url = f"{server_url}/Users/AuthenticateByName"
        
        auth_data = {
            "Username": username,
            "Pw": password,
            "PasswordMd5": ""
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-Emby-Authorization": 'MediaBrowser Client="RedBot", Device="RedBot", DeviceId="redbot-jellyfin", Version="1.0.0"'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(auth_url, json=auth_data, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("AccessToken")
                    else:
                        log.error(f"Autentificare eșuată pentru {server_url}: {resp.status}")
                        return None
        except Exception as e:
            log.error(f"Eroare la autentificare {server_url}: {e}")
            return None
    
    async def _create_jellyfin_user(self, server_url: str, token: str, username: str, password: str) -> Dict[str, Any]:
        """Creează un utilizator pe serverul Jellyfin"""
        create_url = f"{server_url}/Users/New"
        
        user_data = {
            "Name": username,
            "Password": password,
            "PasswordResetRequired": False,
            "IsAdministrator": False,
            "IsHidden": False,
            "IsDisabled": False,
            "EnableUserPreferenceAccess": True,
            "EnableRemoteControlOfOtherUsers": False,
            "EnableSharedDeviceControl": False,
            "EnableRemoteAccess": True,
            "EnableLiveTvManagement": False,
            "EnableLiveTvAccess": True,
            "EnableMediaPlayback": True,
            "EnableAudioPlaybackTranscoding": True,
            "EnableVideoPlaybackTranscoding": True,
            "EnablePlaybackRemuxing": True,
            "EnableContentDeletion": False,
            "EnableContentDeletionFromFolders": [],
            "EnableContentDownloading": False,
            "EnableSyncTranscoding": True,
            "EnableMediaConversion": True,
            "EnabledDevices": [],
            "EnableAllDevices": True,
            "EnabledChannels": [],
            "EnableAllChannels": True,
            "EnabledFolders": [],
            "EnableAllFolders": True,
            "InvalidLoginAttemptCount": 0,
            "EnablePublicSharing": False,
            "RemoteClientBitrateLimit": 0,
            "AuthenticationProviderId": "",
            "PasswordResetProviderId": ""
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-MediaBrowser-Token": token
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(create_url, json=user_data, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {"success": True, "user_id": data.get("Id"), "message": "Utilizator creat cu succes"}
                    else:
                        error_text = await resp.text()
                        return {"success": False, "error": f"Status {resp.status}: {error_text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @commands.group(name="server", aliases=["srv"])
    @checks.is_owner()
    async def server(self, ctx):
        """Comenzi pentru gestionarea serverelor Jellyfin"""
        pass
    
    @server.command(name="addserver")
    @checks.is_owner()
    async def add_server(self, ctx, nume_server: str, url: str, admin_user: str, admin_password: str):
        """
        Adaugă un server Jellyfin
        
        Usage: .server addserver <nume_server> <url> <admin_user> <admin_password>
        Exemplu: .server addserver server1 http://192.168.1.100:8096 admin parola123
        """
        # Verifică dacă URL-ul este valid și se poate conecta
        token = await self._get_jellyfin_auth_token(url, admin_user, admin_password)
        
        if not token:
            await ctx.send("❌ Nu s-a putut conecta la serverul Jellyfin. Verifică URL-ul și credențialele.")
            return
        
        servers = await self.config.servers()
        servers[nume_server] = {
            "url": url,
            "admin_user": admin_user,
            "admin_password": admin_password
        }
        await self.config.servers.set(servers)
        
        await ctx.send(f"✅ Serverul **{nume_server}** a fost adăugat cu succes!")
    
    @server.command(name="removeserver")
    @checks.is_owner()
    async def remove_server(self, ctx, nume_server: str):
        """Elimină un server Jellyfin"""
        servers = await self.config.servers()
        
        if nume_server not in servers:
            await ctx.send(f"❌ Serverul **{nume_server}** nu există.")
            return
        
        del servers[nume_server]
        await self.config.servers.set(servers)
        
        await ctx.send(f"✅ Serverul **{nume_server}** a fost eliminat.")
    
    @server.command(name="listservers")
    @checks.is_owner()
    async def list_servers(self, ctx):
        """Afișează lista serverelor Jellyfin configurate"""
        servers = await self.config.servers()
        
        if not servers:
            await ctx.send("Nu există servere Jellyfin configurate.")
            return
        
        server_list = []
        for name, config in servers.items():
            server_list.append(f"**{name}**: {config['url']}")
        
        await ctx.send("**Servere Jellyfin configurate:**\n" + "\n".join(server_list))
    
    @server.command(name="enable")
    @checks.admin_or_permissions(manage_guild=True)
    async def enable_jellyfin(self, ctx):
        """Activează comenzile Jellyfin pe acest server Discord"""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("✅ Comenzile Jellyfin au fost activate pe acest server.")
    
    @server.command(name="disable")
    @checks.admin_or_permissions(manage_guild=True)
    async def disable_jellyfin(self, ctx):
        """Dezactivează comenzile Jellyfin pe acest server Discord"""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("✅ Comenzile Jellyfin au fost dezactivate pe acest server.")
    
    @commands.command(name="creeaza")
    async def create_user(self, ctx, nume_server: str, nume_utilizator: str, parola: str):
        """
        Creează un utilizator pe serverul Jellyfin specificat
        
        Usage: .creeaza <nume_server> <nume_utilizator> <parola>
        Exemplu: .creeaza server1 john123 parola456
        """
        # Verifică dacă comenzile sunt activate pe server
        if not await self.config.guild(ctx.guild).enabled():
            await ctx.send("❌ Comenzile Jellyfin nu sunt activate pe acest server Discord.")
            return
        
        # Șterge mesajul original pentru securitate (conține parola)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        
        servers = await self.config.servers()
        
        if nume_server not in servers:
            await ctx.send(f"❌ Serverul **{nume_server}** nu există. Servere disponibile: {', '.join(servers.keys())}")
            return
        
        server_config = servers[nume_server]
        
        # Obține token-ul de autentificare
        token = await self._get_jellyfin_auth_token(
            server_config["url"], 
            server_config["admin_user"], 
            server_config["admin_password"]
        )
        
        if not token:
            await ctx.send("❌ Nu s-a putut autentifica pe serverul Jellyfin.")
            return
        
        # Creează utilizatorul
        result = await self._create_jellyfin_user(
            server_config["url"], 
            token, 
            nume_utilizator, 
            parola
        )
        
        if result["success"]:
            embed = discord.Embed(
                title="✅ Utilizator creat cu succes",
                color=0x00ff00,
                description=f"Utilizatorul **{nume_utilizator}** a fost creat pe serverul **{nume_server}**"
            )
            embed.add_field(name="Server URL", value=server_config["url"], inline=False)
            embed.add_field(name="Nume utilizator", value=nume_utilizator, inline=True)
            embed.add_field(name="Utilizator Discord", value=ctx.author.mention, inline=True)
            
            # Trimite mesajul în DM pentru securitate
            try:
                await ctx.author.send(embed=embed)
                await ctx.send(f"✅ Utilizatorul a fost creat! Verifică mesajele private pentru detalii.")
            except discord.Forbidden:
                await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Eroare la crearea utilizatorului: {result['error']}")
