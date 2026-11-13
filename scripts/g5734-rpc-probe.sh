#!/usr/bin/env bash
clear
set -u

# Manual, read-only Ghost RPC capability probe. This script is intentionally
# not run by tests or services; execute it only from the intended SSH session.
CLI="${GHOSTNODE_CLI_PATH:-ghost-cli}"
DATADIR="${GHOSTNODE_DATADIR:-$HOME/.ghost}"
BLOCK_HASH="${GHOSTNODE_PROBE_BLOCK_HASH:-0000000000000000000000000000000000000000000000000000000000000000}"
STAKE_TXID="${GHOSTNODE_PROBE_STAKE_TXID:-1111111111111111111111111111111111111111111111111111111111111111}"
PREV_TXID="${GHOSTNODE_PROBE_PREV_TXID:-2222222222222222222222222222222222222222222222222222222222222222}"
STAKE_ADDRESS="${GHOSTNODE_STAKE_ADDRESS:-}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ghostnode-rpc-probe.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

classify_error() {
    local rc="$1" stderr="$2"
    if (( rc == 0 )); then
        printf 'SUCCESS'
    elif grep -Eiq 'method not found|unknown command|unknown method|not available' <<<"$stderr"; then
        printf 'METHOD_NOT_FOUND'
    elif grep -Eiq 'txindex|transaction index|index required' <<<"$stderr"; then
        printf 'INDEX_REQUIRED'
    elif grep -Eiq 'wallet|no such|not loaded|invalid wallet' <<<"$stderr"; then
        printf 'WALLET_ERROR'
    elif grep -Eiq 'not found|unknown transaction|no such block|not available' <<<"$stderr"; then
        printf 'NOT_FOUND'
    else
        printf 'ERROR'
    fi
}

probe() {
    local label="$1" method="$2"; shift 2
    local out="$TMP_DIR/out" err="$TMP_DIR/err" rc state
    if timeout 15 "$CLI" "-datadir=$DATADIR" "$method" "$@" >"$out" 2>"$err"; then
        rc=0
    else
        rc=$?
    fi
    state="$(classify_error "$rc" "$(cat "$err")")"
    printf '%-24s %-18s exit=%s\n' "$label" "$state" "$rc"
    # Deliberately report no response payload: wallet RPC responses can contain
    # addresses, amounts, txids, or other private information.
}

printf 'Ghost Core RPC capability probe (read-only)\n'
printf 'CLI: %s\nDatadir: %s\n\n' "$CLI" "$DATADIR"
if [[ ! -x "$CLI" ]]; then
    echo 'RESULT=BLOCKED (ghost-cli is not executable)'
    exit 2
fi

[[ -n "$STAKE_TXID" && -n "$BLOCK_HASH" ]] && probe getrawtransaction getrawtransaction "$STAKE_TXID" 1 "$BLOCK_HASH" || echo 'getrawtransaction: NOT_CONFIGURED'
probe gettransaction gettransaction "$STAKE_TXID"
probe listtransactions listtransactions '*' 1 0
probe listunspent listunspent 1 9999999
if [[ -n "$STAKE_ADDRESS" ]]; then probe getaddressinfo getaddressinfo "$STAKE_ADDRESS"; else echo 'getaddressinfo: NOT_CONFIGURED'; fi
[[ -n "$PREV_TXID" ]] && probe gettxout gettxout "$PREV_TXID" 2 true || echo 'gettxout: NOT_CONFIGURED'
[[ -n "$BLOCK_HASH" ]] && probe getblock getblock "$BLOCK_HASH" 2 true || echo 'getblock: NOT_CONFIGURED'
probe getblockhash getblockhash "${GHOSTNODE_PROBE_HEIGHT:-1}"
probe getblockreward getblockreward "${GHOSTNODE_PROBE_HEIGHT:-1}"

echo
echo 'RESULT=COMPLETED (interpret each method status separately)'
