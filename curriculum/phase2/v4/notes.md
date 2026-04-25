# v4 — Docker: Containerizing AOIS
⏱ **Estimated time: 4–6 hours**

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

> **▶ STOP — do this now**
>
> Before building, read the Dockerfile and answer these questions:
> ```bash
> cat /workspaces/aois-system/Dockerfile
> ```
> 1. How many stages are there? (Look for `FROM` lines)
> 2. What is installed in the builder stage that is NOT in the final image?
> 3. What user does the container run as? (Look for `USER`)
> 4. What files are copied from the builder into the final image?
>
> Write down your answers, then build and verify:
> ```bash
> docker build -t aois:v4-check . 2>&1 | tail -5
> docker run --rm aois:v4-check whoami          # should NOT be root
> docker image ls aois:v4-check                 # check image size
> ```
> If you knew the answers before building — you read a Dockerfile correctly.

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

> **▶ STOP — do this now**
>
> Run the Trivy scan and interpret every HIGH/CRITICAL finding:
> ```bash
> trivy image aois:latest --severity HIGH,CRITICAL 2>/dev/null | grep -E "HIGH|CRITICAL|Total"
> ```
> For each finding:
> - Is there a "FIXED VERSION"? If yes: it is actionable — update the base image or package.
> - If no fixed version: document it as accepted risk.
>
> Then understand what scanning caught:
> ```bash
> # Compare: what does the builder stage have vs the final image?
> docker build --target builder -t aois:builder-only . 2>/dev/null
> trivy image aois:builder-only --severity HIGH,CRITICAL 2>/dev/null | grep "Total:"
> trivy image aois:latest --severity HIGH,CRITICAL 2>/dev/null | grep "Total:"
> ```
> The builder stage has more vulnerabilities (it has pip, gcc, etc). Multi-stage builds reduce your attack surface by not shipping build tools.

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

> **▶ STOP — do this now**
>
> Start the stack and observe all three services:
> ```bash
> cd /workspaces/aois-system
> docker compose up -d
>
> # Check all containers are running
> docker compose ps
>
> # Confirm AOIS can reach Redis and Postgres
> docker compose exec aois bash -c "python3 -c 'import redis; r=redis.Redis(host=\"redis\"); print(r.ping())'"
> docker compose exec aois bash -c "python3 -c 'import psycopg2; c=psycopg2.connect(host=\"postgres\",user=\"aois\",password=\"aois\",dbname=\"aois\"); print(\"postgres OK\")'"
>
> # Check the AOIS API through the container
> curl -s http://localhost:8000/health
>
> docker compose down
> ```
> The hostname `redis` and `postgres` in those connection strings work because Compose puts all services on the same Docker network — each service's name becomes its hostname. This same pattern reappears in Kubernetes (where service names become DNS entries).

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

## Common Mistakes

**COPY before installing dependencies — breaking layer cache** *(recognition)*
Docker builds layers sequentially. When a layer changes, all layers after it are rebuilt. Copying source code before installing dependencies means every code change re-runs pip install — what should take 2 seconds takes 60 seconds. Always install dependencies first, copy code second.

*(recall — trigger it)*
Create a Dockerfile with the wrong order:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .                          # <-- code copied first
RUN pip install -r requirements.txt
```
Build it, then change one line in `main.py` and build again:
```bash
time docker build -t aois-wrong-order .    # build 1
# edit main.py — change one comment
time docker build -t aois-wrong-order .    # build 2 — watch pip reinstall
```
Expected: build 2 re-runs `pip install` despite requirements.txt being unchanged. Output shows `pip install` output again, build takes 45–90 seconds.

Fix — correct order:
```dockerfile
COPY requirements.txt .           # copy only what pip needs
RUN pip install -r requirements.txt
COPY . .                          # code goes last
```
Now `pip install` is only re-run when `requirements.txt` changes. Code edits rebuild in under 5 seconds.

---

**No `.dockerignore` — COPY bakes your secrets into the image** *(recognition)*
`COPY . .` copies everything in the build context — including `.env`, `__pycache__`, `.git`, and any local test data. Your API key ends up in the image layer, visible to anyone who pulls the image.

*(recall — trigger it)*
```bash
# Build without .dockerignore (rename it temporarily)
mv .dockerignore .dockerignore.bak
docker build -t aois-leaky .

