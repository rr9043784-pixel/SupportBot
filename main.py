import os
import json
import secrets
import asyncio
import threading
import urllib.parse
import urllib.request
import urllib.error

import discord
from discord.ext import commands
from flask import Flask, request, redirect, session, render_template_string


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.environ["DISCORD_TOKEN"]
CLIENT_ID = os.environ["DISCORD_CLIENT_ID"]
CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"]

REDIRECT_URI = os.environ.get(
    "DISCORD_REDIRECT_URI",
    "https://supportbot-production-c479.up.railway.app/callback"
)

PORT = int(os.environ.get("PORT", 10000))

SETTINGS_FILE = "bot_settings.json"


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
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        settings = DEFAULT_SETTINGS.copy()
        settings.update(data)
        return settings

    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)


settings = load_settings()


# =========================================================
# DISCORD BOT
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

bot_loop = None
bot_running = False
bot_start_task = None


# =========================================================
# DISCORD PRESENCE
# =========================================================

def get_activity(activity_type, text):
    if not text:
        return None

    if activity_type == "playing":
        return discord.Game(name=text)

    if activity_type == "watching":
        return discord.Activity(
            type=discord.ActivityType.watching,
            name=text
        )

    if activity_type == "listening":
        return discord.Activity(
            type=discord.ActivityType.listening,
            name=text
        )

    if activity_type == "streaming":
        return discord.Streaming(
            name=text,
            url="https://www.twitch.tv/"
        )

    return None


def get_status(status):
    statuses = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible
    }

    return statuses.get(status, discord.Status.online)


async def update_presence():
    activity = get_activity(
        settings.get("activity_type", "watching"),
        settings.get("activity_text", "over your server")
    )

    status = get_status(
        settings.get("status", "online")
    )

    await bot.change_presence(
        status=status,
        activity=activity
    )


# =========================================================
# BOT EVENTS
# =========================================================

@bot.event
async def on_ready():
    global bot_loop, bot_running

    bot_loop = asyncio.get_running_loop()
    bot_running = True

    print(f"Logged in as {bot.user} ({bot.user.id})")

    try:
        await bot.user.edit(
            username=settings.get("name", "SupportBot")
        )
    except Exception as e:
        print("Could not change bot name:", e)

    try:
        await update_presence()
    except Exception as e:
        print("Could not update presence:", e)

    print("SupportBot is ready!")


@bot.event
async def on_disconnect():
    global bot_running
    bot_running = False
    print("SupportBot disconnected.")


@bot.event
async def on_resumed():
    global bot_running
    bot_running = True
    print("SupportBot resumed connection.")


# =========================================================
# COMMANDS
# =========================================================

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! `{round(bot.latency * 1000)}ms`")


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)
app.secret_key = CLIENT_SECRET


# =========================================================
# HTML
# =========================================================

