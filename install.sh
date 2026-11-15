#!/usr/bin/env bash
# X-TOOLS installer and helper – one command to install, update, inspect or remove X-TOOLS.
#
#   Install:    curl -fsSL <address of this file> | sudo bash
#   Afterwards: sudo x-tools-ctl update | status | logs | setup-code | uninstall
#
# What the installer does: checks Docker (offers to install it), fetches X-TOOLS with git into /opt/x-tools,
# asks a few questions (how you reach it, time zone, optional website deployer), writes deploy/.env,
# builds and starts the containers and prints the setup code for the first login. Safe to run again: an existing
# installation is updated and keeps its settings and data.
#
# Everything can be preset for unattended runs (--yes or XT_YES=1 takes the defaults):
#   XT_DIR        installation folder                      (default /opt/x-tools)
#   XT_REPO       git address of X-TOOLS                   (default: see REPO_DEFAULT below)
#   XT_REF        branch or tag to install                 (default main)
#   XT_GIT_TOKEN  access token if the repository is private (used for this run only, never stored)
#   XT_MODE       domain | proxy | lan                     (see the question "How do you reach X-TOOLS?")
#   XT_DOMAIN     domain for XT_MODE=domain (Caddy gets the certificate)
#   XT_BASE_URL   public address for XT_MODE=proxy, e.g. https://tools.example.com
#   XT_PORT       port of X-TOOLS on this machine          (default 8080)
#   XT_TIMEZONE   IANA time zone                           (default: of this server)
#   XT_DEPLOYER   yes | no – deploy customer websites      (default no)
#   XT_INSTALL_DOCKER yes | no                             (default: ask)
set -euo pipefail

# Public repository of X-TOOLS.
REPO_DEFAULT="https://github.com/xarxfy/x-tools.git"
SELF_URL_DEFAULT=""

DIR="${XT_DIR:-/opt/x-tools}"
REPO="${XT_REPO:-$REPO_DEFAULT}"
REF="${XT_REF:-main}"
YES="${XT_YES:-no}"
CTL="${XT_CTL:-/usr/local/bin/x-tools-ctl}"
CONF_DIR="${XT_CONF_DIR:-/etc/x-tools}"
CADDY=x-tools-caddy

if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B=; G=; Y=; R=; N=; fi
say()  { printf '%s\n' "$*"; }
step() { printf '\n%s==>%s %s%s%s\n' "$G" "$N" "$B" "$*" "$N"; }
warn() { printf '%s!%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%sError:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }

# --- questions -------------------------------------------------------------------------------------------

# true when questions can be asked (there is a terminal, even if the script itself comes from a pipe)
interactive() { [ "$YES" != yes ] && ( : < /dev/tty ) 2>/dev/null; }

# ask VAR "question" "default"  – an already set VAR wins; --yes takes the default; otherwise the question is asked.
ask() {
  local var=$1 question=$2 default=${3:-} answer=""
  if [ -n "${!var:-}" ]; then return; fi
  if ! interactive; then printf -v "$var" '%s' "$default"; return; fi
  printf '%s%s%s%s: ' "$B" "$question" "$N" "${default:+ [$default]}" > /dev/tty
  IFS= read -r answer < /dev/tty || true
  printf -v "$var" '%s' "${answer:-$default}"
}

# yesno "question" default(yes|no) -> returns 0 for yes
yesno() {
  local answer=""
  if ! interactive; then [ "$2" = yes ]; return; fi
  printf '%s%s%s [%s]: ' "$B" "$1" "$N" "$([ "$2" = yes ] && echo Y/n || echo y/N)" > /dev/tty
  IFS= read -r answer < /dev/tty || true
  answer=${answer:-$2}
  case "$answer" in y|Y|yes|YES|j|J|ja) return 0 ;; *) return 1 ;; esac
}

# --- helpers ---------------------------------------------------------------------------------------------

need_root() {
  [ "${XT_NO_ROOT_CHECK:-}" = 1 ] && return
  if [ "$(id -u)" != 0 ]; then
    command -v sudo >/dev/null 2>&1 || die "Please run as root (sudo is not installed)."
    if [ -f "$0" ] && [ "${0##*/}" != bash ]; then exec sudo -E bash "$0" "$@"; fi
    die "Please run as root: curl -fsSL https://raw.githubusercontent.com/xarxfy/x-tools/main/install.sh | sudo bash"
  fi
}

