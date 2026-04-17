# v4 — Docker: Containerizing AOIS

## What this version builds

The Phase 1 FastAPI application is already working. v4 takes it and puts it in a container. The code does not change — only the environment it runs in changes.

By the end:
- A multi-stage Dockerfile that produces a minimal, secure image
- Docker Compose that starts AOIS + Redis + Postgres with one command
- Trivy vulnerability scan with zero HIGH/CRITICAL findings

This is where the project transitions from "runs on my machine" to "runs anywhere."

---

## Prerequisites

- v1–v3 complete — AOIS is working and all tests pass
- Docker is installed and running

Verify:
```bash
docker --version
```
Expected:
```
Docker version 26.x.x, build abc1234
```

```bash
docker compose version
```
Expected:
```
Docker Compose version v2.x.x
```

If either fails, Docker is not installed or the daemon is not running. In Codespaces, Docker is pre-installed.

Verify Docker daemon is running:
```bash
docker info 2>&1 | head -5
```
Expected: starts with `Client: Docker Engine...`. If you see `Cannot connect to the Docker daemon`, the Docker service needs to start:
```bash
sudo service docker start
```

---

## Learning goals

By the end of this version you will understand:
- What a Docker image is vs a Docker container
- What a multi-stage build is and why it produces smaller, safer images
- Why running as non-root matters for container security
- What Docker Compose orchestrates and why it matters
- What Trivy scans for and how to interpret its output
- How environment variables reach containers without entering the image

---

## Part 1 — Docker concepts

**Image vs container:**
- **Image** — a read-only snapshot of a filesystem. Like a class definition.
- **Container** — a running instance of an image. Like an object instantiation.

One image → many containers. You build the image once. You run as many containers as you need.

**Layers:**
Every `RUN`, `COPY`, and `ADD` instruction in a Dockerfile creates a new layer. Layers are cached — if nothing changed in a layer, Docker reuses the cached version. This makes rebuilds fast.

**The registry:**
Images are stored in registries. Docker Hub is the default public registry. GHCR (GitHub Container Registry) is where AOIS images will live in Phase 9. When you run `FROM python:3.11-slim`, Docker pulls from Docker Hub.

---

## Part 2 — The Dockerfile: section by section

View the current Dockerfile:
```bash
cat /workspaces/aois-system/Dockerfile
```

Walk through every line:

### Stage 1 — Builder

```dockerfile
FROM python:3.11-slim AS builder
```
`python:3.11-slim` is a minimal Debian-based Python image. `slim` omits documentation, locale data, and many packages that the full image includes.

Why not `python:3.11`? The full image includes build tools, compilers, and system packages needed for building software — not for running it. More packages = more CVEs = larger attack surface. `slim` gives the same Python with a fraction of the footprint.

`AS builder` names this stage. The next stage can copy from it.

```dockerfile
WORKDIR /app
```
Sets the working directory inside the container. All subsequent `COPY` and `RUN` commands operate relative to `/app`. Creates the directory if it does not exist. More explicit than `RUN mkdir /app && cd /app`.

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
```

`COPY requirements.txt .` — copies `requirements.txt` from your machine (the build context) into `/app/` inside the container.

**Why copy requirements.txt first, before main.py?**
Docker layer caching. If requirements.txt has not changed since the last build, Docker reuses the cached `pip install` layer. The slow part (downloading packages) is skipped. If you copied all files first, any change to `main.py` would invalidate the pip install cache.

`--no-cache-dir` — pip normally caches downloads. Inside a container image, this cache wastes space without benefit. Skip it.

`--prefix=/install` — installs packages into `/install` instead of the system Python path. This makes it trivial to copy just the installed packages into the next stage with a single `COPY --from=builder /install /usr/local`.

### Stage 2 — Runtime

```dockerfile
FROM python:3.11-slim AS runtime
```
A completely fresh, clean `python:3.11-slim` image. No build tools. No intermediate files. Not even the files from Stage 1 — except what you explicitly copy.

```dockerfile
RUN useradd --create-home --shell /bin/bash aois
WORKDIR /home/aois/app
```

`useradd` creates a non-root user named `aois`.

**Why non-root?** Containers run as root by default. If an attacker exploits a vulnerability in your application and escapes the container, they land on the host as the user the container ran as. If that is root: game over. If that is the `aois` user with no privileges: the blast radius is contained.

Non-root is one of the most important container security practices. It costs nothing and protects a lot.

```dockerfile
COPY --from=builder /install /usr/local
```
Copies the installed Python packages from Stage 1's `/install` directory into the runtime image's Python path (`/usr/local`). Only the packages. Not pip. Not build tools. Not the source downloads. Nothing else from Stage 1.

```dockerfile
RUN pip uninstall -y setuptools wheel 2>/dev/null || true
```
`setuptools` and `wheel` are build tools — needed to compile packages but not to run them. They also contain vendored copies of other libraries that carry their own CVEs. Removing them from the runtime image eliminates those CVEs entirely.

`2>/dev/null || true` — the `2>/dev/null` silences the error output, and `|| true` prevents the build from failing if these packages are not installed.

```dockerfile
COPY main.py .
```
Copies your application code. Only `main.py` — not the entire project directory (curriculum notes, practice files, etc. would unnecessarily bloat the image).

```dockerfile
USER aois
```
Switches to the non-root user. **Must come after all `COPY` commands.** Copying files as root is fine — the files get appropriate ownership. The running process must not be root.

```dockerfile
EXPOSE 8000
```
Documents that the container listens on port 8000. This does not actually open the port — port mapping is done at runtime (`-p 8000:8000`). Think of `EXPOSE` as metadata for humans and tools reading the Dockerfile.

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```
The command that runs when the container starts. JSON array format (`["cmd", "arg1", "arg2"]`) is preferred over shell format (`uvicorn main:app ...`) because it runs the process directly without spawning a shell. The process runs as PID 1, which receives Docker's stop signals correctly.

