#!/usr/bin/env python3.9
"""
Provisioning script for Tailscale, SSH, Mosh, and User Setup on Rocky Linux 9.x.
Filename: linode-server-setup-stage-1.py

Executes a pessimistic, resilient, and idempotent installation and configuration 
process to restrict remote access strictly to the Tailscale network. 
Includes Tailscale expiry validation, a watchdog service, and an interactive system update.

Target: Rocky Linux 9.x
Language: Python 3.9+
"""

import os
import sys
import subprocess
import time
import logging
import re
import shutil
import socket
import json
import pwd
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_cmd(cmd: list[str], check: bool = True, shell: bool = False, silent: bool = False, input_data: str = None) -> subprocess.CompletedProcess:
    """Executes a shell command pessimistically, logging execution and capturing output."""
    cmd_str = ' '.join(cmd) if not shell else cmd
    if not silent:
        logger.info(f"Executing: {cmd_str}")
    try:
        result = subprocess.run(
            cmd, 
            check=check, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            shell=shell,
            input=input_data
        )
        if result.stdout and not silent:
            logger.info(f"STDOUT: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        if not silent:
            logger.error(f"Command failed with return code {e.returncode}")
            logger.error(f"STDERR: {e.stderr.strip()}")
        if check:
            raise RuntimeError(f"Critical execution failure: {cmd_str}") from e
        return e

def enforce_preconditions() -> None:
    """Validates root privileges and OS environment."""
    logger.info("Validating preconditions...")
    if os.geteuid() != 0:
        raise PermissionError("This script must be executed with root privileges.")
    if not os.path.exists('/etc/os-release'):
        raise FileNotFoundError("Cannot identify OS: /etc/os-release is missing.")
    with open('/etc/os-release', 'r') as f:
        if 'ID="rocky"' not in f.read():
            raise ValueError("Unsupported OS. This script mandates Rocky Linux.")

def install_dependencies() -> None:
    """Idempotent installation of core packages."""
    logger.info("Checking dependencies...")
    missing_pkgs = []
    for pkg in ["epel-release", "tailscale", "mosh"]:
        result = run_cmd(["rpm", "-q", pkg], check=False, silent=True)
        if result.returncode != 0:
            missing_pkgs.append(pkg)
            
    if "epel-release" in missing_pkgs:
        run_cmd(["dnf", "install", "-y", "epel-release"])
    if "tailscale" in missing_pkgs:
        run_cmd(["dnf", "config-manager", "--add-repo", "https://pkgs.tailscale.com/stable/centos/9/tailscale.repo"])
        run_cmd(["dnf", "install", "-y", "tailscale"])
    if "mosh" in missing_pkgs:
        run_cmd(["dnf", "install", "-y", "mosh"])

def configure_tailscale() -> str:
    """Ensures Tailscale is running, authenticated, and retrieves the IPv4 address."""
    logger.info("Ensuring tailscaled service is enabled and active...")
    run_cmd(["systemctl", "enable", "--now", "tailscaled"])
    
    status = run_cmd(["tailscale", "status"], check=False, silent=True)
    if "Logged out" in status.stdout or status.returncode != 0:
        print("\n--- ACTION REQUIRED ---")
        print("Tailscale needs to authenticate. Please follow the prompts below.")
        subprocess.run(["tailscale", "up"], check=True)
        print("--- AUTHENTICATION COMPLETE ---\n")
    else:
        run_cmd(["tailscale", "up"], check=True) 

    logger.info("Retrieving Tailscale IPv4 address...")
    for _ in range(5):
        try:
            result = run_cmd(["tailscale", "ip", "-4"], silent=True)
            ts_ip = result.stdout.strip()
            if ts_ip:
                return ts_ip
        except RuntimeError:
            pass
        time.sleep(2)
    raise TimeoutError("Failed to retrieve Tailscale IPv4 address.")

def verify_tailscale_expiry() -> None:
    """
    Checks Tailscale JSON status for node key expiry. Loops until the user
    disables it in the web console, or explicitly overrides.
    """
    print("\n--- TAILSCALE KEY EXPIRY CHECK ---")
    while True:
        result = run_cmd(["tailscale", "status", "--json"], silent=True)
        try:
            ts_data = json.loads(result.stdout)
            expiry_str = ts_data.get('Self', {}).get('KeyExpiry')
            
            if not expiry_str or expiry_str.startswith("0001-01-01") or expiry_str.startswith("1970-01-01"):
                logger.info("Tailscale key expiry is disabled. Connection will persist.")
                break
            
            print(f"\nWARNING: Tailscale key is currently set to expire at: {expiry_str}")
            print("To ensure uninterrupted remote access, you MUST disable key expiry.")
            print("1. Log in to the Tailscale Admin Console: https://login.tailscale.com/admin/machines")
            print("2. Locate this machine, click the menu (...), and select 'Disable key expiry'.")
            
            choice = input("\nPress [Enter] to re-check status, or type 'x' to reluctantly proceed anyway: ").strip().lower()
            if choice == 'x':
                logger.warning("User explicitly bypassed expiry check. The connection WILL eventually drop.")
                break
        except json.JSONDecodeError:
            logger.error("Failed to parse Tailscale JSON status. Skipping expiry verification.")
            break

def setup_tailscale_watchdog() -> None:
    """
    Creates a systemd timer and service to periodically verify Tailscale 
    connectivity and issue 'tailscale up' if the node falls offline.
    """
    logger.info("Deploying Tailscale watchdog service and timer...")
    
    script_path = "/usr/local/bin/tailscale-watchdog.sh"
    service_path = "/etc/systemd/system/tailscale-watchdog.service"
    timer_path = "/etc/systemd/system/tailscale-watchdog.timer"
    
    script_content = """#!/bin/bash
# Pessimistic Tailscale connectivity watchdog
if ! /usr/bin/tailscale status | grep -q 'Tailscale is awake'; then
    /usr/bin/tailscale up
fi
"""
    with open(script_path, 'w') as f:
        f.write(script_content)
    os.chmod(script_path, 0o700)

    service_content = """[Unit]
Description=Tailscale Connectivity Watchdog
After=tailscaled.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/tailscale-watchdog.sh
"""
    with open(service_path, 'w') as f:
        f.write(service_content)

    timer_content = """[Unit]
Description=Run Tailscale Watchdog Every 5 Minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
"""
    with open(timer_path, 'w') as f:
        f.write(timer_content)

    run_cmd(["systemctl", "daemon-reload"])
    run_cmd(["systemctl", "enable", "--now", "tailscale-watchdog.timer"])
    logger.info("Tailscale watchdog deployed successfully.")

def configure_initial_hostname() -> str:
    current_hostname = socket.gethostname().split('.')[0]
    if current_hostname == 'localhost':
        print("\n--- HOSTNAME CONFIGURATION ---")
        new_hostname = input("Current hostname is 'localhost'. Enter a new short hostname: ").strip()
        if not new_hostname:
            raise ValueError("Hostname cannot be empty. Aborting.")
        logger.info(f"Setting initial hostname to: {new_hostname}")
        run_cmd(["hostnamectl", "set-hostname", new_hostname])
        return new_hostname
    return current_hostname

def configure_magicdns_hostname(short_hostname: str) -> None:
    logger.info("Querying Tailscale for MagicDNS suffix...")
    result = run_cmd(["tailscale", "status", "--json"], silent=True)
    try:
        ts_data = json.loads(result.stdout)
        magic_dns = ts_data.get('MagicDNSSuffix')
        if not magic_dns:
            return
        fqdn = f"{short_hostname}.{magic_dns}".strip('.')
        current_fqdn = run_cmd(["hostnamectl", "--static"], silent=True).stdout.strip()
        if current_fqdn != fqdn:
            logger.info(f"Setting system FQDN to: {fqdn}")
            run_cmd(["hostnamectl", "set-hostname", fqdn])
    except json.JSONDecodeError:
        pass

def configure_firewall() -> None:
    logger.info("Configuring firewalld rules for strict isolation...")
    run_cmd(["systemctl", "enable", "--now", "firewalld"], check=False, silent=True)
    run_cmd(["firewall-cmd", "--permanent", "--zone=public", "--remove-service=ssh"], check=False, silent=True)
    run_cmd(["firewall-cmd", "--permanent", "--zone=public", "--remove-port=60000-61000/udp"], check=False, silent=True)
    run_cmd(["firewall-cmd", "--permanent", "--zone=internal", "--add-interface=tailscale0"], check=False, silent=True)
    run_cmd(["firewall-cmd", "--permanent", "--zone=internal", "--add-service=ssh"], check=False, silent=True)
    run_cmd(["firewall-cmd", "--permanent", "--zone=internal", "--add-port=60000-61000/udp"], check=False, silent=True)
    run_cmd(["firewall-cmd", "--reload"])

def setup_admin_user() -> str:
    print("\n--- ADMINISTRATOR ACCOUNT SETUP ---")
    while True:
        admin_user = input("Enter the desired administrator username: ").strip()
        if admin_user and re.match(r'^[a-z_][a-z0-9_-]*$', admin_user):
            break
        print("Invalid username format. Use lowercase alphanumeric characters.")

    try:
        pwd.getpwnam(admin_user)
        logger.info(f"User '{admin_user}' already exists. Ensuring group membership...")
        run_cmd(["usermod", "-aG", "wheel", admin_user])
    except KeyError:
        logger.info(f"User '{admin_user}' does not exist. Creating...")
        run_cmd(["useradd", "-m", "-G", "wheel", admin_user])
        logger.info(f"Setting password for newly created user '{admin_user}'...")
        subprocess.run(["passwd", admin_user], check=True)
        logger.info("Executing skeleton login to initialize home directory and PAM profiles...")
        run_cmd(["su", "-", admin_user, "-c", "exit"])
        
    return admin_user

def setup_ssh_keys(admin_user: str) -> None:
    user_info = pwd.getpwnam(admin_user)
    home_dir = user_info.pw_dir
    ssh_dir = os.path.join(home_dir, '.ssh')
    auth_keys_file = os.path.join(ssh_dir, 'authorized_keys')

    if not os.path.exists(ssh_dir):
        os.makedirs(ssh_dir, mode=0o700)
    else:
        os.chmod(ssh_dir, 0o700)

    keys_exist = False
    if os.path.exists(auth_keys_file):
        with open(auth_keys_file, 'r') as f:
            if f.read().strip():
                keys_exist = True

    if not keys_exist:
        print("\n--- SSH KEY CONFIGURATION ---")
        pub_key = input("Paste the contents of your public SSH key (e.g., ssh-ed25519 AAA...): ").strip()
        if not pub_key:
            raise ValueError("An SSH public key is mandatory for secure access.")
        with open(auth_keys_file, 'w') as f:
            f.write(f"{pub_key}\n")

    os.chmod(auth_keys_file, 0o600)
    os.chown(ssh_dir, user_info.pw_uid, user_info.pw_gid)
    os.chown(auth_keys_file, user_info.pw_uid, user_info.pw_gid)
    run_cmd(["restorecon", "-Rv", ssh_dir])

def configure_sshd_features(ts_ip: str) -> None:
    logger.info("Configuring SSH daemon parameters...")
    sshd_config = '/etc/ssh/sshd_config'
    backup_config = f"{sshd_config}.bak.{int(time.time())}"
    shutil.copy2(sshd_config, backup_config)
    
    with open(sshd_config, 'r') as f:
        content = f.read()

    lines = content.splitlines()
    new_lines = []
    
    for line in lines:
        if re.match(r'^\s*ListenAddress', line) or re.match(r'^\s*PubkeyAuthentication', line):
            new_lines.append(f"# Overridden by provisioning script: {line}")
        else:
            new_lines.append(line)
            
    new_lines.append("\n# Enforced by Provisioning Script")
    new_lines.append(f"ListenAddress {ts_ip}")
    new_lines.append("PubkeyAuthentication yes")
    new_lines.append("AuthorizedKeysFile .ssh/authorized_keys")
    
    with open(sshd_config, 'w') as f:
        f.write('\n'.join(new_lines))
        
    run_cmd(["sshd", "-t"])
    run_cmd(["systemctl", "restart", "sshd"])

def verify_ssh_login(admin_user: str, ts_ip: str) -> None:
    print("\n--- VERIFY SSH LOGIN ---")
    print(f"Please open a NEW terminal and attempt to log in via SSH:")
    print(f"ssh {admin_user}@{ts_ip}")
    print("Watching /var/log/secure for successful login. Waiting up to 60 seconds...")

    log_file = '/var/log/secure'
    timeout = 60
    end_time = time.time() + timeout
    login_successful = False

    with open(log_file, 'r') as f:
        f.seek(0, 2)
        while time.time() < end_time:
            line = f.readline()
            if not line:
                time.sleep(1)
                continue
            
            if f"Accepted publickey for {admin_user}" in line or f"Accepted password for {admin_user}" in line:
                logger.info(f"Detected successful login for {admin_user} in system logs.")
                login_successful = True
                break
                
    prompted = input("\nWere you prompted for a password during that login attempt? (y/n): ").strip().lower()
    if prompted == 'y':
        logger.warning("Password prompt detected. Checking permissions...")
        user_info = pwd.getpwnam(admin_user)
        ssh_dir = os.path.join(user_info.pw_dir, '.ssh')
        os.chmod(ssh_dir, 0o700)
        os.chmod(os.path.join(ssh_dir, 'authorized_keys'), 0o600)
        run_cmd(["restorecon", "-Rv", ssh_dir])
        run_cmd(["systemctl", "restart", "sshd"])
        input("\nFixes applied. Press Enter once you have successfully logged in via SSH using ONLY your key...")

def verify_mosh_login(admin_user: str, ts_ip: str) -> None:
    print("\n--- VERIFY MOSH LOGIN ---")
    print("Please log out of your current SSH session.")
    print("Now, attempt to connect using Mosh:")
    print(f"mosh {admin_user}@{ts_ip}")
    
    success = input("Did Mosh connect successfully? (y/n): ").strip().lower()
    if success != 'y':
        logger.warning("Mosh connection failed. Re-asserting firewall rules...")
        run_cmd(["firewall-cmd", "--permanent", "--zone=internal", "--add-port=60000-61000/udp"])
        run_cmd(["firewall-cmd", "--reload"])
        retry = input("Firewall reloaded. Did Mosh connect successfully this time? (y/n): ").strip().lower()
        if retry != 'y':
            logger.critical("Mosh login still failing. Manual intervention required.")
            sys.exit(1)

def lockdown_root() -> None:
    print("\n--- ROOT ACCOUNT LOCKDOWN ---")
    ready = input("All logins verified. Are you ready to permanently disable direct root access? (y/n): ").strip().lower()
    if ready != 'y':
        return

    logger.info("Disabling root login via SSH in sshd_config...")
    sshd_config = '/etc/ssh/sshd_config'
    with open(sshd_config, 'r') as f:
        lines = f.readlines()
        
    new_lines = []
    for line in lines:
        if re.match(r'^\s*PermitRootLogin', line):
            new_lines.append(f"# Overridden by provisioning script: {line}")
        else:
            new_lines.append(line)
            
    new_lines.append("\n# Enforced Root Lockdown\nPermitRootLogin no\n")
    with open(sshd_config, 'w') as f:
        f.writelines(new_lines)
        
    run_cmd(["systemctl", "restart", "sshd"])
    logger.info("Locking the local root account (usermod -L root)...")
    run_cmd(["usermod", "-L", "root"])

def finalize_and_reboot() -> None:
    """Performs a full system update with real-time output, then prompts for reboot."""
    print("\n--- SYSTEM UPDATE AND REBOOT ---")
    logger.info("Running full DNF system update. This may take a while...")
    logger.info("Press CTRL-C at any time to abort the update and skip to the reboot prompt.")
    
    update_aborted = False
    try:
        # Running natively without capturing stdout/stderr allows real-time terminal output
        subprocess.run(["dnf", "update", "-y"], check=True)
        logger.info("System update completed.")
    except KeyboardInterrupt:
        print("\n")
        logger.warning("System update aborted by user via CTRL-C.")
        print("WARNING: You must run 'dnf update -y' manually later to ensure system security.")
        update_aborted = True
    except subprocess.CalledProcessError as e:
        logger.error(f"DNF update failed with return code {e.returncode}.")
        print("WARNING: System update failed. You must investigate and update manually later.")
        update_aborted = True

    print("\n--- REBOOT CONFIRMATION ---")
    ready = input("Are you ready to reboot the system now? (y/n): ").strip().lower()
    if ready == 'y':
        logger.info("Syncing filesystem buffers...")
        run_cmd(["sync"])
        print("\nProvisioning complete. The system will now reboot.")
        print("Your current session will disconnect. Please reconnect via Tailscale and Mosh after the reboot.")
        time.sleep(3)
        run_cmd(["reboot"], check=False)
    else:
        print("\n--- PENDING ACTIONS SUMMARY ---")
        print("The script has exited without rebooting.")
        if update_aborted:
            print("- PENDING: Run 'dnf update -y' manually to secure the system.")
        print("- PENDING: Reboot the server ('reboot') to apply kernel updates and finalize the environment.")
        sys.exit(0)

def main() -> None:
    logger.info("--- Initiating Pessimistic Provisioning Sequence ---")
    try:
        enforce_preconditions()
        short_hostname = configure_initial_hostname()
        install_dependencies()
        ts_ip = configure_tailscale()
        verify_tailscale_expiry()
        setup_tailscale_watchdog()
        configure_magicdns_hostname(short_hostname)
        configure_firewall()
        
        admin_user = setup_admin_user()
        setup_ssh_keys(admin_user)
        configure_sshd_features(ts_ip)
        verify_ssh_login(admin_user, ts_ip)
        verify_mosh_login(admin_user, ts_ip)
        lockdown_root()
        
        finalize_and_reboot()
    except Exception as e:
        logger.critical(f"FATAL ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
