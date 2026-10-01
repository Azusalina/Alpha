"""Standalone offline administration; passwords enter exclusively via getpass."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import warnings
from pathlib import Path

from .access import AccessError, AccessSession, authorize_database, change_password, setup_access
from .backup import BackupError, create_backup, restore_backup, validate_database


def _prompt(label: str) -> str:
    # Never allow getpass's fallback to echoed stdin (including redirected input).
    if not sys.stdin.isatty():
        raise AccessError("a secure interactive password prompt is required")
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            return getpass.getpass(label)
        except (getpass.GetPassWarning, EOFError):
            raise AccessError("a secure interactive password prompt is required") from None


def _new_password(label: str) -> str:
    first = _prompt(label)
    if first != _prompt('Confirm password: '):
        raise AccessError("password confirmation failed")
    return first


def authorize_cli(db_path: str | Path) -> AccessSession:
    """Prompt once only if configured; callers require() before each operation."""
    return authorize_database(db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description='Alpha local access and encrypted backups')
    actions = parser.add_subparsers(dest='action', required=True)
    status = actions.add_parser('status', help='config-only status; no database reads')
    status.add_argument('--db', required=True, type=Path)
    setup = actions.add_parser('setup', help='offline setup; stop all database clients first')
    setup.add_argument('--db', required=True, type=Path)
    rotate = actions.add_parser('change-password', help='authenticated offline password rotation')
    rotate.add_argument('--db', required=True, type=Path)
    backup = actions.add_parser('backup')
    backup.add_argument('--db', required=True, type=Path)
    backup.add_argument('--output', required=True, type=Path)
    restore = actions.add_parser('restore')
    restore.add_argument('--backup', required=True, type=Path)
    restore.add_argument('--target', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'status':
            result = AccessSession(args.db).status()
        elif args.action == 'setup':
            validate_database(args.db)
            result = {'access_config': str(setup_access(args.db, _new_password('New access password: ')))}
        elif args.action == 'backup':
            session = authorize_cli(args.db)
            result = {'backup': str(create_backup(args.db, args.output,
                                     _new_password('Backup password: '), session=session))}
        elif args.action == 'change-password':
            old_password = _prompt('Current access password: ')
            result = {'access_config': str(change_password(args.db, old_password,
                                           _new_password('New access password: ')))}
        else:
            password = _prompt('Backup password: ')
            result = {'database': str(restore_backup(args.backup, args.target, password,
                                     _new_password('New restored access password: ')))}
    except (AccessError, BackupError) as error:
        parser.exit(2, f'{error}\n')
    except (OSError, KeyboardInterrupt):
        parser.exit(2, 'security operation failed\n')
    json.dump(result, sys.stdout)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
