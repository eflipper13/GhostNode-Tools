from ghostnode.intelligence.db import IntelligenceDB
from ghostnode.intelligence.rewards import (DataCompleteness, RewardStatus, identify_reward, reconcile_wallet,
                                            track_reward, refresh_reward_lifecycle, financial_summary,
                                            maturity_depth_from_core)


def test_attribute_reward_separates_principal_and_reward():
    from ghostnode.intelligence.rewards import attribute_reward
    result = attribute_reward(
        [{"prev_txid": "prev", "prev_vout": 0, "value": "10.0"}],
        [{"vout": 0, "value": "10.0", "output_class": "principal", "owner_verified": True},
         {"vout": 1, "value": "0.5", "output_class": "wallet_reward", "owner_verified": True}],
    )
    assert result.input_value_atomic == 1_000_000_000
    assert result.principal_return_atomic == 1_000_000_000
    assert result.wallet_reward_atomic == 50_000_000
    assert result.completeness == DataCompleteness.COMPLETE


def test_attribute_reward_is_partial_without_prevout_or_ownership():
    from ghostnode.intelligence.rewards import attribute_reward
    missing_input = attribute_reward([{"prev_txid": "prev", "prev_vout": 0}], [])
    assert missing_input.completeness == DataCompleteness.UNKNOWN
    unknown_owner = attribute_reward([{"value": 10}], [{"value": 10, "output_class": "principal"}])
    assert unknown_owner.wallet_reward_atomic is None
    assert unknown_owner.completeness == DataCompleteness.PARTIAL


def block(**extra):
    value = {"blockhash": "block-1", "height": 100, "coinstake": "tx-1",
             "stakereward": "2.00000000", "blockreward": "1.50000000",
             "treasuryreward": "0.50000000", "gvrreward": "0.10000000"}
    value.update(extra)
    return value


def entry(**extra):
    value = {"txid": "tx-1", "blockhash": "block-1", "category": "stake",
             "amount": "1.50000000", "reward": "1.50000000", "vout": 1,
             "confirmations": 10}
    value.update(extra)
    return value


def test_identifies_matured_wallet_reward():
    match = identify_reward(block(), [entry(confirmations=100)], 100)
    assert match is not None
    assert match.wallet_reward_atomic == 150000000
    assert match.status is RewardStatus.MATURED
    assert match.owner_verified
    assert match.completeness is DataCompleteness.COMPLETE


def test_wallet_reward_can_be_matured_with_partial_block_economics():
    match = identify_reward(block().copy(), [entry(confirmations=100)], 100)
    assert match.status is RewardStatus.MATURED
    assert match.completeness is DataCompleteness.COMPLETE
    partial = block(blockreward=None)
    match = identify_reward(partial, [entry(confirmations=100)], 100)
    assert match.status is RewardStatus.MATURED
    assert match.completeness is DataCompleteness.PARTIAL


def test_immature_or_orphaned_and_spent_states():
    assert identify_reward(block(), [entry(confirmations=2)], 100).status is RewardStatus.IMMATURE
    assert identify_reward(block(), [entry(category="orphaned_stake")], 100).status is RewardStatus.ORPHANED
    assert identify_reward(block(), [entry(spent=True)], 100).status is RewardStatus.SPENT


def test_unknown_for_ambiguous_or_incomplete_data():
    assert identify_reward(block(), [entry(), entry(vout=2)], 100) is None
    assert identify_reward({"blockhash": "block-1", "height": 100}, [entry()], 100) is None
    assert identify_reward(block(), [entry(reward="not-a-number")], 100) is None
    assert identify_reward(block(), [entry(confirmations=1)], None).status is RewardStatus.UNVERIFIED


def test_track_reward_is_idempotent_and_keeps_components(tmp_path):
    db = IntelligenceDB(tmp_path / "rewards.sqlite3")
    assert track_reward(db, block(), [entry(confirmations=100)], maturity_depth=100) is RewardStatus.MATURED
    assert track_reward(db, block(), [entry(confirmations=100)], maturity_depth=100) is RewardStatus.MATURED
    row = db.connection.execute("SELECT * FROM staking_rewards").fetchone()
    assert db.connection.execute("SELECT count(*) FROM staking_rewards").fetchone()[0] == 1
    assert row["vout"] == 1
    assert row["wallet_reward_atomic"] == 150000000
    assert row["stake_reward_atomic"] == 200000000
    assert row["treasury_reward_atomic"] == 50000000


