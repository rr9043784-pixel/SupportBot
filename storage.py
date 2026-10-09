import copy
import json
import os
import re
import tempfile
import threading

from config import (
    DATA_DIR,
    DEFAULT_LANGUAGE,
    DEFAULT_SETTINGS,
    SETTINGS_FILE,
)

_lock = threading.RLock()

DEFAULT_SERVER_SETTINGS = {
    "language": DEFAULT_LANGUAGE,
    "tickets": {
        "enabled": True,
        "category_id": None,
        "support_role_id": None,
        "panels": [],
        "vip_dm_only": True,
    },
    "automod": {
        "enabled": False,
        "block_links": True,
        "block_invites": True,
        "block_spam": True,
        "block_profanity": False,
        "max_repeated_messages": 5,
        "spam_window_seconds": 8,
        "penalty": "delete",
        "exempt_role_ids": [],
        "allowed_domains": [],
    },
    "welcome": {
        "enabled": False,
        "channel_id": None,
        "message_type": "embed",
        "message": "Welcome, {user_mention}, to {server_name}!",
    },
    "logs": {
        "enabled": False,
        "channel_id": None,
        "message_type": "embed",
        "message": "{user_name} performed an action: {action}",
    },
    "messages": {
        "custom_variables": {},
    },
}


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _safe_name(name):
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", str(name))


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else copy.deepcopy(default)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return copy.deepcopy(default)


def _atomic_write_json(path, data):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    fd, temporary_path = tempfile.mkstemp(
        prefix=".tmp_",
        suffix=".json",
        dir=directory,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


# =========================
# Global bot settings
# =========================

def load_settings():
    with _lock:
        settings = _read_json(SETTINGS_FILE, DEFAULT_SETTINGS)
        result = copy.deepcopy(DEFAULT_SETTINGS)
        result.update(settings)
        return result


def save_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError("Settings must be a dictionary.")

    with _lock:
        current = load_settings()
        current.update(settings)
        _atomic_write_json(SETTINGS_FILE, current)
        return copy.deepcopy(current)


# =========================
# Per-server settings
# =========================

def _server_path(guild_id):
    return os.path.join(
        DATA_DIR,
        f"server_{_safe_name(guild_id)}.json",
    )


def _merge_defaults(defaults, saved):
    result = copy.deepcopy(defaults)

    if not isinstance(saved, dict):
        return result

    for key, value in saved.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _merge_defaults(result[key], value)
        else:
            result[key] = copy.deepcopy(value)

    return result


def get_server_settings(guild_id):
    if guild_id is None:
        raise ValueError("A server ID is required.")

    with _lock:
        saved = _read_json(
            _server_path(guild_id),
            DEFAULT_SERVER_SETTINGS,
        )
        return _merge_defaults(DEFAULT_SERVER_SETTINGS, saved)


def save_server_settings(guild_id, settings):
    if guild_id is None:
        raise ValueError("A server ID is required.")

    if not isinstance(settings, dict):
        raise ValueError("Server settings must be a dictionary.")

    with _lock:
        current = get_server_settings(guild_id)
        updated = _merge_defaults(current, settings)
        _atomic_write_json(_server_path(guild_id), updated)
        return copy.deepcopy(updated)


def reset_server_settings(guild_id):
    if guild_id is None:
        raise ValueError("A server ID is required.")

    with _lock:
        defaults = copy.deepcopy(DEFAULT_SERVER_SETTINGS)
        _atomic_write_json(_server_path(guild_id), defaults)
        return defaults


# =========================
# Custom variables
# =========================

_VARIABLE_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,39}$")


def get_custom_variables(guild_id):
    settings = get_server_settings(guild_id)
    variables = settings.get("messages", {}).get(
        "custom_variables", {}
    )
    return copy.deepcopy(variables) if isinstance(variables, dict) else {}


def set_custom_variable(guild_id, name, value):
    if not isinstance(name, str) or not _VARIABLE_NAME.fullmatch(name):
        raise ValueError(
            "Variable names must start with a letter and contain only "
            "letters, numbers, and underscores (maximum 40 characters)."
        )

    if not isinstance(value, str):
        raise ValueError("Variable values must be text.")

    if len(value) > 2000:
        raise ValueError("Variable values cannot exceed 2000 characters.")

    settings = get_server_settings(guild_id)
    variables = settings["messages"].setdefault(
        "custom_variables", {}
    )
    variables[name] = value
    save_server_settings(guild_id, settings)
    return copy.deepcopy(variables)


def delete_custom_variable(guild_id, name):
    settings = get_server_settings(guild_id)
    variables = settings["messages"].setdefault(
        "custom_variables", {}
    )

    if name not in variables:
        return False

    del variables[name]
    save_server_settings(guild_id, settings)
    return True


def render_template(guild_id, template, built_in=None):
    if not isinstance(template, str):
        raise ValueError("Template must be text.")

    variables = get_custom_variables(guild_id)
    values = {}

    if isinstance(built_in, dict):
        values.update(built_in)

    values.update(variables)

    # Replace only known {variable_name} placeholders.
    # No eval or arbitrary code execution.
    pattern = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}")

    def replace(match):
        key = match.group(1)
        if key not in values:
            return match.group(0)
        return str(values[key])

    return pattern.sub(replace, template) 
