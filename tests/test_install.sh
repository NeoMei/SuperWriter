#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
python3 -m unittest tests.test_installer_portable tests.test_install_interruptions -v
echo "PASS: native installer is path-safe, marker-safe, and transactional across all hosts and routes"