BASE_STYLE = """
<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #0b0d12;
    color: #ffffff;
    font-family: Arial, sans-serif;
}

.nav {
    height: 70px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 35px;
    background: #11141b;
    border-bottom: 1px solid #242832;
}

.logo {
    font-size: 22px;
    font-weight: 700;
}

.nav a {
    color: #ffffff;
    text-decoration: none;
    margin-left: 20px;
}

.container {
    max-width: 1100px;
    margin: 50px auto;
    padding: 0 25px;
}

.card {
    background: #131720;
    border: 1px solid #242936;
    border-radius: 16px;
    padding: 25px;
    margin-bottom: 20px;
}

h1 {
    font-size: 34px;
}

h2 {
    margin-top: 0;
}

p {
    color: #aeb5c2;
}

.button {
    display: inline-block;
    padding: 13px 20px;
    border-radius: 10px;
    background: #5865f2;
    color: white;
    text-decoration: none;
    border: none;
    cursor: pointer;
    font-size: 15px;
}

.button.red {
    background: #ed4245;
}

.button.green {
    background: #3ba55d;
}

.button.gray {
    background: #363a43;
}

input, textarea, select {
    width: 100%;
    padding: 13px;
    margin-top: 8px;
    margin-bottom: 18px;
    border-radius: 9px;
    border: 1px solid #303541;
    background: #0d1016;
    color: white;
    font-size: 15px;
}

textarea {
    min-height: 110px;
    resize: vertical;
}

label {
    color: #d9dce3;
    font-weight: 600;
}

.server {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px;
    margin-bottom: 12px;
    background: #0e1117;
    border-radius: 12px;
}

.status {
    display: inline-block;
    padding: 7px 11px;
    border-radius: 20px;
    background: #20242d;
    color: #dce0e8;
    font-size: 13px;
}

.preview {
    padding: 20px;
    background: #0d1016;
    border-radius: 12px;
    border: 1px solid #292e39;
}

.preview-name {
    font-size: 19px;
    font-weight: 700;
}

.preview-activity {
    color: #aeb5c2;
    margin-top: 5px;
}

.notice {
    padding: 13px;
    background: #1d2330;
    border-radius: 10px;
    margin-bottom: 20px;
}
</style>
"""


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    logged_in = "user" in session

    if logged_in:
        button = """
        <a class="button" href="/dashboard">Open Dashboard</a>
        """
    else:
        button = """
        <a class="button" href="/login">Login with Discord</a>
        """

    return render_template_string(
        BASE_STYLE + """
        <div class="nav">
            <div class="logo">SupportBot</div>
            <div>
                <a href="/invite">Invite</a>
                {% if logged_in %}
                <a href="/dashboard">Dashboard</a>
                {% endif %}
            </div>
        </div>

        <div class="container">
            <div class="card">
                <h1>SupportBot</h1>
                <p>Your universal Discord support bot.</p>

                <br>

                {{ button|safe }}

                <a class="button gray" href="/invite">
                    Invite SupportBot
                </a>
            </div>

            <div class="card">
                <h2>Bot Status</h2>
                <p>
                    {% if running %}
                        🟢 SupportBot is running
                    {% else %}
                        ⚫ SupportBot is stopped
                    {% endif %}
                </p>
            </div>
        </div>
        """,
        logged_in=logged_in,
        button=button,
        running=bot_running
    )


# =========================================================
# INVITE
# =========================================================

@app.route("/invite")
def invite():

    invite_url = (
        "https://discord.com/oauth2/authorize?"
        + urllib.parse.urlencode({
            "client_id": CLIENT_ID,
            "scope": "bot applications.commands",
            "permissions": "8"
        })
    )

    return redirect(invite_url)


# =========================================================
# LOGIN
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

    url = (
        "https://discord.com/oauth2/authorize?"
        + urllib.parse.urlencode(params)
    )

    return redirect(url)


# =========================================================
# CALLBACK
# =========================================================

