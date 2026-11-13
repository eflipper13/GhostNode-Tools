# Ghost Core detection and guided setup

## `ghostnode doctor`

Run the diagnostic assistant from the isolated project environment:

```bash
./bin/ghostnode doctor --json
```

The command performs only bounded read-only checks. It reports:

- operating system and architecture;
- configured Ghost CLI availability;
- local data-directory availability or remote endpoint configuration;
- `getblockchaininfo`, `getnetworkinfo`, and `getstakinginfo` access;
- detected Ghost Core version;
- expected network mode;
- synchronization state;
- reported staking state;
- whether the configured user completed the read-only preflight.

Each check is `PASS`, `WARN`, `FAIL`, or `SKIP`. RPC errors are reduced to safe
general messages; credentials, cookies, addresses, balances, and transaction
history are not printed.

For a remote node, configure endpoint routing without putting credentials in
the command line:

```bash
GHOSTNODE_RPC_HOST=node.example GHOSTNODE_RPC_PORT=51725 \
  ./bin/ghostnode doctor --json
```

Protect the Ghost Core authentication mechanism separately. Application-level
read-only restrictions do not reduce broader privileges of the underlying
Ghost Core credentials.

## `ghostnode setup`

The setup assistant is deliberately a dry run:

```bash
./bin/ghostnode setup --json
```

It detects the platform, reports local CLI and data-directory availability,
explains local versus remote operation, and prints safe planning guidance. It
does not download or execute installers, write Ghost Core configuration, create
directories in production paths, change permissions, modify services, or touch
wallets.

Official Ghost Core distribution sources, checksums, and signatures must be
verified from official sources by the operator before any separate installation
work. When that verification is not available, setup reports the limitation
instead of generating an executable installation command.

## Wallet readiness and setup guidance

Check wallet readiness without changing wallet state:

```bash
./bin/ghostnode wallet status --json
```

The report distinguishes `WALLET_NOT_LOADED`, `WALLET_READY`,
`STAKING_MONITORING_READY`, `NODE_ONLY_READY`, and
`WALLET_STATUS_UNKNOWN`. It also reports a wallet path only when local
filesystem metadata identifies one unambiguously; remote nodes and unknown or
unsupported layouts report `WALLET_PATH_UNKNOWN`. The tool never opens a
wallet database. Node-only monitoring can remain ready when the
configured wallet is not loaded. A wallet RPC error is not treated as proof
that a wallet is absent.

For safe planning guidance:

```bash
./bin/ghostnode wallet setup --json
```

This command describes three supported modes: create a wallet using official
Ghost Core procedures, use an existing wallet, or continue without a wallet.
It does not generate a wallet command because the exact Ghost Core creation
syntax is not verified by this project. Encrypt wallets and create and verify
backups using Ghost Core's official procedures. Keep backups outside the
application directory and never provide private keys, recovery phrases,
passwords, cookies, or RPC credentials to GhostNode Tools.

The setup report includes backup, encryption, passphrase, and recovery
guidance. It does not copy or verify backups. `GUIDANCE_REVIEWED` means only
that the instructions were displayed; `BACKUP_REPORTED_BY_USER` and
`BACKUP_VERIFIED` are not claimed automatically. Keep passphrases separate
from backups, and never overwrite an existing wallet during recovery. A lost
encryption passphrase is not guaranteed recoverable.

Keep the dashboard on `127.0.0.1` and use an SSH tunnel for authorized remote
viewing. Never expose Ghost Core RPC directly to the public Internet.
