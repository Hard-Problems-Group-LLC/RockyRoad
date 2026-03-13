#!/usr/bin/env python3.9
"""
Bootstrap local Codex-oriented development prerequisites for RockyRoad.

This script is intentionally idempotent and standard-library-only. It is
designed for Rocky Linux 9.x developer workstations running as a standard user
with sudo privileges.

The bootstrap sequence performs the following work:
1. Validates the operating system and execution context.
2. Installs missing DNF/YUM packages needed for local Codex work.
3. Creates or reuses a project-local virtual environment at `.venv`.
4. Installs the Python quality-gate tools used by this repository.
5. Installs managed Git hook wrappers from TheKnowledge.
6. Installs the repo-local `@openai/codex` dependency from `package.json`.
7. Creates a `.venv/bin/codex` launcher that delegates to the repo-local CLI.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SYSTEM_PACKAGES = (
    "git",
    "less",
    "nodejs",
    "python3",
    "python3-pip",
    "python3-virtualenv",
    "ripgrep",
)

REQUIRED_COMMANDS = (
    "git",
    "node",
    "npm",
    "python3",
    "rg",
)

PYTHON_TOOL_PACKAGES = {
    "black": "black",
    "ruff": "ruff",
    "pytest": "pytest",
}


@dataclass(frozen=True)
class OSInfo:
    """Parsed operating system metadata."""

    platform_id: str
    version_id: str
    pretty_name: str


class CommandRunner:
    """Execute shell commands with optional dry-run support."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Optional[Path] = None,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a command and return the completed process."""
        printable = " ".join(command)
        if cwd is not None:
            printable = f"(cd {cwd} && {printable})"
        logger.info("Executing: %s", printable)

        if self.dry_run:
            return subprocess.CompletedProcess(command, 0, "", "")

        try:
            return subprocess.run(
                list(command),
                cwd=str(cwd) if cwd is not None else None,
                check=check,
                text=True,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
            )
        except subprocess.CalledProcessError as exc:
            stderr_text = (exc.stderr or "").strip()
            stdout_text = (exc.stdout or "").strip()
            details = stderr_text or stdout_text or "no diagnostic output"
            raise RuntimeError(
                f"Command failed: {' '.join(command)}; details: {details}"
            ) from exc


def parse_os_release(content: str) -> Dict[str, str]:
    """Parse `/etc/os-release`-style content into a dictionary."""
    parsed: Dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        parsed[key] = value.strip().strip('"')
    return parsed


def load_os_release(path: Path = Path("/etc/os-release")) -> Dict[str, str]:
    """Load operating system metadata from `/etc/os-release` when present."""
    if not path.exists():
        return {}
    return parse_os_release(path.read_text(encoding="utf-8"))


def detect_os_info() -> OSInfo:
    """Collect normalized OS metadata for validation."""
    system = platform.system().lower()
    if system != "linux":
        return OSInfo(system, "", platform.system())

    release = load_os_release()
    return OSInfo(
        platform_id=release.get("ID", "linux").lower(),
        version_id=release.get("VERSION_ID", ""),
        pretty_name=release.get("PRETTY_NAME", "Linux"),
    )


def validate_platform(os_info: OSInfo) -> None:
    """Fail fast when the host is not a supported Rocky Linux workstation."""
    if os_info.platform_id != "rocky":
        raise RuntimeError(
            "This installer supports Rocky Linux 9.x workstations only. "
            f"Detected: {os_info.pretty_name}."
        )
    if not os_info.version_id.startswith("9"):
        raise RuntimeError(
            "This installer supports Rocky Linux 9.x workstations only. "
            f"Detected version: {os_info.version_id or 'unknown'}."
        )


def enforce_preconditions(dry_run: bool) -> None:
    """Validate the expected non-root workstation execution model."""
    if os.geteuid() == 0:
        raise PermissionError(
            "This script must be executed as a standard user, not root."
        )
    if dry_run:
        logger.info("Dry-run mode active; mutating commands will not be executed.")


def select_package_manager() -> str:
    """Choose the available Rocky-compatible package manager."""
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("yum"):
        return "yum"
    raise RuntimeError("Neither dnf nor yum is available on this host.")


