import logging

import discord
from discord.ext import commands

from storage import get_server_settings, render_template

logger = logging.getLogger(__name__)


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            settings = get_server_settings(member.guild.id)
            welcome = settings.get("welcome", {})

            if not welcome.get("enabled", False):
                return

            channel_id = welcome.get("channel_id")
            if not channel_id:
                return

            channel = member.guild.get_channel(int(channel_id))
            if not isinstance(channel, discord.TextChannel):
                logger.warning(
                    "Welcome channel missing in guild %s",
                    member.guild.id,
                )
                return

            built_in = {
                "user_name": member.name,
                "user_display_name": member.display_name,
                "user_mention": member.mention,
                "user_id": str(member.id),
                "server_name": member.guild.name,
                "server_id": str(member.guild.id),
                "member_count": str(member.guild.member_count or 0),
            }

            template = welcome.get(
                "message",
                "Welcome, {user_mention}, to {server_name}!",
            )
            text = render_template(member.guild.id, template, built_in)

            message_type = welcome.get("message_type", "embed")

            if message_type == "normal":
                await channel.send(
                    text,
                    allowed_mentions=discord.AllowedMentions(
                        users=True,
                        roles=False,
                        everyone=False,
                    ),
                )
            else:
                embed = discord.Embed(
                    description=text[:4000],
                    color=discord.Color.green(),
                )
                embed.set_author(
                    name=f"Welcome to {member.guild.name}",
                )

                if member.display_avatar:
                    embed.set_thumbnail(url=member.display_avatar.url)

                embed.set_footer(
                    text=f"Member #{member.guild.member_count or 0}"
                )

                await channel.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(
                        users=True,
                        roles=False,
                        everyone=False,
                    ),
                )

        except discord.Forbidden:
            logger.warning(
                "No permission to send welcome message in guild %s",
                member.guild.id,
            )
        except discord.HTTPException:
            logger.exception(
                "Discord API error while sending welcome message"
            )
        except Exception:
            logger.exception(
                "Unexpected welcome module error in guild %s",
                member.guild.id,
            )

    @commands.command(name="welcome")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def welcome_command(self, ctx, mode: str = None):
        settings = get_server_settings(ctx.guild.id)
        welcome = settings["welcome"]

        if mode is None:
            await ctx.send(
                "Welcome settings:\n"
                f"Enabled: **{welcome.get('enabled', False)}**\n"
                f"Channel ID: `{welcome.get('channel_id')}`\n"
                f"Message type: `{welcome.get('message_type', 'embed')}`\n\n"
                "Commands: `!welcome on`, `!welcome off`, "
                "`!welcomechannel #channel`, `!welcometype embed/normal`"
            )
            return

        mode = mode.lower()
        if mode not in {"on", "off"}:
            await ctx.send("Use `!welcome on` or `!welcome off`.")
            return

        welcome["enabled"] = mode == "on"
        settings["welcome"] = welcome

        from storage import save_server_settings
        save_server_settings(ctx.guild.id, settings)

        await ctx.send(f"Welcome messages are now **{mode.upper()}**.")

    @commands.command(name="welcomechannel")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def welcome_channel(self, ctx, channel: discord.TextChannel):
        settings = get_server_settings(ctx.guild.id)
        settings["welcome"]["channel_id"] = channel.id

        from storage import save_server_settings
        save_server_settings(ctx.guild.id, settings)

        await ctx.send(f"Welcome channel set to {channel.mention}.")

    @commands.command(name="welcometype")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def welcome_type(self, ctx, message_type: str):
        message_type = message_type.lower()

        if message_type not in {"embed", "normal"}:
            await ctx.send("Use `embed` or `normal`.")
            return

        settings = get_server_settings(ctx.guild.id)
        settings["welcome"]["message_type"] = message_type

        from storage import save_server_settings
        save_server_settings(ctx.guild.id, settings)

        await ctx.send(f"Welcome message type set to **{message_type}**.")

    @commands.command(name="welcomemessage")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def welcome_message(self, ctx, *, message: str):
        if len(message) > 4000:
            await ctx.send("The welcome message must be 4000 characters or fewer.")
            return

        settings = get_server_settings(ctx.guild.id)
        settings["welcome"]["message"] = message

        from storage import save_server_settings
        save_server_settings(ctx.guild.id, settings)

        await ctx.send("Welcome message saved.")


async def setup(bot):
    await bot.add_cog(Welcome(bot)) 
