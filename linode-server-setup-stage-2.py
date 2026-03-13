#!/usr/bin/env python3.9
"""
Provisioning script for User Environment, Podman, Tailscale Certs, and Caddy.
Filename: linode-server-setup-stage-2.py

Executes a resilient, idempotent configuration of the user environment (NVM, Pyenv, PS1),
installs development headers, configures rootless Podman, provisions a Tailscale 
Let's Encrypt certificate, and executes an interactive, diagnostic smoketest using Caddy.

Target: Rocky Linux 9.x
Language: Python 3.9+
"""

import os
import sys
import subprocess
import time
import logging
import json
import uuid
import socket
import urllib.request

# Configure verbose logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
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
    logger.info("Validating execution context...")
    if os.geteuid() == 0:
        raise PermissionError("This script must be executed as a normal user, not root.")
    logger.info("Caching sudo credentials. You may be prompted for your password.")
    try:
        subprocess.run(["sudo", "-v"], check=True)
    except subprocess.CalledProcessError:
        raise PermissionError("Sudo authentication failed. This script requires administrative privileges.")

def configure_bashrc_ps1() -> bool:
    """Idempotently appends or updates the custom PS1 prompt. Returns True if changed."""
    logger.info("Configuring custom PS1 prompt...")
    bashrc_path = os.path.expanduser("~/.bashrc")
    new_ps1 = r'export PS1="[\[\033[0;33m\]\$(date \"+%Y%m%d%Z%H%M%S\") \[\033[1m\]\u@\h\[\033[22m\] \W]\$ "'
    
    if not os.path.exists(bashrc_path):
        with open(bashrc_path, 'w') as f:
            f.write(f"\n{new_ps1}\n")
        return True
        
    with open(bashrc_path, 'r') as f:
        lines = f.readlines()
        
    changed = False
    found = False
    
    for i, line in enumerate(lines):
        if r'date \"+%Y%m%d%Z%H%M%S\"' in line:
            found = True
            if line.strip() != new_ps1.strip():
                lines[i] = new_ps1 + "\n"
                changed = True
                
    if not found:
        lines.append(f"\n# Configured by provisioning script\n{new_ps1}\n")
        changed = True
        
    if changed:
        with open(bashrc_path, 'w') as f:
            f.writelines(lines)
        logger.info("PS1 prompt updated.")
    else:
        logger.info("Custom PS1 already present and correct. Skipping.")
        
    return changed

def install_nvm() -> bool:
    """Idempotently installs NVM. Returns True if installed."""
    logger.info("Checking for NVM installation...")
    nvm_dir = os.path.expanduser("~/.nvm")
    if os.path.exists(nvm_dir):
        logger.info("NVM appears to be installed. Skipping.")
        return False

    logger.info("Fetching and executing NVM installer...")
    nvm_url = "https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh"
    req = urllib.request.Request(nvm_url)
    with urllib.request.urlopen(req) as response:
        installer_script = response.read().decode('utf-8')
    
    run_cmd(["bash", "-c", installer_script], shell=False, stream_output=True)
    logger.info("NVM installed successfully.")
    return True

def install_pyenv() -> bool:
    """Idempotently installs Pyenv and pyenv-virtualenv."""
    changed = False
    logger.info("Installing Pyenv build dependencies via DNF...")
    deps = [
        "git", "make", "gcc", "zlib-devel", "bzip2", "bzip2-devel", "readline-devel", 
        "sqlite", "sqlite-devel", "openssl-devel", "tk-devel", "libffi-devel", "xz-devel"
    ]
    run_cmd(["sudo", "dnf", "install", "-y"] + deps, stream_output=True)

    pyenv_root = os.path.expanduser("~/.pyenv")
    if not os.path.exists(pyenv_root):
        logger.info("Fetching and executing Pyenv installer...")
        pyenv_url = "https://pyenv.run"
        req = urllib.request.Request(pyenv_url)
        with urllib.request.urlopen(req) as response:
            installer_script = response.read().decode('utf-8')
        run_cmd(["bash", "-c", installer_script], shell=False, stream_output=True)
        changed = True

    logger.info("Verifying shell configuration for Pyenv/Virtualenv...")
    
    def enforce_pyenv(filepath: str) -> None:
        nonlocal changed
        if not os.path.exists(filepath):
            return
            
        with open(filepath, 'r') as f:
            content = f.read()
            
        if 'eval "$(pyenv virtualenv-init -)"' in content:
            return 
            
        if 'eval "$(pyenv init -)"' in content:
            with open(filepath, 'a') as f_append:
                f_append.write('eval "$(pyenv virtualenv-init -)"\n')
            changed = True
            return
            
        pyenv_config = '\n# Pyenv and Virtualenv configuration\nexport PYENV_ROOT="$HOME/.pyenv"\n[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"\neval "$(pyenv init -)"\neval "$(pyenv virtualenv-init -)"\n'
        with open(filepath, 'a') as f_append:
            f_append.write(pyenv_config)
        changed = True

    enforce_pyenv(os.path.expanduser("~/.bashrc"))
    enforce_pyenv(os.path.expanduser("~/.bash_profile"))
    
    if changed:
        logger.info("Pyenv and Virtualenv configured.")
    else:
        logger.info("Pyenv and Virtualenv configuration already present. Skipping.")
        
    return changed

