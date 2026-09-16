"""Loads the list of ActBlue accounts to pull refunds from.

Account names/keys live in a checked-in YAML file (accounts.yaml); the
matching API credentials live only in environment variables / .env so
secrets never get committed.
"""

import os

import yaml


class MissingCredentialsError(Exception):
    pass


def _env_names(key):
    prefix = f"ACTBLUE_{key.upper()}"
    return f"{prefix}_CLIENT_UUID", f"{prefix}_CLIENT_SECRET"


def load_accounts(config_path="accounts.yaml"):
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    accounts = []
    for entry in raw.get("accounts", []):
        key = entry["key"]
        name = entry.get("name", key)
        uuid_env, secret_env = _env_names(key)
        client_uuid = os.environ.get(uuid_env)
        client_secret = os.environ.get(secret_env)
        if not client_uuid or not client_secret:
            raise MissingCredentialsError(
                f"Missing credentials for account '{key}'. Set {uuid_env} and "
                f"{secret_env} in your environment or .env file."
            )
        accounts.append({"key": key, "name": name, "client_uuid": client_uuid, "client_secret": client_secret})
    return accounts
