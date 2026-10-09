import os

# =========================
# Environment
# =========================

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
DISCORD_CLIENT_ID = os.environ["DISCORD_CLIENT_ID"]
DISCORD_CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"]
FLASK_SECRET_KEY = os.environ["FLASK_SECRET_KEY"]

PORT = int(os.environ.get("PORT", "10000"))

REDIRECT_URI = os.environ.get(
    "REDIRECT_URI",
    "https://supportbot-production-c479.up.railway.app/callback",
)

OWNER_ID = 1176149190192152626

SUPPORT_SERVER_URL = "https://discord.gg/4uKAWftJv"

# =========================
# Storage
# =========================

SETTINGS_FILE = "bot_settings.json"
DATA_DIR = "data"

# =========================
# Discord intents
# =========================

INTENTS_MEMBERS = True
INTENTS_MESSAGE_CONTENT = True

# =========================
# Defaults
# =========================

DEFAULT_SETTINGS = {
    "name": "SupportBot",
    "description": "A helpful support bot for your Discord server.",
    "activity_type": "watching",
    "activity_text": "over server security",
    "status": "online",
}

# =========================
# Languages
# =========================

SUPPORTED_LANGUAGES = {
    "en": "English",
    "ru": "Russian",
    "tr": "Turkish",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
}

DEFAULT_LANGUAGE = "en"

# =========================
# VIP pricing (display only)
# Payments are not implemented yet.
# =========================

VIP_PRICES = {
    "monthly": 3,
    "yearly": 30,
    "lifetime": 50,
}

VIP_CURRENCY = "USD" 
