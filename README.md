# RockyRoad

RockyRoad provides idempotent Python 3.9+ provisioning scripts for
commissioning and securing Rocky Linux 9.x servers and developer
workstations. The project is designed for Tailscale-only administration,
rootless Podman workloads, enforcing SELinux systems, and resilient remote
access with Mosh and SSH.

The repository focuses on the host-side bootstrap required before larger
containerized service stacks are deployed. Server flows are automated and
non-interactive. Workstation flows are interactive and offer explicit
conflict-resolution prompts when existing toolchains are already present.

## What RockyRoad Does

RockyRoad currently covers two implemented provisioning stages plus one
documented future stage:

1. Core operating system and network hardening.
2. Rootless container and developer environment bootstrap.
3. Planned gateway and application-container deployment architecture.

Today, the implemented scripts establish a baseline host that:

* Restricts ingress exclusively to the `tailscale0` overlay network.
* Blackholes public IP ingress through strict `firewalld` zoning.
* Keeps container workloads rootless under Podman.
* Preserves SELinux enforcing mode and uses explicit `:Z`/`:ro,Z` relabeling
  for host-to-container mounts.
* Provisions Tailscale certificates for TLS-enabled diagnostic checks.
* Uses idempotent provisioning logic so scripts can be rerun safely.

## Repository Layout

### Server Provisioning

* `linode-server-setup-stage-1.py`
  Applies the baseline server security posture. It updates packages,
  installs Tailscale and Mosh, configures restrictive firewall behavior,
  and binds SSH to the Tailscale interface.
* `linode-server-setup-stage-2.py`
  Provisions the rootless container runtime and supporting user
  environment. It installs NVM, Node.js, Pyenv, Virtualenv, Podman, and
  development headers, provisions Tailscale-managed TLS certificates, and
  runs an interactive Caddy-based smoketest for rootless networking and
  SELinux relabeling.

### Workstation Provisioning

* `workstation-setup-stage-1.py`
  Updates the workstation and interactively installs or repairs Tailscale
  and Mosh.
* `workstation-setup-stage-2.py`
  Interactively installs or repairs the local development toolchain and
  rootless Podman stack, provisions Tailscale certificates, and runs an
  interactive Caddy-based smoketest for local browser validation.

### Supporting Assets

* `install-codex-prerequisites.py`
  Bootstraps local repository development prerequisites on Rocky Linux 9.x,
  including `.venv`, Python quality tools, managed Git hooks, and the
  repo-local Codex CLI launcher.
* `README-SERVERS.TXT`
  Concise server-oriented operator guide.
* `README-WORKSTATIONS.TXT`
  Concise workstation-oriented operator guide.
* `linode-server-stage-3-instructions.md`
  Architecture and design specification for the planned Stage 3 gateway and
  subordinate service deployment model.
* `AGENTS.md`
  Contributor and automation guidance for AI-assisted work in this
  repository.
* `TheKnowledge/`
  Public standards, templates, and workflow submodule used to structure the
  project.

## Security Model

RockyRoad takes a pessimistic, defense-in-depth approach to host bootstrap:

* Assume the network is hostile.
* Allow remote administration only over Tailscale.
* Treat public ingress as denied by default.
* Keep container workloads rootless.
* Leave SELinux enabled and configure around it rather than bypassing it.
* Require explicit, minimal permissions for host resources exposed to
  containers.
* Fail fast when execution preconditions are not met, including accidental
  execution as `root`.

These constraints are not incidental implementation details. They are core
project policy.

## Execution Model

### Servers

Server scripts are intended for automated, non-interactive use after the
operator has created a standard user with `sudo` access and connected the
node to Tailscale.

Stage 1 establishes the host baseline. Stage 2 then configures the user
environment, rootless Podman runtime, Tailscale certificate material, and a
diagnostic smoketest path.

### Workstations

Workstation scripts follow the same security model but intentionally remain
interactive. When Podman, NVM, Node.js, Pyenv, or related configuration
already exists, the scripts prompt the operator to leave the installation
alone, delete and reinstall it, or repair/update it.

## Prerequisites

Before running the provisioning scripts, ensure the target machine has:

* Rocky Linux 9.x.
* A standard, non-root user account with `sudo` privileges.
* Tailscale account and tailnet access.

For server flows, expect to authenticate the node with `sudo tailscale up`
between Stage 1 and Stage 2.

## Stage Status

### Stage 1: Core System and Security

Implemented for servers and workstations.

### Stage 2: Container and Developer Environment

Implemented for servers and workstations, including interactive smoketests
that validate TLS, rootless Podman networking, and SELinux-aware volume
mounting.

### Stage 3: Gateway Deployment

Not yet implemented in this repository. The design intent is documented in
`linode-server-stage-3-instructions.md`. The current specification describes
a Tailscale-protected Caddy ingress tier, a FastAPI gateway backend, a
React/Vite frontend, and isolated subordinate application containers routed
through a forward-auth pattern.

## Development Notes

RockyRoad prefers:

* Python 3.9 compatibility unless a newer interpreter is explicitly needed.
* Strict type hints and explicit error handling.
* Standard-library-first implementation choices for bootstrap scripts.
* Idempotent behavior suitable for repeated provisioning runs.

Repository-specific contributor workflow details live in `AGENTS.md` and the
`TheKnowledge` submodule.

## License and Attribution

This project is intended to be distributed under the MIT License. See the
repository `LICENSE` file.

Copyright (C) 2025-2026 Hard Problems Group, LLC.

Authored by Matt Heck, President, Hard Problems Group, LLC.
