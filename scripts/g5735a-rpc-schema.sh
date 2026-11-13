#!/usr/bin/env bash
clear
set -u

# Manual read-only schema probe. It reports shapes only; scalar values are
# never printed. Do not run automatically from a service or test suite.
CLI="${GHOSTNODE_CLI_PATH:-ghost-cli}"
DATADIR="${GHOSTNODE_DATADIR:-$HOME/.ghost}"
BLOCK_HASH="${GHOSTNODE_PROBE_BLOCK_HASH:-0000000000000000000000000000000000000000000000000000000000000000}"
STAKE_TXID="${GHOSTNODE_PROBE_STAKE_TXID:-1111111111111111111111111111111111111111111111111111111111111111}"
WALLET_TXID="${GHOSTNODE_PROBE_WALLET_TXID:-3333333333333333333333333333333333333333333333333333333333333333}"
PREV_TXID="${GHOSTNODE_PROBE_PREV_TXID:-2222222222222222222222222222222222222222222222222222222222222222}"
STAKE_ADDRESS="${GHOSTNODE_STAKE_ADDRESS:-}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ghostnode-rpc-schema.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

classify_error() {
    local rc="$1" stderr="$2"
    (( rc == 0 )) && { printf 'SUCCESS'; return; }
    if grep -Eiq 'method not found|unknown command|unknown method' <<<"$stderr"; then printf 'METHOD_NOT_FOUND'
    elif grep -Eiq 'txindex|transaction index|index required' <<<"$stderr"; then printf 'INDEX_REQUIRED'
    elif grep -Eiq 'wallet|not loaded|invalid wallet' <<<"$stderr"; then printf 'WALLET_ERROR'
    elif grep -Eiq 'not found|unknown transaction|no such block' <<<"$stderr"; then printf 'NOT_FOUND'
    else printf 'ERROR'; fi
}

schema_report() {
    "${PYTHON:-python3}" - "$1" <<'PY'
import json, sys

def show(value, indent=0, name=None):
    pad = " " * indent
    label = f"{name}: " if name is not None else ""
    if value is None:
        print(f"{pad}{label}null")
    elif isinstance(value, bool):
        print(f"{pad}{label}boolean")
    elif isinstance(value, (int, float)):
        print(f"{pad}{label}number [REDACTED]")
    elif isinstance(value, str):
        print(f"{pad}{label}string [REDACTED]")
    elif isinstance(value, list):
        print(f"{pad}{label}array [{len(value)} items]")
        if value:
            show(value[0], indent + 2, "[]")
    elif isinstance(value, dict):
        print(f"{pad}{label}object")
        for key, item in value.items():
            show(item, indent + 2, str(key))

try:
    data = json.load(open(sys.argv[1]))
except Exception:
    print("response: INVALID_JSON")
else:
    show(data, 0, "response")
PY
}

semantic_report() {
    "${PYTHON:-python3}" - "$1" "$2" <<'PY'
import json, re, sys
method, path = sys.argv[1:]
raw = open(path, 'r', errors='replace').read()

def tri(value):
    if value is True: return "TRUE"
    if value is False: return "FALSE"
    if value is None: return "NULL"
    return "UNKNOWN"

if method == "gettxout" and not raw.strip():
    print("response: EMPTY_STDOUT")
    raise SystemExit
if method == "getrawtransaction" and not raw.strip().startswith(('{', '[', '"', 'null')):
    print("response: RAW_HEX" if re.fullmatch(r"[0-9a-fA-F\s]+", raw) and raw.strip() else "response: EMPTY" if not raw.strip() else "response: ERROR")
    raise SystemExit
try:
    data = json.loads(raw)
except Exception:
    print("response: NON_JSON")
    raise SystemExit

if method == "getaddressinfo":
    if not isinstance(data, dict):
        print("response: " + ("NULL" if data is None else "UNKNOWN"))
    else:
        for key in ("ismine", "solvable", "iswatchonly", "ischange"):
            print(f"{key}: {tri(data.get(key))}")
elif method == "gettxout":
    if data is None: print("response: NULL")
    elif isinstance(data, dict):
        print("response: OBJECT")
        for key, value in data.items():
            print(f"field: {key} ({type(value).__name__})")
    elif data == "": print("response: EMPTY_STDOUT")
    else: print("response: UNKNOWN")
elif method == "getrawtransaction":
    if data is None: print("response: NULL")
    elif isinstance(data, dict): print("response: JSON_OBJECT")
    else: print("response: ERROR")
elif method in ("getblock",):
    if not isinstance(data, dict):
        print("response: " + ("NULL" if data is None else "UNKNOWN")); raise SystemExit
    print("response: OBJECT")
    txs = data.get("tx") if isinstance(data.get("tx"), list) else []
    for ti, tx in enumerate(txs):
        if not isinstance(tx, dict): continue
        vouts = tx.get("vout") if isinstance(tx.get("vout"), list) else []
        for oi, output in enumerate(vouts):
            if not isinstance(output, dict): continue
            script = output.get("scriptPubKey") if isinstance(output.get("scriptPubKey"), dict) else {}
            print("vout[%d]: n=%s type=%s value=%s scriptPubKey=%s asm=%s addresses=%s stakeaddresses=%s treasury_fund_cfwd=%s gvrreward=%s" % (
                oi, output.get("n", "UNKNOWN"), output.get("type", "UNKNOWN"),
                "PRESENT" if "value" in output else "ABSENT",
                "PRESENT" if "scriptPubKey" in output else "ABSENT",
                "PRESENT" if "asm" in script else "ABSENT",
                "PRESENT" if "addresses" in script else "ABSENT",
                "PRESENT" if "stakeaddresses" in script else "ABSENT",
                "PRESENT" if "treasury_fund_cfwd" in output else "ABSENT",
                "PRESENT" if "gvrreward" in output else "ABSENT"))
else:
    def show(value, indent=0, name="response"):
        pad = " " * indent
        if value is None: print(f"{pad}{name}: null")
        elif isinstance(value, bool): print(f"{pad}{name}: boolean")
        elif isinstance(value, (int, float)): print(f"{pad}{name}: number [REDACTED]")
        elif isinstance(value, str): print(f"{pad}{name}: string [REDACTED]")
        elif isinstance(value, list):
            print(f"{pad}{name}: array [{len(value)} items]")
            if value: show(value[0], indent + 2, "[]")
        elif isinstance(value, dict):
            print(f"{pad}{name}: object")
            for key, item in value.items(): show(item, indent + 2, str(key))
    show(data)
PY
}

