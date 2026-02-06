#!/usr/bin/env bash
# One-time setup script for the sem-mem MCP server.
# Usage: bash scripts/setup.sh
# Safe to run multiple times (idempotent).
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { printf "${GREEN}[OK]${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC} %s\n" "$1"; }
error() { printf "${RED}[ERROR]${NC} %s\n" "$1"; }

# 1. Check for uv, install if missing
if command -v uv &>/dev/null; then
  info "uv is already installed ($(uv --version))"
else
  warn "uv not found -- installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  info "uv installed ($(uv --version))"
fi

# 2. Install the sem-mem package
if uv tool list 2>/dev/null | grep -q '^sem-mem '; then
  info "sem-mem is already installed"
else
  echo "Installing sem-mem..."
  uv tool install sem-mem
  info "sem-mem installed"
fi

# 3. Create default DB directory
DB_DIR="$HOME/.claude/sem-mem"
mkdir -p "$DB_DIR"
info "Database directory ready: $DB_DIR"

# 4. Check required environment variables
MISSING=0
for var in OPENAI_API_KEY ANTHROPIC_API_KEY; do
  if [[ -z "${!var:-}" ]]; then
    warn "Environment variable $var is not set (required for default providers)"
    MISSING=1
  else
    info "$var is set"
  fi
done

if [[ "$MISSING" -eq 1 ]]; then
  echo ""
  warn "You can skip OPENAI_API_KEY / ANTHROPIC_API_KEY if using Bedrock providers:"
  echo "  export EMBEDDING_PROVIDER=bedrock"
  echo "  export LLM_PROVIDER=bedrock"
  echo "  export AWS_PROFILE=<your-profile>"
fi

# 5. Summary
echo ""
echo "========================================="
echo " sem-mem setup complete"
echo "========================================="
echo ""
echo "Run the MCP server:"
echo "  uv tool run sem-mem"
echo ""
echo "Or install as a Claude Code plugin:"
echo "  claude plugin install sem-mem@brainspace"
echo ""
echo "Default database location:"
echo "  $DB_DIR/memory.db"
echo ""
