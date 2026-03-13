<!-- THEKNOWLEDGE_MANAGED_HEADER_START -->
This project uses The Hard Problems Group's specifications and guidance
framework, TheKnowledge. Both AI agents and human developers should reference
`TheKnowledge/AGENTS.md` for detailed instructions.

---

Any project-specific `AGENTS.md` content should go below this line and above
the managed TheKnowledge footer.
<!-- THEKNOWLEDGE_MANAGED_HEADER_END -->

# Agent Instructions: RockyRoad Provisioning

## Project Context
The `RockyRoad` repository contains idempotent Python 3.9+ provisioning
scripts for bootstrapping highly secure, isolated server and developer
workstation environments on Rocky Linux 9.x. These scripts establish the
foundational infrastructure required before higher-level container stacks are
deployed.

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

<!-- THEKNOWLEDGE_MANAGED_FOOTER_START -->
---

<!-- TheKnowledge-managed footer: place overrides here when the consuming
project needs behavior different from TheKnowledge's own repository setup. -->

## TheKnowledge Overrides
- Use `project-management/backlog.txt` as ordered pending work.
- Keep `project-management/tasks-in-progress.txt` minimal and current.
- Record finished work at the top of
  `project-management/completed-tasks.txt` with ISO 8601 timestamps.
- Track operator actions for AI in `project-management/ai-human-requests.txt`.
- Use `project-management/deferred.txt` for explicitly deferred work.
- Queue brief commit-ready summaries in
  `project-management/state/pending-commit-changes.txt`.
- Maintain bug lifecycle files under `project-management/bugs/`.
- Use `TheKnowledge/standards-and-practices/docs/`
  `AI-backlog-iteration.txt` when told to iterate the backlog.
- Use the consuming project's own `project-management/git-flow.txt` for branch
  and merge operations.
- Use `python TheKnowledge/scripts/git_standard_commit_push.py -m
  "<subject>"` so queued commit summaries become commit body text and the
  queue file is cleared after a successful local commit.
<!-- THEKNOWLEDGE_MANAGED_FOOTER_END -->
