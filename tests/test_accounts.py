import pytest

from actblue_refunds.accounts import MissingCredentialsError, load_accounts


def test_load_accounts_reads_config_and_env(tmp_path, monkeypatch):
    config = tmp_path / "accounts.yaml"
    config.write_text(
        "accounts:\n"
        "  - key: campaign_a\n"
        "    name: Campaign A\n"
    )
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_UUID", "uuid-1")
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_SECRET", "secret-1")

    accounts = load_accounts(str(config))

    assert accounts == [
        {"key": "campaign_a", "name": "Campaign A", "client_uuid": "uuid-1", "client_secret": "secret-1"}
    ]


def test_load_accounts_missing_credentials_raises(tmp_path, monkeypatch):
    config = tmp_path / "accounts.yaml"
    config.write_text(
        "accounts:\n"
        "  - key: campaign_a\n"
        "    name: Campaign A\n"
    )
    monkeypatch.delenv("ACTBLUE_CAMPAIGN_A_CLIENT_UUID", raising=False)
    monkeypatch.delenv("ACTBLUE_CAMPAIGN_A_CLIENT_SECRET", raising=False)

    with pytest.raises(MissingCredentialsError):
        load_accounts(str(config))


def test_load_accounts_defaults_name_to_key(tmp_path, monkeypatch):
    config = tmp_path / "accounts.yaml"
    config.write_text("accounts:\n  - key: campaign_a\n")
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_UUID", "uuid-1")
    monkeypatch.setenv("ACTBLUE_CAMPAIGN_A_CLIENT_SECRET", "secret-1")

    accounts = load_accounts(str(config))

    assert accounts[0]["name"] == "campaign_a"
