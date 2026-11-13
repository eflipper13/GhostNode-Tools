#!/usr/bin/env bash
clear
set -u

# Read-only production preflight. Run from an SSH session as etcmc.
PROJECT_DIR="${GHOSTNODE_PROJECT_DIR:-$(pwd)}"
CLI="${GHOSTNODE_CLI_PATH:-ghost-cli}"
DATADIR="${GHOSTNODE_DATADIR:-$HOME/.ghost}"
DB="${GHOSTNODE_INTELLIGENCE_DB:-$PROJECT_DIR/data/staking_intelligence.sqlite3}"
LOCK="${GHOSTNODE_INTELLIGENCE_LOCK:-$DB.lock}"
UNIT="ghostnode-intelligence-collector.service"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ghostnode-g57-preflight.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

pass=0
fail=0
unknown=0

report() {
    local state="$1" name="$2" detail="${3:-}"
    printf '%-7s %s' "$state" "$name"
    [[ -n "$detail" ]] && printf ' — %s' "$detail"
    printf '\n'
    case "$state" in
        PASS) pass=$((pass + 1)) ;;
        FAIL) fail=$((fail + 1)) ;;
        UNKNOWN) unknown=$((unknown + 1)) ;;
    esac
}

run_readonly() {
    "$@" 2>"$TMP_DIR/stderr"
}

systemd_state() {
    local unit="$1" value
    value="$(systemctl is-active "$unit" 2>"$TMP_DIR/stderr")"
    case "$value" in
        active) report PASS "systemd $unit" active ;;
        inactive)
            if [[ "$unit" == "$UNIT" ]]; then
                report PASS "systemd $unit" "inactive before controlled start"
            else
                report FAIL "systemd $unit" inactive
            fi
            ;;
        failed|deactivating|activating) report FAIL "systemd $unit" "$value" ;;
        *) report UNKNOWN "systemd $unit" "systemd/D-Bus unavailable" ;;
    esac
}

echo "GhostNode G5.7 production preflight"
echo "Project: $PROJECT_DIR"
echo

if [[ -x "$CLI" ]]; then report PASS "ghost-cli" "$CLI"; else report FAIL "ghost-cli" "not executable"; fi
if [[ -d "$DATADIR" ]]; then report PASS "Ghost datadir" "$DATADIR"; else report FAIL "Ghost datadir" "missing"; fi

systemd_state ghost.service
systemd_state "$UNIT"

show="$(systemctl show "$UNIT" -p UMask -p MainPID 2>"$TMP_DIR/stderr")"
if [[ $? -eq 0 ]]; then
    umask_value="$(printf '%s\n' "$show" | awk -F= '$1=="UMask"{print $2}')"
    main_pid="$(printf '%s\n' "$show" | awk -F= '$1=="MainPID"{print $2}')"
    [[ "$umask_value" == "0077" ]] && report PASS "collector UMask" "$umask_value" || report FAIL "collector UMask" "${umask_value:-missing}"
    report PASS "collector MainPID" "${main_pid:-0}"
else
    report UNKNOWN "collector UMask/MainPID" "systemd/D-Bus unavailable"
fi

if [[ -x "$CLI" ]]; then
    for method in getblockchaininfo getstakinginfo getnetworkinfo; do
        if timeout 10 "$CLI" "-datadir=$DATADIR" "$method" >"$TMP_DIR/$method.json" 2>"$TMP_DIR/stderr"; then
            report PASS "RPC $method"
        else
            report UNKNOWN "RPC $method" "unavailable from this session"
        fi
    done
else
    report UNKNOWN "RPC methods" "ghost-cli unavailable"
fi

collector_process=""
while read -r pid args; do
    [[ -z "${pid:-}" || "$pid" == "$$" || "$pid" == "${main_pid:-}" ]] && continue
    if [[ "$args" == *"-m ghostnode collector"* || "$args" =~ (^|[[:space:]/])ghostnode[[:space:]]+collector([[:space:]]|$) ]]; then
        collector_process="$pid"
        break
    fi
done < <(ps -eo pid=,args=)
if [[ -n "$collector_process" ]]; then
    report FAIL "collector processes" "active ghostnode collector PID $collector_process"
else
    report PASS "collector processes" "none detected"
fi

if [[ ! -e "$LOCK" ]]; then
    report PASS "collector lock holder" "lock file absent"
elif exec 9<"$LOCK" && flock -n 9; then
    flock -u 9
    exec 9<&-
    report PASS "collector lock holder" "no active holder"
else
    exec 9<&- 2>/dev/null || true
    report FAIL "collector lock holder" "active holder detected"
fi

if [[ ! -f "$DB" ]]; then
    report FAIL "SQLite database" "missing: $DB"
else
    if python3 - "$DB" <<'PY' >"$TMP_DIR/sqlite.txt" 2>"$TMP_DIR/sqlite.err"
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
print("integrity=" + str(con.execute("PRAGMA integrity_check").fetchone()[0]))
print("schema=" + str(con.execute("PRAGMA user_version").fetchone()[0]))
print("wal=" + str(con.execute("PRAGMA journal_mode").fetchone()[0]))
for table in ("staking_snapshots", "chain_blocks", "staking_rewards", "staking_events", "collector_runs", "chain_state"):
    print(table + "=" + str(con.execute("SELECT count(*) FROM " + table).fetchone()[0]))
row = con.execute("SELECT status, started_at, finished_at, error_code FROM collector_runs ORDER BY id DESC LIMIT 1").fetchone()
print("last_run=" + repr(row))
con.close()
PY
    then
        cat "$TMP_DIR/sqlite.txt"
        grep -q '^integrity=ok$' "$TMP_DIR/sqlite.txt" && report PASS "SQLite integrity" || report FAIL "SQLite integrity"
        grep -q '^schema=4$' "$TMP_DIR/sqlite.txt" && report PASS "SQLite schema" "v4" || report FAIL "SQLite schema"
        grep -q '^wal=wal$' "$TMP_DIR/sqlite.txt" && report PASS "SQLite WAL" || report FAIL "SQLite WAL"
    else
        report FAIL "SQLite read-only inspection" "schema or integrity query failed"
    fi
fi

if git -C "$PROJECT_DIR" rev-parse --verify HEAD >/dev/null 2>&1; then
    report PASS "Git HEAD" "$(git -C "$PROJECT_DIR" rev-parse --short HEAD)"
    report PASS "Git status" "$(git -C "$PROJECT_DIR" status --porcelain | wc -l | tr -d ' ') changed paths"
else
    report UNKNOWN "Git" "repository unavailable"
fi

echo
printf 'SUMMARY PASS=%s FAIL=%s UNKNOWN=%s\n' "$pass" "$fail" "$unknown"
if (( fail > 0 )); then
    echo 'RESULT=FAIL'
elif (( unknown > 0 )); then
    echo 'RESULT=UNKNOWN'
else
    echo 'RESULT=PASS'
fi
