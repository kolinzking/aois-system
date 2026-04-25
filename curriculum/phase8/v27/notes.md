# v27 — Auth & Multi-tenancy: JWT, RBAC, OpenFGA, SPIFFE/SPIRE

⏱ **Estimated time: 8–10 hours**

---

## Prerequisites

v26 dashboard running. FastAPI accessible. Python 3.11+.

```bash
# JWT library
pip install python-jose[cryptography] passlib[bcrypt] python-multipart
python3 -c "from jose import jwt; print('ok')"
# ok

# Dashboard running
curl -s http://localhost:5173 | grep -c "AOIS"
# 1
```

---

## Learning Goals

By the end you will be able to:

- Implement JWT access + refresh token authentication in FastAPI
- Define four RBAC roles (viewer, analyst, operator, admin) and enforce them on API endpoints
- Explain why simple RBAC breaks when AI agents act on behalf of users — and what OpenFGA solves
- Build an OpenFGA authorization model for AOIS resource-level access control
- Explain SPIFFE/SPIRE: what problem it solves, where it sits in AOIS, and what breaks without it
- Connect the auth layer to the React dashboard login flow

---

## Why Auth Matters Here

The v26 dashboard has no authentication. Anyone with the URL can see all incidents and approve any remediation. This is fine for local development. It is not fine for a system that can trigger infrastructure changes.

Three distinct problems:

**1. API security**: the `/api/approve/{session_id}` endpoint must only be callable by operators or admins — not by a viewer who can only read.

**2. Agent-scoped authorization**: when the LangGraph agent calls `get_pod_logs` on behalf of user A, the authorization question is not "does the agent have permission?" — it is "does user A have permission to see logs in this namespace, right now?" Simple RBAC (role assigned to the agent) cannot express this. OpenFGA expresses it.

**3. Service-to-service identity**: the AOIS API, the Kafka consumer, and the LangGraph agent all communicate. A compromised pod should not be able to impersonate the AOIS API. SPIFFE/SPIRE provides workload identity — each service has a cryptographic identity that cannot be spoofed.

---

## JWT Authentication

### Token Flow

```
Client: POST /auth/login {username, password}
Server: validates credentials → issues access_token (15m) + refresh_token (7d)
Client: stores tokens (memory for access, httpOnly cookie for refresh)
Client: every request: Authorization: Bearer {access_token}
Server: validates JWT signature, extracts role, enforces RBAC
Client: when access_token expires → POST /auth/refresh with httpOnly cookie
Server: validates refresh_token → issues new access_token
```

---

### Implementation

```python
# auth/jwt_handler.py
"""JWT access and refresh token handling."""
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import os

_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
_ALGORITHM = "HS256"
_ACCESS_EXPIRE_MINUTES = 15
_REFRESH_EXPIRE_DAYS = 7

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=_ACCESS_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire, "type": "access"},
        _SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=_REFRESH_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        _SECRET_KEY,
        algorithm=_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    """Raises JWTError on invalid/expired token."""
    return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
```

---

### RBAC: Four Roles

```python
# auth/rbac.py
"""Role-based access control for AOIS API endpoints."""
from enum import Enum
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth.jwt_handler import decode_token
from jose import JWTError

_bearer = HTTPBearer()


class Role(str, Enum):
    viewer   = "viewer"    # read-only: list incidents, view analyses
    analyst  = "analyst"   # viewer + run investigations
    operator = "operator"  # analyst + approve remediations
    admin    = "admin"     # full access + manage users


_ROLE_HIERARCHY = {Role.viewer: 0, Role.analyst: 1, Role.operator: 2, Role.admin: 3}


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return {"user_id": payload["sub"], "role": payload["role"]}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_role(minimum_role: Role):
    """Dependency factory — enforces minimum role level."""
    def _check(user: dict = Depends(get_current_user)):
        user_level = _ROLE_HIERARCHY.get(Role(user["role"]), -1)
        required_level = _ROLE_HIERARCHY[minimum_role]
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{minimum_role}' or higher required. Your role: {user['role']}",
            )
        return user
    return _check
```

---

### Auth Endpoints in FastAPI

