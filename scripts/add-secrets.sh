#!/usr/bin/env bash
# Add CRM API keys to Google Cloud Secret Manager, one at a time.
#
# Run in Google Cloud Shell:
#   bash add-secrets.sh
#
# Keys are typed at hidden prompts and piped straight to Secret Manager.
# Nothing is written to disk, shown on screen, or saved in shell history.
#
# Naming follows the vault guide: <crm>_<client>, with labels crm, client, env.

set -euo pipefail

PROJECT="goodman-homebase"
ENV_LABEL="prod"

if ! command -v gcloud >/dev/null; then
  echo "gcloud not found. Run this in Google Cloud Shell." >&2
  exit 1
fi
if ! command -v jq >/dev/null; then
  echo "jq not found. Run this in Google Cloud Shell, which has it built in." >&2
  exit 1
fi

gcloud config set project "$PROJECT" >/dev/null 2>&1

# Lowercase letters, numbers and dashes only, max 63 characters (label limit).
valid_part() {
  [[ "$1" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]
}

# Lowercase and strip surrounding spaces.
trim_lower() {
  local s="${1,,}"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

# Hidden prompt that refuses empty input. Result goes in the variable named $2.
read_hidden() {
  local prompt="$1" __var="$2" __val=""
  while [[ -z "$__val" ]]; do
    read -rsp "$prompt" __val
    echo
    [[ -z "$__val" ]] && echo "  Can't be empty. Try again."
  done
  printf -v "$__var" '%s' "$__val"
}

added=()
updated=()

echo
echo "Adding keys to Secret Manager in project: $PROJECT"
echo "Press Ctrl+C at any time to stop. Keys already saved stay saved."

while true; do
  echo
  echo "------------------------------------------------------------"
  read -rp "CRM (e.g. actblue, ngp, mailchimp), or press Enter to finish: " crm
  crm="$(trim_lower "$crm")"
  [[ -z "$crm" ]] && break
  if ! valid_part "$crm"; then
    echo "  Use only lowercase letters, numbers and dashes."
    continue
  fi

  read -rp "Client (e.g. smith-for-senate): " client
  client="$(trim_lower "$client")"
  if ! valid_part "$client"; then
    echo "  Use only lowercase letters, numbers and dashes (no spaces)."
    continue
  fi

  name="${crm}_${client}"

  exists=false
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    exists=true
    read -rp "  '$name' already exists. Add a NEW value to it (rotation)? [y/N]: " yn
    [[ "$yn" =~ ^[Yy]$ ]] || { echo "  Skipped."; continue; }
  fi

  # Choose the value format. Two-part credentials are stored together as JSON.
  case "$crm" in
    actblue) format="actblue" ;;
    ngp|ngpvan|van) format="ngp" ;;
    *)
      echo "  Key format:"
      echo "    1) Single API key or token"
      echo "    2) Two parts: Client UUID + Client Secret"
      echo "    3) Two parts: Application name + API key"
      read -rp "  Choose 1, 2 or 3 [1]: " choice
      case "${choice:-1}" in
        2) format="actblue" ;;
        3) format="ngp" ;;
        *) format="single" ;;
      esac
      ;;
  esac

  case "$format" in
    actblue)
      read_hidden "  Client UUID (hidden): " part1
      read_hidden "  Client Secret (hidden): " part2
      value="$(P1="$part1" P2="$part2" jq -cn '{client_uuid: env.P1, client_secret: env.P2}')"
      ;;
    ngp)
      read_hidden "  Application name (hidden): " part1
      read_hidden "  API key (hidden): " part2
      value="$(P1="$part1" P2="$part2" jq -cn '{app: env.P1, key: env.P2}')"
      ;;
    single)
      read_hidden "  API key (hidden): " value
      ;;
  esac
  unset part1 part2

  if $exists; then
    if printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null; then
      echo "  Added a new version to $name."
      echo "  After confirming the new key works, disable the old version (vault guide, Step 8)."
      updated+=("$name")
    else
      echo "  FAILED to update $name. Nothing was changed."
    fi
  else
    if printf '%s' "$value" | gcloud secrets create "$name" \
        --data-file=- \
        --replication-policy=automatic \
        --labels="crm=${crm},client=${client},env=${ENV_LABEL}" >/dev/null; then
      echo "  Created $name."
      added+=("$name")
    else
      echo "  FAILED to create $name. Nothing was saved."
    fi
  fi
  unset value
done

echo
echo "============================================================"
echo "Done. Created ${#added[@]}, updated ${#updated[@]}."
for n in "${added[@]}";   do echo "  + $n"; done
for n in "${updated[@]}"; do echo "  ~ $n (new version)"; done
echo
echo "Next: delete the old copies of these keys from wherever they were stored."