pkg_install() {
  if command -v apt-get >/dev/null 2>&1; then DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" >/dev/null
  elif command -v dnf >/dev/null 2>&1; then dnf install -y -q "$@" >/dev/null
  elif command -v yum >/dev/null 2>&1; then yum install -y -q "$@" >/dev/null
  elif command -v zypper >/dev/null 2>&1; then zypper -q install -y "$@" >/dev/null
  elif command -v pacman >/dev/null 2>&1; then pacman -S --noconfirm --needed "$@" >/dev/null
  elif command -v apk >/dev/null 2>&1; then apk add -q "$@" >/dev/null
  else die "Please install these first: $*"
  fi
}

ensure_tools() {
  local missing=()
  for tool in git curl; do command -v "$tool" >/dev/null 2>&1 || missing+=("$tool"); done
  if [ "${#missing[@]}" -gt 0 ]; then
    step "Installing ${missing[*]}"
    command -v apt-get >/dev/null 2>&1 && apt-get update -qq >/dev/null
    pkg_install "${missing[@]}"
  fi
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker info >/dev/null 2>&1 || die "Docker is installed but not running or not reachable (try: systemctl start docker)."
    return
  fi
  step "Docker with the compose plugin is missing"
  if [ "${XT_INSTALL_DOCKER:-ask}" = no ]; then die "Docker is required. Install it first: https://docs.docker.com/engine/install/"; fi
  if [ "${XT_INSTALL_DOCKER:-ask}" = yes ] || yesno "Install Docker now with the official script (get.docker.com)?" yes; then
    curl -fsSL https://get.docker.com | sh
    command -v systemctl >/dev/null 2>&1 && systemctl enable --now docker >/dev/null 2>&1 || true
    docker compose version >/dev/null 2>&1 || die "Docker was installed but the compose plugin is missing."
  else
    die "Docker is required. Install it first: https://docs.docker.com/engine/install/"
  fi
}

# git with the token passed through the environment (never written into .git/config)
git_auth() {
  if [ -n "${XT_GIT_TOKEN:-}" ]; then
    local auth
    auth=$(printf 'oauth2:%s' "$XT_GIT_TOKEN" | base64 | tr -d '\n')
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraHeader GIT_CONFIG_VALUE_0="Authorization: Basic $auth" GIT_TERMINAL_PROMPT=0 git "$@"
  else
    GIT_TERMINAL_PROMPT=0 git "$@"
  fi
}

# setenv KEY VALUE – sets KEY in deploy/.env (replaces an existing or commented example line)
setenv() {
  local file="$DIR/deploy/.env"
  case "$2" in *$'\n'*|*"'"*|*'"'*|*'$'*|*'`'*|*'\'*) die "Value for $1 contains characters that are not allowed." ;; esac
  grep -vE "^#? ?$1=" "$file" > "$file.tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$file.tmp"
  mv "$file.tmp" "$file"
}

getenv() { sed -n "s/^$1=//p" "$DIR/deploy/.env" 2>/dev/null | tail -n1; }

server_ip() { hostname -I 2>/dev/null | awk '{print $1}' || true; }

timezone() {
  local tz=""
  command -v timedatectl >/dev/null 2>&1 && tz=$(timedatectl show -p Timezone --value 2>/dev/null || true)
  [ -z "$tz" ] && [ -r /etc/timezone ] && tz=$(cat /etc/timezone)
  echo "${tz:-UTC}"
}

fetch() {
  if [ -d "$DIR/.git" ]; then
    step "Updating $DIR"
    [ -z "$(git -C "$DIR" status --porcelain --untracked-files=no)" ] || die "$DIR has local changes – commit or discard them first."
    git_auth -C "$DIR" fetch --quiet origin "$REF" --tags
    git -C "$DIR" checkout --quiet "$REF" 2>/dev/null || git -C "$DIR" checkout --quiet FETCH_HEAD
    git -C "$DIR" merge --quiet --ff-only FETCH_HEAD 2>/dev/null || true
  else
    [ ! -e "$DIR" ] || [ -z "$(ls -A "$DIR" 2>/dev/null)" ] || die "$DIR exists and is not an X-TOOLS installation. Choose another folder (XT_DIR=…)."
    step "Fetching X-TOOLS ($REF) into $DIR"
    mkdir -p "$(dirname "$DIR")"
    git_auth clone --quiet --branch "$REF" "$REPO" "$DIR" || die "Cannot clone $REPO. For a private repository set XT_GIT_TOKEN."
  fi
  say "Version: $(git -C "$DIR" describe --tags --always 2>/dev/null || echo unknown)"
}

# --- configuration (first install only) ---------------------------------------------------------------------