```python
# In main.py — add auth endpoints
from auth.jwt_handler import create_access_token, create_refresh_token, verify_password, decode_token
from auth.rbac import get_current_user, require_role, Role
from fastapi import Response
from jose import JWTError

# In-memory user store for v27 (replace with DB in production)
_USERS = {
    "admin": {"hashed_password": "$2b$12$...", "role": "admin"},
    "operator": {"hashed_password": "$2b$12$...", "role": "operator"},
    "analyst": {"hashed_password": "$2b$12$...", "role": "analyst"},
    "viewer": {"hashed_password": "$2b$12$...", "role": "viewer"},
}


@app.post("/auth/login")
async def login(body: dict, response: Response):
    username = body.get("username", "")
    password = body.get("password", "")
    user = _USERS.get(username)
    if not user or not verify_password(password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(username, user["role"])
    refresh_token = create_refresh_token(username)

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 3600,
    )
    return {"access_token": access_token, "role": user["role"]}


@app.post("/auth/refresh")
async def refresh_token(request: Request):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = _USERS.get(payload["sub"])
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return {"access_token": create_access_token(payload["sub"], user["role"])}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


# Protected endpoint — only operators+ can approve
@app.post("/api/approve/{session_id}")
async def approve_remediation(
    session_id: str,
    user: dict = Depends(require_role(Role.operator)),
):
    from langgraph_agent.graph import approve_and_continue
    result = await approve_and_continue(session_id)
    return {"status": "approved", "approved_by": user["user_id"], "result": result.get("remediation_result", "")}
```

---

## ▶ STOP — do this now

Test the role enforcement:

```bash
# Get a viewer token (should not be able to approve)
VIEWER_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "viewer", "password": "viewer-password"}' | jq -r .access_token)

# Try to approve — should be rejected
curl -s -X POST http://localhost:8000/api/approve/test-session \
  -H "Authorization: Bearer $VIEWER_TOKEN" | jq .
# {"detail": "Role 'operator' or higher required. Your role: viewer"}

# Get an operator token
OPERATOR_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "operator", "password": "operator-password"}' | jq -r .access_token)

# List incidents — should work for operator
curl -s http://localhost:8000/api/incidents \
  -H "Authorization: Bearer $OPERATOR_TOKEN" | jq 'length'
# 5 (or however many you have)
```

---

## OpenFGA: Fine-Grained Authorization

Simple RBAC assigns a role to a user. OpenFGA assigns relationships between users and specific resources.

### The Problem RBAC Cannot Solve

```
User A (operator) can approve remediations for namespace "payments"
User B (operator) can approve remediations for namespace "monitoring"
User A CANNOT approve in namespace "monitoring" even though both are "operator"
```

With RBAC: both operators have the same role. You cannot express namespace-level restrictions.

With OpenFGA:
```
user:A operator namespace:payments
user:B operator namespace:monitoring
```

Check: "can user:A approve in namespace:payments?" → yes
Check: "can user:A approve in namespace:monitoring?" → no

---

### OpenFGA Authorization Model for AOIS

```python
# auth/openfga.py
"""OpenFGA authorization checks for AOIS resource-level access."""
import httpx
import os
import logging

log = logging.getLogger("aois.openfga")

_FGA_API_URL = os.getenv("OPENFGA_API_URL", "http://localhost:8080")
_FGA_STORE_ID = os.getenv("OPENFGA_STORE_ID", "")


async def can_approve_in_namespace(user_id: str, namespace: str) -> bool:
    """Check if user can approve remediations in a specific namespace."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{_FGA_API_URL}/stores/{_FGA_STORE_ID}/check",
                json={
                    "tuple_key": {
                        "user": f"user:{user_id}",
                        "relation": "can_approve",
                        "object": f"namespace:{namespace}",
                    }
                },
            )
            return resp.json().get("allowed", False)
        except Exception as e:
            log.warning("OpenFGA check failed: %s — defaulting to deny", e)
            return False


async def write_namespace_permission(user_id: str, namespace: str, relation: str = "can_approve"):
    """Grant a user permission on a namespace."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{_FGA_API_URL}/stores/{_FGA_STORE_ID}/write",
            json={
                "writes": {
                    "tuple_keys": [{
                        "user": f"user:{user_id}",
                        "relation": relation,
                        "object": f"namespace:{namespace}",
                    }]
                }
            },
        )
```

The AOIS authorization model in OpenFGA DSL:

