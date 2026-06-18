#!/usr/bin/env bash
# ghpr.sh — minimal GitHub PR helper for the AETHER build loop.
# Replaces the GitHub MCP (disabled to save per-call tool-schema cost). Uses the
# token already stored in the repo's authed git remote, so no extra secrets.
#
# Usage:
#   ghpr.sh create <base> <head> "<title>" "<body>"   -> prints PR number
#   ghpr.sh merge  <number> [squash|merge|rebase]      -> squash default
#   ghpr.sh list   [state]                             -> open by default
#
# Repo is read from the git remote of the current directory.
set -euo pipefail

remote_url=$(git config --get remote.origin.url)
# https://<token>@github.com/<owner>/<repo>.git
TOKEN=$(printf '%s' "$remote_url" | sed -E 's#https://([^@]*)@.*#\1#; s#.*:##')
SLUG=$(printf '%s' "$remote_url" | sed -E 's#.*github.com/##; s#\.git$##')
API="https://api.github.com/repos/$SLUG"
hdr_auth="Authorization: token $TOKEN"
hdr_acc="Accept: application/vnd.github+json"

cmd="${1:-}"; shift || true
case "$cmd" in
  create)
    base="$1"; head="$2"; title="$3"; body="${4:-}"
    payload=$(python -c "import json,sys; print(json.dumps({'title':sys.argv[1],'head':sys.argv[2],'base':sys.argv[3],'body':sys.argv[4]}))" "$title" "$head" "$base" "$body")
    curl -s --max-time 30 -X POST -H "$hdr_auth" -H "$hdr_acc" "$API/pulls" -d "$payload" \
      | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('number') or d)"
    ;;
  merge)
    num="$1"; method="${2:-squash}"
    curl -s --max-time 30 -X PUT -H "$hdr_auth" -H "$hdr_acc" "$API/pulls/$num/merge" \
      -d "$(python -c "import json,sys;print(json.dumps({'merge_method':sys.argv[1]}))" "$method")" \
      | python -c "import sys,json; d=json.load(sys.stdin); print('merged' if d.get('merged') else d)"
    ;;
  list)
    state="${1:-open}"
    curl -s --max-time 20 -H "$hdr_auth" -H "$hdr_acc" "$API/pulls?state=$state&per_page=20" \
      | python -c "import sys,json; [print(f\"#{p['number']} [{p['state']}] {p['title']}\") for p in json.load(sys.stdin)]"
    ;;
  *)
    echo "usage: ghpr.sh {create <base> <head> <title> <body>|merge <num> [method]|list [state]}" >&2
    exit 2 ;;
esac
