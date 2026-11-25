# CI notifications (Discord)

The root `Jenkinsfile` posts one Discord embed when a `develop` (staging) or `main` (prod) build
finishes, from `post { always }` via `ci/discord-notify.sh`. Other branches stay quiet.
The script is copied from the tent project (`tent/ci/`); keep the two in sync.

## Setup

1. Discord: channel settings -> Integrations -> Webhooks -> New Webhook, copy the URL.
2. Jenkins: Manage Jenkins -> Credentials -> (global) -> Add Credentials
   - Kind: **Secret text**
   - Secret: the webhook URL
   - ID: `sindhu-discord-webhook-ci` (exact; the Jenkinsfile references it)

Notifications never fail a build: a missing credential, a missing script or a Discord outage only
logs a `WARNING`. If the build fails before the `mgmt` agent is allocated, `post` does not run and
nothing is sent.

The webhook URL is a secret: keep it only in the Jenkins credential store. On a suspected leak,
regenerate the webhook in Discord and update the credential.

## `ci/discord-notify.sh` env contract

Inputs are environment variables only. Bash only, no `jq`/`python3` needed.

| Variable | Required | Meaning |
| --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | yes (unless `DRY_RUN=1`) | Webhook URL; secret. Empty -> warning on stderr, exit 0 |
| `NOTIFY_KIND` | yes | `build` / `deploy` / `e2e` / `janitor` (selects the title label) |
| `NOTIFY_RESULT` | yes | `SUCCESS` / `FAILURE` / `UNSTABLE` / `ABORTED` / `NOT_BUILT` (emoji and colour) |
| `NOTIFY_JOB`, `NOTIFY_BUILD_NUMBER` | recommended | Shown in the title |
| `NOTIFY_BUILD_URL` | recommended | Embed title link |
| `NOTIFY_TARGET` | optional | `staging` / `prod`, appended to the title |
| `NOTIFY_BRANCH`, `NOTIFY_COMMIT`, `NOTIFY_DURATION`, `NOTIFY_E2E_RESULT` | optional | Embed fields |
| `NOTIFY_DETAIL` | optional | Embed description |
| `NOTIFY_USERNAME` | optional | Per-message webhook name (must not contain "discord") |
| `NOTIFY_AVATAR_URL` | optional | Per-message avatar, `https://` only |
| `DRY_RUN` | optional | `1` prints the JSON payload and sends nothing |

## Test locally

```bash
bash ci/test-discord-notify.sh

DRY_RUN=1 NOTIFY_KIND=deploy NOTIFY_TARGET=staging NOTIFY_RESULT=SUCCESS \
  NOTIFY_JOB=sindhu/develop NOTIFY_BUILD_NUMBER=42 NOTIFY_BRANCH=develop \
  ./ci/discord-notify.sh | python3 -m json.tool
```