```
model
  schema 1.1

type user

type namespace
  relations
    define can_view: [user, user:*]
    define can_approve: [user] or admin from namespace
    define admin: [user]

type investigation
  relations
    define owner: [user]
    define can_view: owner or viewer from namespace
```

---

## ▶ STOP — do this now

Install and run OpenFGA locally:

```bash
# Using Docker
docker run -d -p 8080:8080 openfga/openfga run

# Create a store
curl -s -X POST http://localhost:8080/stores \
  -H "Content-Type: application/json" \
  -d '{"name": "aois"}' | jq .id
# "01HXXXXXXXXXXXXXX"

export OPENFGA_STORE_ID="01HXXXXXXXXXXXXXX"

# Write a permission: operator1 can approve in namespace "payments"
curl -s -X POST http://localhost:8080/stores/$OPENFGA_STORE_ID/write \
  -H "Content-Type: application/json" \
  -d '{
    "writes": {
      "tuple_keys": [{
        "user": "user:operator1",
        "relation": "can_approve",
        "object": "namespace:payments"
      }]
    }
  }' | jq .

# Check: can operator1 approve in payments?
curl -s -X POST http://localhost:8080/stores/$OPENFGA_STORE_ID/check \
  -H "Content-Type: application/json" \
  -d '{
    "tuple_key": {
      "user": "user:operator1",
      "relation": "can_approve",
      "object": "namespace:payments"
    }
  }' | jq .
# {"allowed": true}

# Check: can operator1 approve in monitoring? (not granted)
curl -s -X POST http://localhost:8080/stores/$OPENFGA_STORE_ID/check \
  -H "Content-Type: application/json" \
  -d '{
    "tuple_key": {
      "user": "user:operator1",
      "relation": "can_approve",
      "object": "namespace:monitoring"
    }
  }' | jq .
# {"allowed": false}
```

---

## SPIFFE/SPIRE: Workload Identity

### The Problem

The AOIS API, Kafka consumer, and LangGraph agent all run as separate processes or pods. When the Kafka consumer calls the AOIS API, how does the API know the caller is actually the Kafka consumer and not an attacker who has compromised a pod?

With static secrets (API keys, passwords): the API key can be stolen from environment variables. Once stolen, the attacker can impersonate the consumer indefinitely.

SPIFFE/SPIRE solves this with short-lived X.509 certificates:
- Each workload (AOIS API, Kafka consumer, agent) has a unique SPIFFE ID (`spiffe://aois.internal/kafka-consumer`)
- SPIRE issues a certificate valid for 1 hour
- The workload presents this certificate when calling other services
- mTLS: both sides verify each other's certificate
- A compromised certificate expires in 1 hour. There are no long-lived secrets to steal.

---

### SPIFFE/SPIRE in AOIS

```
SPIRE Server (runs on Hetzner)
    ↓ issues SVIDs (certificates)
SPIRE Agent (runs as DaemonSet on each node)
    ↓ delivers SVIDs via Unix socket
Workload (AOIS API, Kafka consumer, LangGraph agent)
    ↓ presents SVID in mTLS handshake
Other Workload
    ↑ verifies SVID against SPIRE trust domain
```

Each workload's SPIFFE ID:
- AOIS API: `spiffe://aois.internal/aois-api`
- Kafka consumer: `spiffe://aois.internal/kafka-consumer`
- LangGraph agent: `spiffe://aois.internal/langgraph-agent`

mTLS configuration in the nginx nginx proxy:

```nginx
# nginx/aois-internal.conf — mTLS for service-to-service
server {
    listen 8443 ssl;
    ssl_certificate     /run/spire/certs/svid.pem;
    ssl_certificate_key /run/spire/certs/svid-key.pem;
    ssl_client_certificate /run/spire/certs/bundle.pem;
    ssl_verify_client on;

    location / {
        proxy_pass http://aois-api:8000;
    }
}
```

---

### SPIRE Deployment on Hetzner k3s

```bash
# Apply SPIRE server deployment
kubectl apply -f k8s/spire/server.yaml
kubectl apply -f k8s/spire/agent.yaml

# Wait for SPIRE server to be ready
kubectl wait --for=condition=ready pod -l app=spire-server -n spire --timeout=120s

# Verify: check the SPIRE server bundle
kubectl exec -n spire -c spire-server $(kubectl get pod -n spire -l app=spire-server -o name) -- \
  /opt/spire/bin/spire-server bundle show -format spiffe
```