def test_v2_attribution_is_integrated_atomically(tmp_path):
    db = IntelligenceDB(tmp_path / "v2.sqlite3")
    value = block(reward_inputs=[{"prev_txid": "prev", "prev_vout": 0, "value": "10.0",
                                 "owner_verified": True}],
                  reward_outputs=[{"vout": 0, "value": "10.0", "output_class": "principal",
                                   "owner_verified": True},
                                  {"vout": 1, "value": "0.5", "output_class": "wallet_reward",
                                   "owner_verified": True}])
    assert track_reward(db, value, [entry(reward="0.5", amount="0.5", confirmations=100)], maturity_depth=100) is RewardStatus.MATURED
    row = db.connection.execute("SELECT wallet_reward_atomic,data_completeness FROM staking_rewards").fetchone()
    assert row[0] == 50000000 and row[1] == "COMPLETE"
    assert db.connection.execute("SELECT count(*) FROM reward_inputs").fetchone()[0] == 1
    assert db.connection.execute("SELECT count(*) FROM reward_outputs").fetchone()[0] == 2
    assert db.connection.execute("SELECT count(*) FROM reward_evidence").fetchone()[0] == 1
    track_reward(db, value, [entry(reward="0.5", amount="0.5", confirmations=100)], maturity_depth=100)
    assert db.connection.execute("SELECT count(*) FROM reward_inputs").fetchone()[0] == 1


def test_v2_partial_attribution_is_not_confirmed_income(tmp_path):
    db = IntelligenceDB(tmp_path / "partial.sqlite3")
    value = block(reward_inputs=[{"prev_txid": "prev", "prev_vout": 0}],
                  reward_outputs=[{"vout": 1, "value": "0.5", "output_class": "reward"}])
    assert track_reward(db, value, [entry(reward="0.5", amount="0.5", confirmations=100)], maturity_depth=100) is RewardStatus.UNVERIFIED
    row = db.connection.execute("SELECT wallet_reward_atomic,status,data_completeness FROM staking_rewards").fetchone()
    assert row[0] is None and row[1] == "UNVERIFIED" and row[2] == "PARTIAL"


def test_unknown_class_never_becomes_reward_even_with_wallet_proof():
    from ghostnode.intelligence.rewards import attribute_reward
    result = attribute_reward(
        [{"prev_txid": "p", "prev_vout": 0, "value": "10"}],
        [{"vout": 0, "value": "0.5", "output_class": "unknown", "owner_verified": True}],
    )
    assert result.wallet_reward_atomic is None
    assert result.completeness is DataCompleteness.PARTIAL


def test_duplicate_prevout_cannot_inflate_attribution():
    from ghostnode.intelligence.rewards import attribute_reward
    result = attribute_reward(
        [{"prev_txid": "p", "prev_vout": 0, "value": "10"},
         {"prev_txid": "p", "prev_vout": 0, "value": "10"}],
        [{"vout": 0, "value": "1", "output_class": "wallet_reward", "owner_verified": True}],
    )
    assert result.wallet_reward_atomic is None
    assert result.completeness is DataCompleteness.PARTIAL