configure() {
  [ -f "$DIR/deploy/.env" ] && { say "Keeping the settings in $DIR/deploy/.env"; return; }
  cp "$DIR/deploy/.env.example" "$DIR/deploy/.env"
  chmod 600 "$DIR/deploy/.env"
  # an aborted configuration must not leave a half-filled .env behind (the next run would keep it)
  trap 'rm -f "$DIR/deploy/.env"' EXIT
  step "Configuration"
  say "How do you reach X-TOOLS?"
  say "  1) domain  – with a domain name; Caddy fetches the HTTPS certificate (ports 80 and 443 must be free and reachable)"
  say "  2) proxy   – behind your own reverse proxy or Cloudflare Tunnel on this server"
  say "  3) lan     – only at home: open http://<server-ip>:<port> in the browser, no proxy"
  local mode="${XT_MODE:-}" choice=""
  if [ -z "$mode" ]; then ask choice "Your choice (1-3)" "3"; case "$choice" in 1) mode=domain ;; 2) mode=proxy ;; *) mode=lan ;; esac; fi
  ask XT_PORT "Port of X-TOOLS on this server" "8080"
  [[ "$XT_PORT" =~ ^[0-9]{2,5}$ ]] || die "Invalid port."
  ask XT_TIMEZONE "Time zone" "$(timezone)"
  setenv XT_TIMEZONE "$XT_TIMEZONE"
  setenv XT_PORT "$XT_PORT"
  case "$mode" in
    domain)
      ask XT_DOMAIN "Domain (its DNS record must point to this server)" ""
      [[ "$XT_DOMAIN" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || die "Please enter a valid domain, e.g. tools.example.com"
      setenv XT_HOST 127.0.0.1; setenv XT_BASE_URL "https://$XT_DOMAIN"
      WANT_CADDY=yes ;;
    proxy)
      ask XT_BASE_URL "Public address X-TOOLS will have" "https://tools.example.com"
      setenv XT_HOST 127.0.0.1; setenv XT_BASE_URL "$XT_BASE_URL" ;;
    lan)
      local ip; ip=$(server_ip)
      setenv XT_HOST 0.0.0.0; setenv XT_TRUST_PROXY false; setenv XT_BASE_URL "http://${ip:-localhost}:$XT_PORT" ;;
    *) die "Unknown XT_MODE '$mode' (domain, proxy or lan)." ;;
  esac
  local deployer="${XT_DEPLOYER:-}"
  if [ -z "$deployer" ]; then yesno "Deploy customer websites from git (starts an extra container with Docker access)?" no && deployer=yes || deployer=no; fi
  if [ "$deployer" = yes ]; then setenv COMPOSE_PROFILES deploy; fi
  [ "${WANT_CADDY:-no}" = yes ] && setenv XT_PROTECTED_CONTAINERS "x-tools,x-tools-collector,x-tools-deployer,$CADDY"
  trap - EXIT
  return 0
}

