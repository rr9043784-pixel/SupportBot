import logging

import discord
from flask import (
    Blueprint,
    abort,
    redirect,
    render_template_string,
    session,
    url_for,
)

from config import (
    DISCORD_CLIENT_ID,
    OWNER_ID,
    SUPPORT_SERVER_URL,
)
from storage import (
    get_server_settings,
    reset_server_settings,
    save_server_settings,
)

logger = logging.getLogger(__name__)

dashboard = Blueprint("dashboard", __name__)

# This reference is set by main.py during application startup.
bot = None

PAGE_STYLE = """
<style>
* { box-sizing: border-box; }
body {
    margin: 0; background: #111318; color: #f2f3f5;
    font: 15px Arial, sans-serif;
}
.layout { display: flex; min-height: 100vh; }
aside {
    width: 230px; padding: 24px 16px; background: #191b22;
    border-right: 1px solid #30323b;
}
aside h2 { font-size: 20px; margin: 0 0 24px; }
aside a {
    display: block; color: #c6c9d2; text-decoration: none;
    padding: 12px; border-radius: 8px; margin: 5px 0;
}
aside a:hover { background: #292c36; color: white; }
main { padding: 30px; width: 100%; max-width: 1100px; }
h1 { margin-top: 0; }
.card {
    background: #191b22; border: 1px solid #30323b;
    border-radius: 12px; padding: 20px; margin: 14px 0;
}
input, select, textarea {
    width: 100%; padding: 11px; margin: 7px 0 15px;
    border-radius: 7px; border: 1px solid #414450;
    background: #111318; color: white;
}
button, .button {
    display: inline-block; padding: 10px 15px;
    border: 0; border-radius: 7px; cursor: pointer;
    background: #5865f2; color: white; text-decoration: none;
}
.secondary { background: #393c47; }
.danger { background: #b83b48; }
.good { color: #70d49a; }
.muted { color: #a5a8b3; }
.grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(240px,1fr)); gap: 14px; }
label { display: block; color: #c6c9d2; }
.notice { padding: 12px; background: #252832; border-radius: 8px; }
@media(max-width:650px) {
    .layout { display: block; }
    aside { width: 100%; }
    main { padding: 18px; }
}
</style>
"""

def set_bot(bot_instance):
    global bot
    bot = bot_instance


def current_user():
    user = session.get("user")
    if not isinstance(user, dict) or not user.get("id"):
        return None
    return user


def can_manage_guild(guild_data):
    try:
        permissions = int(guild_data.get("permissions", "0"))
    except (ValueError, TypeError):
        permissions = 0

    # Administrator or Manage Server permission.
    return bool(permissions & 0x8 or permissions & 0x20)


def is_owner():
    user = current_user()
    return bool(user and str(user.get("id")) == str(OWNER_ID))


def get_user_guild(guild_id):
    user = current_user()
    if not user:
        abort(401)

    guilds = session.get("guilds", [])
    for guild in guilds:
        if str(guild.get("id")) == str(guild_id):
            if can_manage_guild(guild):
                return guild

    abort(403)


def guild_bot_installed(guild_id):
    if bot is None or not getattr(bot, "is_ready", lambda: False)():
        return False

    try:
        return bot.get_guild(int(guild_id)) is not None
    except (ValueError, TypeError):
        return False


def render_page(title, body, **context):
    return render_template_string(
        """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <title>{{ title }} — SupportBot</title>
          {{ style|safe }}
        </head>
        <body>
          <div class="layout">
            <aside>
              <h2>SupportBot</h2>
              <a href="{{ url_for('dashboard.home') }}">Dashboard</a>
              {% if selected_id %}
              <a href="{{ url_for('dashboard.server_page', server_id=selected_id) }}">Server settings</a>
              {% endif %}
              <a href="{{ url_for('dashboard.bot_settings') }}">Bot Settings</a>
              <a href="{{ url_for('dashboard.language_settings', server_id=selected_id) if selected_id else url_for('dashboard.home') }}">Language</a>
              <a href="{{ support_url }}" target="_blank" rel="noopener">Support Server</a>
              <a href="{{ url_for('logout') }}">Log out</a>
            </aside>
            <main>
              <h1>{{ title }}</h1>
              {{ body|safe }}
            </main>
          </div>
        </body>
        </html>
        """,
        title=title,
        body=body,
        style=PAGE_STYLE,
        support_url=SUPPORT_SERVER_URL,
        selected_id=context.get("selected_id"),
    )


@dashboard.route("/")
def home():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    guilds = session.get("guilds", [])
    manageable = [g for g in guilds if can_manage_guild(g)]

    cards = []
    for guild in manageable:
        guild_id = str(guild.get("id", ""))
        if not guild_id.isdigit():
            continue

        installed = guild_bot_installed(guild_id)
        status = (
            '<span class="good">● Bot installed</span>'
            if installed
            else '<span class="muted">● Bot not detected</span>'
        )

        action = (
            f'<a class="button" href="{url_for("dashboard.server_page", server_id=guild_id)}">Manage</a>'
            if installed
            else f'<a class="button secondary" href="{url_for("dashboard.add_bot", server_id=guild_id)}">Add Bot</a>'
        )

        icon = guild.get("icon")
        if icon:
            image_url = (
                f'https://cdn.discordapp.com/icons/{guild_id}/{icon}.png?size=64'
            )
            icon_html = (
                f'<img src="{image_url}" width="40" height="40" '
                'style="border-radius:50%;vertical-align:middle;margin-right:10px" '
                'alt="">'
            )
        else:
            icon_html = ""

        cards.append(
            '<div class="card">'
            f'{icon_html}<strong>{_escape(guild.get("name", "Discord server"))}</strong>'
            f'<p>{status}</p>{action}</div>'
        )

    cards_html = "".join(cards) or (
        '<div class="card">No manageable servers found. '
        'Make sure you signed in with the correct Discord account and have '
        'Manage Server or Administrator permissions.</div>'
    )

    body = (
        f'<p class="muted">Signed in as {_escape(user.get("username", "Discord user"))}</p>'
        '<div class="grid">' + cards_html + '</div>'
        '<div class="grid">'
        '<div class="card"><h3>Bot Hosting</h3><p>Hosting tools are coming soon.</p>'
        '<button disabled>Coming Soon</button></div>'
        '<div class="card"><h3>VIP</h3><p>$3/month · $30/year · $50 lifetime</p>'
        '<p>VIP features and payment processing are not available yet.</p>'
        '<button disabled>Coming Soon</button></div>'
        '</div>'
    )

    return render_page("Dashboard", body)


