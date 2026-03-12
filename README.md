# Agent Instructions: RockyRoad Provisioning

## Project Context
The `RockyRoad` repository contains idempotent Python 3.9+ provisioning
scripts for bootstrapping highly secure, isolated server and developer
workstation environments on Rocky Linux 9.x. These scripts establish the
foundational infrastructure required to host complex, isolated container
stacks (Stage 3). 

This file defines the domain-specific constraints for this repository. It is
designed to be merged with the generalized operational standards provided by
`TheKnowledge` submodule.

## Core Architectural Values & Constraints
When modifying, extending, or executing code in this repository, AI agents
must strictly adhere to the following rules:

1.  **Pessimistic Security & Network Isolation:**
    * Assume a hostile network. All remote access and ingress traffic is
      restricted exclusively to the `tailscale0` overlay network.
    * Public IP ingress is blackholed via strict `firewalld` internal
      zoning.
2.  **Strictly Rootless Containerization:**
    * All container workloads must use rootless Podman. 
    * You are strictly forbidden from executing, configuring, or generating
      `podman` commands intended for the `root` user.
3.  **Mandatory SELinux Compliance:**
    * Rocky Linux runs SELinux in enforcing mode. Do not disable or bypass
      it. 
    * All host-to-container volume mounts must explicitly use the private
      unshared relabeling flag (`:ro,Z` or `:Z`) to apply
      `container_file_t` contexts.
4.  **Absolute Idempotency:**
    * Scripts must be safe to execute multiple times without destructive
      side effects or duplication (e.g., verify a line does not exist in
      `.bashrc` before appending it).
5.  **Execution Privilege:**
    * Scripts must be executed as a standard user with `sudo` privileges.
    * Scripts must aggressively enforce preconditions and fail fast if
      executed directly by UID 0.

## Workstation vs. Server Paradigms
* **Servers (`linode-server-setup-*.py`):** Automated, non-interactive
  execution. Scripts should autonomously achieve the desired state.
* **Workstations (`workstation-setup-*.py`):** Interactive execution.
  Scripts must prompt the user for conflict resolution (Leave, Delete,
  Repair) when existing toolchains or configurations are detected.

## Coding Standards
* **Language:** Python 3.9 preferred (Python 3.12 acceptable if specifically
  required).
* **Style:** Enforce strict type hints, comprehensive documentation, and
  verbose, explicit error handling. Avoid boilerplate.
* **Dependencies:** Rely strictly on Python standard libraries (e.g.,
  `subprocess`, `os`, `urllib`) to minimize bootstrap friction. Do not
  introduce `pip` dependencies for core provisioning scripts unless
  explicitly authorized.