# Inspect the image layers for secret files
docker run --rm aois-leaky ls -la /app/.env
docker run --rm aois-leaky cat /app/.env
```
Expected: `.env` is in the image and readable — your `ANTHROPIC_API_KEY` is visible. Restore the protection:
```bash
mv .dockerignore.bak .dockerignore
```
Minimum `.dockerignore`:
```
.env
.git
__pycache__
*.pyc
.pytest_cache
```
One memory hook: **if you can `cat /app/.env` from inside a running container, anyone who pulls your image can too.**

---

**Running as root in the container** *(recognition)*
The default Docker container runs as root (UID 0). If a container escape vulnerability exists, the attacker gets root on the host. Your final stage should set `USER nonroot`.

*(recall — trigger it)*
```bash
# Check which user your built image runs as
docker run --rm ghcr.io/kolinzking/aois:v7 whoami
```
Expected if correct: `nonroot`

Expected if you forgot `USER nonroot`:
```
root
```
And with root confirmed:
```bash
docker run --rm ghcr.io/kolinzking/aois:v7 id
# uid=0(root) gid=0(root) groups=0(root)
```
Fix: ensure your final stage Dockerfile contains:
```dockerfile
USER nonroot
```
After the fix, `whoami` inside the container returns `nonroot` and `id` shows UID 65532 (the nonroot user in distroless).

---

**Using `:latest` tag — not reproducible** *(recognition)*
`FROM python:3.12` pulls whatever `latest` is at build time. When Python releases 3.12.8, your next build silently uses a different base — different CVE profile, potentially different behavior. Pin the exact version.

*(recall — trigger it)*
```bash
# Pull the python:3.12 image and check what you actually got
docker pull python:3.12
docker inspect python:3.12 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['RepoDigests'])"
```
The digest changes each time Python releases a patch. Two engineers building from `FROM python:3.12` on different days get different images. Fix:
```dockerfile
FROM python:3.12.6-slim      # pinned minor version
```
Or pin the digest directly for complete reproducibility:
```dockerfile
FROM python:3.12.6-slim@sha256:abc123...   # immutable
```

---

**`docker compose up` vs `docker compose up --build`** *(recognition)*
`docker compose up` starts containers using cached images. If you changed `main.py`, the running container has the old code — compose does not rebuild automatically. During development, you will forget this repeatedly.

*(recall — trigger it)*
```bash
docker compose up -d          # start AOIS
curl localhost:8000/health    # confirm it's up

# Now change main.py — add a visible header to /health response
# (e.g., return {"status": "ok", "version": "v4-test"})

