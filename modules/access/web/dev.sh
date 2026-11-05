#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$SCRIPT_DIR/.node/bin:$PATH"
node "$SCRIPT_DIR/node_modules/.bin/vite" "$@"
