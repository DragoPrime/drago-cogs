import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, Optional, Union, List
from datetime import datetime, timedelta, timezone

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
        self.config = Config.get_conf(self, identifier=1234567890)
        
        default_global = {
            "servers": {},
            "users": {}  # Format: {"discord_user_id": {"server_name": {"jellyfin_username": {"data": "...", "created_at": "timestamp", "jellyfin_id": "id", "status": "active"}}}}
        }
        
        default_guild = {
            "enabled": False,
            "server_roles": {},  # Format: {"server_name": role_id}
            "notification_channel": None,  # Channel pentru notificări automatice
            "auto_cleanup_enabled": True   # Activează/dezactivează cleanup-ul automat
        }
        
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        
        # Task pentru verificarea zilnică
        self.cleanup_task = None
        self.bot.loop.create_task(self._start_cleanup_task())
        
    def cog_unload(self):
        """Oprește task-ul când cog-ul este descărcat"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
    
    async def _start_cleanup_task(self):
        """Pornește task-ul de cleanup zilnic"""
        await self.bot.wait_until_ready()
        self.cleanup_task = self.bot.loop.create_task(self._daily_cleanup_loop())
    
    async def _daily_cleanup_loop(self):
        """Loop principal pentru verificarea zilnică"""
        while True:
            try:
                await asyncio.sleep(24 * 60 * 60)  # Așteaptă 24 de ore
                await self._check_inactive_users()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Eroare în daily cleanup loop: {e}")
                await asyncio.sleep(60 * 60)  # Încearcă din nou în 1 oră
    
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
    
    async def _get_user_last_activity(self, server_url: str, token: str, user_id: str) -> Optional[datetime]:
        """Obține ultima activitate a unui utilizator (ultima vizionare)"""
        # Încearcă să obțină ultimele items vizionate
        items_url = f"{server_url}/Users/{user_id}/Items"
        
        params = {
            "SortBy": "DatePlayed",
            "SortOrder": "Descending",
            "Limit": "1",
            "Filters": "IsPlayed",
            "Recursive": "true",
            "Fields": "DateLastSaved"
        }
        
        headers = {
            "X-MediaBrowser-Token": token
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # Încearcă să obțină ultimul item vizionat
                async with session.get(items_url, params=params, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("Items", [])
                        if items and len(items) > 0:
                            # Caută UserData pentru DateLastSaved
                            user_data = items[0].get("UserData", {})
                            last_played_str = user_data.get("LastPlayedDate")
                            
                            if last_played_str:
                                # Convertește la datetime naive
                                dt = datetime.fromisoformat(last_played_str.replace("Z", "+00:00"))
                                return dt.replace(tzinfo=None)
                
                # Dacă nu găsim activitate de playback, verificăm când s-a creat utilizatorul
                user_url = f"{server_url}/Users/{user_id}"
                async with session.get(user_url, headers=headers, timeout=10) as user_resp:
                    if user_resp.status == 200:
                        user_info = await user_resp.json()
                        # Folosim LastLoginDate sau LastActivityDate ca fallback
                        last_login_str = user_info.get("LastLoginDate") or user_info.get("LastActivityDate")
                        if last_login_str:
                            dt = datetime.fromisoformat(last_login_str.replace("Z", "+00:00"))
                            return dt.replace(tzinfo=None)
                
                return None
        except Exception as e:
            log.error(f"Eroare la obținerea ultimei activități pentru user {user_id}: {e}")
            return None
    
    async def _disable_jellyfin_user(self, server_url: str, token: str, user_id: str) -> bool:
        """Dezactivează un utilizator Jellyfin"""
        disable_url = f"{server_url}/Users/{user_id}/Policy"
    
        # Obține politica actuală
        headers = {"X-MediaBrowser-Token": token}
    
        try:
            async with aiohttp.ClientSession() as session:
                log.info(f"Obținere politică pentru user {user_id} de la {disable_url}")
                async with session.get(disable_url, headers=headers, timeout=10) as resp:
                    log.info(f"Status GET policy: {resp.status}")
                    if resp.status == 200:
                        policy = await resp.json()
                        log.info(f"Politică obținută, IsDisabled curent: {policy.get('IsDisabled', 'N/A')}")
                        policy["IsDisabled"] = True
                    
                        # Actualizează politica
                        log.info(f"Trimit UPDATE cu IsDisabled=True")
                        async with session.post(disable_url, json=policy, headers=headers, timeout=10) as update_resp:
                            log.info(f"Status POST policy: {update_resp.status}")
                            if update_resp.status == 204:
                                log.info("✅ Utilizator dezactivat cu succes")
                                return True
                            else:
                                error_text = await update_resp.text()
                                log.error(f"POST a returnat {update_resp.status}: {error_text}")
                                return False
                    else:
                        error_text = await resp.text()
                        log.error(f"GET policy a returnat {resp.status}: {error_text}")
                        return False
        except Exception as e:
            log.error(f"Eroare la dezactivarea utilizatorului: {e}", exc_info=True)
    
        return False
    
    async def _delete_jellyfin_user(self, server_url: str, token: str, user_id: str) -> bool:
        """Șterge un utilizator Jellyfin"""
        delete_url = f"{server_url}/Users/{user_id}"
        
        headers = {"X-MediaBrowser-Token": token}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(delete_url, headers=headers, timeout=10) as resp:
                    return resp.status == 204
        except Exception as e:
            log.error(f"Eroare la ștergerea utilizatorului: {e}")
        
        return False
    
    async def _check_inactive_users(self):
        """Verifică utilizatorii inactivi și îi gestionează"""
        log.info("=== ÎNCEPE VERIFICAREA INACTIVITĂȚII ===")
        
        servers = await self.config.servers()
        users = await self.config.users()
        
        log.info(f"Servere configurate: {len(servers)}")
        log.info(f"Utilizatori în tracking: {len(users)}")
        
        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)
        
        log.info(f"Data curentă: {now}")
        log.info(f"Limită 30 zile: {thirty_days_ago}")
        log.info(f"Limită 60 zile: {sixty_days_ago}")
        
        total_checked = 0
        total_disabled = 0
        total_deleted = 0
        
        for discord_user_id, user_servers in users.items():
            log.info(f"\n--- Verificare utilizator Discord ID: {discord_user_id} ---")
            
            for server_name, server_users in user_servers.items():
                log.info(f"  Server: {server_name}")
                
                if server_name not in servers:
                    log.warning(f"  ⚠️ Server {server_name} nu mai există în configurație, skip")
                    continue
                
                server_config = servers[server_name]
                log.info(f"  Conectare la: {server_config['url']}")
                
                token = await self._get_jellyfin_auth_token(
                    server_config["url"],
                    server_config["admin_user"],
                    server_config["admin_password"]
                )
                
                if not token:
                    log.error(f"  ❌ Nu s-a putut obține token pentru {server_name}")
                    continue
                
                log.info(f"  ✅ Token obținut cu succes")
                
                for jellyfin_username, user_data in server_users.items():
                    total_checked += 1
                    jellyfin_id = user_data.get("jellyfin_id")
                    current_status = user_data.get("status", "active")
                    
                    log.info(f"\n    👤 Utilizator Jellyfin: {jellyfin_username}")
                    log.info(f"       ID: {jellyfin_id}")
                    log.info(f"       Status curent: {current_status}")
                    
                    if not jellyfin_id:
                        log.warning(f"       ⚠️ Nu există jellyfin_id, skip")
                        continue
                    
                    # Obține ultima activitate
                    last_activity = await self._get_user_last_activity(
                        server_config["url"], token, jellyfin_id
                    )
                    
                    if not last_activity:
                        log.warning(f"       ⚠️ Nu s-a putut obține last_activity")
                        # Dacă nu putem obține activitatea, folosim data creării
                        created_at_str = user_data.get("created_at")
                        if created_at_str:
                            created_at = datetime.fromisoformat(created_at_str)
                            if created_at.tzinfo is not None:
                                created_at = created_at.replace(tzinfo=None)
                            last_activity = created_at
                            log.info(f"       📅 Folosim created_at ca fallback: {created_at}")
                        else:
                            log.error(f"       ❌ Nu există nici created_at, skip complet")
                            continue
                    else:
                        log.info(f"       📅 Last activity găsit: {last_activity}")
                    
                    # Calculează zilele de inactivitate
                    days_inactive = (now - last_activity).days
                    log.info(f"       ⏰ Zile de inactivitate: {days_inactive}")
                    
                    # Verifică dacă trebuie șters (60+ zile)
                    if last_activity <= sixty_days_ago and current_status != "deleted":
                        log.info(f"       🗑️ TREBUIE ȘTERS (>60 zile, status: {current_status})")
                        
                        success = await self._delete_jellyfin_user(
                            server_config["url"], token, jellyfin_id
                        )
                        
                        if success:
                            log.info(f"       ✅ Utilizator șters cu succes")
                            # Actualizează statusul
                            user_data["status"] = "deleted"
                            await self.config.users.set(users)
                            total_deleted += 1
                            
                            # Trimite notificare
                            await self._send_cleanup_notification(
                                server_name, jellyfin_username, discord_user_id, "deleted", last_activity
                            )
                        else:
                            log.error(f"       ❌ Ștergerea a eșuat")
                    
                    # Verifică dacă trebuie dezactivat (30+ zile)
                    elif last_activity <= thirty_days_ago and current_status == "active":
                        log.info(f"       ⚠️ TREBUIE DEZACTIVAT (>30 zile, status: active)")
                        
                        success = await self._disable_jellyfin_user(
                            server_config["url"], token, jellyfin_id
                        )
                        
                        if success:
                            log.info(f"       ✅ Utilizator dezactivat cu succes")
                            # Actualizează statusul
                            user_data["status"] = "disabled"
                            await self.config.users.set(users)
                            total_disabled += 1
                            
                            # Trimite notificare
                            await self._send_cleanup_notification(
                                server_name, jellyfin_username, discord_user_id, "disabled", last_activity
                            )
                        else:
                            log.error(f"       ❌ Dezactivarea a eșuat")
                    else:
                        log.info(f"       ✅ Nu necesită acțiuni (zile: {days_inactive}, status: {current_status})")
        
        log.info(f"\n=== VERIFICARE COMPLETATĂ ===")
        log.info(f"Total verificați: {total_checked}")
        log.info(f"Total dezactivați: {total_disabled}")
        log.info(f"Total șterși: {total_deleted}")
    
    async def _send_cleanup_notification(self, server_name: str, jellyfin_username: str, discord_user_id: int, action: str, last_activity: datetime):
        """Trimite notificare despre acțiunea de cleanup"""
        # Caută toate guild-urile unde este configurat acest server
        all_guilds = await self.config.all_guilds()
        
        for guild_id, guild_config in all_guilds.items():
            if not guild_config.get("auto_cleanup_enabled", True):
                continue
                
            notification_channel_id = guild_config.get("notification_channel")
            if not notification_channel_id:
                continue
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            
            channel = guild.get_channel(notification_channel_id)
            if not channel:
                continue
            
            # Obține informații despre utilizatorul Discord
            try:
                discord_user = await self.bot.fetch_user(discord_user_id)
                discord_user_name = str(discord_user)
            except:
                discord_user_name = f"Utilizator necunoscut (ID: {discord_user_id})"
            
            # Creează embed-ul de notificare
            color = 0xffa500 if action == "disabled" else 0xff0000  # Orange pentru disabled, roșu pentru deleted
            action_text = "dezactivat" if action == "disabled" else "șters"
            icon = "⚠️" if action == "disabled" else "🗑️"
            
            embed = discord.Embed(
                title=f"{icon} Utilizator {action_text}",
                color=color,
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 Utilizator Discord", value=discord_user_name, inline=True)
            embed.add_field(name="🎬 Utilizator Jellyfin", value=jellyfin_username, inline=True)
            embed.add_field(name="🖥️ Server", value=server_name, inline=True)
            embed.add_field(name="📅 Ultima activitate", value=last_activity.strftime("%d.%m.%Y %H:%M"), inline=False)
            
            days_inactive = (datetime.now() - last_activity).days
            embed.add_field(name="⏰ Zile inactive", value=str(days_inactive), inline=True)
            
            if action == "disabled":
                embed.add_field(name="ℹ️ Notă", value="Utilizatorul va fi șters în 30 de zile dacă rămâne inactiv", inline=False)
            
            embed.set_footer(text="Cleanup automat Jellyfin")
            
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                log.error(f"Nu am permisiuni să trimit mesaj în canalul {channel.id}")
            except Exception as e:
                log.error(f"Eroare la trimiterea notificării: {e}")
    
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
    
    async def _add_user_to_tracking(self, discord_user_id: int, server_name: str, jellyfin_username: str, jellyfin_id: str):
        """Adaugă utilizatorul la sistemul de tracking"""
        users = await self.config.users()
        user_id_str = str(discord_user_id)
        
        if user_id_str not in users:
            users[user_id_str] = {}
        
        if server_name not in users[user_id_str]:
            users[user_id_str][server_name] = {}
        
        users[user_id_str][server_name][jellyfin_username] = {
            "created_at": datetime.now().isoformat(),
            "server_name": server_name,
            "jellyfin_id": jellyfin_id,
            "status": "active"
        }
        
        await self.config.users.set(users)
    
    async def _get_user_by_jellyfin_username(self, jellyfin_username: str) -> Optional[Dict[str, Any]]:
        """Găsește utilizatorul Discord după username-ul Jellyfin"""
        users = await self.config.users()
        
        for discord_user_id, user_data in users.items():
            for server_name, server_users in user_data.items():
                if jellyfin_username in server_users:
                    user_info = server_users[jellyfin_username]
                    return {
                        "discord_user_id": int(discord_user_id),
                        "server_name": server_name,
                        "jellyfin_username": jellyfin_username,
                        "created_at": user_info["created_at"],
                        "jellyfin_id": user_info.get("jellyfin_id"),
                        "status": user_info.get("status", "active")
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
    
    @server.command(name="setchannel")
    @checks.admin_or_permissions(manage_channels=True)
    async def set_notification_channel(self, ctx, channel: discord.TextChannel):
        """Setează canalul pentru notificări de cleanup automat"""
        await self.config.guild(ctx.guild).notification_channel.set(channel.id)
        await ctx.send(f"✅ Canalul pentru notificări a fost setat la {channel.mention}")
    
    @server.command(name="removechannel")
    @checks.admin_or_permissions(manage_channels=True)
    async def remove_notification_channel(self, ctx):
        """Elimină canalul pentru notificări"""
        await self.config.guild(ctx.guild).notification_channel.set(None)
        await ctx.send("✅ Canalul pentru notificări a fost eliminat")
    
    @server.command(name="togglecleanup")
    @checks.admin_or_permissions(manage_guild=True)
    async def toggle_cleanup(self, ctx):
        """Activează/dezactivează cleanup-ul automat pe acest server"""
        current = await self.config.guild(ctx.guild).auto_cleanup_enabled()
        new_status = not current
        await self.config.guild(ctx.guild).auto_cleanup_enabled.set(new_status)
        
        status_text = "activat" if new_status else "dezactivat"
        await ctx.send(f"✅ Cleanup-ul automat a fost {status_text}")
    
    @server.command(name="checkcleanup")
    @checks.is_owner()
    async def manual_cleanup_check(self, ctx):
        """Execută manual verificarea pentru cleanup (doar pentru testare)"""
        await ctx.send("🔄 Încep verificarea manuală a utilizatorilor inactivi...")
        await self._check_inactive_users()
        await ctx.send("✅ Verificarea a fost completată!")
    
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
        
        # Informații despre cleanup
        notification_channel_id = await self.config.guild(ctx.guild).notification_channel()
        cleanup_enabled = await self.config.guild(ctx.guild).auto_cleanup_enabled()
        
        embed = discord.Embed(title="🖥️ Servere Jellyfin configurate", color=0x3498db)
        embed.description = "\n".join(server_list)
        
        cleanup_info = f"**Cleanup automat:** {'✅ Activat' if cleanup_enabled else '❌ Dezactivat'}\n"
        if notification_channel_id:
            channel = ctx.guild.get_channel(notification_channel_id)
            cleanup_info += f"**Canal notificări:** {channel.mention if channel else 'Canal șters'}"
        else:
            cleanup_info += "**Canal notificări:** Nu este setat"
        
        embed.add_field(name="⚙️ Configurația Cleanup", value=cleanup_info, inline=False)
        
        await ctx.send(embed=embed)
    
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
            await self._add_user_to_tracking(ctx.author.id, nume_server, nume_utilizator, result["user_id"])
            
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
            embed.add_field(name="Status", value="🟢 Activ", inline=True)
            
            if role_assigned:
                embed.add_field(name="Rol atribuit", value="✅ Da", inline=True)
            else:
                embed.add_field(name="Rol atribuit", value="❌ Nu (verifică configurația)", inline=True)
            
            embed.add_field(name="ℹ️ Notă", value="Utilizatorul va fi dezactivat după 30 de zile de inactivitate și șters după 60 de zile", inline=False)
            
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
            active_users = 0
            disabled_users = 0
            deleted_users = 0
            
            for server_name, server_users in users_data[user_id_str].items():
                if server_name in servers_data:
                    server_url = servers_data[server_name]["url"]
                    
                    users_list = []
                    for username, user_info in server_users.items():
                        status = user_info.get("status", "active")
                        if status == "active":
                            status_icon = "🟢"
                            active_users += 1
                        elif status == "disabled":
                            status_icon = "🟡"
                            disabled_users += 1
                        else:  # deleted
                            status_icon = "🔴"
                            deleted_users += 1
                        
                        users_list.append(f"{status_icon} {username}")
                        total_users += 1
                    
                    embed.add_field(
                        name=f"🖥️ {server_name}",
                        value=f"**URL:** {server_url}\n**Utilizatori:**\n" + "\n".join(users_list),
                        inline=False
                    )
            
            # Footer cu statistici
            footer_text = f"Total: {total_users} | "
            footer_text += f"🟢 Activi: {active_users} | "
            footer_text += f"🟡 Dezactivați: {disabled_users} | "
            footer_text += f"🔴 Șterși: {deleted_users}"
            
            embed.set_footer(text=footer_text)
            
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
            
            # Determină culoarea și statusul
            status = user_info.get("status", "active")
            if status == "active":
                color = 0x00ff00
                status_text = "🟢 Activ"
            elif status == "disabled":
                color = 0xffa500
                status_text = "🟡 Dezactivat"
            else:  # deleted
                color = 0xff0000
                status_text = "🔴 Șters"
            
            embed = discord.Embed(
                title="🔍 Informații utilizator Jellyfin",
                color=color,
                description=f"Detalii pentru utilizatorul **{utilizator}**"
            )
            
            embed.add_field(name="👤 Utilizator Discord", value=discord_user_name, inline=True)
            embed.add_field(name="📊 Status", value=status_text, inline=True)
            embed.add_field(name="🖥️ Server", value=user_info["server_name"], inline=True)
            embed.add_field(name="🌐 URL Server", value=server_url, inline=False)
            embed.add_field(name="📅 Creat la", value=created_at, inline=True)
            
            # Calculează zilele de inactivitate (doar pentru utilizatori activi/dezactivați)
            if status != "deleted":
                created_date = datetime.fromisoformat(user_info["created_at"])
                days_since_creation = (datetime.now() - created_date).days
                
                if status == "active":
                    if days_since_creation >= 30:
                        embed.add_field(name="⚠️ Atenție", value="Acest utilizator ar trebui să fie dezactivat pentru inactivitate", inline=False)
                elif status == "disabled":
                    if days_since_creation >= 60:
                        embed.add_field(name="🗑️ Atenție", value="Acest utilizator ar trebui să fie șters pentru inactivitate", inline=False)
            
            # Caută și alți utilizatori de pe același server Discord
            user_id_str = str(user_info["discord_user_id"])
            if user_id_str in users_data:
                all_servers = []
                total_accounts = 0
                for srv_name, srv_users in users_data[user_id_str].items():
                    active_count = sum(1 for u in srv_users.values() if u.get("status", "active") == "active")
                    disabled_count = sum(1 for u in srv_users.values() if u.get("status", "active") == "disabled")
                    deleted_count = sum(1 for u in srv_users.values() if u.get("status", "active") == "deleted")
                    
                    status_info = f"🟢{active_count}"
                    if disabled_count > 0:
                        status_info += f" 🟡{disabled_count}"
                    if deleted_count > 0:
                        status_info += f" 🔴{deleted_count}"
                    
                    all_servers.append(f"• {srv_name} ({status_info})")
                    total_accounts += len(srv_users)
                
                if len(all_servers) > 1:
                    embed.add_field(
                        name="📋 Toate serverele utilizatorului",
                        value="\n".join(all_servers),
                        inline=False
                    )
                    embed.set_footer(text=f"Total conturi pe toate serverele: {total_accounts}")
        
        await ctx.send(embed=embed)
