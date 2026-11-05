#!/usr/bin/env bash
# Pulls the `deploy` branch and redeploys the UZEX stack when a new commit appears.
# Run by uzex-deploy.timer every 30 s. Manual: FORCE=1 /opt/uzex/app/deploy/auto-deploy.sh
set -euo pipefail
APP=/opt/uzex
REPO=$APP/app
BRANCH=deploy
COMPOSE=(docker compose -f "$REPO/deploy/compose.prod.yml")
CADDYFILE=/opt/botir/Caddyfile
CADDY_CONTAINER=botir-caddy-1

exec 9>"$APP/.lock"
flock -n 9 || exit 0
log() { echo "$(date -u +%FT%TZ) $*"; }

ensure_caddy_sites() {
  # Our two domains live in the shared Caddy (it owns :80/:443 and issues certificates).
  # Re-add the block only if it disappeared; never edit anything else in that file.
  # Opt-in: only when /opt/uzex/.manage-caddy exists (the Caddyfile belongs to another stack).
  [ -f "$APP/.manage-caddy" ] || return 0
  [ -f "$CADDYFILE" ] || return 0
  grep -q "vitality-api.comma.uz" "$CADDYFILE" && return 0
  log "UZEX block missing from Caddyfile: re-adding"
  cp -p "$CADDYFILE" "$APP/Caddyfile.bak.$(date +%s)"
  local candidate; candidate=$(mktemp)
  cat "$CADDYFILE" "$REPO/deploy/caddy-sites.caddy" > "$candidate"
  if docker exec -i -e API_DOMAIN=x.invalid -e DASHBOARD_DOMAIN=y.invalid "$CADDY_CONTAINER" \
       sh -c 'cat > /tmp/uzex-check.caddy && caddy adapt --config /tmp/uzex-check.caddy --adapter caddyfile >/dev/null' < "$candidate"; then
    cat "$REPO/deploy/caddy-sites.caddy" >> "$CADDYFILE"   # append in place: keeps the bind-mounted inode
    docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
    log "Caddy reloaded"
  else
    log "Caddy config check failed; Caddyfile left unchanged"
  fi
  rm -f "$candidate"
}

cd "$REPO"
git fetch -q origin "$BRANCH"
REMOTE=$(git rev-parse "origin/$BRANCH")
DEPLOYED=$(cat "$APP/.deployed" 2>/dev/null || true)

if [ "$REMOTE" = "$DEPLOYED" ] && [ "${FORCE:-0}" != "1" ]; then
  ensure_caddy_sites
  exit 0
fi

log "deploying $REMOTE (was ${DEPLOYED:-none})"
git reset -q --hard "$REMOTE"
if "${COMPOSE[@]}" build --pull -q && "${COMPOSE[@]}" up -d --remove-orphans --wait --wait-timeout 180 \
   && curl -fsS --max-time 5 -H 'Host: vitality-api.comma.uz' http://172.17.0.1:18080/api/agent/status | grep -q '"ready":true'; then
  echo "$REMOTE" > "$APP/.deployed"
  log "deployed $REMOTE"
  docker image prune -f --filter "label=com.docker.compose.project=uzex" >/dev/null || true
else
  log "deploy of $REMOTE FAILED"
  if [ -n "$DEPLOYED" ]; then
    log "rolling back to $DEPLOYED"
    git reset -q --hard "$DEPLOYED"
    "${COMPOSE[@]}" up -d --build --remove-orphans --wait --wait-timeout 180 || true
  fi
  # remember the failed commit so we don't rebuild it every 30 s
  echo "$REMOTE" > "$APP/.deployed"
  exit 1
fi
ensure_caddy_sites