def install_system_dependencies() -> None:
    logger.info("Enabling EPEL repository...")
    run_cmd(["sudo", "dnf", "install", "-y", "epel-release"], stream_output=True)
    
    logger.info("Installing core build tools, database headers, and Podman...")
    pkgs = [
        "dnf-plugins-core", "podman", "podman-plugins", "slirp4netns",
        "postgresql-devel", "libdb-devel", "libdb-utils", "python3-devel"
    ]
    run_cmd(["sudo", "dnf", "install", "-y"] + pkgs, stream_output=True)

    logger.info("Enabling lingering for current user...")
    current_user = os.environ.get("USER", os.getlogin())
    run_cmd(["sudo", "loginctl", "enable-linger", current_user])

def configure_tailscale_certs() -> tuple[str, str, str]:
    logger.info("Querying Tailscale for MagicDNS FQDN and IP...")
    status_out = run_cmd(["tailscale", "status", "--json"], silent=True).stdout
    try:
        ts_data = json.loads(status_out)
        fqdn = ts_data.get('CertDomains', [])[0]
        ts_ip = ts_data.get('TailscaleIPs', [])[0]
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        raise RuntimeError("Failed to parse Tailscale status for FQDN/IP.") from e

    cert_dir = "/etc/pki/tls/tailscale"
    run_cmd(["sudo", "mkdir", "-p", cert_dir])
    cert_path, key_path = f"{cert_dir}/ts.crt", f"{cert_dir}/ts.key"

    logger.info(f"Requesting Let's Encrypt certificate for {fqdn}...")
    run_cmd(["sudo", "tailscale", "cert", "--cert-file", cert_path, "--key-file", key_path, fqdn])

    run_cmd(["sudo", "chmod", "644", cert_path])
    run_cmd(["sudo", "chmod", "600", key_path])
    run_cmd(["sudo", "chgrp", os.environ.get("USER", os.getlogin()), key_path])
    run_cmd(["sudo", "chmod", "640", key_path])

    timer_content = "[Unit]\nDescription=Daily Tailscale Certificate Renewal\n[Timer]\nOnCalendar=daily\nRandomizedDelaySec=12h\nPersistent=true\n[Install]\nWantedBy=timers.target\n"
    service_content = f"[Unit]\nDescription=Tailscale Certificate Renewal Service\nAfter=tailscaled.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/tailscale cert --cert-file {cert_path} --key-file {key_path} {fqdn}\nExecStartPost=/usr/bin/chmod 640 {key_path}\n"
    run_cmd(["sudo", "bash", "-c", f"cat << 'EOF' > /etc/systemd/system/tailscale-cert-renewal.timer\n{timer_content}\nEOF"])
    run_cmd(["sudo", "bash", "-c", f"cat << 'EOF' > /etc/systemd/system/tailscale-cert-renewal.service\n{service_content}\nEOF"])
    run_cmd(["sudo", "systemctl", "daemon-reload"])
    run_cmd(["sudo", "systemctl", "enable", "--now", "tailscale-cert-renewal.timer"])
    
    return ts_ip, fqdn, cert_dir


