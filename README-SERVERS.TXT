==============================================================================
SERVER PROVISIONING GUIDE
Target: Rocky Linux 9.x
==============================================================================

This repository contains idempotent Python scripts for bootstrapping a secure,
isolated server environment. The architecture strictly enforces rootless
containers, Tailscale-only ingress, and private SELinux volume relabeling.

PREREQUISITES
-------------
* Fresh Rocky Linux 9.x installation.
* A standard (non-root) user account with sudo privileges.
* Tailscale account/network access.

STAGE 1: CORE SYSTEM & SECURITY (linode-server-setup-stage-1.py)
----------------------------------------------------------------
This script establishes the baseline OS security posture.
1. Updates all system packages.
2. Installs Tailscale and Mosh.
3. Configures firewalld to strictly drop all public ingress.
4. Binds sshd explicitly to the tailscale0 interface.

Note: You must run 'sudo tailscale up' and authenticate your node to the
Tailnet before proceeding to Stage 2. If SSH drops after execution, reconnect
using the new Tailscale IP address.

STAGE 2: CONTAINER & DEV ENVIRONMENT (linode-server-setup-stage-2.py)
---------------------------------------------------------------------
This script provisions the rootless container runtime and validation path.
1. Injects a custom timestamped Yellow PS1 prompt.
2. Installs NVM, Node.js, Pyenv, and Virtualenv.
3. Installs Podman, passt-selinux, and required development headers.
4. Provisions Let's Encrypt TLS certificates via Tailscale MagicDNS.
5. Deploys a diagnostic Caddy container to verify rootless networking,
   SELinux :Z volume relabeling, and TLS termination.
   
Note: The script will automatically halt and require a user logout/login
cycle if shell profile modifications are made. Execute the script again
after logging back in to complete the process.

APPLICATION STACKS
------------------
Application gateway stacks are out of scope for RockyRoad itself. Use a
separate deployment repository, such as `Trailhead`, after the host baseline
has been validated with Stages 1 and 2.
