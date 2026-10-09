import os
import json
import secrets
import asyncio
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import html

import discord
from discord.ext import commands
from flask import Flask, request, redirect, session, render_template_string, url_for

from config import (
    DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET,
    FLASK_SECRET_KEY, PORT, OWNER_ID, SUPPORT_SERVER_URL,
    SETTINGS_FILE, DEFAULT_SETTINGS, SUPPORTED_LANGUAGES,
)
from storage import get_server_settings, save_server_settings, reset_server_settings

TOKEN = DISCORD_TOKEN.strip()
CLIENT_ID = DISCORD_CLIENT_ID.strip()
CLIENT_SECRET = DISCORD_CLIENT_SECRET.strip()
REDIRECT_URI = os.environ.get(
    "DISCORD_REDIRECT_URI",
    os.environ.get("REDIRECT_URI", "https://supportbot-production-c479.up.railway.app/callback"),
).strip()

def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = DEFAULT_SETTINGS.copy()
        if isinstance(data, dict):
            result.update(data)
        return result
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()

settings = load_settings()
settings_lock = threading.RLock()

def save_settings():
    tmp = SETTINGS_FILE + ".tmp"
    with settings_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SETTINGS_FILE)

def get_activity():
    text = str(settings.get("activity_text", "")).strip()
    kind = str(settings.get("activity_type", "watching")).lower()
    if not text or kind in {"none", "off", "disabled"}:
        return None
    if kind == "playing":
        return discord.Game(name=text)
    if kind == "listening":
        return discord.Activity(type=discord.ActivityType.listening, name=text)
    if kind == "streaming":
        return discord.Streaming(name=text, url="https://www.twitch.tv/discord")
    if kind == "competing":
        return discord.Activity(type=discord.ActivityType.competing, name=text)
    return discord.Activity(type=discord.ActivityType.watching, name=text)

def get_status():
    return {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible,
    }.get(str(settings.get("status", "online")).lower(), discord.Status.online)

async def apply_bot_settings(instance=None):
    instance = instance or bot
    if instance is None or not instance.is_ready():
        return
    await instance.change_presence(status=get_status(), activity=get_activity())
    name = str(settings.get("name", "SupportBot")).strip()[:32]
    if name and instance.user and instance.user.name != name:
        try:
            await instance.user.edit(username=name)
        except discord.HTTPException as exc:
            print("Bot username update failed:", repr(exc))

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = None
bot_loop = None
bot_task = None
bot_running = False
bot_lock = threading.RLock()

def create_bot():
    instance = commands.Bot(command_prefix="!", intents=intents)

    @instance.event
    async def on_ready():
        global bot_running
        bot_running = True
        print(f"Logged in as {instance.user} ({instance.user.id})")
        try:
            await apply_bot_settings(instance)
            await instance.tree.sync()
        except Exception as exc:
            print("Bot setup/sync warning:", repr(exc))

    @instance.command()
    async def ping(ctx):
        await ctx.send(f"Pong! `{round(instance.latency * 1000)}ms`")

    @instance.tree.command(name="language", description="Set this server's SupportBot language")
    @discord.app_commands.choices(language=[
        discord.app_commands.Choice(name="English", value="en"),
        discord.app_commands.Choice(name="Russian", value="ru"),
        discord.app_commands.Choice(name="Turkish", value="tr"),
        discord.app_commands.Choice(name="Spanish", value="es"),
        discord.app_commands.Choice(name="German", value="de"),
        discord.app_commands.Choice(name="French", value="fr"),
    ])
    async def language(interaction: discord.Interaction, language: discord.app_commands.Choice[str]):
        if interaction.guild is None:
            await interaction.response.send_message("Use this command in a server.", ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member) or not (
            member.guild_permissions.manage_guild or member.guild_permissions.administrator
        ):
            await interaction.response.send_message("You need Manage Server permission.", ephemeral=True)
            return
        data = get_server_settings(interaction.guild.id)
        data["language"] = language.value
        save_server_settings(interaction.guild.id, data)
        await interaction.response.send_message(f"Server language set to **{language.name}**.", ephemeral=True)

    return instance

async def bot_runner(instance):
    global bot_running
    for extension in ("cogs.tickets", "cogs.automod", "cogs.welcome", "cogs.logs", "cogs.messages"):
        try:
            await instance.load_extension(extension)
            print("Loaded extension:", extension)
        except Exception:
            print("Failed to load extension:", extension)
            raise
    try:
        await instance.start(TOKEN)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print("Discord bot stopped with error:", repr(exc))
    finally:
        bot_running = False
        if not instance.is_closed():
            await instance.close()
        print("Discord bot connection ended.")

