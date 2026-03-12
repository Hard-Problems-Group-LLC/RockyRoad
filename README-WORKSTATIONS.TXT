==============================================================================
WORKSTATION PROVISIONING GUIDE
Target: Rocky Linux 9.x
==============================================================================

This documentation covers the idempotent Python scripts for bootstrapping a
developer workstation. These scripts parallel the server environment but
include interactive prompts to detect, skip, or repair existing toolchains.

PREREQUISITES
-------------
* Rocky Linux 9.x workstation.
* Standard user account with sudo privileges.
* Tailscale account/network access.

STAGE 1: CORE SYSTEM (workstation-setup-stage-1.py)
---------------------------------------------------
1. Applies core OS updates and enables EPEL.
2. Interactively installs or repairs Tailscale and Mosh.

Note: Run 'sudo tailscale up' to connect your machine to the Tailnet before
running Stage 2.

STAGE 2: DEV ENVIRONMENT & CONTAINERS (workstation-setup-stage-2.py)
--------------------------------------------------------------------
This script sets up the local development toolchain and tests the container
runtime.
1. Injects a custom timestamped Cyan PS1 prompt (if none exists).
2. Interactively installs/repairs rootless Podman.
3. Interactively installs/repairs NVM, Node.js (LTS), Pyenv, and Virtualenv.
4. Provisions Let's Encrypt TLS certificates via Tailscale MagicDNS.
5. Deploys a diagnostic Caddy container (Dark UI) to verify local rootless
   networking and SELinux volume relabeling.

Note: Like the server script, this will safely halt and require a logout/login
if shell profiles (.bashrc/.bash_profile) are modified. Re-run the script
after logging back in.
