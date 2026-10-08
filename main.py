import os
import secrets
import urllib.parse
import urllib.request
import urllib.error
import json

import discord
from discord.ext import commands
from flask import Flask, session, redirect, request, render_template_string


# =========================
# SETTINGS
# =========================

TOKEN = os.environ["DISCORD_TOKEN"]

CLIENT_ID = os.environ["DISCORD_CLIENT_ID"]
CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"]
REDIRECT_URI = os.environ["DISCORD_REDIRECT_URI"]

# Используем стабильный ключ для Flask-сессии
app_secret = CLIENT_SECRET


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
app.secret_key = app_secret


# =========================
# HTML
# =========================

HOME_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>SupportBot</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            background: #0f1117;
            color: white;
            font-family: Arial, sans-serif;

            display: flex;
            justify-content: center;
            align-items: center;
        }

        .container {
            width: 90%;
            max-width: 700px;
            text-align: center;
        }

        h1 {
            font-size: 48px;
            margin-bottom: 10px;
        }

        p {
            color: #aeb4c0;
            font-size: 18px;
        }

        .login {
            display: inline-block;
            margin-top: 30px;
            padding: 15px 25px;

            background: #5865F2;
            color: white;

            text-decoration: none;
            border-radius: 10px;

            font-size: 17px;
            font-weight: bold;
        }

        .login:hover {
            opacity: 0.9;
        }
    </style>
</head>

<body>

<div class="container">

    <h1>SupportBot</h1>

    <p>
        Manage your Discord servers with an easy dashboard.
    </p>

    <a class="login" href="/login">
        Login with Discord
    </a>

</div>

</body>
</html>
"""


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Dashboard - SupportBot</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            background: #0f1117;
            color: white;
            font-family: Arial, sans-serif;
        }

        header {
            padding: 20px 30px;
            background: #171a22;

            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo {
            font-size: 22px;
            font-weight: bold;
        }

        .user {
            color: #b9bec9;
        }

        .container {
            width: 90%;
            max-width: 1100px;
            margin: 40px auto;
        }

        h1 {
            margin-bottom: 30px;
        }

        .servers {
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(250px, 1fr));

            gap: 20px;
        }

        .server {
            background: #191d27;
            border: 1px solid #292e3a;
            border-radius: 14px;
            padding: 22px;
        }

        .server h2 {
            margin-top: 0;
        }

        .manage {
            display: inline-block;
            margin-top: 15px;
            padding: 10px 16px;

            background: #5865F2;
            color: white;

            text-decoration: none;
            border-radius: 8px;
        }

        .invite {
            display: inline-block;
            margin-top: 15px;
            padding: 10px 16px;

            background: #20242e;
            color: white;

            text-decoration: none;
            border-radius: 8px;
        }

        .logout {
            color: #ff6b6b;
            text-decoration: none;
        }
    </style>
</head>

<body>

<header>

    <div class="logo">
        SupportBot
    </div>

    <div>
        {{ username }}
        &nbsp; | &nbsp;
        <a class="logout" href="/logout">Logout</a>
    </div>

</header>


<div class="container">

    <h1>Your Servers</h1>

    <div class="servers">

        {% for server in servers %}

        <div class="server">

            <h2>{{ server.name }}</h2>

            {% if server.manageable %}

                <a class="manage"
                   href="/server/{{ server.id }}">
                    Manage
                </a>

            {% else %}

                <a class="invite"
                   href="{{ server.invite }}"
                   target="_blank">
                    Add SupportBot
                </a>

            {% endif %}

        </div>

        {% endfor %}

    </div>

</div>

</body>
</html>
"""


SERVER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>{{ server.name }} - SupportBot</title>

    <style>

        body {
            margin: 0;
            background: #0f1117;
            color: white;
            font-family: Arial, sans-serif;
        }

        .container {
            width: 90%;
            max-width: 900px;
            margin: 50px auto;
        }

        .card {
            background: #191d27;
            border: 1px solid #292e3a;
            border-radius: 14px;
            padding: 30px;
        }

        a {
            color: white;
            text-decoration: none;
        }

        .back {
            color: #aeb4c0;
        }

    </style>
</head>

<body>

<div class="container">

    <a class="back" href="/dashboard">
        ← Back to Dashboard
    </a>

    <div class="card">

        <h1>{{ server.name }}</h1>

        <p>
            Server ID: {{ server.id }}
        </p>

        <p>
            Dashboard settings will be added here.
        </p>

    </div>

