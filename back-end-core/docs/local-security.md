# Local access and encrypted backups

F13 API, CLI and evaluation access integration is implemented. AccessSession gates
all private reads/writes with LOCKED; malformed unlock clears authorization/cache,
and CLIs retain and recheck their session. Frontend unlock/cache UI remains pending.
Argon2id protects the access gate; XChaCha20-Poly1305 encrypts backups, not SQLite.
Use only synthetic temporary databases during development. Do not run setup,
backup or restore against the user's live database as a development test.

Install from `back-end-core`: `python -m pip install '.[security]'`.
The optional extra pins `PyNaCl==1.6.2`. Unconfigured applications need no crypto
dependency. Configured authorization and all backup operations fail closed if
the dependency is missing. The `alpha-security` entry point is also available
as `python -m core.security_cli` without reinstalling the package.

## Integration contract

```python
from core.access import (
    AccessError, AccessSession, SessionAccess,
    authorize_database, check_authorized,
)

AccessSession(db_path: str | pathlib.Path)
SessionAccess = AccessSession
AccessSession.status(self) -> dict
AccessSession.unlock(self, password: str) -> dict
AccessSession.lock(self) -> dict
AccessSession.require(self) -> None
authorize_database(path: str | pathlib.Path) -> AccessSession
check_authorized(path: str | pathlib.Path, *, session: AccessSession | None = None) -> None

from core.security_cli import authorize_cli
authorize_cli(db_path: str | pathlib.Path) -> AccessSession  # Same CLI helper.

from core.access import setup_access, change_password
setup_access(db_path: str | pathlib.Path, password: str) -> pathlib.Path
change_password(db_path: str | pathlib.Path, old_password: str,
                new_password: str) -> pathlib.Path
from core.backup import create_backup, restore_backup
create_backup(db_path: str | pathlib.Path, output_path: str | pathlib.Path,
              password: str, *, session: AccessSession) -> pathlib.Path
restore_backup(backup_path: str | pathlib.Path, target_path: str | pathlib.Path,
               password: str, new_password: str) -> pathlib.Path
```

The first three session methods return exactly `{"configured": bool, "locked": bool}`.
Construction is initially locked for a configured database. `status()` reads only
the access config; it never opens, stats or initializes SQLite. A protected health
response before unlock must use this static status, with no store/model object,
database-derived statistics, excerpts, paths or existence probes. Malformed or
unreadable configs raise `AccessError`; integrations should report a safe locked
error, never fall back to legacy mode. A session that has observed configuration
also fails closed if its config disappears, even if previously unlocked. An absent
config for a new session returns false/false and
`require()` succeeds for legacy compatibility.

Call `require()` before constructing a store/model, before every sensitive read
or write, and before any database-backed health operation. Reads include source
text, excerpts, evidence, history, state, search, export, backup and evaluations.
Every method refreshes the bounded config; credential/config replacement revokes
an earlier unlock. `lock()` revokes the session; a failed unlock also revokes it.
Do not retain database-derived caches across lock/config changes or automatically
unlock on reconnect. A gate check is not an atomic lock around a database request;
integration must serialize requests and keep configuration changes offline.

`authorize_database()` / `authorize_cli()` are CLI-only helpers: return a session,
prompt once with getpass only when configured, reject non-TTY stdin and no-echo
fallback, and sanitize all authorization exceptions to `access authorization failed`.
After authentication, configured CLI paths must be existing regular nonempty DB
files before the helper returns, preventing implicit creation of a replacement
when the original is missing. This filesystem check belongs to the CLI helper,
not config-only session methods, and permits legitimate additive schema upgrades.
Call them before opening even a read-only evaluation database. They do not import
`core.api`. `check_authorized()` is noninteractive for libraries: absent config
permits access; configured access requires a caller-provided, matching unlocked
session. It refreshes and raises `AccessError` on denial. Do not route library/API
calls through an interactive helper or pass passwords via argv, environment,
logs, request diagnostics, fixtures containing real secrets, or saved config.

Passwords are strings of 1–1024 UTF-8 bytes, without trimming or normalization;
empty values, NUL and unpaired surrogates are rejected. Choose long unique
passwords; this bound is an input safety policy, not a strength estimate. Access
verifiers use PyNaCl Argon2id `str` and `verify`, with two passes and 64 MiB.
Verifiers are strictly bounded and checked before invoking Argon2id. Wrong
passwords and invalid unlock inputs return `authentication failed`, without details.
At most five attempts per database/backup path per rolling minute are allowed in
one process, shared across session objects. This is not a persistent or OS-wide
rate limiter; restarting a process resets it. A missing dependency is denied;
config-only status can still report locked without that dependency.

## Explicit offline setup and commands

Stop every desktop/backend/CLI database client before setup. The tool cannot
prove that all clients are stopped. Setup accepts only an existing absolute
valid Alpha database and exclusively creates `<dbpath>.access.json` with mode
0600. It never creates/migrates the DB, overwrites a config, or implicitly enables
the gate on application startup. There is no password reset or hidden key bypass.
An incomplete config write leaves a fail-closed config for explicit repair.

```sh
python -m core.security_cli status --db /absolute/synthetic.sqlite3
python -m core.security_cli setup --db /absolute/synthetic.sqlite3
python -m core.security_cli change-password --db /absolute/synthetic.sqlite3
python -m core.security_cli backup --db /absolute/synthetic.sqlite3 --output /absolute/new.alpha
python -m core.security_cli restore --backup /absolute/new.alpha --target /absolute/new-restored.sqlite3
```