def test_financial_summary_requires_complete_positive_matured_reward(tmp_path):
    db = IntelligenceDB(tmp_path / "financial.sqlite3")
    for index, completeness, status, amount in (
        (1, "COMPLETE", "MATURED", 100),
        (2, "PARTIAL", "MATURED", 200),
        (3, "UNKNOWN", "MATURED", 300),
        (4, "COMPLETE", "MATURED", None),
        (5, "COMPLETE", "MATURED", 0),
        (6, "COMPLETE", "ORPHANED", 400),
    ):
        db.connection.execute(
            "INSERT INTO staking_events(event_key,network,event_type,status,detected_at) VALUES(?,?,?,?,?)",
            (f"e{index}", "main", "staking_reward", status, "now"),
        )
        event_id = db.connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.connection.execute(
            """INSERT INTO staking_rewards(event_id,network,block_hash,coinstake_txid,wallet_name,
               wallet_reward_atomic,spent_status,status,data_completeness,source_rpc,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, "main", f"b{index}", f"t{index}", "ghostmain", amount,
             "UNKNOWN", status, completeness, "fixture", "now", "now"),
        )
    db.connection.commit()
    assert financial_summary(db)["confirmed"] == 100


def test_reconciliation_warns_without_claiming_balance_is_history(tmp_path):
    db = IntelligenceDB(tmp_path / "rewards.sqlite3")
    assert reconcile_wallet(db, [], None).startswith("RECONCILIATION_WARNING")


def test_schema_migration_adds_vout_and_history(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE staking_events (id INTEGER PRIMARY KEY, event_key TEXT UNIQUE, network TEXT,
      event_type TEXT, block_hash TEXT, height INTEGER, txid TEXT, wallet_name TEXT,
      status TEXT, detected_at TEXT, confirmed_at TEXT, orphaned_at TEXT, metadata_json TEXT);
    CREATE TABLE staking_rewards (id INTEGER PRIMARY KEY, event_id INTEGER UNIQUE, network TEXT,
      block_hash TEXT, coinstake_txid TEXT, wallet_name TEXT, wallet_reward_atomic INTEGER,
      stake_reward_atomic INTEGER, block_reward_atomic INTEGER, treasury_reward_atomic INTEGER,
      gvr_reward_atomic INTEGER, maturity_height INTEGER, matured_at TEXT, spent_status TEXT,
      source_rpc TEXT, created_at TEXT, updated_at TEXT);
    PRAGMA user_version = 1;
    """)
    conn.close()
    db = IntelligenceDB(path)
    columns = {row[1] for row in db.connection.execute("PRAGMA table_info(staking_rewards)")}
    assert {"vout", "status", "data_completeness"} <= columns
    assert db.connection.execute("PRAGMA user_version").fetchone()[0] == 6
    assert (tmp_path / "old.sqlite3.pre-v6").exists()


def test_interrupted_migration_rolls_back_and_can_retry(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE staking_events (id INTEGER PRIMARY KEY, event_key TEXT UNIQUE, network TEXT,
      event_type TEXT, block_hash TEXT, height INTEGER, txid TEXT, wallet_name TEXT,
      status TEXT, detected_at TEXT, confirmed_at TEXT, orphaned_at TEXT, metadata_json TEXT);
    CREATE TABLE staking_rewards (id INTEGER PRIMARY KEY, event_id INTEGER UNIQUE, network TEXT,
      block_hash TEXT, coinstake_txid TEXT, wallet_name TEXT, wallet_reward_atomic INTEGER,
      stake_reward_atomic INTEGER, block_reward_atomic INTEGER, treasury_reward_atomic INTEGER,
      gvr_reward_atomic INTEGER, maturity_height INTEGER, matured_at TEXT, spent_status TEXT,
      source_rpc TEXT, created_at TEXT, updated_at TEXT);
    INSERT INTO staking_rewards(event_id,network,block_hash,wallet_name,spent_status,source_rpc,created_at,updated_at)
      VALUES(1,'main','b','ghostmain','UNKNOWN','fixture','now','now');
    PRAGMA user_version = 1;
    """)
    conn.close()
    try:
        IntelligenceDB(path, migration_hook=lambda step: (_ for _ in ()).throw(RuntimeError(step)))
    except RuntimeError:
        pass
    with IntelligenceDB(path) as db:
        assert db.connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert db.connection.execute("SELECT count(*) FROM staking_rewards").fetchone()[0] == 1
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_lifecycle_updates_only_immature_and_financial_summary(tmp_path):
    db = IntelligenceDB(tmp_path / "rewards.sqlite3")
    assert maturity_depth_from_core() == 100
    assert track_reward(db, block(), [entry(confirmations=2)], maturity_depth=100) is RewardStatus.IMMATURE
    assert refresh_reward_lifecycle(db, 199) == 0
    assert refresh_reward_lifecycle(db, 200) == 1
    assert financial_summary(db) == {"confirmed": 150000000, "pending": 0, "orphaned": 0, "spent": 0, "unverified": 0}
    assert refresh_reward_lifecycle(db, 999) == 0


def test_orphaned_reward_never_matures(tmp_path):
    db = IntelligenceDB(tmp_path / "rewards.sqlite3")
    assert track_reward(db, block(), [entry(category="orphaned_stake")], maturity_depth=100) is RewardStatus.ORPHANED
    assert refresh_reward_lifecycle(db, 999) == 0
    assert financial_summary(db)["orphaned"] == 150000000
