#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
"""
One-time setup script for the memory-access MCP server.
Usage: uv run scripts/setup.py
Safe to run multiple times (idempotent).
"""
import os
import sys
import subprocess
from pathlib import Path


def get_colors():
    """Return color codes if NO_COLOR is not set."""
    if os.environ.get("NO_COLOR"):
        return "", "", "", ""
    return "\033[0;32m", "\033[1;33m", "\033[0;31m", "\033[0m"


GREEN, YELLOW, RED, NC = get_colors()


def info(msg: str) -> None:
    """Print info message."""
    print(f"{GREEN}[OK]{NC} {msg}")


def warn(msg: str) -> None:
    """Print warning message."""
    print(f"{YELLOW}[WARN]{NC} {msg}")


def error(msg: str) -> None:
    """Print error message."""
    print(f"{RED}[ERROR]{NC} {msg}")


def run_cmd(cmd: list[str], description: str = "") -> bool:
    """
    Run a command and return True if successful.
    If description is provided, show it on failure.
    """
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        if description:
            error(f"{description}: {e.stderr.strip()}")
        return False
    except FileNotFoundError:
        if description:
            error(f"{description}: command not found")
        return False


def check_uv_installed() -> bool:
    """Check if uv is installed."""
    return run_cmd(["uv", "--version"])


def install_memory_access() -> bool:
    """Install memory-access via uv tool install."""
    return run_cmd(
        ["uv", "tool", "install", "memory-access"],
        "Failed to install memory-access"
    )


def is_memory_access_installed() -> bool:
    """Check if memory-access is installed via uv tool list."""
    result = subprocess.run(
        ["uv", "tool", "list"],
        capture_output=True,
        text=True,
    )
    return "memory-access" in result.stdout


def create_db_directory() -> str:
    """Create default DB directory and return path."""
    db_dir = Path.home() / ".claude" / "memory-access"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir)


def check_env_vars() -> bool:
    """Check for required environment variables. Return True if all present."""
    required_vars = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    missing = []

    for var in required_vars:
        if os.environ.get(var):
            info(f"{var} is set")
        else:
            warn(f"Environment variable {var} is not set (required for default providers)")
            missing.append(var)

    if missing:
        print()
        warn("You can skip OPENAI_API_KEY / ANTHROPIC_API_KEY if using Bedrock providers:")
        print("  export EMBEDDING_PROVIDER=bedrock")
        print("  export LLM_PROVIDER=bedrock")
        print("  export AWS_PROFILE=<your-profile>")
        print("  export AWS_REGION=us-east-1  # optional, default shown")
        return False

    return True


def print_summary(db_dir: str) -> None:
    """Print setup summary."""
    print()
    print("=========================================")
    print(" memory-access setup complete")
    print("=========================================")
    print()
    print("Run the MCP server:")
    print("  uv run memory-access")
    print()
    print("Or install as a Claude Code plugin:")
    print("  claude plugin install memory-access@emmahyde")
    print()
    print("Default database location:")
    print(f"  {db_dir}/memory.db")
    print()


def main() -> int:
    """Main setup flow."""
    print("Setting up memory-access MCP server...")
    print()

    # 1. Check for uv
    if check_uv_installed():
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
        )
        version = result.stdout.strip()
        info(f"uv is already installed ({version})")
    else:
        warn("uv not found")
        error("Please install uv first: https://docs.astral.sh/uv/getting-started/installation/")
        error("Then run this script again with: uv run scripts/setup.py")
        return 1

    # 2. Install or check memory-access
    if is_memory_access_installed():
        info("memory-access is already installed")
    else:
        print("Installing memory-access...")
        if install_memory_access():
            info("memory-access installed")
        else:
            error("Failed to install memory-access")
            return 1

    # 3. Create DB directory
    db_dir = create_db_directory()
    info(f"Database directory ready: {db_dir}")

    # 4. Check environment variables
    print()
    env_vars_ok = check_env_vars()

    # 5. Print summary
    print_summary(db_dir)

    return 0 if env_vars_ok else 0  # Return 0 even if env vars missing (just warning)


if __name__ == "__main__":
    sys.exit(main())