probe() {
    local label="$1" method="$2"; shift 2
    local out="$TMP_DIR/out" err="$TMP_DIR/err" rc state
    if timeout 15 "$CLI" "-datadir=$DATADIR" "$method" "$@" >"$out" 2>"$err"; then rc=0; else rc=$?; fi
    state="$(classify_error "$rc" "$(cat "$err")")"
    printf '%s:\n  status: %s\n  exit_code: %s\n' "$label" "$state" "$rc"
    if (( rc == 0 )); then semantic_report "$method" "$out" | sed 's/^/  /'; fi
}

[[ -x "$CLI" ]] || { echo 'RESULT=BLOCKED (ghost-cli is not executable)'; exit 2; }
echo 'Ghost Core sanitized RPC schema probe (read-only)'
[[ -n "$STAKE_TXID" && -n "$BLOCK_HASH" ]] && probe getrawtransaction_raw getrawtransaction "$STAKE_TXID" 0 "$BLOCK_HASH" || echo 'getrawtransaction_raw: NOT_CONFIGURED'
[[ -n "$STAKE_TXID" && -n "$BLOCK_HASH" ]] && probe getrawtransaction_verbose getrawtransaction "$STAKE_TXID" 1 "$BLOCK_HASH" || echo 'getrawtransaction_verbose: NOT_CONFIGURED'
probe gettransaction_wallet gettransaction "$WALLET_TXID"
[[ -n "$STAKE_TXID" ]] && probe gettransaction_coinstake gettransaction "$STAKE_TXID" || echo 'gettransaction_coinstake: NOT_CONFIGURED'
probe listtransactions listtransactions '*' 1 0
probe listunspent listunspent 1 9999999
if [[ -n "${GHOSTNODE_OWN_ADDRESS:-}" ]]; then
    probe getaddressinfo_own getaddressinfo "$GHOSTNODE_OWN_ADDRESS"
else
    echo 'getaddressinfo_own:'
    echo '  status: NOT_CONFIGURED'
fi
if [[ -n "${GHOSTNODE_FOREIGN_ADDRESS:-}" ]]; then
    probe getaddressinfo_foreign getaddressinfo "$GHOSTNODE_FOREIGN_ADDRESS"
else
    echo 'getaddressinfo_foreign:'
    echo '  status: NOT_CONFIGURED'
fi
[[ -n "$PREV_TXID" ]] && probe gettxout_available gettxout "$PREV_TXID" 2 true || echo 'gettxout_available: NOT_CONFIGURED'
[[ -n "$PREV_TXID" ]] && probe gettxout_spent gettxout "$PREV_TXID" 2 false || echo 'gettxout_spent: NOT_CONFIGURED'
[[ -n "$BLOCK_HASH" ]] && probe getblock getblock "$BLOCK_HASH" 2 true || echo 'getblock: NOT_CONFIGURED'
probe getblockreward getblockreward "${GHOSTNODE_PROBE_HEIGHT:-1}"
echo 'RESULT=COMPLETED (shape only; interpret statuses separately)'