The SPIRE node attestor for k3s must use the Kubernetes workload attestor (`k8s`) — not `aws_iid` or `gcp_iit`. On bare metal VPS (Hetzner), only the k8s attestor applies:

```yaml
# k8s/spire/agent.yaml — relevant section
nodeAttestor "k8s_sat" {
  cluster = "hetzner-k3s"
}
workloadAttestor "k8s" {
  skip_kubelet_verification = true  # Required for k3s — kubelet uses different certs
}
```

⚠️ **SPIFFE/SPIRE retrofit note (from April 2026 audit)**: This is the workload identity fix identified for v6. The gap: v6 shipped with static API keys in k8s/secret.yaml. SPIRE closes that gap by giving every workload a short-lived, verified identity. By implementing SPIRE here in v27, we close the audit finding. The live cluster now has workload identity — no long-lived secrets needed for service-to-service auth.

---

## ▶ STOP — do this now

Verify SPIRE is issuing SVIDs to workloads:

```bash
# Check the SPIRE agent is connecting to workloads
kubectl logs -n spire -l app=spire-agent --tail=20

# Get the SVID for the AOIS API workload
kubectl exec -n aois -c spire-helper $(kubectl get pod -n aois -l app=aois -o name | head -1) -- \
  /opt/spire/bin/spire-agent api fetch x509 -socketPath /run/spire/sockets/agent.sock \
  | grep "SPIFFE ID"
# SPIFFE ID: spiffe://aois.internal/aois-api
```

---

## Supabase Alternative: Full-Stack Managed Platform

Supabase is Postgres + pgvector + auth + realtime + edge functions — the full AOIS stack in one managed platform.

The pattern: instead of deploying FastAPI + Postgres + Redis + authentication separately, Supabase handles auth (with JWT by default), provides a Postgres database with row-level security, and offers a realtime subscription layer over WebSockets.

For AOIS, the Supabase integration point is authentication: replace the hand-rolled JWT system with Supabase Auth.

```python
# Using Supabase Auth instead of hand-rolled JWT
from supabase import create_client, Client
import os

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY"),
)


async def login_with_supabase(email: str, password: str) -> dict:
    response = supabase.auth.sign_in_with_password({"email": email, "password": password})
    return {
        "access_token": response.session.access_token,
        "user": response.user.dict(),
    }
```

When to use Supabase vs hand-rolled: Supabase accelerates development by 2-3 days on auth alone. The tradeoff: you are dependent on a managed service. For a portfolio project or startup, Supabase is the right call. For an enterprise system with compliance requirements, hand-rolled on your own infrastructure gives full control.

---

## Common Mistakes

### 1. Access token stored in localStorage (XSS vulnerability)

```tsx
// Wrong — localStorage is accessible to any JavaScript on the page
localStorage.setItem('access_token', token)

// Correct — keep access token in memory (React state)
const [accessToken, setAccessToken] = useState<string | null>(null)
// Refresh token in httpOnly cookie — cannot be accessed by JavaScript
```

If a third-party script is compromised (supply chain attack), it cannot steal a token from memory before the page unloads. A token in localStorage can be exfiltrated by any script that runs on the page.

---

### 2. JWT secret key not rotated

The JWT_SECRET_KEY in `.env` signs all tokens. If it leaks, all tokens issued with it are compromised — there is no per-token revocation with JWT.

Mitigations:
- Rotate the key every 90 days (all existing tokens become invalid — users must log in again)
- Use short access token expiry (15 minutes) — even a leaked token expires quickly
- Maintain a token blocklist in Redis for emergency revocation of specific tokens

---

### 3. OpenFGA check not called before approve

```python
# Wrong — RBAC check only, no namespace-level check
@app.post("/api/approve/{session_id}")
async def approve_remediation(user: dict = Depends(require_role(Role.operator))):
    await approve_and_continue(session_id)  # can approve in ANY namespace

# Correct — RBAC + OpenFGA namespace check
@app.post("/api/approve/{session_id}")
async def approve_remediation(session_id: str, user: dict = Depends(require_role(Role.operator))):
    incident = await get_incident(session_id)
    allowed = await can_approve_in_namespace(user["user_id"], incident["namespace"])
    if not allowed:
        raise HTTPException(403, "Not authorized for this namespace")
    await approve_and_continue(session_id)
```

