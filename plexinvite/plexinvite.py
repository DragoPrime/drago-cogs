import discord
from redbot.core import commands, Config, checks
from plexapi.myplex import MyPlexAccount
import asyncio

class PlexInvite(commands.Cog):
    """Un cog care invită utilizatorii la un server Plex după ce obțin un anumit rol în Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {
            "plex_username": None,
            "plex_password": None,
            "plex_token": None,
            "invite_role": None
        }
        self.config.register_global(**default_global)

    async def initialize(self):
        plex_username = await self.config.plex_username()
        plex_password = await self.config.plex_password()
        plex_token = await self.config.plex_token()

        if not plex_username or not plex_password:
            raise ValueError("Numele de utilizator sau parola Plex nu sunt setate.")
        self.plex_account = MyPlexAccount(plex_username, plex_password, plex_token)

    @commands.group()
    @checks.is_owner()
    async def plex(self, ctx):
        """Plex management commands."""
        pass

    @plex.command()
    async def setup(self, ctx, username: str, password: str, token: str, role: discord.Role):
        """Setup Plex account credentials and the invite role."""
        await self.config.plex_username.set(username)
        await self.config.plex_password.set(password)
        await self.config.plex_token.set(token)
        await self.config.invite_role.set(role.id)
        await ctx.send(f"Acreditările Plex și rol de invitație setat la {role.name}!")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Listener to detect role assignment."""
        invite_role_id = await self.config.invite_role()
        if invite_role_id is None:
            return  # No role set

        invite_role = discord.utils.get(after.guild.roles, id=invite_role_id)

        # Check if the role was just added
        if invite_role in after.roles and invite_role not in before.roles:
            try:
                await after.send(
                    f"Salut {after.name}, ți s-a acordat acces la un rol special! "
                    "Pentru a vă finaliza accesul, vă rugăm să răspundeți cu adresa dvs. de e-mail pentru a primi o invitație pe serverul nostru Plex."
                )

                def check(m):
                    return m.author == after and isinstance(m.channel, discord.DMChannel)

                email_message = await self.bot.wait_for("message", check=check, timeout=300)
                email = email_message.content.strip()

                plex_username = await self.config.plex_username()
                plex_password = await self.config.plex_password()
                plex_token = await self.config.plex_token()

                plex_account = MyPlexAccount(plex_username, plex_password, plex_token)
                plex_account.inviteFriend(email, plex_account.resources())
                await after.send(f"S-a invitat cu succes {email} pe serverul Plex.")
            except asyncio.TimeoutError:
                await after.send("Ai luat prea mult timp să răspunzi. Vă rugăm să contactați un administrator pentru a fi invitat pe serverul Plex.")
            except Exception as e:
                await after.send(f"Nu s-a putut invita pe serverul Plex: {str(e)}")

    @commands.command()
    async def remove_invite(self, ctx, email: str):
        """Remove a user's invite from your Plex server."""
        await ctx.trigger_typing()

        try:
            plex_username = await self.config.plex_username()
            plex_password = await self.config.plex_password()
            plex_token = await self.config.plex_token()

            plex_account = MyPlexAccount(plex_username, plex_password, plex_token)
            plex_account.removeFriend(email)
            await ctx.send(f"{email} a fost eliminat cu succes de pe serverul Plex.")
        except Exception as e:
            await ctx.send(f"Failed to remove user: {str(e)}")

def setup(bot):
    plex_cog = PlexInvite(bot)
    bot.add_cog(plex_cog)
    bot.loop.create_task(plex_cog.initialize())
