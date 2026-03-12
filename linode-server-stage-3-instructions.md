# Architecture & Design Specification: Secure Subordinate Container Gateway
## System Context: Stage 3 Deployment

### 1. Environmental Baseline & Security Posture
This project operates in a highly pessimistic, strictly isolated environment.
The host OS is Rocky Linux 9.x. All remote access and ingress traffic is
restricted exclusively to the `tailscale0` overlay network interface via
strict `firewalld` zoning and daemon-level bindings. Public IP ingress is
entirely blackholed. 

The containerization strategy mandates **rootless Podman**. Consequently,
SELinux is actively enforcing boundaries. All host-to-container volume
mounts must explicitly utilize private unshared relabeling (the `:Z` flag)
to grant `container_file_t` contexts, avoiding permission-denied crashes.

### 2. High-Level Architecture
The system utilizes a single-entrypoint reverse proxy that delegates
authentication to a central Gateway application. Subordinate applications
run in entirely isolated containers, bound only to local, non-routable
interfaces or internal Podman networks, completely offloading access
control to the proxy/gateway tier.



#### 2.1 Component Overview
* **Ingress / Reverse Proxy (Caddy):** The absolute edge of the
    container network. Terminates TLS using Let's Encrypt certificates
    provisioned natively by the host's Tailscale daemon. Handles all
    internal routing.
* **Gateway Frontend (React/Vite):** The user-facing portal. Provides
    the login interface and the dynamic dashboard menu of available
    subordinate services.
* **Gateway Backend (FastAPI - Python 3.9):** Handles session
    management, credential verification, OAuth2 flows, and service
    discovery.
* **Database (PostgreSQL/BerkeleyDB):** Persistent storage for local
    user credentials, roles, and session state.
* **Subordinate Services:** Independent solution containers. They
    assume the network is hostile but rely on the ingress tier to block
    unauthenticated requests.

### 3. Authentication & Authorization Strategy
The Gateway Backend is the sole source of truth for identity. It must
support dual-stack authentication:

1.  **Local Authentication:** Username and password. Passwords must be
    hashed using a modern, memory-hard algorithm (Argon2id or bcrypt).
2.  **Google OAuth2:** Standard OpenID Connect flow using a Google Cloud
    Console Client ID/Secret, restricted to specific authorized email
    addresses or domains.

#### 3.1 The "Forward Auth" Pattern
To protect subordinate containers without rewriting authentication logic
for each one, Caddy will utilize a Forward Auth pattern. 

* When a user requests `https://<fqdn>/app/subordinate-1`, Caddy
    intercepts the request.
* Caddy issues an internal sub-request to the Gateway Backend (e.g.,
    `FastAPI:/api/auth/verify`).
* If FastAPI returns `200 OK` (valid session token/cookie), Caddy
    forwards the original request to the subordinate container.
* If FastAPI returns `401 Unauthorized`, Caddy intercepts the failure
    and issues a `302 Redirect` to the Gateway Frontend login page.

### 4. Service Discovery & Dynamic Routing
The Gateway Frontend must dynamically generate its navigation menu based
on available subordinate services. The Codex agent must implement the
following static approach to maintain absolute SELinux isolation and
minimize attack vectors:

* **Static/Config-Driven Routing:** A YAML or JSON configuration
    file mapped into the Gateway Backend container. When a new
    subordinate service is deployed, this file is updated, and the
    FastAPI endpoint parses it to serve the menu to the React frontend.
    Caddy routing is updated via `Caddyfile` reloads. Highly reliable,
    zero SELinux friction.

### 5. Implementation Requirements for Codex
* **Language & Frameworks:** Python 3.9 for backend (FastAPI), modern
    React/Vite for frontend. Caddy for ingress.
* **Idempotency:** All deployment scripts, `Containerfile`s, and
    `compose.yaml` (or podman pods) must be repeatable without
    destructive side-effects.
* **State Management:** Any container requiring persistent state
    (PostgreSQL data, BerkeleyDB files) must write to explicitly defined
    host directories mounted with `:Z`. Ephemeral container storage must
    not be trusted.
* **Secrets:** Google OAuth tokens, database passwords, and API keys
    must not be hardcoded. They must be passed via Podman secrets or
    tightly permissioned `.env` files owned strictly by the deployment
    user.
* **Code Quality:** Production-grade Python. Type hints enforced.
    Comprehensive documentation and verbose, explicit error handling
    required across all components. Do not interpolate dependencies; pin
    all library versions.
