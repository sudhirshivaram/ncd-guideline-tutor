#!/bin/bash
set -euo pipefail
INDEX_DIR="${INDEX_DIR:-/app/indexes}"
export INDEX_DIR
if ! python -m app.rag.indexing --check; then
  echo "Index missing or invalid; rebuilding from WHO PDFs..."
  python -m app.rag.indexing
fi
python -m app.rag.indexing --check
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}"
