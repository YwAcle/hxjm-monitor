"""Offline configuration and journal validation. Never contacts an API or starts work."""
import argparse
import ast
import json
import os
from pathlib import Path
import sys

from .persistence_config import PersistenceConfig


def check_journal(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('Spool directory does not exist; nothing was created')
    count = 0
    for directory in ('pending', 'state'):
        for path in (root / directory).glob('*.json'):
            value = json.loads(path.read_text())
            if not isinstance(value, dict):
                raise ValueError('Journal entry must be an object')
            if directory == 'pending' and not {'lane', 'kind', 'payload', 'queued_at'} <= set(value):
                raise ValueError('Invalid pending journal envelope')
            count += 1
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', action='store_true', help='validate enabled config from environment; no network')
    parser.add_argument('--journal', metavar='DIRECTORY', help='read JSON journal without acquiring ownership or changing it')
    args = parser.parse_args(argv)
    for path in Path(__file__).parent.glob('*.py'):
        ast.parse(path.read_text(), filename=str(path), feature_version=(3, 9))
    print('Python 3.9 syntax: PASS')
    if args.config:
        config = PersistenceConfig()
        if not config.enabled:
            raise ValueError('Persistence is disabled; enable it in this shell to validate the complete configuration')
        # Constructing the client only validates its address; it never calls the opener.
        from .tracking_client import BusinessClient
        BusinessClient(config.business_base_url, config.service_id, config.service_token, config.timeout)
        print('Persistence configuration: PASS (no API or database contacted)')
    if args.journal:
        print('Journal JSON: PASS (%d files; read only)' % check_journal(args.journal))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, SyntaxError):
        print('Offline validation failed; check configuration fields, source UUIDs and journal JSON. No credentials were printed.', file=sys.stderr)
        sys.exit(1)