def start_bot_process():
    global bot, bot_task, bot_running
    with bot_lock:
        if bot_task is not None and not bot_task.done():
            return False
        if bot_loop is None or not bot_loop.is_running():
            raise RuntimeError("Discord event loop is not available.")
        bot = create_bot()
        bot_running = False
        bot_task = asyncio.run_coroutine_threadsafe(bot_runner(bot), bot_loop)
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

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=28800,
)

STYLE = """
<style>
*{box-sizing:border-box}body{margin:0;background:#0b0d12;color:#f4f6fb;font-family:Arial,sans-serif}
.nav{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:18px 24px;background:#11141b;border-bottom:1px solid #242832;flex-wrap:wrap}
.nav a{color:#dfe4ff;text-decoration:none;margin-left:12px}.logo{font-size:22px;font-weight:bold}
.container{max-width:1050px;margin:30px auto;padding:0 16px}.card{background:#131720;border:1px solid #242936;border-radius:16px;padding:22px;margin-bottom:18px}
p{color:#aeb5c2;line-height:1.5}.button,button{display:inline-block;padding:11px 16px;border:0;border-radius:9px;background:#5865f2;color:white;text-decoration:none;cursor:pointer;margin:3px}
.red{background:#ed4245}.green{background:#248046}.gray{background:#363a43}
input,textarea,select{display:block;width:100%;padding:12px;margin:8px 0 17px;border-radius:9px;border:1px solid #303541;background:#0d1016;color:white}
label{color:#d9dce3;font-weight:600}.server{background:#0e1117;border-radius:12px;padding:16px;margin:10px 0}.notice{padding:13px;background:#1d2330;border-radius:10px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.muted{color:#8992a4;font-size:13px}
</style>
"""

def page(title, body, **ctx):
    template = """<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }}</title>""" + STYLE + """
    </head><body><div class="nav"><div class="logo">SupportBot</div>
    <div><a href="/">Home</a><a href="/dashboard">Dashboard</a><a href="/invite">Invite</a>
    {% if logged_in %}<a href="/logout">Logout</a>{% endif %}</div></div>
    <div class="container">""" + body + """</div></body></html>"""
    ctx.setdefault("logged_in", "user" in session)
    return render_template_string(template, title=title, **ctx)

def discord_api(endpoint, access_token):
    req = urllib.request.Request("https://discord.com/api" + endpoint, headers={
        "Authorization": f"Bearer {access_token}", "Accept": "application/json",
        "User-Agent": "SupportBot-Dashboard/1.0",
    })
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))

def logged_in():
    return "user" in session and "access_token" in session

def is_owner():
    try:
        return int(session.get("user", {}).get("id", 0)) == OWNER_ID
    except (TypeError, ValueError):
        return False

def get_manageable_guilds():
    guilds = discord_api("/users/@me/guilds", session["access_token"])
    return [g for g in guilds if int(g.get("permissions", "0")) & (0x8 | 0x20)]

def csrf_token():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(24)
    return session["csrf_token"]

def valid_owner_post():
    token = request.form.get("csrf_token", "")
    saved = session.get("csrf_token", "")
    return logged_in() and is_owner() and bool(saved) and secrets.compare_digest(token, saved)

@app.route("/")
def home():
    return page("SupportBot", """
    <div class="card"><h1>SupportBot</h1><p>Discord support, tickets and moderation dashboard.</p>
    <a class="button" href="/login">Login with Discord</a><a class="button gray" href="/invite">Invite SupportBot</a>
    <a class="button gray" href="{{ support }}">Support Server</a></div>
    <div class="card"><h2>Bot Status</h2><p>{{ '🟢 Running' if running else '⚫ Stopped' }}</p></div>
    """, support=SUPPORT_SERVER_URL, running=bot_running)

@app.route("/invite")
def invite():
    params = {"client_id": CLIENT_ID, "permissions": "125968", "scope": "bot applications.commands"}
    return redirect("https://discord.com/oauth2/authorize?" + urllib.parse.urlencode(params))

@app.route("/login")
def login():
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    params = {"client_id": CLIENT_ID, "response_type": "code", "redirect_uri": REDIRECT_URI,
              "scope": "identify guilds", "state": state}
    return redirect("https://discord.com/oauth2/authorize?" + urllib.parse.urlencode(params))