</div>

</body>
</html>
"""


# =========================
# DISCORD OAUTH
# =========================

def discord_request(url, data=None, headers=None):

    if data is not None:
        encoded = urllib.parse.urlencode(data).encode()
    else:
        encoded = None

    req = urllib.request.Request(
        url,
        data=encoded,
        headers=headers or {}
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


def get_discord_user(access_token):

    return discord_request(
        "https://discord.com/api/v10/users/@me",
        headers={
            "Authorization": f"Bearer {access_token}"
        }
    )


def get_discord_guilds(access_token):

    return discord_request(
        "https://discord.com/api/v10/users/@me/guilds",
        headers={
            "Authorization": f"Bearer {access_token}"
        }
    )


# =========================
# HOME
# =========================

@app.route("/")
def home():

    if session.get("user"):
        return redirect("/dashboard")

    return render_template_string(HOME_HTML)


# =========================
# LOGIN
# =========================

@app.route("/login")
def login():

    state = secrets.token_urlsafe(32)

    session["oauth_state"] = state

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state
    }

    url = (
        "https://discord.com/oauth2/authorize?"
        + urllib.parse.urlencode(params)
    )

    return redirect(url)


# =========================
# CALLBACK
# =========================

@app.route("/callback")
def callback():

    error = request.args.get("error")

    if error:
        return f"""
        <h1>Discord Login Failed</h1>
        <p>{error}</p>
        """

    state = request.args.get("state")

    if not state or state != session.get("oauth_state"):
        return "Invalid OAuth state.", 400

    code = request.args.get("code")

    if not code:
        return "Missing authorization code.", 400

    try:

        token_data = discord_request(
            "https://discord.com/api/v10/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI
            },
            headers={
                "Content-Type":
                    "application/x-www-form-urlencoded"
            }
        )

        access_token = token_data["access_token"]

        user = get_discord_user(access_token)

        session["access_token"] = access_token
        session["user"] = user

        session.pop("oauth_state", None)

        return redirect("/dashboard")

    except Exception as e:

        print("OAuth error:", e)

        return """
        <h1>Login Error</h1>
        <p>Could not complete Discord login.</p>
        """, 500


# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():

    if not session.get("user"):
        return redirect("/login")

    access_token = session.get("access_token")

    try:

        guilds = get_discord_guilds(access_token)

    except Exception:

        session.clear()

        return redirect("/login")

    servers = []

    for guild in guilds:

        permissions = int(guild.get("permissions", 0))

        owner = guild.get("owner", False)

        # MANAGE_GUILD = 0x20
        manageable = owner or bool(
            permissions & 0x20
        )

        invite = (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={CLIENT_ID}"
            f"&scope=bot%20applications.commands"
            f"&permissions=8"
            f"&guild_id={guild['id']}"
        )

        servers.append({
            "id": guild["id"],
            "name": guild["name"],
            "manageable": manageable,
            "invite": invite
        })

    return render_template_string(
        DASHBOARD_HTML,
        username=session["user"].get("username", "User"),
        servers=servers
    )


# =========================
# SERVER
# =========================

@app.route("/server/<server_id>")
def server_dashboard(server_id):

    if not session.get("user"):
        return redirect("/login")

    access_token = session.get("access_token")

    try:

        guilds = get_discord_guilds(access_token)

    except Exception:

        session.clear()

        return redirect("/login")

    selected = None

    for guild in guilds:

        if guild["id"] == server_id:

            permissions = int(
                guild.get("permissions", 0)
            )

            owner = guild.get("owner", False)

            manageable = owner or bool(
                permissions & 0x20
            )

            if manageable:
                selected = guild

            break

    if not selected:
        return "You do not have permission to manage this server.", 403

    return render_template_string(
        SERVER_HTML,
        server=selected
    )


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================
# HEALTH
# =========================

@app.route("/health")
def health():

    return "OK"


# =========================
# FLASK
# =========================

def run_website():

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================
# BOT EVENTS
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

    await ctx.send(
        f"🏓 Pong! `{round(bot.latency * 1000)}ms`"
    )


# =========================
# START
# =========================

if __name__ == "__main__":

    from threading import Thread

    website_thread = Thread(
        target=run_website,
        daemon=True
    )

    website_thread.start()

    bot.run(TOKEN)
