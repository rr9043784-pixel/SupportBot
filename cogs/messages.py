import re

import discord
from discord.ext import commands

from storage import (
    get_custom_variables,
    set_custom_variable,
    delete_custom_variable,
)


VARIABLE_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,39}$")


class CustomMessages(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="variable", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def variable_group(self, ctx):
        await ctx.send(
            "Custom variable commands:\n"
            "`!variable list` — list variables\n"
            "`!variable set name value` — create or update a variable\n"
            "`!variable delete name` — delete a variable\n\n"
            "Example: `!variable set website https://example.com`\n"
            "Use it in templates as `{website}`."
        )

    @variable_group.command(name="list")
    async def variable_list(self, ctx):
        variables = get_custom_variables(ctx.guild.id)

        if not variables:
            await ctx.send("No custom variables have been created yet.")
            return

        lines = []
        for name, value in sorted(variables.items()):
            safe_value = str(value).replace("`", "ˋ")
            if len(safe_value) > 150:
                safe_value = safe_value[:147] + "..."
            lines.append(f"`{{{name}}}` = `{safe_value}`")

        # Keep the response within Discord's message limit.
        output = "\n".join(lines)
        if len(output) > 1800:
            output = output[:1790] + "\n..."

        await ctx.send(output, allowed_mentions=discord.AllowedMentions.none())

    @variable_group.command(name="set")
    async def variable_set(self, ctx, name: str, *, value: str):
        if not VARIABLE_NAME_RE.fullmatch(name):
            await ctx.send(
                "Invalid variable name. Use 1–40 letters, numbers, or "
                "underscores, and start with a letter."
            )
            return

        if len(value) > 2000:
            await ctx.send("Variable values cannot exceed 2000 characters.")
            return

        try:
            set_custom_variable(ctx.guild.id, name, value)
        except ValueError as exc:
            await ctx.send(str(exc))
            return

        await ctx.send(
            f"Saved custom variable `{{{name}}}`.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @variable_group.command(name="delete")
    async def variable_delete(self, ctx, name: str):
        if not VARIABLE_NAME_RE.fullmatch(name):
            await ctx.send("Invalid variable name.")
            return

        deleted = delete_custom_variable(ctx.guild.id, name)

        if not deleted:
            await ctx.send(f"Variable `{{{name}}}` was not found.")
            return

        await ctx.send(
            f"Deleted custom variable `{{{name}}}`.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="variablehelp")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def variable_help(self, ctx):
        embed = discord.Embed(
            title="Custom Variables",
            description=(
                "Create reusable placeholders for your server's message templates."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Create or update",
            value="`!variable set website https://example.com`",
            inline=False,
        )
        embed.add_field(
            name="Use in a template",
            value="`Visit {website} for more information.`",
            inline=False,
        )
        embed.add_field(
            name="List variables",
            value="`!variable list`",
            inline=False,
        )
        embed.add_field(
            name="Delete a variable",
            value="`!variable delete website`",
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(CustomMessages(bot)) 
