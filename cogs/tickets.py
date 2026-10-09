import asyncio
import logging
import re

import discord
from discord.ext import commands

from config import OWNER_ID
from storage import get_server_settings, save_server_settings

logger = logging.getLogger(__name__)


def tr(language, english, russian):
    return russian if language == "ru" else english


class TicketCreateView(discord.ui.View):
    def __init__(self, cog, panel_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.panel_id = str(panel_id)

        button = discord.ui.Button(
            label="Create Support Ticket",
            style=discord.ButtonStyle.primary,
            emoji="🎫",
            custom_id=f"supportbot:ticket:create:{self.panel_id}",
        )
        button.callback = self.create_ticket
        self.add_item(button)

    async def create_ticket(self, interaction: discord.Interaction):
        await self.cog.create_ticket(interaction, self.panel_id)


class TicketControlView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="supportbot:ticket:close",
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await self.cog.close_ticket(interaction)


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._registered_views = set()

    async def cog_load(self):
        # Re-register persistent views after bot restarts.
        for guild in list(self.bot.guilds):
            try:
                settings = get_server_settings(guild.id)
                for panel in settings["tickets"].get("panels", []):
                    panel_id = str(panel.get("id", ""))
                    if panel_id and panel_id not in self._registered_views:
                        self.bot.add_view(TicketCreateView(self, panel_id))
                        self._registered_views.add(panel_id)
            except Exception:
                logger.exception(
                    "Could not register ticket views for guild %s", guild.id
                )

        self.bot.add_view(TicketControlView(self))

    @staticmethod
    def _channel_name(member):
        name = re.sub(r"[^a-z0-9-]", "-", member.name.lower())
        name = re.sub(r"-+", "-", name).strip("-")[:40]
        return f"ticket-{name or member.id}"

    async def create_ticket(self, interaction, panel_id):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Please use this button in a server.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        member = interaction.user

        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Could not verify your server membership.",
                ephemeral=True,
            )
            return

        settings = get_server_settings(guild.id)
        ticket_settings = settings["tickets"]

        if not ticket_settings.get("enabled", True):
            await interaction.response.send_message(
                "Tickets are disabled on this server.",
                ephemeral=True,
            )
            return

        panel = next(
            (
                item for item in ticket_settings.get("panels", [])
                if str(item.get("id")) == str(panel_id)
            ),
            None,
        )

        if panel is None:
            await interaction.response.send_message(
                "This ticket panel is no longer configured. Please contact staff.",
                ephemeral=True,
            )
            return

        # Avoid creating duplicate open tickets for the same user.
        for channel in guild.text_channels:
            if (
                channel.topic
                and f"supportbot-ticket:{member.id}:" in channel.topic
            ):
                await interaction.response.send_message(
                    f"You already have an open ticket: {channel.mention}",
                    ephemeral=True,
                )
                return

        category = None
        category_id = ticket_settings.get("category_id")
        if category_id:
            category = guild.get_channel(int(category_id))

        if category_id and category is None:
            await interaction.response.send_message(
                "The configured ticket category no longer exists.",
                ephemeral=True,
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            ),
        }

        support_role_id = ticket_settings.get("support_role_id")
        if support_role_id:
            support_role = guild.get_role(int(support_role_id))
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                )

        try:
            channel = await guild.create_text_channel(
                name=self._channel_name(member),
                category=category,
                topic=(
                    f"supportbot-ticket:{member.id}:"
                    f"panel:{panel_id}"
                ),
                overwrites=overwrites,
                reason=f"Support ticket opened by {member}",
            )

            embed = discord.Embed(
                title="Support Ticket",
                description=(
                    f"Hello {member.mention}! Please describe your issue.\n\n"
                    "A staff member will respond as soon as possible."
                ),
                color=discord.Color.blurple(),
            )
            embed.add_field(
                name="Opened by",
                value=f"{member.mention} (`{member.id}`)",
                inline=False,
            )

            await channel.send(
                content=member.mention,
                embed=embed,
                view=TicketControlView(self),
                allowed_mentions=discord.AllowedMentions(
                    users=[member],
                    roles=False,
                    everyone=False,
                ),
            )

            await interaction.response.send_message(
                f"Your ticket has been created: {channel.mention}",
                ephemeral=True,
            )

        except discord.Forbidden:
            logger.warning(
                "Missing permissions to create ticket in guild %s", guild.id
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "I cannot create a ticket. Check my Manage Channels "
                    "and View Channels permissions.",
                    ephemeral=True,
                )

        except discord.HTTPException:
            logger.exception("Discord API failed while creating a ticket")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Discord could not create the ticket. Please try again later.",
                    ephemeral=True,
                )

    async def close_ticket(self, interaction):
        channel = interaction.channel
        guild = interaction.guild
        member = interaction.user

        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "This button only works inside a server ticket channel.",
                ephemeral=True,
            )
            return

        topic = channel.topic or ""
        match = re.search(r"supportbot-ticket:(\d+):", topic)
        if not match:
            await interaction.response.send_message(
                "This channel is not a SupportBot ticket.",
                ephemeral=True,
            )
            return

        requester_id = int(match.group(1))
        settings = get_server_settings(guild.id)
        support_role_id = settings["tickets"].get("support_role_id")

        is_requester = member.id == requester_id
        is_support = (
            isinstance(member, discord.Member)
            and (
                member.guild_permissions.manage_channels
                or member.guild_permissions.administrator
                or member.id == OWNER_ID
                or (
                    support_role_id
                    and any(
                        role.id == int(support_role_id)
                        for role in member.roles
                    )
                )
            )
        )

        if not is_requester and not is_support:
            await interaction.response.send_message(
                "Only the ticket creator or support staff can close this ticket.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Closing this ticket in 5 seconds...",
            ephemeral=True,
        )

        await asyncio.sleep(5)

        try:
            await channel.delete(
                reason=f"Ticket closed by {member} ({member.id})"
            )
        except discord.Forbidden:
            logger.warning("Missing permission to delete ticket %s", channel.id)
        except discord.HTTPException:
            logger.exception("Failed to delete ticket channel %s", channel.id)

    @commands.command(name="ticketpanel")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def ticket_panel(self, ctx, *, title="Support Ticket"):
        """Create a simple ticket panel in the current channel."""
        settings = get_server_settings(ctx.guild.id)
        ticket_settings = settings["tickets"]

        panel_id = str(discord.utils.MISSING)
        # A random persistent ID lets multiple panels coexist.
        import secrets
        panel_id = secrets.token_hex(6)

        embed = discord.Embed(
            title=title[:256],
            description="Click the button below to open a private support ticket.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="SupportBot")

        try:
            message = await ctx.send(
                embed=embed,
                view=TicketCreateView(self, panel_id),
            )
        except discord.Forbidden:
            await ctx.send(
                "I cannot send the panel. Check Send Messages and Embed Links permissions."
            )
            return

        panels = ticket_settings.setdefault("panels", [])
        panels.append({
            "id": panel_id,
            "channel_id": ctx.channel.id,
            "message_id": message.id,
            "title": title[:256],
        })
        ticket_settings["enabled"] = True
        settings["tickets"] = ticket_settings
        save_server_settings(ctx.guild.id, settings)

        self._registered_views.add(panel_id)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="ticketcategory")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def ticket_category(self, ctx, category_id: int):
        category = ctx.guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            await ctx.send("That ID is not a category on this server.")
            return

        settings = get_server_settings(ctx.guild.id)
        settings["tickets"]["category_id"] = category.id
        save_server_settings(ctx.guild.id, settings)
        await ctx.send(f"Ticket category set to **{category.name}**.")

    @commands.command(name="ticketsupportrole")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def ticket_support_role(self, ctx, role: discord.Role):
        settings = get_server_settings(ctx.guild.id)
        settings["tickets"]["support_role_id"] = role.id
        save_server_settings(ctx.guild.id, settings)
        await ctx.send(f"Support role set to {role.mention}.")

    @commands.command(name="ticketdisable")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def ticket_disable(self, ctx):
        settings = get_server_settings(ctx.guild.id)
        settings["tickets"]["enabled"] = False
        save_server_settings(ctx.guild.id, settings)
        await ctx.send("Tickets are now disabled on this server.")

    @commands.command(name="ticketenable")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def ticket_enable(self, ctx):
        settings = get_server_settings(ctx.guild.id)
        settings["tickets"]["enabled"] = True
        save_server_settings(ctx.guild.id, settings)
        await ctx.send("Tickets are now enabled on this server.")


async def setup(bot):
    await bot.add_cog(Tickets(bot)) 
