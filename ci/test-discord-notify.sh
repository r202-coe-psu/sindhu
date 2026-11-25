#!/usr/bin/env bash
# Offline checks for ci/discord-notify.sh. Only DRY_RUN payloads and URL validation are tested;
# nothing is sent. Needs bash and python3 (JSON validation on the developer machine only).
set -Eeuo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/discord-notify.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fails=0

pass() { printf 'ok   - %s\n' "$1"; }
fail() { printf 'FAIL - %s\n' "$1" >&2; fails=$((fails + 1)); }

# dry_run VAR=value...: run the script with a clean env; payload goes to $work/payload.json.
dry_run() {
	env -i PATH="$PATH" DRY_RUN=1 "$@" bash "$script" >"$work/payload.json" 2>"$work/stderr.txt"
}

# check NAME EXPR [ARGS...]: EXPR is Python over d (payload), e (first embed), a (ARGS).
# The payload must parse as JSON first.
check() {
	local name="$1" expr="$2"
	shift 2
	if python3 -I -c "
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
e = d['embeds'][0]
a = sys.argv[2:]
sys.exit(0 if ($expr) else 1)
" "$work/payload.json" "$@" 2>/dev/null; then
		pass "$name"
	else
		fail "$name"
	fi
}

# 1. Syntax
if bash -n "$script"; then pass "bash -n"; else fail "bash -n"; fi

# 2. Result -> colour and verb
for pair in SUCCESS:3066993 FAILURE:15158332 UNSTABLE:15844367 ABORTED:9807270 NOT_BUILT:9807270 WHATEVER:9807270; do
	r="${pair%%:*}"
	c="${pair##*:}"
	dry_run NOTIFY_RESULT="$r" || fail "DRY_RUN exit code for $r"
	check "NOTIFY_RESULT=$r has colour $c" "e['color'] == $c"
done
dry_run NOTIFY_RESULT= || fail "DRY_RUN exit code for empty result"
check "empty NOTIFY_RESULT falls back to UNKNOWN" "'unknown' in e['title']"

# 3. Minimal env
dry_run || fail "DRY_RUN exit code for minimal env"
check "minimal env: no fields, no identity keys" "e['fields'] == [] and 'username' not in d and 'avatar_url' not in d"
check "minimal env: allowed_mentions parse is empty" "d['allowed_mentions'] == {'parse': []}"

# 4. Tricky characters round-trip exactly (quote, backslash, LF, TAB, CR, \x01, Thai, emoji)
tricky=$'a"b\\c\nd\te\rf\x01g ไทย 🎉'
dry_run NOTIFY_JOB=tent NOTIFY_BRANCH="$tricky" NOTIFY_E2E_RESULT="$tricky" || fail "DRY_RUN exit code for tricky chars"
check "tricky chars: branch field round-trips" "e['fields'][0]['value'] == a[0]" "$tricky"
check "tricky chars: E2E field round-trips" "e['fields'][-1]['value'] == a[0]" "$tricky"

# 5. Discord limits with very long values
long=$(head -c 5000 /dev/zero | tr '\0' 'x')
thai=$(python3 -I -c 'print("ไทย" * 300)')
dry_run NOTIFY_JOB="$long" NOTIFY_DETAIL="$long" NOTIFY_BRANCH="$long" NOTIFY_E2E_RESULT="$long" \
	NOTIFY_DURATION="$long" NOTIFY_USERNAME="$long" NOTIFY_BUILD_URL="https://x/$long" || fail "DRY_RUN exit code for long values"
check "title <= 256 chars" "len(e['title']) <= 256"
check "description <= 4096 chars" "len(e.get('description', '')) <= 4096"
check "field values <= 1024 chars" "all(len(f['value']) <= 1024 for f in e['fields'])"
check "field names <= 256 chars" "all(len(f['name']) <= 256 for f in e['fields'])"
check "username <= 80 chars" "len(d['username']) <= 80"
check "embed total <= 6000 chars (title+description+fields)" \
	"len(e['title']) + len(e.get('description', '')) + sum(len(f['name']) + len(f['value']) for f in e['fields']) <= 6000"

dry_run NOTIFY_JOB="$thai" || fail "DRY_RUN exit code for long Thai title"
check "long Thai title stays valid and <= 256 chars" "len(e['title']) <= 256 and '�' not in e['title']"

# 6. Identity: valid and invalid username / avatar
dry_run NOTIFY_USERNAME='Tent "E2E" \ bot' NOTIFY_AVATAR_URL='https://example.com/a.png' || fail "DRY_RUN exit code for valid identity"
check "valid username and https avatar are kept" "d['username'] == 'Tent \"E2E\" \\\\ bot' and d['avatar_url'] == 'https://example.com/a.png'"

dry_run NOTIFY_USERNAME='my Discord bot' NOTIFY_AVATAR_URL='http://example.com/a.png' || fail "DRY_RUN exit code for invalid identity"
check "username containing 'discord' is dropped" "'username' not in d"
check "non-https avatar is dropped" "'avatar_url' not in d"
if grep -q 'discord-notify:' "$work/stderr.txt"; then pass "dropped identity warning on stderr"; else fail "dropped identity warning on stderr"; fi

# 7. Webhook URL handling (not DRY_RUN; a URL is only validated, never contacted)
rc=0
env -i PATH="$PATH" DISCORD_WEBHOOK_URL= bash "$script" >/dev/null 2>&1 || rc=$?
if ((rc == 0)); then pass "empty DISCORD_WEBHOOK_URL exits 0"; else fail "empty DISCORD_WEBHOOK_URL exits $rc (want 0)"; fi

rc=0
env -i PATH="$PATH" DISCORD_WEBHOOK_URL='https://example.invalid/x"y' bash "$script" >/dev/null 2>"$work/stderr.txt" || rc=$?
if ((rc == 1)); then pass "malformed DISCORD_WEBHOOK_URL exits 1"; else fail "malformed DISCORD_WEBHOOK_URL exits $rc (want 1)"; fi
if grep -q 'example.invalid' "$work/stderr.txt"; then fail "webhook URL leaked to stderr"; else pass "webhook URL not echoed on error"; fi

printf '\n%d failure(s)\n' "$fails"
((fails == 0))