Each new password is entered and confirmed through getpass. Backup uses a separate
password, not the access verifier; record it securely yourself. Restore always
requires a newly entered access password and generates a fresh salt/verifier.
It does not restore the old access config. Using the same password text is not
forbidden, but a new distinct password is recommended. Never auto-run setup
or restore at app startup, and never target a live database for restore.

Password rotation also requires stopped clients, the current password and a
confirmed new password. It requires an existing valid config and Alpha DB,
authenticates before DB access, writes/fsyncs a mode-0600 staged config, rechecks
the authenticated fingerprint immediately before atomic replacement, and fsyncs
the parent. Existing sessions revoke authorization on their next request. A
concurrent observed config change aborts rotation; this is not an OS-level CAS
against a hostile same-user race. If durability fails after replacement, the
new config may already be installed; inspect status and use the new password.

## Snapshot and format version 1

Backup opens SQLite using a `mode=ro` URI and `Connection.backup()` into a private
temporary snapshot; it never copies the main file. This includes committed WAL
transactions and excludes uncommitted changes. The snapshot is converted to
DELETE journal mode and validated before encryption. Read-only WAL access can
require SQLite's WAL/shared-memory support and filesystem permissions. Snapshot
copying has a 60 second deadline and 1 GiB page/size bound.

The fixed 68-byte big-endian header `>8sIIIQ16s24s` contains magic/version
`ALPHABK1`, Argon2id ops=2, memory=67108864, chunk size=65536, plaintext size,
random 16-byte salt, and random 24-byte secretstream header. No path, source text
or access verifier is included. The entire header is authenticated as additional
data on every XChaCha20-Poly1305 secretstream record. Each record is a four-byte
big-endian ciphertext length followed by ciphertext, exactly bounded by the
expected plaintext chunk plus 17 authentication bytes. Nonfinal records must
use `TAG_MESSAGE`; the last must use `TAG_FINAL`. Missing/early final tags,
truncation, reordering, tampering and trailing bytes are rejected. Unsupported
headers/KDF costs are rejected before allocation or derivation. Maximum plaintext
is 1 GiB; encrypted input is bounded to that size plus record/header overhead.
There is no compression or unbounded JSON metadata.

Backup output is a new exclusive mode-0600 file. Existing files and symlinks are
never replaced. Snapshot plaintext lives in a mode-0700 temporary directory,
with mode-0600 files; normal failure and success remove temporary data and failed
outputs. Different backups use independent salts and stream headers.

## Fresh-target restore and limits

All operational paths must be absolute with existing parents and no symlink
components. Restore refuses existing targets, target configs and SQLite sidecars.
It decrypts into a mode-0700 directory on the target filesystem, checks stream
completion, SQLite integrity, foreign keys, current Alpha table columns/types/
primary keys and foreign-key declarations, and compares exact table/index/trigger
DDL against the production schema (including consent triggers). Extra or missing
objects and views are rejected. All input checks, including baseline metadata,
run inside one read snapshot transaction. Standalone legacy MemoryStore databases are supported. Model
databases must match the current schema and baseline fingerprint; the existing
read-only reset verifier is reused. Expected schemas are obtained from actual
production initializers in a separate throwaway database; the input is never
migrated, reset or trained. Schema recognition is not an adversarial SQLite
sandbox or a validation of the psychological meaning of stored values.

After validation, restore publishes its fsynced fresh config first, fsyncs the
parent, then publishes the fsynced DB with exclusive hard links and fsyncs again.
This requires a local POSIX filesystem supporting permissions, hard links and
directory fsync. It never overwrites either target. Caught publication failures
remove the database before removing the config; if DB removal fails, its gate is
retained. A crash during publication can leave a config without a DB, which needs
explicit cleanup before retry; it cannot publish a DB ahead of its gate.

These guarantees assume an ordinary functioning local filesystem and no hostile
same-user manipulation during operations. The same OS user can read plaintext
SQLite, edit/delete the config, substitute paths, or invoke ungated code. Removing
the config permits legacy mode in a fresh session/process; previously configured
sessions deny access after removal. Permissions alone are not encryption;
The sidecar is bound to the selected pathname, not cryptographically to the DB
file or its identity. API construction must separately reject a missing/empty
configured DB after unlocking; session methods deliberately never touch the DB.
the application gate is not an OS security boundary. Use full-disk encryption and
OS account separation when needed. Python cannot promise credential/key memory
erasure. Swap, snapshots and crash leftovers can preserve plaintext; abrupt
termination may leave a private staging directory. Cleanup is not secure erasure.
Forgotten backup passwords have no recovery backdoor. No existing private DB was
used in implementation or tests.

Primary API sources: [PyNaCl password hashing](https://pynacl.readthedocs.io/en/latest/api/pwhash/),
[libsodium secretstream](https://doc.libsodium.org/secret-key_cryptography/secretstream),
[SQLite online backup](https://www.sqlite.org/backup.html).

Verification: `python -m unittest tests.test_security -v` from `back-end-core`.
All fixtures are synthetic and use temporary paths. API-wide locked coverage and
protected evaluation snapshots are implemented and tested; frontend unlock/cache
UI and physical native acceptance remain pending. SQLite and same-OS-user limits
above still apply.
