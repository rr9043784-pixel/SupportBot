
import os
import discord

from discord.ext import commands
from flask import Flask
from threading import Thread


# =========================
# SETTINGS
# =========================

TOKEN = os.environ["DISCORD_TOKEN"]

OWNER_ID = 1176149190192152626


# =========================
# DISCORD BOT
# =========================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# WEBSITE
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">

        <title>Discord Bot Dashboard</title>

        <style>
            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: #0f1117;
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }

            .container {
                text-align: center;
                padding: 40px;
            }

            h1 {
                font-size: 42px;
                margin-bottom: 10px;
            }

            p {
                color: #aeb4c0;
                font-size: 18px;
            }

            .status {
                display: inline-block;
                margin-top: 25px;
                padding: 12px 22px;
                border-radius: 10px;
                background: #20242d;
                color: #55ff88;
            }
        </style>
    </head>

    <body>
        <div class="container">
            <h1>Discord Bot Dashboard</h1>

            <p>
                Manage your Discord server with an easy dashboard.
            </p>

            <div class="status">
                ● Bot is online
            </div>
        </div>
    </body>
    </html>
    """


@app.route("/health")
def health():
    return "OK"


def run_website():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================
# DISCORD EVENTS
# =========================

@bot.event
async def on_ready():
    print("--------------------------------")
    print(f"Logged in as: {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print(f"Servers: {len(bot.guilds)}")
    print("--------------------------------")


# =========================
# TEST COMMAND
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")


# =========================
# START
# =========================

if __name__ == "__main__":
    website_thread = Thread(
        target=run_website,
        daemon=True
    )

    website_thread.start()

    bot.run(TOKEN)
