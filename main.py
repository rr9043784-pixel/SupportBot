
import os
import json
import secrets
import asyncio
import threading
import urllib.parse
import urllib.request
import urllib.error
import html

import discord
from discord.ext import commands
from flask import (
    Flask, request, redirect, session,
    render_template_string
)

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.environ["DISCORD_TOKEN"].strip()
CLIENT_ID = os.environ["DISCORD_CLIENT_ID"].strip()
CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"].strip()

REDIRECT_URI = os.environ.get(
    "DISCORD_REDIRECT_URI",
    "https://supportbot-production-c479.up.railway.app/callback"
).strip()

PORT = int(os.environ.get("PORT", "10000"))
SETTINGS_FILE = "bot_settings.json"
SUPPORT_SERVER = "https://discord.gg/4uKAWftJv"

# =========================================================
# SETTINGS
# =========================================================

DEFAULT_SETTINGS = {
    "name": "SupportBot",
    "description": "Your universal Discord support bot.",
    "activity_type": "watching",
    "activity_text": "over your server",
    "status": "online"
}


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        result = DEFAULT_SETTINGS.copy()
        result.update(data)
        return result

    except (OSError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()


settings = load_settings()


def save_settings():
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)


# =========================================================
# DISCORD BOT
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = None
bot_loop = None
bot_task = None
bot_running = False
bot_lock = threading.Lock()


def get_activity():
    text = settings.get("activity_text", "").strip()
    kind = settings.get("activity_type", "watching").lower()

    if not text:
        return None
    if kind == "playing":
        return discord.Game(name=text)
    if kind == "listening":
        return discord.Activity(
            type=discord.ActivityType.listening, name=text
        )
    if kind == "streaming":
        return discord.Streaming(
            name=text, url="https://www.twitch.tv/discord"
        )

    return discord.Activity(
        type=discord.ActivityType.watching, name=text
    )


def get_status():
    statuses = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible
    }
    return statuses.get(
        settings.get("status", "online"),
        discord.Status.online
    )


async def apply_bot_settings(instance=None):
    instance = instance or bot

    if instance is None or not instance.is_ready():
        return

    await instance.change_presence(
        status=get_status(),
        activity=get_activity()
    )

    desired_name = settings.get("name", "SupportBot").strip()
    if desired_name and instance.user and instance.user.name != desired_name:
        try:
            await instance.user.edit(username=desired_name[:32])
        except discord.HTTPException as exc:
            print("Bot name update failed:", repr(exc))


def create_bot():
    instance = commands.Bot(
        command_prefix="!",
        intents=intents
    )

    @instance.event
    async def on_ready():
        global bot_running
        bot_running = True
        print(f"Logged in as {instance.user} ({instance.user.id})")

        try:
            await apply_bot_settings(instance)
        except Exception as exc:
            print("Presence update failed:", repr(exc))

        print("SupportBot is ready!")

    @instance.command()
    async def ping(ctx):
        await ctx.send(f"Pong! `{round(instance.latency * 1000)}ms`")

    return instance


async def bot_runner(instance):
    global bot_running

    try:
        await instance.start(TOKEN)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print("Discord bot stopped with error:", repr(exc))
    finally:
        if instance is bot:
            bot_running = False
        print("Discord bot connection ended.")


def start_bot_process():
    global bot, bot_task, bot_running

    with bot_lock:
        if bot_task is not None and not bot_task.done():
            return False

        bot = create_bot()
        bot_running = False

        if bot_loop is None or not bot_loop.is_running():
            raise RuntimeError("Discord event loop is not available.")

        bot_task = asyncio.run_coroutine_threadsafe(
            bot_runner(bot), bot_loop
        )

        return True


async def close_current_bot():
    global bot_running

    instance = bot
    if instance is not None and not instance.is_closed():
        await instance.close()

    bot_running = False


def start_event_loop():
    global bot_loop

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot_loop = loop
    loop.run_forever()


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)
app.secret_key = CLIENT_SECRET