docker compose up -d          # restart WITHOUT --build
curl localhost:8000/health    # still shows old response — no "v4-test"
```
Expected: the change is invisible. The container is running the old image.

Fix:
```bash
docker compose up --build -d  # rebuild first, then start
curl localhost:8000/health    # now shows {"status": "ok", "version": "v4-test"}
```
One memory hook: **if your code change has no effect after a restart, you forgot `--build`.**

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

---


## Build-It-Blind Challenge

Close the notes. From memory: write the AOIS multi-stage Dockerfile — build stage installs dependencies, runtime stage uses a minimal base, runs as non-root user `aois`, exposes port 8000. No `latest` tags. 20 minutes.

```bash
docker build -t aois:test .
docker run --rm aois:test id
# uid=1001(aois) gid=1001(aois) — must NOT be root
docker run --rm aois:test python3 -c "import fastapi; print('ok')"
# ok
```

---

## Failure Injection

Build the image running as root and run Trivy against it:

```dockerfile
FROM python:3.11-slim
# No USER directive — runs as root
COPY . .
RUN pip install -r requirements.txt
CMD ["uvicorn", "main:app"]
```

```bash
trivy image aois:root-test --severity HIGH,CRITICAL
```

Count the vulnerabilities. Now build the hardened version and compare. This is the before/after that justifies the multi-stage pattern in every security review.

---

## Osmosis Check

1. Your Dockerfile copies `requirements.txt` before copying the application code. This is deliberate — why does layer ordering matter for build cache? Which v0.1 concept about filesystem operations explains the underlying mechanism?
2. The container starts successfully but `os.getenv("ANTHROPIC_API_KEY")` returns `None` inside it. Name the two correct ways to inject the env var, and why you must not bake it into the image. (v0.5 + v0.3 git security)

---

## Mastery Checkpoint

Containerization is not optional at Phase 3+. Everything from v6 onwards lives in containers. These exercises make the mental model automatic.

**1. Understand every layer of the Dockerfile**
Read the current Dockerfile line by line. For each line, explain: what does it do, and why is it there? Pay particular attention to:
- Why two `FROM` statements? (multi-stage: why does this matter for image size and security?)
- What is the difference between `RUN`, `COPY`, and `CMD`?
- Why `COPY --from=builder` instead of just installing pip packages in the runtime stage?
- Why `USER nonroot`? (What attack does this prevent?)
- What does `EXPOSE 8000` actually do? (Hint: less than you might think — it does not publish the port)

**2. Measure the impact of multi-stage builds**
```bash
# Build a single-stage version (add everything to one stage) and compare sizes
# First, check current image size
docker images aois

# Build the current multi-stage image
docker build -t aois:v4-multistage .

# Compare: what would it cost to ship the builder stage's 1GB+ Python ecosystem vs the runtime stage?
docker history aois:v4-multistage
```
The `docker history` command shows every layer and its size. Understanding layer sizes is how you debug large images.

**3. Docker Compose dependency chain**
Stop everything: `docker compose down`. Now start only the AOIS container without Redis and Postgres: `docker compose up aois`. What happens? Why? Now start with `docker compose up` (all services). Watch the startup order.

Next: modify `docker-compose.yml` to add a proper healthcheck to the postgres service:
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U aois"]
  interval: 5s
  timeout: 3s
  retries: 5
```
And change `depends_on` to:
```yaml
depends_on:
  postgres:
    condition: service_healthy
```
Now AOIS waits for Postgres to actually be ready, not just started. Restart and observe the difference.

**4. Shell into a running container**
With `docker compose up -d` running:
```bash
docker compose exec aois /bin/bash
```
You are now inside the container. Run the Linux commands from v0.1:
- `whoami` — what user are you? (should be non-root)
- `ls -la /app` — what files are here?
- `cat /etc/os-release` — what OS is this?
- `ps aux` — what processes are running?
- `python3 -c "import anthropic; print(anthropic.__version__)"` — packages installed?
- `env | grep ANTHROPIC` — is the key available?
Exit with `exit`.

This is exactly how you debug a misbehaving container in production.

**5. Trivy scan and understand the output**
```bash
trivy image --severity HIGH,CRITICAL aois:v4
```
Read every finding. For each HIGH or CRITICAL finding:
- What package has the CVE?
- What is the affected version?
- Is there a fixed version?
- Is this CVE in the base image or something you installed?

If there are zero findings: understand why the combination of distroless + pinned dependencies produces a clean scan.

**6. Container networking mental model**
With `docker compose up -d`, run:
```bash
docker network ls                   # see the docker network
docker network inspect aois-system_default    # see all containers and their IPs
```
Now understand: why can the AOIS container reach `postgres:5432` using the service name `postgres`? (Docker Compose creates a DNS entry for each service name on the shared network.) Why can YOU reach `localhost:5432`? (The `ports:` mapping publishes it to the host.) What if you removed the `ports:` from postgres? (You could not reach it from your machine, but AOIS still could — internal network still works.)

**The mastery bar**: You can build an image from scratch, explain every Dockerfile instruction, run a multi-service application with Compose, debug inside containers, and interpret security scan output. Docker is transparent to you now — you see through it to what it is actually doing.

---

## 4-Layer Tool Understanding

*Every tool introduced in this version, understood at four levels.*

---

### Docker