@app.route("/callback")
def callback():
    error = request.args.get("error")
    if error:
        return f"Discord authorization error: {html.escape(error)}", 400
    code, state = request.args.get("code"), request.args.get("state")
    saved_state = session.pop("oauth_state", None)
    if not code:
        return "Authorization code is missing.", 400
    if not saved_state or state != saved_state:
        return "Invalid OAuth state. Please start login again.", 400
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "authorization_code",
        "code": code, "redirect_uri": REDIRECT_URI,
    }).encode()
    req = urllib.request.Request(
        "https://discord.com/api/v10/oauth2/token",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "DiscordBot (https://supportbot-production-c479.up.railway.app, 1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            token = json.loads(response.read().decode())
        access = token.get("access_token")
        if not access:
            return "Discord did not return an access token.", 500
        user = discord_api("/users/@me", access)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print("OAuth HTTP error:", exc.code, detail)
        return f"OAuth error HTTP {exc.code}: {html.escape(detail)}", exc.code
    except Exception as exc:
        print("OAuth error:", repr(exc))
        return "Discord login failed. Check Railway logs and the callback URL.", 500
    session.clear()
    session["user"], session["access_token"] = user, access
    session.permanent = True
    csrf_token()
    return redirect("/dashboard")

@app.route("/dashboard")
def dashboard():
    if not logged_in():
        return redirect("/login")
    try:
        guilds = get_manageable_guilds()
    except Exception as exc:
        print("Guild list error:", repr(exc))
        session.clear()
        return redirect("/login")
    installed = {str(g.id) for g in bot.guilds} if bot else set()
    for guild in guilds:
        guild["installed"] = str(guild["id"]) in installed
    username = session["user"].get("global_name") or session["user"].get("username", "User")
    return page("Dashboard", """
    <div class="card"><h1>Dashboard</h1><p>Welcome, {{ username }}!</p>
    {% if owner %}<a class="button" href="/bot-settings">Global Bot Settings</a>{% endif %}</div>
    <div class="card"><h2>Your Servers</h2><div class="grid">
    {% for g in guilds %}<div class="server"><strong>{{ g['name'] }}</strong><p class="muted">ID: {{ g['id'] }}</p>
    <p>{{ '🟢 Bot installed' if g['installed'] else '⚪ Bot not installed' }}</p>
    <a class="button" href="/server/{{ g['id'] }}">Manage</a>
    {% if not g['installed'] %}<a class="button gray" href="/add-bot/{{ g['id'] }}">Add Bot</a>{% endif %}
    </div>{% else %}<p>No manageable servers found.</p>{% endfor %}
    </div></div>
    """, username=username, guilds=guilds, owner=is_owner())

@app.route("/add-bot/<server_id>")
def add_bot(server_id):
    if not logged_in():
        return redirect("/login")
    try:
        if not any(str(g["id"]) == str(server_id) for g in get_manageable_guilds()):
            return "You do not have permission to manage this server.", 403
    except Exception:
        return redirect("/login")
    params = {"client_id": CLIENT_ID, "permissions": "125968", "scope": "bot applications.commands",
              "guild_id": str(server_id), "disable_guild_select": "true"}
    return redirect("https://discord.com/oauth2/authorize?" + urllib.parse.urlencode(params))

@app.route("/server/<server_id>", methods=["GET", "POST"])
def server_page(server_id):
    if not logged_in():
        return redirect("/login")
    try:
        guilds = get_manageable_guilds()
        guild = next((g for g in guilds if str(g["id"]) == str(server_id)), None)
    except Exception:
        session.clear()
        return redirect("/login")
    if guild is None:
        return "You do not have permission to manage this server.", 403
    data = get_server_settings(int(server_id))
    message = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "language":
            value = request.form.get("language", "en")
            if value not in SUPPORTED_LANGUAGES:
                message = "Unsupported language."
            else:
                data["language"] = value
                save_server_settings(int(server_id), data)
                message = "Language saved."
        elif action == "reset":
            reset_server_settings(int(server_id))
            data = get_server_settings(int(server_id))
            message = "Server settings reset."
    installed = bool(bot and bot.get_guild(int(server_id)))
    return page("Server Settings", """
    <div class="card"><h1>{{ name }}</h1><p>Server ID: {{ server_id }}</p>
    <p>{{ '🟢 Bot installed' if installed else '⚪ Bot not installed' }}</p>
    {% if message %}<div class="notice">{{ message }}</div>{% endif %}
    <form method="post"><input type="hidden" name="action" value="language"><label>Server language</label>
    <select name="language">{% for code, label in languages.items() %}
    <option value="{{ code }}" {% if data.get('language','en') == code %}selected{% endif %}>{{ label }}</option>
    {% endfor %}</select><button>Save Language</button></form>
    <form method="post" onsubmit="return confirm('Reset server settings?')"><input type="hidden" name="action" value="reset">
    <button class="red">Reset Server Settings</button></form><a class="button gray" href="/dashboard">Back</a></div>
    <div class="card"><h2>Bot commands</h2><p><code>!ticketpanel</code>, <code>!ticketcategory ID</code>, <code>!ticketsupportrole @Role</code></p>
    <p><code>!automod on</code>, <code>!automodlinks on</code>, <code>!automodinvites on</code>, <code>!automodspam on</code></p>
    <p><code>!welcome on</code>, <code>!welcomechannel #channel</code>, <code>!logs on</code>, <code>!logschannel #channel</code>, <code>!variable list</code></p>
    <p>Slash command: <code>/language</code></p></div>
    """, name=guild.get("name", "Discord Server"), server_id=server_id, installed=installed,
       data=data, message=message, languages=SUPPORTED_LANGUAGES)

@app.route("/bot-settings", methods=["GET", "POST"])
def bot_settings():
    if not logged_in():
        return redirect("/login")
    if not is_owner():
        return "Only the bot owner can access global bot settings.", 403
    message = None
    if request.method == "POST":
        name = request.form.get("name", "").strip() or "SupportBot"
        description = request.form.get("description", "").strip()
        kind = request.form.get("activity_type", "watching").lower()
        activity_text = request.form.get("activity_text", "").strip()
        status = request.form.get("status", "online").lower()
        if kind not in {"playing", "watching", "listening", "streaming", "competing", "none"}:
            kind = "watching"
        if status not in {"online", "idle", "dnd", "invisible"}:
            status = "online"
        with settings_lock:
            settings.update({"name": name[:32], "description": description[:1000],
                             "activity_type": kind, "activity_text": activity_text[:128], "status": status})
            save_settings()
        message = "Settings saved."
        if bot_loop and bot_loop.is_running() and bot_running and bot:
            try:
                asyncio.run_coroutine_threadsafe(apply_bot_settings(bot), bot_loop).result(timeout=12)
                message = "Settings saved and applied."
            except Exception as exc:
                print("Apply settings error:", repr(exc))
                message = "Saved, but Discord update failed. Check Railway logs."
    return page("Bot Settings", """
    <div class="card"><h1>Global Bot Settings</h1>{% if message %}<div class="notice">{{ message }}</div>{% endif %}
    <form method="post"><label>Bot Name</label><input name="name" maxlength="32" value="{{ s['name'] }}" required>
    <label>Description</label><textarea name="description" maxlength="1000">{{ s['description'] }}</textarea>
    <label>Activity Type</label><select name="activity_type">{% for v,l in [('playing','Playing'),('watching','Watching'),('listening','Listening'),('streaming','Streaming'),('competing','Competing'),('none','None / Clear Activity')] %}
    <option value="{{ v }}" {% if s['activity_type']==v %}selected{% endif %}>{{ l }}</option>{% endfor %}</select>
    <label>Activity Text</label><input name="activity_text" maxlength="128" value="{{ s['activity_text'] }}">
    <label>Status</label><select name="status">{% for v,l in [('online','Online'),('idle','Idle'),('dnd','Do Not Disturb'),('invisible','Invisible')] %}
    <option value="{{ v }}" {% if s['status']==v %}selected{% endif %}>{{ l }}</option>{% endfor %}</select>
    <button>Save Changes</button></form></div>
    <div class="card"><h2>Bot Control</h2><p>{{ '🟢 Running' if running else '⚫ Stopped' }}</p>
    {% if running %}<form method="post" action="/bot/stop"><input type="hidden" name="csrf_token" value="{{ csrf }}"><button class="red">Stop Bot</button></form>
    {% else %}<form method="post" action="/bot/start"><input type="hidden" name="csrf_token" value="{{ csrf }}"><button class="green">Start Bot</button></form>{% endif %}
    <a class="button gray" href="/dashboard">Back</a></div>
    """, s=settings.copy(), message=message, running=bot_running, csrf=csrf_token())

@app.route("/bot/stop", methods=["POST"])
def stop_bot():
    if not logged_in():
        return redirect("/login")
    if not is_owner() or not secrets.compare_digest(request.form.get("csrf_token", ""), session.get("csrf_token", "")):
        return "Forbidden.", 403
    if bot and bot_loop and bot_loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(close_current_bot(), bot_loop).result(timeout=15)
        except Exception as exc:
            print("Stop bot error:", repr(exc))
    return redirect("/bot-settings")

@app.route("/bot/start", methods=["POST"])
def start_bot():
    if not logged_in():
        return redirect("/login")
    if not is_owner() or not secrets.compare_digest(request.form.get("csrf_token", ""), session.get("csrf_token", "")):
        return "Forbidden.", 403
    try:
        start_bot_process()
    except Exception as exc:
        print("Start bot error:", repr(exc))
    return redirect("/bot-settings")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/health")
def health():
    return "SupportBot website is online!", 200

if __name__ == "__main__":
    threading.Thread(target=start_event_loop, daemon=True).start()
    for _ in range(100):
        if bot_loop and bot_loop.is_running():
            break
        time.sleep(0.1)
    try:
        start_bot_process()
    except Exception as exc:
        print("Initial bot start error:", repr(exc))
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
