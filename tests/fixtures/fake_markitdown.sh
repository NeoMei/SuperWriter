#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  *.docx) output="${FAKE_MARKITDOWN_DOCX_OUTPUT:-${FAKE_MARKITDOWN_OUTPUT:-}}" ;;
  *.pdf) output="${FAKE_MARKITDOWN_PDF_OUTPUT:-${FAKE_MARKITDOWN_OUTPUT:-}}" ;;
  *) output="${FAKE_MARKITDOWN_OUTPUT:-}" ;;
esac

printf '%s\n' "${output:?fake markitdown output is required}"
