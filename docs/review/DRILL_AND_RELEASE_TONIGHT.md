# Tonight: drill → release → resume (operator steps)

Everything below is done by the operator on the Mac. Claude never sees passwords, codes or tokens.
Do not paste passwords, MFA codes, tokens or account numbers into chat.

## 0. After 16:30 ET — pause paper activity (main user)
Open http://127.0.0.1:8765/legacy#controls → **Pause**. (Keeps the system idle during the drill.)

## 1. Switch to the `robinhoodproxy` macOS user
Apple menu → your name → switch to **robinhoodproxy** (log in with its password in macOS).
Open **Terminal** there and run:

```sh
cd /Users/Shared/RobinhoodShadow/private/current/app
../python/bin/python3 -B -E -s -m broker_proxy.revocation begin
```
Expect a JSON line with `"status": "AWAITING_REMOTE_REVOKE"`.

## 2. Disconnect in Robinhood (you, personally)
In the Robinhood app/website: disconnect the **Agentic Trading** connection.

## 3. Prove the old access is dead
```sh
../python/bin/python3 -B -E -s -m broker_proxy.revocation verify-revoked
```
Expect `"status": "REMOTE_REJECTION_VERIFIED"`. **If anything else: stop and tell Claude.**

## 4. Remove the old local credentials
```sh
../python/bin/python3 -B -E -s -m broker_proxy.revocation remove-local-credentials
```
Expect `"status": "AWAITING_REAUTHORIZATION"`.

## 5. Re-authorize (you do the login/consent in the browser that opens)
```sh
../python/bin/python3 -B -E -s -m scripts.authorize_robinhood
```

## 6. Prove the new access works
```sh
../python/bin/python3 -B -E -s -m broker_proxy.revocation verify-reauthorized
```
Expect `"status": "COMPLETED"` with four timestamps. **Paste only that output line to Claude**
(it contains statuses/timestamps/config hashes — no token). Then switch back to your main user.

## 7. Release (only after Claude confirms the drill evidence and you say "go release")
Main user, Terminal:

```sh
cd ~/.codex/worktrees/robinhood-live-rehearsal && git fetch origin claude/continuation-2026-09-30 \
 && git switch --detach FETCH_HEAD && git log --oneline -1 \
 && /Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python scripts/release_install.py \
    --primary /Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent --source . \
    --manifest docs/review/release-2026-09-30-manifest.json
```
That is a **dry run**: it must print `"status": "VERIFIED"`. Then run the same last command
again with `--install` added. It prints `INSTALLED` (or `ROLLED_BACK` with the reason — then nothing changed).

## 7b. Add the 9 sector ETFs to your local config (only after step 7 printed INSTALLED)
Main user, Terminal. This makes a backup first and changes only the `instrument_whitelist` line:

```sh
P=/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent; cp -p $P/config/settings.local.yaml $P/config/settings.local.yaml.before-sector-etfs && $P/.venv/bin/python - <<'PY'
import re
p='/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/config/settings.local.yaml'
text=open(p).read(); add=['XLC','XLY','XLP','XLF','XLV','XLI','XLB','XLRE','XLK']
m=re.search(r'^(\s*instrument_whitelist:\s*\[)([^\]]*)(\])', text, re.M)
assert m, 'whitelist line not in [..] form: stop and tell Claude'
items=[x.strip() for x in m.group(2).split(',') if x.strip()]
items+= [x for x in add if x not in items]
open(p,'w').write(text[:m.start()]+m.group(1)+', '.join(items)+m.group(3)+text[m.end():])
print('whitelist', len(items))
PY
```
Expect `whitelist 23`. Remove the temporary rehearsal copy too: `rm $P/config/settings.rehearsal23.local.yaml`.

## 8. Resume before Thursday 10:00 ET
http://127.0.0.1:8765/legacy#controls → **Resume**. If left paused, Thursday's run will not happen.
Keep the Mac awake and plugged in 09:45–16:35 Thursday.
