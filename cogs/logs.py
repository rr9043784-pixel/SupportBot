import logging

import discord
from discord.ext import commands

from storage import get_server_settings, render_template, save_server_settings

logger = logging.getLogger(__name__)


class ServerLogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_log(self, guild, action, built_in=None):
        try:
            settings = get_server_settings(guild.id)
            logs = settings.get("logs", {})

            if not logs.get("enabled", False):
                return

            channel_id = logs.get("channel_id")
            if not channel_id:
                return

            channel = guild.get_channel(int(channel_id))
            if not isinstance(channel, discord.TextChannel):
                return

            values = {
                "action": action,
                "server_name": guild.name,
                "server_id": str(guild.id),
            }
            if built_in:
                values.update(built_in)

            template = logs.get(
                "message",
                "{user_name} performed an action: {action}",
            )
            text = render_template(guild.id, template, values)
            message_type = logs.get("message_type", "embed")

            if message_type == "normal":
                await channel.send(
                    text[:2000],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                embed = discord.Embed(
                    title="Server Log",
                    description=text[:4000],
                    color=discord.Color.orange(),
                    timestamp=discord.utils.utcnow(),
                )
                await channel.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )

        except discord.Forbidden:
            logger.warning(
                "Cannot send logs in guild %s: missing permissions",
                guild.id,
            )
        except discord.HTTPException:
            logger.exception("Discord API error while sending a server log")
        except Exception:
            logger.exception("Unexpected server logging error")

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild is None or message.author.bot:
            return

        content = message.content or "[No text content]"
        await self.send_log(
            message.guild,
            "Message deleted",
            {
                "user_name": message.author.name,
                "user_display_name": getattr(
                    message.author, "display_name", message.author.name
                ),
                "user_mention": f"<@{message.author.id}>",
                "user_id": str(message.author.id),
                "channel_name": getattr(message.channel, "name", "unknown"),
                "channel_id": str(message.channel.id),
                "message_content": content[:1000],
            },
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild is None or before.author.bot:
            return

        if before.content == after.content:
            return

        await self.send_log(
            before.guild,
            "Message edited",
            {
                "user_name": before.author.name,
                "user_display_name": getattr(
                    before.author, "display_name", before.author.name
                ),
                "user_mention": f"<@{before.author.id}>",
                "user_id": str(before.author.id),
                "channel_name": getattr(before.channel, "name", "unknown"),
                "channel_id": str(before.channel.id),
                "message_before": (before.content or "[Empty]")[:800],
                "message_after": (after.content or "[Empty]")[:800],
                "message_id": str(before.id),
            },
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.send_log(
            member.guild,
            "Member joined",
            {
                "user_name": member.name,
                "user_display_name": member.display_name,
                "user_mention": f"<@{member.id}>",
                "user_id": str(member.id),
                "member_count": str(member.guild.member_count or 0),
            },
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.send_log(
            member.guild,
            "Member left",
            {
                "user_name": member.name,
                "user_display_name": member.display_name,
                "user_mention": f"<@{member.id}>",
                "user_id": str(member.id),
                "member_count": str(member.guild.member_count or 0),
            },
        )

    @commands.command(name="logs")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_command(self, ctx, mode: str = None):
        settings = get_server_settings(ctx.guild.id)
        logs = settings["logs"]

        if mode is None:
            await ctx.send(
                "Server logs:\n"
                f"Enabled: **{logs.get('enabled', False)}**\n"
                f"Channel ID: `{logs.get('channel_id')}`\n"
                f"Message type: `{logs.get('message_type', 'embed')}`\n\n"
                "Commands: `!logs on`, `!logs off`, "
                "`!logschannel #channel`, `!logstype embed/normal`"
            )
            return

        mode = mode.lower()
        if mode not in {"on", "off"}:
            await ctx.send("Use `!logs on` or `!logs off`.")
            return

        logs["enabled"] = mode == "on"
        settings["logs"] = logs
        save_server_settings(ctx.guild.id, settings)

        await ctx.send(f"Server logs are now **{mode.upper()}**.")

    @commands.command(name="logschannel")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_channel(self, ctx, channel: discord.TextChannel):
        settings = get_server_settings(ctx.guild.id)
        settings["logs"]["channel_id"] = channel.id
        save_server_settings(ctx.guild.id, settings)

        await ctx.send(f"Log channel set to {channel.mention}.")

    @commands.command(name="logstype")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_type(self, ctx, message_type: str):
        message_type = message_type.lower()

        if message_type not in {"embed", "normal"}:
            await ctx.send("Use `embed` or `normal`.")
            return

        settings = get_server_settings(ctx.guild.id)
        settings["logs"]["message_type"] = message_type
        save_server_settings(ctx.guild.id, settings)

        await ctx.send(f"Log message type set to **{message_type}**.")

    @commands.command(name="logmessage")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_message(self, ctx, *, message: str):
        if len(message) > 4000:
            await ctx.send("The log template must be 4000 characters or fewer.")
            return

        settings = get_server_settings(ctx.guild.id)
        settings["logs"]["message"] = message
        save_server_settings(ctx.guild.id, settings)

        await ctx.send("Log message template saved.")


async def setup(bot):
    await bot.add_cog(ServerLogs(bot)) 