---

## Troubleshooting

### `JWTError: Signature has expired`

The access token (15-minute TTL) has expired. The client should catch 401 responses and call `/auth/refresh` automatically.

```tsx
// In fetch wrapper — auto-refresh on 401
async function apiFetch(url: string, options?: RequestInit) {
  const res = await fetch(url, {
    ...options,
    headers: { ...options?.headers, Authorization: `Bearer ${accessToken}` },
  })
  if (res.status === 401) {
    const refreshRes = await fetch('/auth/refresh', { method: 'POST', credentials: 'include' })
    if (refreshRes.ok) {
      const { access_token } = await refreshRes.json()
      setAccessToken(access_token)
      return fetch(url, { ...options, headers: { Authorization: `Bearer ${access_token}` } })
    }
  }
  return res
}
```

---

### OpenFGA: `store not found`

```
{"error": "store not found"}
```

The `OPENFGA_STORE_ID` environment variable is not set or is incorrect. Run:

```bash
curl -s http://localhost:8080/stores | jq '.stores[].id'
```

Copy the store ID and set `OPENFGA_STORE_ID`.

---

## Connection to Later Phases

### To v28 (CI/CD)
The JWT secret key is stored as a Kubernetes Secret, managed via External Secrets Operator pulling from Vault. The GitHub Actions pipeline does not have direct access to the JWT key — it only builds and deploys the image.

### To v34.5 (Capstone)
The RBAC model is the human oversight layer. During the game day, P1 incidents require operator-level approval. The approval audit trail (who approved what, when, from which IP) is in the `investigation_reports` table with `approved_by` populated by the auth system.

---


## Build-It-Blind Challenge

Close the notes. From memory: write `create_access_token()` — accepts user_id and role, signs with HS256, sets 15-minute expiry, and `create_refresh_token()` — same structure with 7-day expiry. Write the FastAPI dependency that validates the access token and injects the current user. 20 minutes.

```python
token = create_access_token(user_id="collins", role="operator")
user = get_current_user(token)
print(user.role)   # operator
```

---

## Failure Injection

Use the wrong algorithm to verify a token and observe the error:

```python
jwt.decode(token, SECRET_KEY, algorithms=["RS256"])   # signed with HS256
# InvalidAlgorithmError or DecodeError?
```

Then decode a token without verifying the signature:

```python
jwt.decode(token, options={"verify_signature": False})
# This succeeds — and this is how JWT vulnerabilities happen
```

An attacker who knows you are not verifying the signature can forge any token. Understand why `verify_signature=False` exists (debugging) and why it must never appear in production code.

---

## Osmosis Check

1. OpenFGA stores the authorisation model — user X can perform action Y on resource Z. A user with `viewer` role attempts to approve a remediation (requires `operator` role). The check fails. But OpenFGA itself is down. Does the AOIS endpoint fail open (allow) or fail closed (deny)? Which is correct for a security gate — and which is correct for a health check endpoint?
2. SPIFFE/SPIRE (v6) issues SVIDs for service-to-service auth. JWT (v27) handles user-to-service auth. An incoming request to `/approve-remediation` has both a valid JWT and a valid SVID. Which identity does the OpenFGA check use — the user identity or the service identity? Why?

---

## Mastery Checkpoint

1. Generate a viewer token and an operator token. Confirm `GET /api/incidents` works for both. Confirm `POST /api/approve/{id}` returns 403 for the viewer and 200 for the operator.

2. Start OpenFGA locally. Create two users: `user:alice` with `can_approve` on `namespace:payments`, and `user:bob` with `can_approve` on `namespace:monitoring`. Run the OpenFGA check for both namespaces with both users — show all four results.

3. Add RBAC to the `/api/chat` streaming endpoint. Which role should be required? Implement it.

4. The `JWT_SECRET_KEY` is `"change-me-in-production"` in the default config. What happens if this ships to production? Write the specific exploit: how does an attacker use this to gain admin access?

5. Explain to a junior engineer: what is the difference between authentication (JWT) and authorization (RBAC + OpenFGA)? Give one example where authentication succeeds but authorization fails.

6. Explain to a senior engineer: why does fine-grained authorization (OpenFGA) matter for agentic systems specifically, as opposed to web apps with human users only?