def cleanup_smoketest_resources(container_name: str, port: str, local_test_dir: str) -> None:
    """Best-effort teardown for server smoketest resources."""
    logger.info("Tearing down smoketest infrastructure...")
    run_cmd(["podman", "rm", "-f", container_name], check=False, silent=True)
    run_cmd(
        ["sudo", "firewall-cmd", "--zone=internal", f"--remove-port={port}/tcp"],
        check=False,
        silent=True,
    )
    run_cmd(["rm", "-rf", local_test_dir], check=False, silent=True)
    logger.info("Cleanup complete.")


def run_smoketest(ts_ip: str, fqdn: str, cert_dir: str) -> None:
    container_name = "stage2-podman-smoketest"
    port = "9876"
    challenge_secret = str(uuid.uuid4())
    current_user = os.environ.get("USER", os.getlogin())
    hostname = socket.gethostname()
    local_test_dir = os.path.expanduser("~/.smoketest_env")

    try:
        logger.info("Ensuring firewalld permits smoketest traffic on the internal zone...")
        run_cmd(
            ["sudo", "firewall-cmd", "--zone=internal", f"--add-port={port}/tcp"],
            check=False,
            silent=True,
        )

        logger.info("Cleaning up any existing smoketest containers...")
        run_cmd(["podman", "rm", "-f", container_name], check=False, silent=True)

        run_cmd(["mkdir", "-p", local_test_dir])
        run_cmd(["sudo", "cp", f"{cert_dir}/ts.crt", f"{cert_dir}/ts.key", local_test_dir])
        run_cmd(["sudo", "chown", "-R", f"{current_user}:{current_user}", local_test_dir])

        # Caddyfile configuring a cache-busting redirect and serving the HTML template
        caddyfile_content = f"""
{fqdn}:{port} {{
    tls /certs/ts.crt /certs/ts.key
    log {{
        output stdout
    }}
    
    # Require cache buster query string, otherwise redirect with timestamp
    @needs_cb {{
        path /challenge/{challenge_secret}
        not query cb=*
    }}
    redir @needs_cb /challenge/{challenge_secret}?cb={{time.now.unix}} 302
    
    # Handle the cache-busted request
    @has_cb {{
        path /challenge/{challenge_secret}
        query cb=*
    }}
    
    handle @has_cb {{
        header Cache-Control "no-cache, no-store, must-revalidate"
        templates
        root * /usr/share/caddy
        rewrite * /index.html
        file_server
    }}
    
    handle {{
        respond "404 Not Found. Provide the correct challenge sequence." 404
    }}
}}
"""
        # High-impact HTML with neon/dark UI and Caddy template tags for real-time evaluation
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Challenge Accepted</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #ffffff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; }}
        .container {{ background-color: #1e1e1e; padding: 40px; border-radius: 10px; box-shadow: 0 4px 20px rgba(0,255,128,0.2); border: 1px solid #00ff80; }}
        h1 {{ color: #00ff80; margin-bottom: 10px; font-size: 2.5em; text-transform: uppercase; letter-spacing: 2px; }}
        p {{ font-size: 1.2em; color: #aaaaaa; }}
        .meta {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #333; font-size: 0.9em; color: #777; }}
        .highlight {{ color: #00ff80; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Success!</h1>
        <p>Challenge authenticated securely via Tailscale and Caddy.</p>
        <p>You may now close this browser tab.</p>
        <div class="meta">
            Server: <span class="highlight">{hostname}</span><br>
            Time: <span class="highlight">{{{{now | date "Mon, 02 Jan 2006 15:04:05 MST"}}}}</span>
        </div>
    </div>
</body>
</html>
"""
        caddyfile_path = os.path.join(local_test_dir, "Caddyfile")
        html_path = os.path.join(local_test_dir, "index.html")

        with open(caddyfile_path, "w") as f:
            f.write(caddyfile_content)
        with open(html_path, "w") as f:
            f.write(html_content)

        logger.info(f"Deploying '{container_name}' using official Caddy image...")
        podman_cmd = [
            "podman", "run", "-d", "--name", container_name,
            "-p", f"{ts_ip}:{port}:{port}",
            "-v", f"{local_test_dir}:/certs:ro,Z",
            "-v", f"{caddyfile_path}:/etc/caddy/Caddyfile:ro,Z",
            "-v", f"{html_path}:/usr/share/caddy/index.html:ro,Z",
            "docker.io/library/caddy:alpine"
        ]
        run_cmd(podman_cmd, stream_output=True)

        url = f"https://{fqdn}:{port}/challenge/{challenge_secret}"

        while True:
            print("\n" + "="*60)
            print("--- PODMAN SECURE DEPLOYMENT SMOKETEST (via CADDY) ---")
            print("Caddy container is running. Open this URL in your local browser:")
            print(f"\n{url}\n")
            print("Select the result observed in your browser:")
            print("  1 - Success page (Dark UI) observed successfully")
            print("  2 - ERROR: ERR_ADDRESS_UNREACHABLE")
            print("  3 - ERROR: ERR_CONNECTION_TIMED_OUT")
            print("  4 - ERROR: ERR_CONNECTION_REFUSED")
            print("  5 - ERROR: NET::ERR_CERT_AUTHORITY_INVALID (or SSL error)")
            print("  6 - ERROR: DNS_PROBE_FINISHED_NXDOMAIN")
            print("  7 - ERROR: HTTP 404 / 500")
            print("  q - Quit (abort and cleanup)")
            print("="*60)

            choice = input("\nEnter choice: ").strip().lower()

            if choice == '1':
                logs = run_cmd(["podman", "logs", container_name], silent=True).stdout
                # Validate HTTP 200 via Caddy access logs
                if challenge_secret in logs and "200" in logs:
                    logger.info("Success verified in Caddy logs! Infrastructure is operating nominally.")
                    break
                logger.warning("The expected 200 OK wasn't found in Caddy's logs. Are you sure you hit the exact URL?")
                input("Press Enter to return to the menu...")
            elif choice == '2':
                print("\n[DIAGNOSTIC: ERR_ADDRESS_UNREACHABLE]\nClient device lacks IP route to Tailscale subnet.")
                input("\nPress Enter to return...")
            elif choice == '3':
                print("\n[DIAGNOSTIC: ERR_CONNECTION_TIMED_OUT]\nFirewall is dropping packets. Test with: sudo firewall-cmd --list-all --zone=internal")
                input("\nPress Enter to return...")
            elif choice == '4':
                print("\n[DIAGNOSTIC: ERR_CONNECTION_REFUSED]\nNothing is listening. Container likely crashed. Test with: podman logs stage2-podman-smoketest")
                input("\nPress Enter to return...")
            elif choice == '5':
                print("\n[DIAGNOSTIC: SSL / CERTIFICATE ERRORS]\nBrowser rejecting cert. Check output of: curl -kv https://" + fqdn + ":" + port)
                input("\nPress Enter to return...")
            elif choice == '6':
                print("\n[DIAGNOSTIC: DNS_PROBE_FINISHED_NXDOMAIN]\nMagicDNS failure. Ensure Tailscale DNS settings are active on the client.")
                input("\nPress Enter to return...")
            elif choice == '7':
                print("\n[DIAGNOSTIC: HTTP ERRORS]\nHit the catch-all 404 route. Verify the exact challenge UUID URL.")
                input("\nPress Enter to return...")
            elif choice == 'q':
                logger.warning("User aborted the smoketest.")
                break
            else:
                print("Invalid selection.")
    finally:
        cleanup_smoketest_resources(container_name, port, local_test_dir)

def main() -> None:
    logger.info("--- Initiating Stage 2 Provisioning Sequence ---")
    try:
        enforce_preconditions()
        
        restart_required = False
        if configure_bashrc_ps1(): restart_required = True
        if install_nvm(): restart_required = True
        if install_pyenv(): restart_required = True
        
        if restart_required:
            print("\n" + "="*60)
            print("ACTION REQUIRED: Shell Environment Updated")
            print("Modifications were made to your shell configuration.")
            print("To ensure these tools are fully initialized and available to sub-processes,")
            print("you MUST log out, log back in, and execute this script again.")
            print("="*60 + "\n")
            sys.exit(0)
            
        install_system_dependencies()
        ts_ip, fqdn, cert_dir = configure_tailscale_certs()
        run_smoketest(ts_ip, fqdn, cert_dir)
        
        logger.info("--- Stage 2 Provisioning Completed ---")
    except KeyboardInterrupt:
        logger.warning("Provisioning interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"FATAL ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