@dashboard.route("/server/<server_id>", methods=["GET"])
def server_page(server_id):
    get_user_guild(server_id)

    if not guild_bot_installed(server_id):
        return render_page(
            "Bot not detected",
            '<div class="card">The bot is not currently detected in this server. '
            'Add it to the server and try again.</div>',
        ), 409

    settings = get_server_settings(server_id)
    ticket_settings = settings["tickets"]
    automod_settings = settings["automod"]
    welcome_settings = settings["welcome"]
    logs_settings = settings["logs"]

    body = f"""
    <div class="card">
      <h3>Tickets</h3>
      <p>Enabled: {_escape(str(ticket_settings.get('enabled')))}</p>
      <p>Ticket panels: {len(ticket_settings.get('panels', []))}</p>
      <p class="muted">Ticket configuration editor is being connected.</p>
    </div>
    <div class="card">
      <h3>AutoMod</h3>
      <p>Enabled: {_escape(str(automod_settings.get('enabled')))}</p>
      <p>Block links: {_escape(str(automod_settings.get('block_links')))}</p>
      <p>Block invites: {_escape(str(automod_settings.get('block_invites')))}</p>
      <p class="muted">AutoMod configuration editor is being connected.</p>
    </div>
    <div class="card">
      <h3>Welcome</h3>
      <p>Enabled: {_escape(str(welcome_settings.get('enabled')))}</p>
      <p>Message type: {_escape(str(welcome_settings.get('message_type')))}</p>
    </div>
    <div class="card">
      <h3>Logs</h3>
      <p>Enabled: {_escape(str(logs_settings.get('enabled')))}</p>
      <p>Message type: {_escape(str(logs_settings.get('message_type')))}</p>
    </div>
    <div class="card">
      <h3>Reset server settings</h3>
      <p>This restores this server's settings to defaults.</p>
      <form method="post" action="{url_for('dashboard.reset_server', server_id=server_id)}">
        <button class="danger" type="submit">Reset settings</button>
      </form>
    </div>
    """
    return render_page("Server Settings", body, selected_id=server_id)


@dashboard.route("/server/<server_id>/reset", methods=["POST"])
def reset_server(server_id):
    get_user_guild(server_id)

    if not guild_bot_installed(server_id):
        abort(409)

    reset_server_settings(server_id)
    return redirect(url_for("dashboard.server_page", server_id=server_id))


@dashboard.route("/server/<server_id>/language", methods=["GET", "POST"])
def language_settings(server_id):
    get_user_guild(server_id)

    if not guild_bot_installed(server_id):
        abort(409)

    settings = get_server_settings(server_id)
    languages = {
        "en": "English",
        "ru": "Russian",
        "tr": "Turkish",
        "es": "Spanish",
        "de": "German",
        "fr": "French",
    }

    if __import__("flask").request.method == "POST":
        from flask import request

        language = request.form.get("language", "en")
        if language not in languages:
            abort(400)

        settings["language"] = language
        save_server_settings(server_id, settings)
        return redirect(url_for("dashboard.language_settings", server_id=server_id))

    options = "".join(
        f'<option value="{code}" {"selected" if settings.get("language") == code else ""}>'
        f'{label}</option>'
        for code, label in languages.items()
    )

    body = f"""
    <div class="card">
      <form method="post">
        <label for="language">Server language</label>
        <select id="language" name="language">{options}</select>
        <button type="submit">Save Language</button>
      </form>
    </div>
    """
    return render_page("Language", body, selected_id=server_id)


@dashboard.route("/add-bot/<server_id>")
def add_bot(server_id):
    guild = get_user_guild(server_id)
    if guild_bot_installed(server_id):
        return redirect(url_for("dashboard.server_page", server_id=server_id))

    # The user must have Manage Server or Administrator permission.
    return redirect(
        "https://discord.com/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        "&scope=bot%20applications.commands"
        "&permissions=8"
        f"&guild_id={server_id}"
        "&disable_guild_select=true"
    )


@dashboard.route("/bot-settings", methods=["GET"])
def bot_settings():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if not is_owner():
        abort(403)

    body = """
    <div class="card">
      <h3>Bot Settings</h3>
      <p>Global bot settings are restricted to the bot owner.</p>
      <p>Use the existing settings route in main.py for now.</p>
    </div>
    """
    return render_page("Bot Settings", body)


def _escape(value):
    import html
    return html.escape(str(value), quote=True)


def register_dashboard(app, bot_instance):
    set_bot(bot_instance)
    app.register_blueprint(dashboard) 
