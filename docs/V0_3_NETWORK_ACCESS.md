# GhostNode Tools v0.3.0 network access

The dashboard is localhost-only by default:

```text
127.0.0.1:44678
```

The optional `localhost_lan` mode adds exactly one assigned private IPv4
address. It never binds `0.0.0.0`, `[::]`, wildcard addresses, or an address
that is not currently assigned to a local interface.

## LAN security

LAN mode defaults to `token_required`, using a bearer token supplied through a
private token file. There is no default password and GhostNode Tools never
generates, prints, or commits the token. An explicitly selected `trusted_lan`
mode allows direct unauthenticated read-only dashboard/API access to every
client able to reach the configured LAN address; state-changing and
configuration endpoints remain token-protected. A specific LAN bind is not an
authentication boundary. Plain HTTP does not provide confidentiality or
integrity against a hostile LAN; use an appropriately secured HTTPS layer or
an SSH tunnel when that matters.

Example private environment settings:

```text
GHOSTNODE_DASHBOARD_MODE=localhost_lan
GHOSTNODE_DASHBOARD_LAN_ADDRESS=192.168.1.100
GHOSTNODE_DASHBOARD_PORT=44678
GHOSTNODE_DASHBOARD_LAN_AUTH_MODE=token_required
GHOSTNODE_DASHBOARD_TOKEN_FILE=/private/path/ghostnode-dashboard.token
```

The token file should be owned by the service account and mode `0600`.

## First-run review

`ghostnode init --json --network-mode localhost_lan --lan-address 192.168.1.100 --lan-auth-mode token_required`
prints a proposed configuration. It does not apply it. Applying settings
requires the explicit pair `--apply-network --confirm-network` and writes only
the private non-secret configuration atomically. The dashboard's network
settings endpoint is read-only; its POST endpoint validates proposals but does
not write files or restart services.

For an explicitly reviewed trusted-LAN deployment, use
`--lan-auth-mode trusted_lan`. This does not protect read-only dashboard data
from other reachable LAN clients; keep the mode limited to a trusted network.

Always preserve the previous working configuration, test both listeners, and
keep the existing SSH tunnel or proxy until the replacement is verified.