STYLE = """
<style>
* { box-sizing: border-box; }
body {
    margin: 0; background: #0b0d12; color: white;
    font-family: Arial, sans-serif;
}
.nav {
    min-height: 70px; display: flex; align-items: center;
    justify-content: space-between; padding: 16px 30px;
    background: #11141b; border-bottom: 1px solid #242832;
}
.logo { font-size: 22px; font-weight: 700; }
.nav a { color: white; text-decoration: none; margin-left: 15px; }
.container { max-width: 1000px; margin: 40px auto; padding: 0 20px; }
.card {
    background: #131720; border: 1px solid #242936;
    border-radius: 16px; padding: 24px; margin-bottom: 20px;
}
p { color: #aeb5c2; line-height: 1.5; }
.button, button {
    display: inline-block; padding: 12px 18px; border: 0;
    border-radius: 9px; background: #5865f2; color: white;
    text-decoration: none; cursor: pointer; font-size: 15px;
}
.red { background: #ed4245; }
.green { background: #248046; }
.gray { background: #363a43; }
input, textarea, select {
    display: block; width: 100%; padding: 12px; margin: 8px 0 18px;
    border-radius: 9px; border: 1px solid #303541;
    background: #0d1016; color: white; font-size: 15px;
}
textarea { min-height: 100px; resize: vertical; }
label { color: #d9dce3; font-weight: 600; }
.server, .preview {
    background: #0e1117; border-radius: 12px;
    padding: 17px; margin: 10px 0;
}
.notice { padding: 13px; background: #1d2330; border-radius: 10px; }
</style>
"""


def page(title, body, **context):
    return render_template_string(
        """
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>{{ title }}</title>
        """ + STYLE + """
        </head>
        <body>
            <div class="nav">
                <div class="logo">SupportBot</div>
                <div>
                    <a href="/">Home</a>
                    <a href="/dashboard">Dashboard</a>
                    <a href="/invite">Invite</a>
                </div>
            </div>
            <div class="container">
                """ + body + """
            </div>
        </body>
        </html>
        """,
        title=title,
        **context
    )


# =========================================================
# HOME AND INVITE
# =========================================================

@app.route("/")
def home():
    logged_in = "user" in session

    return page(
        "SupportBot",
        """
        <div class="card">
            <h1>SupportBot</h1>
            <p>Your universal Discord support bot.</p>
            <a class="button" href="/login">
                Login with Discord
            </a>
            <a class="button gray" href="/invite">
                Invite SupportBot
            </a>
            <a class="button gray" href="{{ support }}">
                Support Server
            </a>
        </div>
        <div class="card">
            <h2>Bot Status</h2>
            <p>{{ "🟢 SupportBot is running" if running else "⚫ SupportBot is stopped" }}</p>
        </div>
        """,
        support=SUPPORT_SERVER,
        running=bot_running,
        logged_in=logged_in
    )


@app.route("/invite")
def invite():
    params = {
        "client_id": CLIENT_ID,
        "permissions": "125968",
        "scope": "bot applications.commands"
    }
    return redirect(
        "https://discord.com/oauth2/authorize?"
        + urllib.parse.urlencode(params)
    )


# =========================================================
# OAUTH LOGIN
# =========================================================

@app.route("/login")
def login():
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "identify guilds",
        "state": state
    }

    return redirect(
        "https://discord.com/oauth2/authorize?"
        + urllib.parse.urlencode(params)
    )