def package_installed(package_name: str, runner: CommandRunner) -> bool:
    """Return True when the named RPM package is already installed."""
    if runner.dry_run:
        result = subprocess.run(
            ["rpm", "-q", package_name],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode == 0

    result = runner.run(
        ["rpm", "-q", package_name],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def ensure_system_packages(runner: CommandRunner) -> None:
    """Install any missing Rocky Linux packages required for local development."""
    missing_packages = [
        package_name
        for package_name in SYSTEM_PACKAGES
        if not package_installed(package_name, runner)
    ]
    if not missing_packages:
        logger.info("All required Rocky Linux packages are already installed.")
        return

    if shutil.which("sudo") is None and not runner.dry_run:
        raise PermissionError(
            "sudo is required to install Rocky Linux system prerequisites: "
            + ", ".join(missing_packages)
        )

    manager = select_package_manager()
    install_command = ["sudo", manager, "install", "-y", *missing_packages]
    logger.info(
        "Installing missing Rocky Linux packages: %s",
        ", ".join(missing_packages),
    )
    runner.run(install_command)


def verify_required_commands() -> None:
    """Confirm the expected binaries are visible on PATH after installation."""
    missing_commands = [
        command_name
        for command_name in REQUIRED_COMMANDS
        if shutil.which(command_name) is None
    ]
    if missing_commands:
        raise RuntimeError(
            "Required commands are still missing after bootstrap: "
            + ", ".join(missing_commands)
        )


def venv_python_path(venv_path: Path) -> Path:
    """Return the Python interpreter path inside the local virtual environment."""
    return venv_path / "bin" / "python"


def ensure_virtualenv(
    python_executable: str,
    venv_path: Path,
    runner: CommandRunner,
) -> Path:
    """Create the local virtual environment when absent."""
    python_path = venv_python_path(venv_path)
    if python_path.exists():
        logger.info("Virtual environment already present at %s.", venv_path)
        return python_path

    logger.info("Creating virtual environment at %s.", venv_path)
    runner.run([python_executable, "-m", "venv", str(venv_path)])
    return python_path


def upgrade_pip_tooling(venv_python: str, runner: CommandRunner) -> None:
    """Upgrade baseline packaging helpers inside the local virtual environment."""
    runner.run(
        [
            venv_python,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
        ]
    )


def pip_package_installed(
    venv_python: str,
    package_name: str,
    runner: CommandRunner,
) -> bool:
    """Return True when a pip package is already installed in the venv."""
    if runner.dry_run and not Path(venv_python).exists():
        return False
    if runner.dry_run:
        result = subprocess.run(
            [venv_python, "-m", "pip", "show", package_name],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode == 0

    result = runner.run(
        [venv_python, "-m", "pip", "show", package_name],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def ensure_python_tools(venv_python: str, runner: CommandRunner) -> None:
    """Install the repository's Python development tools into `.venv`."""
    missing_packages = [
        package_name
        for package_name in PYTHON_TOOL_PACKAGES
        if not pip_package_installed(venv_python, package_name, runner)
    ]
    if not missing_packages:
        logger.info("Python development tools are already installed in .venv.")
        return

    logger.info(
        "Installing missing Python development tools into .venv: %s",
        ", ".join(missing_packages),
    )
    runner.run(
        [
            venv_python,
            "-m",
            "pip",
            "install",
            "--upgrade",
            *missing_packages,
        ]
    )


def install_git_hooks(repo_root: Path, venv_python: str, runner: CommandRunner) -> None:
    """Install or refresh managed Git hook wrappers from TheKnowledge."""
    hook_installer = repo_root / "TheKnowledge" / "scripts" / "install_git_hooks.py"
    if not hook_installer.exists():
        raise RuntimeError(
            "TheKnowledge Git hook installer was not found at "
            f"{hook_installer}."
        )
    runner.run([venv_python, str(hook_installer)], cwd=repo_root)


def read_package_json(package_json_path: Path) -> Dict[str, object]:
    """Load and parse `package.json`."""
    if not package_json_path.exists():
        raise RuntimeError(f"package.json not found at {package_json_path}.")
    return json.loads(package_json_path.read_text(encoding="utf-8"))


def ensure_codex_declared(package_json: Dict[str, object]) -> None:
    """Require a repo-local Codex CLI dependency declaration."""
    dependency_blocks = [
        package_json.get("dependencies", {}),
        package_json.get("devDependencies", {}),
    ]
    for block in dependency_blocks:
        if isinstance(block, dict) and "@openai/codex" in block:
            return
    raise RuntimeError(
        "package.json does not declare @openai/codex. "
        "This bootstrapper expects a repo-local Codex CLI dependency."
    )


def ensure_node_dependencies(repo_root: Path, runner: CommandRunner) -> Path:
    """Install repo-local npm dependencies when the Codex CLI is missing."""
    package_json = read_package_json(repo_root / "package.json")
    ensure_codex_declared(package_json)

    codex_binary = repo_root / "node_modules" / ".bin" / "codex"
    if codex_binary.exists():
        logger.info("Repo-local Codex CLI is already installed.")
        return codex_binary

    install_command = ["npm", "install", "--no-fund", "--no-audit"]
    if (
        (repo_root / "package-lock.json").exists()
        and not (repo_root / "node_modules").exists()
    ):
        install_command = ["npm", "ci", "--no-fund", "--no-audit"]

    logger.info("Installing repo-local npm dependencies for Codex CLI access.")
    runner.run(install_command, cwd=repo_root)

    if not runner.dry_run and not codex_binary.exists():
        raise RuntimeError(
            "npm installation completed but node_modules/.bin/codex is still "
            "missing."
        )
    return codex_binary


def ensure_codex_launcher(
    venv_path: Path,
    runner: CommandRunner,
) -> Path:
    """Create a repo-local Codex launcher inside `.venv/bin`."""
    launcher_path = venv_path / "bin" / "codex"
    launcher_content = """#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CODEX_BIN="${ROOT_DIR}/node_modules/.bin/codex"

if [ ! -x "${CODEX_BIN}" ]; then
  echo "Repo-local Codex CLI missing at ${CODEX_BIN}. Run install-codex-prerequisites.py again." >&2
  exit 1
fi

exec "${CODEX_BIN}" "$@"
"""

    if launcher_path.exists():
        existing_content = launcher_path.read_text(encoding="utf-8")
        if existing_content == launcher_content:
            logger.info("Local Codex launcher already present at %s.", launcher_path)
            return launcher_path

    logger.info("Writing local Codex launcher to %s.", launcher_path)
    if runner.dry_run:
        return launcher_path

    launcher_path.write_text(launcher_content, encoding="utf-8")
    current_mode = launcher_path.stat().st_mode
    launcher_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return launcher_path


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Install local Codex-oriented development prerequisites."
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to create the project-local virtual environment.",
    )
    parser.add_argument(
        "--venv",
        default=".venv",
        help="Project-local virtual environment path. Defaults to .venv.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the actions that would be taken without executing them.",
    )
    parser.add_argument(
        "--skip-git-hooks",
        action="store_true",
        help="Skip managed Git hook installation.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the local Codex prerequisite bootstrap."""
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parent
    venv_path = (repo_root / args.venv).resolve()
    runner = CommandRunner(dry_run=args.dry_run)

    os_info = detect_os_info()
    logger.info(
        "Detected platform: %s (%s %s)",
        os_info.pretty_name,
        os_info.platform_id,
        os_info.version_id or "unknown",
    )

    validate_platform(os_info)
    enforce_preconditions(args.dry_run)
    ensure_system_packages(runner)

    if not args.dry_run:
        verify_required_commands()

    venv_python = ensure_virtualenv(args.python, venv_path, runner)
    venv_python_str = str(venv_python)
    upgrade_pip_tooling(venv_python_str, runner)
    ensure_python_tools(venv_python_str, runner)

    if not args.skip_git_hooks:
        install_git_hooks(repo_root, venv_python_str, runner)

    ensure_node_dependencies(repo_root, runner)
    launcher_path = ensure_codex_launcher(venv_path, runner)

    logger.info("Local Codex prerequisite bootstrap completed.")
    logger.info("Virtual environment: %s", venv_path)
    logger.info("Codex launcher: %s", launcher_path)
    logger.info("Next step: source %s/bin/activate", venv_path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.warning("Bootstrap interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        logger.critical("FATAL ERROR: %s", exc)
        sys.exit(1)