---

## Part 3 — Building and checking the image

### Step 1: Build
```bash
cd /workspaces/aois-system
docker build -t aois:v4 .
```

Expected output (first build, takes a few minutes):
```
[+] Building 45.2s (12/12) FINISHED
 => [internal] load build definition from Dockerfile
 => [internal] load .dockerignore
 => [builder 1/4] FROM docker.io/library/python:3.11-slim
 => [builder 2/4] WORKDIR /app
 => [builder 3/4] COPY requirements.txt .
 => [builder 4/4] RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
 => [runtime 1/5] FROM docker.io/library/python:3.11-slim
 => [runtime 2/5] RUN useradd --create-home --shell /bin/bash aois
 => [runtime 3/5] WORKDIR /home/aois/app
 => [runtime 4/5] COPY --from=builder /install /usr/local
 => [runtime 5/5] RUN pip uninstall -y setuptools wheel 2>/dev/null || true
 => [runtime 6/5] COPY main.py .
 => exporting to image
 => => naming to docker.io/library/aois:v4
```

Rebuild (requirements unchanged — uses cache):
```bash
docker build -t aois:v4 .
```
Expected: much faster. You will see `CACHED` on the pip install layer.

### Step 2: Check the image
```bash
docker images aois:v4
```
Expected:
```
REPOSITORY   TAG   IMAGE ID       CREATED         SIZE
aois         v4    abc123def456   2 minutes ago   245MB
```
The size should be roughly 200-300MB. A non-optimized image with all build tools would be 600MB+.

### Step 3: Verify non-root user
Run the container and check:
```bash
docker run --rm --env-file .env -p 8000:8000 --name aois-test aois:v4 &
sleep 3    # wait for startup
docker exec aois-test whoami
```
Expected:
```
aois
```

Test the server:
```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```
Expected:
```json
{"status": "ok"}
```

Stop the test container:
```bash
docker stop aois-test
```

---

## Part 4 — Scanning with Trivy

Install Trivy:
```bash
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
  | sh -s -- -b $HOME/.local/bin
export PATH=$PATH:$HOME/.local/bin
trivy --version
```
Expected: `Version: 0.xx.x`

If the PATH change does not persist, add it:
```bash
echo 'export PATH=$PATH:$HOME/.local/bin' >> ~/.bashrc
source ~/.bashrc
```

### Run the scan

```bash
trivy image --severity HIGH,CRITICAL aois:v4
```

Expected output (clean image):
```
aois:v4 (debian 12.5)

Total: 0 (HIGH: 0, CRITICAL: 0)
```