@app.route("/callback")
def callback():
    oauth_error = request.args.get("error")
    if oauth_error:
        return f"Discord authorization error: {html.escape(oauth_error)}", 400

    code = request.args.get("code")
    state = request.args.get("state")
    saved_state = session.pop("oauth_state", None)

    if not code:
        return "Authorization code is missing.", 400

    if not saved_state or state != saved_state:
        return "Invalid OAuth state. Please start login again.", 400

    token_data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }).encode("utf-8")

    token_request = urllib.request.Request(
        "https://discord.com/api/oauth2/token",
        data=token_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "SupportBot-Dashboard/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(token_request, timeout=15) as response:
            token = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        print(f"OAuth token HTTP {exc.code}: {details}")
        return (
            f"<h2>OAuth token error: HTTP {exc.code}</h2>"
            f"<pre>{html.escape(details)}</pre>"
        ), exc.code

    except Exception as exc:
        print("OAuth token request failed:", repr(exc))
        return "OAuth token request failed. Check Railway logs.", 500

    access_token = token.get("access_token")
    if not access_token:
        print("OAuth response had no access token:", token)
        return "Discord did not return an access token.", 500

    try:
        user = discord_api("/users/@me", access_token)
    except Exception as exc:
        print("OAuth user request failed:", repr(exc))
        return "Could not load your Discord account. Please log in again.", 500

    session["user"] = user
    session["access_token"] = access_token
    return redirect("/dashboard")


def discord_api(endpoint, access_token):
    req = urllib.request.Request(
        "https://discord.com/api" + endpoint,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "SupportBot-Dashboard/1.0"
        }
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():
    if "user" not in session or "access_token" not in session:
        return redirect("/login")

    try:
        guilds = discord_api("/users/@me/guilds", session["access_token"])
    except Exception as exc:
        print("Guild request failed:", repr(exc))
        session.pop("user", None)
        session.pop("access_token", None)
        return redirect("/login")

    manageable = []
    for guild in guilds:
        try:
            permissions = int(guild.get("permissions", "0"))
        except (TypeError, ValueError):
            permissions = 0

        if permissions & 0x8 or permissions & 0x20:
            manageable.append(guild)

    return page(
        "Dashboard",
        """
        <div class="card">
            <h1>Dashboard</h1>
            <p>Welcome, {{ username }}!</p>
            <a class="button" href="/bot-settings">Bot Settings</a>
            <a class="button gray" href="/logout">Logout</a>
        </div>
        <div class="card">
            <h2>Your Servers</h2>
            {% for guild in guilds %}
                <div class="server">
                    <strong>{{ guild["name"] }}</strong>
                    <p>Server ID: {{ guild["id"] }}</p>
                    <a class="button" href="/server/{{ guild['id'] }}">Manage</a>
                </div>
            {% else %}
                <p>No servers with Manage Server permission were found.</p>
                <a class="button" href="/invite">Invite SupportBot</a>
            {% endfor %}
        </div>
        """,
        username=session["user"].get("username", "User"),
        guilds=manageable
    )


@app.route("/server/<server_id>")
def server_page(server_id):
    if "user" not in session or "access_token" not in session:
        return redirect("/login")

    try:
        guilds = discord_api("/users/@me/guilds", session["access_token"])
        permitted_ids = set()

        for guild in guilds:
            permissions = int(guild.get("permissions", "0"))
            if permissions & 0x8 or permissions & 0x20:
                permitted_ids.add(guild["id"])

        if server_id not in permitted_ids:
            return "You do not have permission to manage this server.", 403

    except Exception:
        return redirect("/login")

    return page(
        "Server Settings",
        """
        <div class="card">
            <h1>Server Dashboard</h1>
            <p>Server ID: {{ server_id }}</p>
            <a class="button" href="/bot-settings">Bot Settings</a>
            <a class="button gray" href="/dashboard">Back</a>
        </div>
        """,
        server_id=server_id
    )


# =========================================================
# BOT SETTINGS
# =========================================================

@app.route("/bot-settings", methods=["GET", "POST"])
def bot_settings():
    if "user" not in session:
        return redirect("/login")

    message = None

    if request.method == "POST":
        new_name = request.form.get("name", "").strip() or "SupportBot"
        description = request.form.get("description", "").strip()
        activity_type = request.form.get("activity_type", "watching").lower()
        activity_text = request.form.get("activity_text", "").strip()
        status = request.form.get("status", "online").lower()

        if activity_type not in {"playing", "watching", "listening", "streaming"}:
            activity_type = "watching"

        if status not in {"online", "idle", "dnd", "invisible"}:
            status = "online"

        settings.update({
            "name": new_name[:32],
            "description": description[:1000],
            "activity_type": activity_type,
            "activity_text": activity_text[:128],
            "status": status
        })

        save_settings()
        message = "Settings saved."

        if bot_loop and bot_loop.is_running() and bot_running and bot:
            future = asyncio.run_coroutine_threadsafe(
                apply_bot_settings(bot), bot_loop
            )
            try:
                future.result(timeout=12)
                message = "Settings saved and applied."
            except Exception as exc:
                print("Settings apply failed:", repr(exc))
                message = "Settings saved, but the Discord update failed. Check Railway logs."

    return page(
        "Bot Settings",
        """
        <div class="card">
            <h1>Bot Settings</h1>
            {% if message %}<div class="notice">{{ message }}</div>{% endif %}

            <form method="post">
                <label>Bot Name</label>
                <input name="name" maxlength="32" value="{{ settings['name'] }}" required>

                <label>Description</label>
                <textarea name="description" maxlength="1000">{{ settings['description'] }}</textarea>

                <label>Activity Type</label>
                <select name="activity_type">
                    {% for value, label in [
                        ('playing', 'Playing'),
                        ('watching', 'Watching'),
                        ('listening', 'Listening'),
                        ('streaming', 'Streaming')
                    ] %}
                    <option value="{{ value }}" {% if settings['activity_type'] == value %}selected{% endif %}>
                        {{ label }}
                    </option>
                    {% endfor %}
                </select>

                <label>Activity Text</label>
                <input name="activity_text" maxlength="128" value="{{ settings['activity_text'] }}">

                <label>Status</label>
                <select name="status">
                    {% for value, label in [
                        ('online', 'Online'),
                        ('idle', 'Idle'),
                        ('dnd', 'Do Not Disturb'),
                        ('invisible', 'Invisible')
                    ] %}
                    <option value="{{ value }}" {% if settings['status'] == value %}selected{% endif %}>
                        {{ label }}
                    </option>
                    {% endfor %}
                </select>

                <button type="submit">Save Changes</button>
            </form>
        </div>

        <div class="card">
            <h2>Preview</h2>
            <div class="preview">
                <strong>🤖 {{ settings['name'] }}</strong>
                <p>{{ settings['activity_type']|capitalize }} {{ settings['activity_text'] }}</p>
                <p>{{ settings['description'] }}</p>
            </div>
        </div>

        <div class="card">
            <h2>Bot Control</h2>
            <p>{{ "🟢 SupportBot is running." if running else "⚫ SupportBot is stopped." }}</p>
            {% if running %}
                <form method="post" action="/bot/stop">
                    <button class="red" type="submit">Stop Bot</button>
                </form>
            {% else %}
                <form method="post" action="/bot/start">
                    <button class="green" type="submit">Start Bot</button>
                </form>
            {% endif %}
            <p><a class="button gray" href="/invite">Invite SupportBot</a></p>
        </div>
        """,
        settings=settings,
        message=message,
        running=bot_running
    )


# =========================================================
# BOT START / STOP
# =========================================================

@app.route("/bot/stop", methods=["POST"])
def stop_bot():
    if "user" not in session:
        return redirect("/login")

    if bot is not None and bot_loop and bot_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(close_current_bot(), bot_loop)
        try:
            future.result(timeout=10)
        except Exception as exc:
            print("Bot stop error:", repr(exc))

    return redirect("/bot-settings")


@app.route("/bot/start", methods=["POST"])
def start_bot():
    if "user" not in session:
        return redirect("/login")

    try:
        start_bot_process()
    except Exception as exc:
        print("Bot start error:", repr(exc))

    return redirect("/bot-settings")


# =========================================================
# LOGOUT / HEALTH
# =========================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/health")
def health():
    return "SupportBot website is online!"


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":
    threading.Thread(
        target=start_event_loop,
        daemon=True
    ).start()

    # Wait briefly for the bot event loop to initialize.
    import time

    for _ in range(50):
        if bot_loop and bot_loop.is_running():
            break
        time.sleep(0.1)

    try:
        start_bot_process()
    except Exception as exc:
        print("Initial bot start error:", repr(exc))

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False
    )