| Layer | |
|---|---|
| **Plain English** | Packages your application and everything it needs to run into a single portable box — so it works identically on your laptop, on a Hetzner server, and on AWS, with no "it works on my machine" problems. |
| **System Role** | Docker is the delivery mechanism for AOIS. The Dockerfile produces an image that is pushed to GHCR and pulled by Kubernetes. Every environment (dev, staging, prod) runs the same image — differences are in config (env vars), not in the application. Without Docker, deploying to k3s (v6) would require manual dependency installation on every node. |
| **Technical** | A container runtime that uses Linux namespaces and cgroups to isolate processes. A `Dockerfile` defines a layered build: each `RUN`, `COPY`, and `FROM` instruction creates a filesystem layer. `docker build` produces an image (immutable snapshot). `docker run` creates a container (running instance). Multi-stage builds use one stage for compiling/installing and a minimal stage for the runtime — dramatically reducing image size and attack surface. |
| **Remove it** | Without Docker, AOIS is a Python application that requires manual setup (Python version, venv, dependencies) on every machine it runs on. Kubernetes cannot orchestrate it. CI cannot build and push it. The entire GitOps pipeline (v8) depends on Docker images. |

**Say it at three levels:**
- *Non-technical:* "Docker packages the application with all its dependencies into a container — like a shipping container that holds everything needed to run the app anywhere, regardless of what's installed on the machine."
- *Junior engineer:* "The Dockerfile is the build recipe. `FROM python:3.11-slim` is the base. `COPY requirements.txt && pip install` installs dependencies. `CMD ["uvicorn", "main:app"]` starts it. Multi-stage: build in a full image, copy only the binary/files to a minimal runtime image. Result: smaller, faster, fewer vulnerabilities."
- *Senior engineer:* "Image layers are content-addressed and cached. Ordering matters: `COPY requirements.txt` before `COPY .` means dependency layers are cached even when source code changes. For AOIS: non-root user, read-only filesystem, no shell in the runtime stage, distroless base. Trivy scans the final image — zero HIGH/CRITICAL is the CI gate. The image digest (SHA256) is the immutable identifier; tags are mutable pointers to digests."

---

### Docker Compose

| Layer | |
|---|---|
| **Plain English** | A tool for running multiple related services together with a single command — so you can start the entire AOIS stack (app, database, cache, monitoring) locally without manually starting each piece. |
| **System Role** | Docker Compose is the local development environment for AOIS. `docker compose up` starts AOIS + Redis + Postgres + OTel Collector + Prometheus + Grafana + Loki + Tempo as a single stack. It mirrors the production Kubernetes setup, making local development representative of what runs in prod. |
| **Technical** | A YAML-based tool for defining multi-container applications. Each `service` in `docker-compose.yml` maps to a container with its own image, environment variables, ports, volumes, and network. Services share a Docker network — service names resolve as hostnames within that network. `depends_on` controls startup order. |
| **Remove it** | Without Compose, each service must be started manually with `docker run`, with manually specified network flags and environment variables. The full local stack requires 7+ separate commands that must be run in the correct order. Any time a new developer joins, setup takes hours instead of minutes. |

**Say it at three levels:**
- *Non-technical:* "Docker Compose is a conductor for the whole orchestra. Instead of starting each instrument (service) one by one, one command starts everything at once in the right order."
- *Junior engineer:* "`docker compose up -d` starts everything in the background. `docker compose logs -f aois` follows AOIS logs. `docker compose down` stops and removes containers. Service names are DNS hostnames — AOIS connects to Postgres at `postgres:5432` because that's the Compose service name."
- *Senior engineer:* "Compose is for development and testing, not production. The production equivalent is Helm + ArgoCD (v7, v8). The value is that Compose and Kubernetes use the same image — the gap between local and prod is config, not code. `healthcheck` in Compose maps to k8s readiness probes. `depends_on: condition: service_healthy` is the Compose-native equivalent of k8s init containers."

---

### Redis