@app.route("/callback")
def callback():

    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        return "Authorization cancelled.", 400

    if state != session.get("oauth_state"):
        return "Invalid OAuth state.", 400

    token_data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }).encode()

    token_request = urllib.request.Request(
        "https://discord.com/api/oauth2/token",
        data=token_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    try:
        with urllib.request.urlopen(token_request) as response:
            token = json.loads(response.read().decode())

    except Exception as e:
        return f"OAuth token error: {e}", 500

    access_token = token.get("access_token")

    if not access_token:
        return "Could not get Discord access token.", 500

    user_request = urllib.request.Request(
        "https://discord.com/api/users/@me",
        headers={
            "Authorization": f"Bearer {access_token}"
        }
    )

    try:
        with urllib.request.urlopen(user_request) as response:
            user = json.loads(response.read().decode())

    except Exception as e:
        return f"Discord user error: {e}", 500

    session["user"] = user
    session["access_token"] = access_token

    return redirect("/dashboard")


# =========================================================
# DISCORD API HELPER
# =========================================================

def discord_api(endpoint, access_token):

    req = urllib.request.Request(
        "https://discord.com/api" + endpoint,
        headers={
            "Authorization": f"Bearer {access_token}"
        }
    )

    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    access_token = session.get("access_token")

    try:
        guilds = discord_api(
            "/users/@me/guilds",
            access_token
        )
    except Exception:
        return "Could not load your Discord servers.", 500

    manageable = []

    for guild in guilds:

        permissions = int(guild.get("permissions", 0))

        # Administrator
        is_admin = bool(permissions & 0x8)

        # Manage Guild
        manage_guild = bool(permissions & 0x20)

        if is_admin or manage_guild:
            manageable.append(guild)

    return render_template_string(
        BASE_STYLE + """
        <div class="nav">
            <div class="logo">SupportBot</div>
            <div>
                <a href="/bot-settings">Bot Settings</a>
                <a href="/logout">Logout</a>
            </div>
        </div>

        <div class="container">
            <h1>Dashboard</h1>

            <div class="card">
                <h2>Hello, {{ user["username"] }}</h2>
                <p>Select a server to manage SupportBot.</p>
            </div>

            {% for guild in guilds %}
            <div class="server">
                <div>
                    <strong>{{ guild["name"] }}</strong>
                </div>

                <a class="button" href="/server/{{ guild["id"] }}">
                    Manage
                </a>
            </div>
            {% endfor %}

            {% if not guilds %}
            <div class="card">
                <p>
                    No servers with Manage Server permission were found.
                </p>

                <a class="button" href="/invite">
                    Invite SupportBot
                </a>
            </div>
            {% endif %}
        </div>
        """,
        user=session["user"],
        guilds=manageable
    )


# =========================================================
# SERVER
# =========================================================

@app.route("/server/<server_id>")
def server(server_id):

    if "user" not in session:
        return redirect("/login")

    return render_template_string(
        BASE_STYLE + """
        <div class="nav">
            <div class="logo">SupportBot</div>
            <div>
                <a href="/dashboard">Dashboard</a>
            </div>
        </div>

        <div class="container">

            <div class="card">
                <h1>Server Dashboard</h1>
                <p>Server ID: {{ server_id }}</p>
            </div>

            <div class="card">
                <h2>Bot Settings</h2>
                <p>
                    Configure the SupportBot profile and status.
                </p>

                <a class="button" href="/bot-settings">
                    Open Bot Settings
                </a>
            </div>

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

    global settings

    message = None

    if request.method == "POST":

        new_name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        activity_type = request.form.get("activity_type", "watching")
        activity_text = request.form.get("activity_text", "").strip()
        status = request.form.get("status", "online")

        if not new_name:
            new_name = "SupportBot"

        allowed_activity = {
            "playing",
            "watching",
            "listening",
            "streaming"
        }

        allowed_status = {
            "online",
            "idle",
            "dnd",
            "invisible"
        }

        if activity_type not in allowed_activity:
            activity_type = "watching"

        if status not in allowed_status:
            status = "online"

        settings = {
            "name": new_name[:32],
            "description": description[:1000],
            "activity_type": activity_type,
            "activity_text": activity_text[:128],
            "status": status
        }

        save_settings(settings)

        # Update Discord bot immediately
        if bot_loop and bot_running:

            future = asyncio.run_coroutine_threadsafe(
                apply_bot_settings(),
                bot_loop
            )

            try:
                future.result(timeout=10)
                message = "Settings saved successfully!"
            except Exception as e:
                message = f"Settings saved, but Discord update failed: {e}"

        else:
            message = "Settings saved. The bot is currently stopped."

    return render_template_string(
        BASE_STYLE + """
        <div class="nav">
            <div class="logo">SupportBot</div>
            <div>
                <a href="/dashboard">Dashboard</a>
                <a href="/logout">Logout</a>
            </div>
        </div>

        <div class="container">

            <h1>Bot Settings</h1>

            {% if message %}
            <div class="notice">
                {{ message }}
            </div>
            {% endif %}

            <div class="card">

                <h2>Bot Profile</h2>

                <form method="POST">

                    <label>Bot Name</label>
                    <input
                        type="text"
                        name="name"
                        maxlength="32"
                        value="{{ settings['name'] }}"
                        placeholder="SupportBot"
                    >

                    <label>Description</label>
                    <textarea
                        name="description"
                        maxlength="1000"
                        placeholder="Your bot description..."
                    >{{ settings['description'] }}</textarea>

                    <label>Activity Type</label>
                    <select name="activity_type">
                        <option value="playing"
                            {% if settings['activity_type'] == 'playing' %}selected{% endif %}>
                            Playing
                        </option>

                        <option value="watching"
                            {% if settings['activity_type'] == 'watching' %}selected{% endif %}>
                            Watching
                        </option>

                        <option value="listening"
                            {% if settings['activity_type'] == 'listening' %}selected{% endif %}>
                            Listening
                        </option>

                        <option value="streaming"
                            {% if settings['activity_type'] == 'streaming' %}selected{% endif %}>
                            Streaming
                        </option>
                    </select>

                    <label>Activity Text</label>
                    <input
                        type="text"
                        name="activity_text"
                        maxlength="128"
                        value="{{ settings['activity_text'] }}"
                        placeholder="over your server"
                    >

                    <label>Status</label>
                    <select name="status">

                        <option value="online"
                            {% if settings['status'] == 'online' %}selected{% endif %}>
                            🟢 Online
                        </option>

                        <option value="idle"
                            {% if settings['status'] == 'idle' %}selected{% endif %}>
                            🌙 Idle
                        </option>

                        <option value="dnd"
                            {% if settings['status'] == 'dnd' %}selected{% endif %}>
                            ⛔ Do Not Disturb
                        </option>

                        <option value="invisible"
                            {% if settings['status'] == 'invisible' %}selected{% endif %}>
                            ⚫ Invisible
                        </option>

                    </select>

                    <button class="button" type="submit">
                        Save Changes
                    </button>

                </form>

            </div>

            <div class="card">

                <h2>Preview</h2>

                <div class="preview">

                    <div class="preview-name">
                        🤖 {{ settings['name'] }}
                    </div>

                    <div class="preview-activity">
                        {{ settings['activity_type']|capitalize }}
                        {{ settings['activity_text'] }}
                    </div>

                    <br>

                    <p>
                        {{ settings['description'] }}
                    </p>

                </div>

            </div>

            <div class="card">

                <h2>Bot Control</h2>

                <p>
                    {% if running %}
                        🟢 SupportBot is currently running.
                    {% else %}
                        ⚫ SupportBot is currently stopped.
                    {% endif %}
                </p>

                {% if running %}

                <form method="POST" action="/bot/stop">
                    <button class="button red" type="submit">
                        🛑 Stop Bot
                    </button>
                </form>

                {% else %}

                <form method="POST" action="/bot/start">
                    <button class="button green" type="submit">
                        ▶️ Start Bot
                    </button>
                </form>

                {% endif %}

            </div>

            <div class="card">

                <h2>Invite</h2>

                <p>
                    Invite SupportBot to another Discord server.
                </p>

                <a class="button" href="/invite">
                    ➕ Invite SupportBot
                </a>

            </div>

        </div>
        """,
        settings=settings,
        running=bot_running,
        message=message
    )


# =========================================================
# APPLY SETTINGS
# =========================================================

async def apply_bot_settings():

    try:
        if bot.user:

            try:
                await bot.user.edit(
                    username=settings.get(
                        "name",
                        "SupportBot"
                    )
                )
            except Exception as e:
                print("Name update error:", e)

        await update_presence()

    except Exception as e:
        print("Settings update error:", e)
        raise


# =========================================================
# STOP BOT
# =========================================================

@app.route("/bot/stop", methods=["POST"])
def stop_bot():

    global bot_running

    if not bot_loop:
        return redirect("/bot-settings")

    async def close_bot():
        global bot_running
        bot_running = False
        await bot.close()

    asyncio.run_coroutine_threadsafe(
        close_bot(),
        bot_loop
    )

    return redirect("/bot-settings")


# =========================================================
# START BOT
# =========================================================

@app.route("/bot/start", methods=["POST"])
def start_bot():

    global bot_start_task
    global bot_running

    if not bot_loop:
        return redirect("/bot-settings")

    if bot_running:
        return redirect("/bot-settings")

    async def start_bot_connection():

        global bot_running

        try:
            bot_running = True

            await bot.start(
                TOKEN,
                reconnect=True
            )

        except Exception as e:
            bot_running = False
            print("Bot start error:", e)

    bot_start_task = asyncio.run_coroutine_threadsafe(
        start_bot_connection(),
        bot_loop
    )

    return redirect("/bot-settings")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()
    return redirect("/")


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "bot_running": bot_running
    }


# =========================================================
# FLASK THREAD
# =========================================================

def run_flask():

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    bot.run(TOKEN)