setup_caddy() {
  [ "${WANT_CADDY:-no}" = yes ] || return 0
  local domain port; domain=$(getenv XT_BASE_URL); domain=${domain#https://}; port=$(getenv XT_PORT); port=${port:-8080}
  step "Setting up Caddy for $domain"
  mkdir -p "$DIR/caddy"
  printf '%s {\n\treverse_proxy 127.0.0.1:%s\n}\n' "$domain" "$port" > "$DIR/caddy/Caddyfile"
  docker rm -f "$CADDY" >/dev/null 2>&1 || true
  docker run -d --name "$CADDY" --restart unless-stopped --network host \
    -v "$DIR/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" -v x-tools-caddy-data:/data caddy:2 >/dev/null
  say "Caddy is running; the certificate is requested on the first visit of https://$domain"
}

install_ctl() {
  local src="${BASH_SOURCE[0]:-$0}"
  if [ -f "$DIR/install.sh" ]; then cp "$DIR/install.sh" "$CTL"; elif [ -f "$src" ]; then cp "$src" "$CTL"; else return 0; fi
  chmod 755 "$CTL"
  # remember where X-TOOLS lives so the helper finds it later
  mkdir -p "$CONF_DIR" && printf 'XT_DIR=%s\nXT_REPO=%s\nXT_REF=%s\n' "$DIR" "$REPO" "$REF" > "$CONF_DIR/ctl.conf"
}

start() {
  step "Building and starting X-TOOLS (the first build takes a few minutes)"
  ( cd "$DIR/deploy" && sh setup.sh )
}

summary() {
  local url; url=$(getenv XT_BASE_URL)
  printf '\n%sX-TOOLS is installed.%s\n' "$G$B" "$N"
  say "  Open:      ${url:-http://127.0.0.1:$(getenv XT_PORT)}"
  say "  Update:    sudo x-tools-ctl update"
  say "  Status:    sudo x-tools-ctl status      Logs: sudo x-tools-ctl logs"
  say "  Backup:    in X-TOOLS under Settings → Backup (before an uninstall too)"
  say "  Setup code (first login): sudo x-tools-ctl setup-code"
}

# --- commands --------------------------------------------------------------------------------------------

cmd_install() {
  step "X-TOOLS installer"
  say "Note: X-TOOLS is entirely AI-written (\"vibe coded\") and has had no independent security audit."
  say "Make backups and read the README before you expose it to the internet."
  ensure_tools
  ensure_docker
  fetch
  configure
  start
  setup_caddy
  install_ctl
  summary
}

cmd_update() {
  [ -d "$DIR/.git" ] || die "No installation found in $DIR."
  ensure_docker
  fetch
  start
  install_ctl
  say "Updated. Agents on other servers show an update hint when they are outdated (Settings → Agents)."
}

cmd_status() {
  docker ps -a --filter name=x-tools --format 'table {{.Names}}\t{{.Status}}'
  local port; port=$(getenv XT_PORT); port=${port:-8080}
  if curl -fs -o /dev/null "http://127.0.0.1:$port/api/health"; then say "Web UI answers on port $port."; else warn "The web UI does not answer on port $port."; fi
  say "Version: $(git -C "$DIR" describe --tags --always 2>/dev/null || echo unknown)"
}

cmd_logs() { docker logs --tail "${1:-100}" -f x-tools; }

cmd_setup_code() {
  local code; code=$(docker logs x-tools 2>&1 | grep "Setup code:" | tail -n1 || true)
  [ -n "$code" ] && say "$code" || say "No setup code: the first account already exists."
}

cmd_uninstall() {
  [ -d "$DIR" ] || die "No installation found in $DIR."
  warn "This removes the X-TOOLS containers. Make a backup first (Settings → Backup) if you want to keep your data."
  yesno "Remove X-TOOLS from this server?" no || { say "Cancelled."; exit 0; }
  ( cd "$DIR/deploy" && COMPOSE_PROFILES=deploy docker compose down --remove-orphans ) || true
  docker rm -f "$CADDY" >/dev/null 2>&1 || true
  if yesno "Also delete ALL data (database, secret key, stored credentials)? This cannot be undone." no; then
    docker volume rm deploy_x-tools-data deploy_x-tools-exchange x-tools-caddy-data >/dev/null 2>&1 || true
    say "Data deleted."
  else
    say "Data volumes kept (deploy_x-tools-data): a new installation will find them again."
  fi
  if yesno "Delete the program folder $DIR?" yes; then rm -rf -- "$DIR"; fi
  rm -f "$CTL"; rm -rf "$CONF_DIR"
  say "X-TOOLS removed. Agents on other servers: see docs/agents.md#remove-an-agent (or the uninstall command in Settings → Agents)."
}

usage() {
  cat <<EOF
X-TOOLS helper
  install        install X-TOOLS (default when nothing is installed yet)
  update         fetch the latest version and rebuild
  status         containers, health and version
  logs [lines]   follow the log of the web container
  setup-code     show the one-time code for the first login
  uninstall      remove X-TOOLS (asks about the data)
Options: --yes (take all defaults), XT_DIR=… XT_REF=… (see the top of this file)
EOF
}

main() {
  local cmd=""
  case "$YES" in 1|true|yes) YES=yes ;; *) YES=no ;; esac
  for arg in "$@"; do
    case "$arg" in
      --yes|-y) YES=yes ;;
      -h|--help|help) usage; exit 0 ;;
      *) [ -z "$cmd" ] && cmd=$arg || ARGS="${ARGS:-} $arg" ;;
    esac
  done
  # settings of an existing installation (when called as x-tools-ctl)
  if [ -f "$CONF_DIR/ctl.conf" ]; then
    # shellcheck disable=SC1091
    . "$CONF_DIR/ctl.conf"
    DIR="${XT_DIR:-$DIR}"; REPO="${XT_REPO:-$REPO}"; REF="${XT_REF:-$REF}"
  fi
  need_root "$@"
  if [ -z "$cmd" ]; then
    if [ -d "$DIR/.git" ] && [ "${0##*/}" = x-tools-ctl ]; then usage; exit 0; fi
    cmd=install
  fi
  case "$cmd" in
    install) cmd_install ;;
    update) cmd_update ;;
    status) cmd_status ;;
    logs) cmd_logs ${ARGS:-} ;;
    setup-code) cmd_setup_code ;;
    uninstall) cmd_uninstall ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