7. Describe the SPIFFE/SPIRE deployment for the Hetzner k3s cluster. What node attestor is used and why? What breaks if `skip_kubelet_verification` is false on k3s?

**The mastery bar:** AOIS has a working login flow, four roles enforced on every endpoint, OpenFGA namespace-level checks on the approve endpoint, and SPIRE deploying short-lived workload certificates — no long-lived service-to-service secrets anywhere in the system.

---

## 4-Layer Tool Understanding

### JWT (JSON Web Tokens)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | After a user logs in, the server needs to know who is making each subsequent request without asking for a password every time. JWT is a signed token the user carries — like a wristband at a concert. The server can verify it without a database lookup. |
| **System Role** | Where does it sit in AOIS? | Between the browser (or API client) and every FastAPI endpoint. The login endpoint issues a JWT; every subsequent request includes it in the Authorization header. FastAPI's `get_current_user` dependency decodes it and extracts the user ID and role before the endpoint handler runs. |
| **Technical** | What is it, precisely? | A base64-encoded JSON object signed with HMAC-SHA256 (or RSA). Contains: subject (user ID), role, expiry. The signature is verified against the secret key — if the payload is tampered with, the signature becomes invalid. Access token: 15-minute TTL. Refresh token: 7-day TTL, stored in httpOnly cookie. |
| **Remove it** | What breaks, and how fast? | Remove JWT → either every request requires a password (unusable) or there is no authentication at all. Any user with the URL can approve any remediation, read all incidents, and trigger agent investigations. The approve gate exists in code but is callable by anyone. |

### OpenFGA (Fine-Grained Authorization)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | RBAC says "all operators can approve remediations." OpenFGA says "operator Alice can approve remediations for the payments namespace, and operator Bob can approve for the monitoring namespace." When you have many namespaces and many operators, RBAC cannot express this — OpenFGA can. |
| **System Role** | Where does it sit in AOIS? | Between the RBAC check (does this user have the operator role?) and the LangGraph approval gate (does this user have permission to approve in the specific namespace of this incident?). Both checks must pass before `approve_and_continue()` is called. |
| **Technical** | What is it, precisely? | A Google Zanzibar-inspired authorization service. Stores relationship tuples (user, relation, object). Answers: "does user X have relation Y to object Z?" The AOIS authorization model defines types (user, namespace, investigation) and relations (can_view, can_approve, admin). The service resolves transitive relationships — admin of namespace implies can_approve in namespace. |
| **Remove it** | What breaks, and how fast? | Remove OpenFGA → only RBAC remains. All operators can approve in all namespaces. An operator granted access for monitoring can approve a remediation that restarts a production payments pod. Namespace-level isolation is gone. In a multi-tenant environment (multiple teams, multiple namespaces), this means any operator can affect any team's infrastructure. |

### SPIFFE/SPIRE (Workload Identity)

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | When the Kafka consumer calls the AOIS API, the API has no way to verify it is actually the Kafka consumer and not an attacker. SPIFFE gives every service a cryptographic identity — like a passport — that is automatically renewed every hour. The API checks the passport before accepting the call. |
| **System Role** | Where does it sit in AOIS? | Between every pair of AOIS services that call each other: Kafka consumer → AOIS API, LangGraph agent → AOIS API. SPIRE Agent runs as a DaemonSet, delivers certificates to each pod via a Unix socket. Every outbound call uses mTLS with the SPIFFE certificate. No long-lived API keys needed for service-to-service auth. |
| **Technical** | What is it, precisely? | SPIFFE is a standard for workload identity: each workload gets a SPIFFE ID (URI: `spiffe://trust-domain/path`) and an X.509 certificate (SVID) signed by SPIRE. SPIRE is the implementation: a server that signs SVIDs and agents that deliver them to workloads. SVIDs expire every 1 hour and are automatically rotated. mTLS: both sides present and verify SVIDs. Node attestation determines which workloads are eligible for which SPIFFE IDs. |
| **Remove it** | What breaks, and how fast? | Remove SPIRE → service-to-service auth falls back to API keys in environment variables. A compromised pod can read its API key from the environment and impersonate that service indefinitely. SPIRE limits the blast radius of a compromised pod to 1 hour — the current certificate's lifetime. Without it, a stolen API key is valid until manually rotated. |