Or you may see some findings:
```
┌──────────────────┬────────────────┬──────────┬───────────────────┬───────────────┬─────────────────┐
│     Library      │ Vulnerability  │ Severity │ Installed Version │ Fixed Version │      Title      │
├──────────────────┼────────────────┼──────────┼───────────────────┼───────────────┼─────────────────┤
│ libncursesw6     │ CVE-2023-50495 │ HIGH     │ 6.4-4             │               │ ncurses: ...   │
└──────────────────┴────────────────┴──────────┴───────────────────┴───────────────┴─────────────────┘
```

### Reading the Trivy output

Every finding tells you:
- **Library** — which package has the vulnerability
- **CVE ID** — the unique identifier (searchable at nvd.nist.gov)
- **Severity** — CRITICAL, HIGH, MEDIUM, LOW
- **Installed Version** — what is in your image
- **Fixed Version** — what version fixes it (empty = no fix available yet)

### Fixing Python package CVEs

If a Python package shows a CVE with a fixed version:
```bash
# Add the fixed version to requirements.txt
echo "jaraco.context>=6.1.0" >> requirements.txt

# Rebuild with no cache to pick up the fix
docker build --no-cache -t aois:v4 .

# Scan again
trivy image --severity HIGH,CRITICAL aois:v4
```

### Handling OS CVEs with no fix

Some OS packages (like `libncursesw6`) may show `HIGH` with no fixed version. This means the Linux distribution has not released a patch yet.

Correct response:
1. **Document it** — note the CVE, note it has no fix
2. **Accept the risk** — it is not actionable until a patch ships
3. **Re-scan regularly** — when a fix arrives, it shows as `fixed`

The goal is zero **fixable** HIGH/CRITICAL vulnerabilities. An unfixable vulnerability is noted and tracked.

---

## Part 5 — Docker Compose

View the current compose file:
```bash
cat /workspaces/aois-system/docker-compose.yml
```

### Why Docker Compose?

In production, AOIS will use:
- Redis (rate limiting in v5, caching later)
- Postgres (persistent incident storage, agent memory in v20)
- AOIS itself

Starting and linking these manually with `docker run` commands would be:
```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
docker run -d --name postgres -p 5432:5432 -e POSTGRES_DB=aois -e POSTGRES_USER=aois -e POSTGRES_PASSWORD=secret postgres:16-alpine
docker run -d --name aois --env-file .env -p 8000:8000 --link redis --link postgres aois:v4
```

Docker Compose replaces all of that with `docker compose up`. One file, one command.

### Compose file explained

```yaml
services:
  aois:
    build: .                    # build image from Dockerfile in current directory
    ports:
      - "8000:8000"             # host_port:container_port
    env_file:
      - .env                    # inject variables from .env file into container
    depends_on:
      - redis
      - postgres
    restart: unless-stopped     # restart if container crashes, not if manually stopped

  redis:
    image: redis:7-alpine       # use this existing image from Docker Hub
    ports:
      - "6379:6379"
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: aois
      POSTGRES_USER: aois
      POSTGRES_PASSWORD: aois_local
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data   # persist data across container restarts
    restart: unless-stopped

volumes:
  postgres_data:                # declares the named volume
```

**Key concepts:**

`env_file: .env` — the `.env` file's content becomes environment variables inside the AOIS container. The secrets never enter the image — they are injected at runtime. This is correct secrets handling at the container level. (Phase 3+ will use Vault for production secrets.)

`depends_on` — tells Compose to start Redis and Postgres before starting AOIS. Important: `depends_on` waits for the container to start, not for the service inside to be ready. Postgres takes a few seconds to initialize after the container starts. For production, you use `condition: service_healthy` with healthchecks.

`volumes: postgres_data:` — a named Docker volume that persists beyond the container lifecycle. If Postgres container is recreated (after `docker compose down && docker compose up`), the data survives. Without a volume, all database data is lost when the container stops.

`restart: unless-stopped` — if the process crashes, Docker automatically restarts it. Does not restart if you run `docker compose stop` manually.

`redis:7-alpine` and `postgres:16-alpine` — Alpine variants. Alpine Linux is a minimal distribution (~5MB) with far fewer packages than Debian. Smaller image, fewer CVEs, faster pulls.

---

## Part 6 — Running with Docker Compose

### Start everything

```bash
cd /workspaces/aois-system
docker compose up -d
```

`-d` = detached (background). Without it, logs stream to your terminal.

Expected output:
```
[+] Running 4/4
 ✔ Network aois-system_default  Created
 ✔ Container aois-system-postgres-1  Started
 ✔ Container aois-system-redis-1     Started
 ✔ Container aois-system-aois-1      Started
```

