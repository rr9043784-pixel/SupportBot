import logging
import re
import time
import unicodedata
from collections import defaultdict, deque
from urllib.parse import urlparse

import discord
from discord.ext import commands

from config import OWNER_ID
from storage import get_server_settings, save_server_settings

logger = logging.getLogger(__name__)

INVITE_RE = re.compile(
    r"(?:discord(?:app)?\.com/invite/|discord\.gg/|discord\.com/invite/)",
    re.IGNORECASE,
)

URL_RE = re.compile(
    r"\b(?:https?://|www\.)[^\s<>]+|\b[a-z0-9-]+\.(?:com|net|org|gg|io|me|co|ru|dev|app|xyz)\b",
    re.IGNORECASE,
)

# Basic examples only. Server admins can configure their own list.
DEFAULT_BLOCKED_WORDS = {
    "exampleblockedword",
}

def normalize_text(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    # Remove combining marks and invisible formatting characters.
    chars = []
    for char in text:
        category = unicodedata.category(char)
        if category in {"Mn", "Cf"}:
            continue
        if char.isalnum() or char.isspace():
            chars.append(char)
    return re.sub(r"\s+", "", "".join(chars))


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_history = defaultdict(deque)
        self.last_messages = {}

    def exempt(self, message, settings):
        if message.author.id == OWNER_ID:
            return True

        if message.guild is None or not isinstance(message.author, discord.Member):
            return True

        if message.author.bot:
            return True

        if message.author.guild_permissions.administrator:
            return True

        if message.author.guild_permissions.manage_messages:
            return True

        exempt_ids = settings.get("automod", {}).get("exempt_role_ids", [])
        return any(role.id in exempt_ids for role in message.author.roles)

    @staticmethod
    def is_allowed_domain(url, allowed_domains):
        try:
            hostname = urlparse(
                url if "://" in url else "https://" + url
            ).hostname
        except ValueError:
            return False

        if not hostname:
            return False

        hostname = hostname.lower().rstrip(".")
        for domain in allowed_domains:
            domain = str(domain).lower().strip().rstrip(".")
            if domain and (
                hostname == domain or hostname.endswith("." + domain)
            ):
                return True

        return False

    def detect_violation(self, message, automod):
        content = message.content or ""

        if automod.get("block_invites", True) and INVITE_RE.search(content):
            return "Discord invites are not allowed."

        if automod.get("block_links", True):
            urls = URL_RE.findall(content)
            allowed_domains = automod.get("allowed_domains", [])
            for url in urls:
                if not self.is_allowed_domain(url, allowed_domains):
                    return "Links are not allowed in this server."

        if automod.get("block_spam", True):
            now = time.monotonic()
            key = (message.guild.id, message.author.id)
            history = self.message_history[key]
            window = max(1, int(automod.get("spam_window_seconds", 8)))

            while history and now - history[0] > window:
                history.popleft()

            history.append(now)

            if len(history) > 7:
                return "Please slow down. Spam is not allowed."

            repeat_key = (message.guild.id, message.author.id)
            normalized = normalize_text(content)
            previous = self.last_messages.get(repeat_key)

            if normalized and previous == normalized:
                count_key = (message.guild.id, message.author.id, normalized)
                count = getattr(self, "_repeat_counts", {})
                count[count_key] = count.get(count_key, 1) + 1
                self._repeat_counts = count

                limit = max(
                    2,
                    int(automod.get("max_repeated_messages", 5)),
                )
                if count[count_key] >= limit:
                    return "Repeated messages are not allowed."
            else:
                self._repeat_counts = getattr(self, "_repeat_counts", {})
                for old_key in list(self._repeat_counts):
                    if old_key[:2] == repeat_key:
                        del self._repeat_counts[old_key]

            self.last_messages[repeat_key] = normalized

        return None

    async def apply_penalty(self, message, reason, automod):
        penalty = automod.get("penalty", "delete")

        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            logger.warning(
                "AutoMod cannot delete message %s in guild %s",
                message.id,
                message.guild.id,
            )
            return
        except discord.HTTPException:
            logger.exception("AutoMod failed to delete message")
            return

        if penalty == "warn":
            try:
                await message.author.send(
                    f"Your message in **{message.guild.name}** was removed: {reason}"
                )
            except discord.Forbidden:
                pass

        elif penalty == "timeout":
            if not isinstance(message.author, discord.Member):
                return

            if not message.guild.me.guild_permissions.moderate_members:
                logger.warning("AutoMod needs Moderate Members permission.")
                return

            try:
                await message.author.timeout(
                    discord.utils.utcnow()
                    + __import__("datetime").timedelta(minutes=5),
                    reason=f"AutoMod: {reason}",
                )
            except discord.Forbidden:
                logger.warning("AutoMod could not timeout member %s", message.author.id)
            except discord.HTTPException:
                logger.exception("AutoMod timeout failed")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None or message.author.bot:
            return

        try:
            settings = get_server_settings(message.guild.id)
            automod = settings.get("automod", {})

            if not automod.get("enabled", False):
                return

            if self.exempt(message, settings):
                return

            reason = self.detect_violation(message, automod)
            if reason:
                await self.apply_penalty(message, reason, automod)

        except Exception:
            logger.exception(
                "AutoMod error in guild %s",
                getattr(message.guild, "id", "unknown"),
            )

    @commands.command(name="automod")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_command(self, ctx, mode: str = None):
        settings = get_server_settings(ctx.guild.id)

        if mode is None:
            automod = settings["automod"]
            await ctx.send(
                "AutoMod status: "
                + ("ON" if automod.get("enabled") else "OFF")
                + "\nCommands: `!automod on`, `!automod off`, "
                "`!automod links on/off`, `!automod invites on/off`, "
                "`!automod spam on/off`"
            )
            return

        mode = mode.lower()
        if mode not in {"on", "off"}:
            await ctx.send("Use `!automod on` or `!automod off`.")
            return

        settings["automod"]["enabled"] = mode == "on"
        save_server_settings(ctx.guild.id, settings)
        await ctx.send(f"AutoMod is now **{mode.upper()}**.")

    @commands.command(name="automodlinks")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_links(self, ctx, mode: str):
        await self.set_flag(ctx, "block_links", mode)

    @commands.command(name="automodinvites")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_invites(self, ctx, mode: str):
        await self.set_flag(ctx, "block_invites", mode)

    @commands.command(name="automodspam")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_spam(self, ctx, mode: str):
        await self.set_flag(ctx, "block_spam", mode)

    async def set_flag(self, ctx, key, mode):
        mode = mode.lower()
        if mode not in {"on", "off"}:
            await ctx.send("Use `on` or `off`.")
            return

        settings = get_server_settings(ctx.guild.id)
        settings["automod"][key] = mode == "on"
        save_server_settings(ctx.guild.id, settings)
        await ctx.send(f"{key.replace('_', ' ').title()}: **{mode.upper()}**")

    @commands.command(name="automodallowdomain")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_allow_domain(self, ctx, domain: str):
        domain = domain.lower().strip().rstrip(".")
        if (
            not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain)
            or ".." in domain
        ):
            await ctx.send("Enter a valid domain, for example `example.com`.")
            return

        settings = get_server_settings(ctx.guild.id)
        domains = settings["automod"].setdefault("allowed_domains", [])

        if domain not in domains:
            domains.append(domain)

        save_server_settings(ctx.guild.id, settings)
        await ctx.send(f"Allowed domain added: `{domain}`")

    @commands.command(name="automodremovedomain")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_remove_domain(self, ctx, domain: str):
        settings = get_server_settings(ctx.guild.id)
        domains = settings["automod"].setdefault("allowed_domains", [])

        try:
            domains.remove(domain.lower().strip().rstrip("."))
        except ValueError:
            await ctx.send("That domain is not in the allowlist.")
            return

        save_server_settings(ctx.guild.id, settings)
        await ctx.send(f"Allowed domain removed: `{domain}`")


async def setup(bot):
    await bot.add_cog(AutoMod(bot)) 
