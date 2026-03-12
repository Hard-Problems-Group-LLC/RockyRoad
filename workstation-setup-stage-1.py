#!/usr/bin/env python3.9
"""
Provisioning script for Workstation Core System (Updates, Tailscale, Mosh).
Filename: workstation-setup-stage-1.py

Executes system updates, configures EPEL, and interactively installs core
networking utilities necessary for the developer workstation baseline.

Target: Rocky Linux 9.x
Language: Python 3.9+
"""

import os
import sys
import subprocess
import shutil
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_cmd(cmd: list[str], check: bool = True, shell: bool = False, silent: bool = False, stream_output: bool = False) -> subprocess.CompletedProcess:
    """Executes a shell command pessimistically."""
    cmd_str = ' '.join(cmd) if not shell else cmd
    if not silent:
        logger.info(f"Executing: {cmd_str}")
        
    try:
        kwargs = {'check': check, 'shell': shell, 'text': True}
        if not stream_output:
            kwargs['stdout'] = subprocess.PIPE
            kwargs['stderr'] = subprocess.PIPE

        result = subprocess.run(cmd, **kwargs)

        if not stream_output and result.stdout and not silent:
            logger.info(f"STDOUT: {result.stdout.strip()}")
            
        return result
    except subprocess.CalledProcessError as e:
        if not silent:
            logger.error(f"Command failed with return code {e.returncode}")
            if not stream_output and e.stderr:
                logger.error(f"STDERR: {e.stderr.strip()}")
        if check:
            raise RuntimeError(f"Critical execution failure: {cmd_str}") from e
        return e

def enforce_preconditions() -> None:
    """Validates execution as a normal user with sudo privileges."""
    if os.geteuid() == 0:
        raise PermissionError("This script must be executed as a normal user, not root.")
    try:
        subprocess.run(["sudo", "-v"], check=True)
    except subprocess.CalledProcessError:
        raise PermissionError("Sudo authentication failed.")

def prompt_existing(tool_name: str) -> str:
    """Prompts the user on how to handle an existing installation."""
    while True:
        print(f"\n[?] {tool_name} is already installed.")
        choice = input("    Select action: [L]eave alone, [D]elete & Reinstall, [R]epair/Update: ").strip().upper()
        if choice in ['L', 'D', 'R']:
            return choice
        print("    Invalid selection.")

def update_system() -> None:
    """Applies all pending OS updates and enables EPEL."""
    logger.info("Applying core OS updates...")
    run_cmd(["sudo", "dnf", "update", "-y"], stream_output=True)
    logger.info("Ensuring EPEL repository is enabled...")
    run_cmd(["sudo", "dnf", "install", "-y", "epel-release"], stream_output=True)

def install_networking_tools() -> None:
    """Installs Tailscale and Mosh interactively."""
    # Tailscale
    if shutil.which("tailscale"):
        action = prompt_existing("Tailscale")
        if action == 'D':
            run_cmd(["sudo", "dnf", "remove", "-y", "tailscale"])
            run_cmd(["sudo", "rm", "-rf", "/var/lib/tailscale"])
        elif action == 'R':
            run_cmd(["sudo", "dnf", "upgrade", "-y", "tailscale"], stream_output=True)
    
    if not shutil.which("tailscale"):
        run_cmd(["sudo", "dnf", "config-manager", "--add-repo", "https://pkgs.tailscale.com/stable/centos/9/tailscale.repo"])
        run_cmd(["sudo", "dnf", "install", "-y", "tailscale"], stream_output=True)
        run_cmd(["sudo", "systemctl", "enable", "--now", "tailscaled"])

    # Mosh
    if shutil.which("mosh"):
        action = prompt_existing("Mosh")
        if action == 'D':
            run_cmd(["sudo", "dnf", "remove", "-y", "mosh"])
        elif action == 'R':
            run_cmd(["sudo", "dnf", "upgrade", "-y", "mosh"], stream_output=True)
            
    if not shutil.which("mosh"):
        run_cmd(["sudo", "dnf", "install", "-y", "mosh"], stream_output=True)

def main() -> None:
    try:
        enforce_preconditions()
        update_system()
        install_networking_tools()
        logger.info("--- Workstation Stage 1 Provisioning Completed ---")
        print("\nIf Tailscale was freshly installed, run 'sudo tailscale up' to authenticate before proceeding to Stage 2.")
    except Exception as e:
        logger.critical(f"FATAL ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