| Layer | |
|---|---|
| **Plain English** | An extremely fast temporary storage that keeps data in memory — used to avoid repeating expensive operations (like LLM calls) and to share state between multiple instances of the application. |
| **System Role** | Redis serves two roles in AOIS: rate limiting state (slowapi in v5 uses Redis to count requests per IP across all pod replicas) and response caching (avoid re-calling the LLM for identical log inputs). Without Redis, rate limits reset when pods restart and identical log lines re-hit the LLM every time. |
| **Technical** | An in-memory data structure store supporting strings, hashes, lists, sets, sorted sets, and streams. Data persists optionally to disk (RDB snapshots or AOF log). Sub-millisecond latency because all reads/writes happen in RAM. Expiry (TTL) on keys is a first-class feature — keys automatically disappear after a set time. |
| **Remove it** | Without Redis: rate limiting becomes per-pod (trivially bypassed by load balancers), response caching disappears (duplicate log lines hit the LLM repeatedly), and any shared session state between pods is lost. In a 5-replica AOIS deployment under KEDA scaling, Redis is what makes the replicas behave like a single coherent system. |

**Say it at three levels:**
- *Non-technical:* "Redis is a super-fast notepad that all instances of the application share. Instead of each copy of the app doing the same work, they check the notepad first — if the answer is already there, they use it."
- *Junior engineer:* "`redis.set('rate_limit:IP:endpoint', count, ex=60)` — sets a key with a 60-second TTL. `redis.incr()` is atomic — multiple pods can safely increment the same counter. `redis.get('cache:' + hash(log))` returns a cached analysis. If None, call the LLM and `redis.setex()` the result."
- *Senior engineer:* "Redis as a rate limit store requires the sliding window algorithm (sorted sets) for correct semantics — the fixed window (INCR + TTL) approach has edge cases at window boundaries where 2x the limit can get through. For AOIS at scale, Redis Cluster handles failover; Sentinel handles single-node HA. The eviction policy matters: `allkeys-lru` (evict least recently used) is correct for a cache; `noeviction` is correct for session state. Never use `noeviction` for a cache — the server OOMs when memory fills."

---

### Trivy

| Layer | |
|---|---|
| **Plain English** | A security scanner that checks your Docker image for known vulnerabilities — so you don't accidentally deploy a container with a critical security flaw that attackers could exploit. |
| **System Role** | Trivy is the shift-left security gate for AOIS. It runs in CI (v28) after every build: `trivy image aois:latest`. Zero HIGH or CRITICAL vulnerabilities is the gate to pass before an image can be pushed. It catches vulnerable base image packages, outdated Python dependencies, and misconfigured Dockerfiles. |
| **Technical** | An open-source vulnerability scanner for containers, filesystems, and IaC. It scans: OS packages (Alpine apk, Debian apt), language dependencies (pip, npm), and IaC configs (Dockerfile, Terraform). Matches against CVE databases (NVD, GitHub Advisory, OS vendor advisories). Reports by severity: CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN. |
| **Remove it** | Without Trivy, a deployed AOIS container could have a critical CVE in its base image or a dependency — invisible until an attacker exploits it. The 2023 Log4Shell incident was a `HIGH` CVE in a Java library that every SBOM-unaware organisation shipped unknowingly. Trivy makes CVEs visible before they reach production. |

**Say it at three levels:**
- *Non-technical:* "Trivy is a security check that scans the container for known weaknesses before it's deployed. Like a metal detector at the airport — nothing dangerous gets through without being flagged."
- *Junior engineer:* "`trivy image --exit-code 1 --severity HIGH,CRITICAL aois:latest` — exits with code 1 (failing CI) if any HIGH or CRITICAL CVE is found. Fix by updating the base image (`FROM python:3.11-slim` → `FROM python:3.12-slim`), pinning newer dependency versions, or accepting the risk with a justification comment."
- *Senior engineer:* "Trivy scans at the layer level — it knows which layer introduced the vulnerability. Multi-stage builds reduce the attack surface by leaving build tools out of the runtime image. For a serious production deployment, Trivy runs at build time (shift-left) AND at runtime via `trivy image` on the running registry image (catch new CVEs in already-deployed images). Cosign (v4) signs the image digest after Trivy passes — the signature is evidence that the scan passed."
