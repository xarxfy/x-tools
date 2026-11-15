#!/usr/bin/env bash
# X-TOOLS uninstaller – works like install.sh, one command:
#
#   curl -fsSL https://raw.githubusercontent.com/xarxfy/x-tools/main/uninstall.sh | sudo bash
#
# Removes the X-TOOLS containers (web, collector, deployer, Caddy if the installer set it up) and, if you
# agree, the program folder, the helper x-tools-ctl and – only after a separate question – ALL data
# (database, secret key, stored credentials). Make a backup first (Settings → Backup).
#
# Not touched: websites you deployed with X-TOOLS (they keep running, folder XT_SITES_DIR), agents on other servers
# (remove them with the uninstall command in Settings → Agents), Docker itself.
#
# Variables for unattended runs (--yes takes the answers below):
#   XT_DIR          installation folder                       (default: the one the installer used, else /opt/x-tools)
#   --force         skip the first question "Remove X-TOOLS?" (needed for unattended runs; --yes alone answers it with no)
#   XT_REMOVE_DATA  yes | no  delete the data volumes         (default no – also with --yes)
#   XT_REMOVE_DIR   yes | no  delete the program folder       (default yes)
set -euo pipefail

CTL="${XT_CTL:-/usr/local/bin/x-tools-ctl}"
CONF_DIR="${XT_CONF_DIR:-/etc/x-tools}"
CADDY=x-tools-caddy
YES="${XT_YES:-no}"
DIR="${XT_DIR:-}"

if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B=; G=; Y=; R=; N=; fi
say()  { printf '%s\n' "$*"; }
step() { printf '\n%s==>%s %s%s%s\n' "$G" "$N" "$B" "$*" "$N"; }
warn() { printf '%s!%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%sError:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }

interactive() { [ "$YES" != yes ] && ( : < /dev/tty ) 2>/dev/null; }

# yesno "question" default(yes|no) [env value that overrides]
yesno() {
  local answer="" preset="${3:-}"
  case "$preset" in yes) return 0 ;; no) return 1 ;; esac
  if ! interactive; then [ "$2" = yes ]; return; fi
  printf '%s%s%s [%s]: ' "$B" "$1" "$N" "$([ "$2" = yes ] && echo Y/n || echo y/N)" > /dev/tty
  IFS= read -r answer < /dev/tty || true
  answer=${answer:-$2}
  case "$answer" in y|Y|yes|YES|j|J|ja) return 0 ;; *) return 1 ;; esac
}

need_root() {
  [ "${XT_NO_ROOT_CHECK:-}" = 1 ] && return
  [ "$(id -u)" = 0 ] || die "Please run as root: curl -fsSL <address> | sudo bash"
}

main() {
  case "$YES" in 1|true|yes) YES=yes ;; *) YES=no ;; esac
  local force="${XT_FORCE:-}"
  for arg in "$@"; do case "$arg" in --yes|-y) YES=yes ;; --force) force=yes ;; -h|--help) sed -n 2,20p "$0"; exit 0 ;; esac; done
  case "$force" in 1|true|yes) force=yes ;; *) force="" ;; esac
  need_root
  command -v docker >/dev/null 2>&1 || die "Docker is not installed – nothing to remove."

  if [ -z "$DIR" ] && [ -f "$CONF_DIR/ctl.conf" ]; then
    # shellcheck disable=SC1091
    . "$CONF_DIR/ctl.conf"; DIR="${XT_DIR:-}"
  fi
  DIR="${DIR:-/opt/x-tools}"

  step "X-TOOLS uninstaller"
  local found=""
  docker ps -a --format '{{.Names}}' | grep -qE '^(x-tools|x-tools-collector|x-tools-deployer|x-tools-caddy)$' && found=1
  [ -d "$DIR/deploy" ] && found=1
  [ -n "$found" ] || die "No X-TOOLS installation found (folder $DIR, no containers). Set XT_DIR=… if it lives elsewhere."
  say "Installation folder: $DIR"
  docker ps -a --filter name=x-tools --format '  {{.Names}}  ({{.Status}})'

  warn "This stops and removes X-TOOLS. Make a backup first if you want to keep your data (Settings → Backup)."
  yesno "Remove X-TOOLS from this server?" no "$force" || { say "Cancelled – nothing was changed."; exit 0; }

  step "Removing containers"
  if [ -f "$DIR/deploy/docker-compose.yml" ]; then
    ( cd "$DIR/deploy" && COMPOSE_PROFILES=deploy docker compose down --remove-orphans ) || warn "docker compose down failed – removing the containers directly."
  fi
  for c in x-tools x-tools-collector x-tools-deployer "$CADDY"; do docker rm -f "$c" >/dev/null 2>&1 || true; done
  say "Containers removed."

  step "Data"
  if yesno "Also delete ALL data (database, secret key, stored credentials, backups in the data volume)? This cannot be undone." no "${XT_REMOVE_DATA:-}"; then
    docker volume rm deploy_x-tools-data deploy_x-tools-exchange x-tools-caddy-data >/dev/null 2>&1 || true
    docker image rm x-tools:local x-tools-deployer:local >/dev/null 2>&1 || true
    say "Data and images deleted."
  else
    say "Data volumes kept (deploy_x-tools-data). Installing X-TOOLS again finds them: same accounts, same credentials."
  fi

  step "Files"
  if [ -d "$DIR" ] && yesno "Delete the program folder $DIR?" yes "${XT_REMOVE_DIR:-}"; then
    case "$DIR" in /|/home|/root|/usr|/etc|/var|/opt) die "Refusing to delete $DIR." ;; esac
    rm -rf -- "$DIR"
    say "Deleted $DIR"
  fi
  rm -f "$CTL"; rm -rf "$CONF_DIR"

  printf '\n%sX-TOOLS is removed.%s\n' "$G$B" "$N"
  say "  Websites deployed with X-TOOLS keep running (folder ${XT_SITES_DIR:-/srv/x-tools-sites}); remove them with docker compose there."
  say "  Agents on other servers: Settings → Agents shows the uninstall command – or on each server:"
  say "    systemctl disable --now x-tools-agent; rm -rf /opt/x-tools-agent /etc/x-tools-agent /etc/systemd/system/x-tools-agent.service"
}

main "$@"