### Check status

```bash
docker compose ps
```
Expected:
```
NAME                       IMAGE          COMMAND                  STATUS
aois-system-aois-1         aois-system    "uvicorn main:app..."    Up 30 seconds
aois-system-postgres-1     postgres:16-alpine   "docker-entrypoint..."  Up 30 seconds
aois-system-redis-1        redis:7-alpine  "docker-entrypoint..."   Up 30 seconds
```

All three should show `Up`.

### Test the containerized service

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```
Expected:
```json
{"status": "ok"}
```

Full analysis test:
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service memory_limit=512Mi restarts=14"}' \
  | python3 -m json.tool
```
Expected: valid `IncidentAnalysis` response.

### View logs

```bash
docker compose logs aois           # all logs
docker compose logs -f aois        # follow/stream
docker compose logs postgres       # database logs
```

### Stop everything

```bash
docker compose down           # stop and remove containers (data volume persists)
docker compose down -v        # stop, remove containers AND volumes (wipes database data)
```

---

## Troubleshooting

**"docker: Cannot connect to the Docker daemon":**
```bash
sudo service docker start
# or
sudo systemctl start docker
```

**Build fails with "COPY failed: file not found: requirements.txt":**
You are not running `docker build` from the project root, or `requirements.txt` is missing.
```bash
pwd                              # must be /workspaces/aois-system
ls requirements.txt              # must exist
docker build -t aois:v4 .        # the . sends current directory as build context
```

**Container starts but /health returns connection refused:**
```bash
docker compose logs aois         # read the startup logs for errors
docker compose ps                # is the container actually running?
```
Common causes: Python import error (check logs), wrong API key (check logs for AuthenticationError).

**Trivy reports many CRITICAL/HIGH findings:**
```bash
trivy image --severity HIGH,CRITICAL --format json aois:v4 | python3 -m json.tool | grep -A5 '"FixedVersion"'
```
Focus on CVEs with a non-empty `FixedVersion`. Those are actionable. CVEs with empty `FixedVersion` have no available fix yet.

**"postgres-1 exited with code 1":**
```bash
docker compose logs postgres     # read Postgres startup error
```
Common cause: the data volume from a previous run has an incompatible format. Fix:
```bash
docker compose down -v           # wipe volumes
docker compose up -d             # fresh start
```

**"ERROR: Service 'aois' failed to build":**
Read the full error — it is usually a pip install failure. Check your requirements.txt for typos or unavailable packages.

---

## Git — committing v4

```bash
cd /workspaces/aois-system
git add Dockerfile docker-compose.yml requirements.txt
git status    # verify nothing unexpected is staged
git diff --staged   # read what you are about to commit
git commit -m "v4: multi-stage Dockerfile, Docker Compose (AOIS + Redis + Postgres), Trivy clean"
```

Do NOT commit:
- `.env` (secrets)
- `venv/` (local Python environment)
- `__pycache__/` (Python bytecode)
- The built Docker image itself (images go to a registry, not git)

---

## What v4 does not have (solved in v5)

| Gap | What can happen | Fixed in |
|-----|----------------|---------|
| No rate limiting | Anyone can flood the endpoint with 1000 requests per second | v5: slowapi |
| No input size limit | A 500KB "log" consumes enormous tokens and costs | v5: payload middleware |
| No prompt injection defense | Attacker embeds instructions in log content | v5: sanitize_log + hardened system prompt |
| API keys in flat `.env` | Readable by any process on the host | Phase 3+: HashiCorp Vault |
| Image not signed | No way to verify the image came from you | Phase 9 (v28): Cosign |

---

## Connection to later phases

- **Phase 3 (v6–v8)**: The same Dockerfile gets deployed to a k3s Kubernetes cluster on Hetzner. `docker build` becomes `docker build && docker push ghcr.io/...` and ArgoCD deploys it.
- **Phase 3 (v9)**: Redis (already in Docker Compose) gets used by KEDA for scaling decisions and by the rate limiter for distributed state.
- **Phase 6 (v16)**: Docker Compose grows to include Prometheus, Grafana, Loki, and Tempo for the full observability stack.
- **Phase 8 (v26)**: The React dashboard service is added to Docker Compose alongside AOIS, served by nginx.
- **The pattern**: Docker Compose is your local development environment. Helm (Phase 3 v7) is the same thing for Kubernetes. The same services, different orchestration layer.
