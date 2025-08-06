import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime

import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.predicates import MessagePredicate

log = logging.getLogger("red.jellyfincog")

class JellyfinCog(commands.Cog):
    """Cog pentru gestionarea utilizatorilor pe servere Jellyfin multiple"""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1237567650)
        
        default_global = {
            "servers": {},
            "users": {}  # Format: {"discord_user_id": {"server_name": {"jellyfin_username": "data", "created_at": "timestamp"}}}
        }
        
        default_guild = {
            "enabled": False,
            "server_roles": {}  # Format: {"server_name": role_id}
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
    
    async def _add_user_to_tracking(self, discord_user_id: int, server_name: str, jellyfin_username: str):
        """Adaugă utilizatorul la sistemul de tracking"""
        users = await self.config.users()
        user_id_str = str(discord_user_id)
        
        if user_id_str not in users:
            users[user_id_str] = {}
        
        if server_name not in users[user_id_str]:
            users[user_id_str][server_name] = {}
        
        users[user_id_str][server_name][jellyfin_username] = {
            "created_at": datetime.now().isoformat(),
            "server_name": server_name
        }
        
        await self.config.users.set(users)
    
    async def _get_user_by_jellyfin_username(self, jellyfin_username: str) -> Optional[Dict[str, Any]]:
        """Găsește utilizatorul Discord după username-ul Jellyfin"""
        users = await self.config.users()
        
        for discord_user_id, user_data in users.items():
            for server_name, server_users in user_data.items():
                if jellyfin_username in server_users:
                    return {
                        "discord_user_id": int(discord_user_id),
                        "server_name": server_name,
                        "jellyfin_username": jellyfin_username,
                        "created_at": server_users[jellyfin_username]["created_at"]
                    }
        return None
    
    async def _assign_role(self, guild: discord.Guild, member: discord.Member, server_name: str):
        """Atribuie rolul corespunzător utilizatorului"""
        server_roles = await self.config.guild(guild).server_roles()
        
        if server_name in server_roles:
            role_id = server_roles[server_name]
            role = guild.get_role(role_id)
            
            if role:
                try:
                    await member.add_roles(role, reason=f"Utilizator creat pe serverul Jellyfin: {server_name}")
                    return True
                except discord.Forbidden:
                    log.error(f"Nu am permisiuni să atribui rolul {role.name}")
                except discord.HTTPException as e:
                    log.error(f"Eroare la atribuirea rolului: {e}")
            else:
                log.error(f"Rolul cu ID {role_id} nu a fost găsit")
        
        return False
    
    @commands.group(name="server", aliases=["srv"])
    @checks.is_owner()
    async def server(self, ctx):
        """Comenzi pentru gestionarea serverelor Jellyfin"""
        pass
    
    @server.command(name="addserver")
    @checks.is_owner()
    async def add_server(self, ctx, nume_server: str, url: str, admin_user: str, admin_password: str, *, rol: discord.Role = None):
        """
        Adaugă un server Jellyfin cu rol opțional
        
        Usage: .server addserver <nume_server> <url> <admin_user> <admin_password> [rol]
        Exemplu: .server addserver server1 http://192.168.1.100:8096 admin parola123 @JellyfinUsers
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
        
        # Dacă s-a specificat un rol, îl salvăm
        if rol:
            server_roles = await self.config.guild(ctx.guild).server_roles()
            server_roles[nume_server] = rol.id
            await self.config.guild(ctx.guild).server_roles.set(server_roles)
        
        success_msg = f"✅ Serverul **{nume_server}** a fost adăugat cu succes!"
        if rol:
            success_msg += f"\n🎭 Rol atribuit: {rol.mention}"
        
        await ctx.send(success_msg)
    
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
        
        # Elimină și rolul asociat dacă există
        server_roles = await self.config.guild(ctx.guild).server_roles()
        if nume_server in server_roles:
            del server_roles[nume_server]
            await self.config.guild(ctx.guild).server_roles.set(server_roles)
        
        await ctx.send(f"✅ Serverul **{nume_server}** a fost eliminat.")
    
    @server.command(name="listservers")
    @checks.is_owner()
    async def list_servers(self, ctx):
        """Afișează lista serverelor Jellyfin configurate"""
        servers = await self.config.servers()
        
        if not servers:
            await ctx.send("Nu există servere Jellyfin configurate.")
            return
        
        server_roles = await self.config.guild(ctx.guild).server_roles()
        server_list = []
        
        for name, config in servers.items():
            role_info = ""
            if name in server_roles:
                role = ctx.guild.get_role(server_roles[name])
                role_info = f" | Rol: {role.mention if role else 'Rol șters'}"
            
            server_list.append(f"**{name}**: {config['url']}{role_info}")
        
        await ctx.send("**Servere Jellyfin configurate:**\n" + "\n".join(server_list))
    
    @server.command(name="setrole")
    @checks.admin_or_permissions(manage_roles=True)
    async def set_role(self, ctx, nume_server: str, rol: discord.Role):
        """Setează rolul pentru un server Jellyfin"""
        servers = await self.config.servers()
        
        if nume_server not in servers:
            await ctx.send(f"❌ Serverul **{nume_server}** nu există.")
            return
        
        server_roles = await self.config.guild(ctx.guild).server_roles()
        server_roles[nume_server] = rol.id
        await self.config.guild(ctx.guild).server_roles.set(server_roles)
        
        await ctx.send(f"✅ Rolul {rol.mention} a fost setat pentru serverul **{nume_server}**.")
    
    @server.command(name="removerole")
    @checks.admin_or_permissions(manage_roles=True)
    async def remove_role(self, ctx, nume_server: str):
        """Elimină rolul pentru un server Jellyfin"""
        server_roles = await self.config.guild(ctx.guild).server_roles()
        
        if nume_server not in server_roles:
            await ctx.send(f"❌ Serverul **{nume_server}** nu are rol atribuit.")
            return
        
        del server_roles[nume_server]
        await self.config.guild(ctx.guild).server_roles.set(server_roles)
        
        await ctx.send(f"✅ Rolul a fost eliminat pentru serverul **{nume_server}**.")
    
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
            # Adaugă la tracking
            await self._add_user_to_tracking(ctx.author.id, nume_server, nume_utilizator)
            
            # Încearcă să atribuie rolul
            role_assigned = await self._assign_role(ctx.guild, ctx.author, nume_server)
            
            embed = discord.Embed(
                title="✅ Utilizator creat cu succes",
                color=0x00ff00,
                description=f"Utilizatorul **{nume_utilizator}** a fost creat pe serverul **{nume_server}**"
            )
            embed.add_field(name="Server URL", value=server_config["url"], inline=False)
            embed.add_field(name="Nume utilizator", value=nume_utilizator, inline=True)
            embed.add_field(name="Utilizator Discord", value=ctx.author.mention, inline=True)
            
            if role_assigned:
                embed.add_field(name="Rol atribuit", value="✅ Da", inline=True)
            else:
                embed.add_field(name="Rol atribuit", value="❌ Nu (verifică configurația)", inline=True)
            
            # Trimite mesajul în DM pentru securitate
            try:
                await ctx.author.send(embed=embed)
                await ctx.send(f"✅ Utilizatorul a fost creat! Verifică mesajele private pentru detalii.")
            except discord.Forbidden:
                await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Eroare la crearea utilizatorului: {result['error']}")
    
    @commands.command(name="utilizator", aliases=["user"])
    async def user_info(self, ctx, utilizator: Union[discord.Member, str]):
        """
        Afișează informații despre utilizatori Jellyfin
        
        Usage: .utilizator <@utilizator_discord sau nume_jellyfin>
        Exemplu: .utilizator @John sau john123
        """
        if not await self.config.guild(ctx.guild).enabled():
            await ctx.send("❌ Comenzile Jellyfin nu sunt activate pe acest server Discord.")
            return
        
        users_data = await self.config.users()
        servers_data = await self.config.servers()
        
        if isinstance(utilizator, discord.Member):
            # Caută după utilizatorul Discord
            user_id_str = str(utilizator.id)
            
            if user_id_str not in users_data or not users_data[user_id_str]:
                await ctx.send(f"❌ {utilizator.mention} nu are utilizatori Jellyfin creați.")
                return
            
            embed = discord.Embed(
                title="👤 Utilizatori Jellyfin",
                color=0x3498db,
                description=f"Utilizatori creați de {utilizator.mention}"
            )
            
            total_users = 0
            for server_name, server_users in users_data[user_id_str].items():
                if server_name in servers_data:
                    server_url = servers_data[server_name]["url"]
                    usernames = list(server_users.keys())
                    total_users += len(usernames)
                    
                    users_list = "\n".join([f"• {username}" for username in usernames])
                    embed.add_field(
                        name=f"🖥️ {server_name}",
                        value=f"**URL:** {server_url}\n**Utilizatori:**\n{users_list}",
                        inline=False
                    )
            
            embed.set_footer(text=f"Total utilizatori: {total_users}")
            
        else:
            # Caută după username-ul Jellyfin
            user_info = await self._get_user_by_jellyfin_username(utilizator)
            
            if not user_info:
                await ctx.send(f"❌ Utilizatorul Jellyfin **{utilizator}** nu a fost găsit.")
                return
            
            discord_user = self.bot.get_user(user_info["discord_user_id"])
            if not discord_user:
                try:
                    discord_user = await self.bot.fetch_user(user_info["discord_user_id"])
                except discord.NotFound:
                    discord_user_name = f"Utilizator necunoscut (ID: {user_info['discord_user_id']})"
                else:
                    discord_user_name = str(discord_user)
            else:
                discord_user_name = str(discord_user)
            
            server_url = servers_data.get(user_info["server_name"], {}).get("url", "URL necunoscut")
            created_at = datetime.fromisoformat(user_info["created_at"]).strftime("%d.%m.%Y %H:%M")
            
            embed = discord.Embed(
                title="🔍 Informații utilizator Jellyfin",
                color=0xe74c3c,
                description=f"Detalii pentru utilizatorul **{utilizator}**"
            )
            
            embed.add_field(name="👤 Utilizator Discord", value=discord_user_name, inline=True)
            embed.add_field(name="🖥️ Server", value=user_info["server_name"], inline=True)
            embed.add_field(name="🌐 URL Server", value=server_url, inline=False)
            embed.add_field(name="📅 Creat la", value=created_at, inline=True)
            
            # Caută și alți utilizatori de pe același server Discord
            user_id_str = str(user_info["discord_user_id"])
            if user_id_str in users_data:
                all_servers = []
                total_accounts = 0
                for srv_name, srv_users in users_data[user_id_str].items():
                    all_servers.append(f"• {srv_name} ({len(srv_users)} utilizatori)")
                    total_accounts += len(srv_users)
                
                if len(all_servers) > 1:
                    embed.add_field(
                        name="📋 Toate serverele utilizatorului",
                        value="\n".join(all_servers),
                        inline=False
                    )
                    embed.set_footer(text=f"Total conturi pe toate serverele: {total_accounts}")
        
        await ctx.send(embed=embed)
