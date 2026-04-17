# v4 — Docker

## What this version builds
Takes the Phase 1 FastAPI application and puts it inside a container.
The code does not change — the environment it runs in does.
A multi-stage Dockerfile produces a minimal, hardened image.
Docker Compose brings up AOIS alongside Redis and Postgres with one command.
Trivy scans the image for vulnerabilities. Zero HIGH/CRITICAL before proceeding.

---

## Before you start

### What you need
- Docker installed and running: `docker --version`
- Docker Compose: `docker compose version`
- Trivy installed (see below)
- The Phase 1 `main.py` and `requirements.txt` in your project root

### Install Trivy
```bash
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
  | sh -s -- -b $HOME/.local/bin
export PATH=$PATH:$HOME/.local/bin
trivy --version
```
To make the PATH change permanent, add it to your `~/.bashrc` or `~/.zshrc`:
```bash
echo 'export PATH=$PATH:$HOME/.local/bin' >> ~/.bashrc
source ~/.bashrc
```

---

## The Dockerfile — built section by section

```dockerfile
# Stage 1 — build: install dependencies into a clean layer
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2 — runtime: copy only what is needed to run
FROM python:3.11-slim AS runtime

RUN useradd --create-home --shell /bin/bash aois
WORKDIR /home/aois/app

COPY --from=builder /install /usr/local

RUN pip uninstall -y setuptools wheel 2>/dev/null || true

COPY main.py .

USER aois

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Why two stages (multi-stage build)?

A single-stage build would install everything — pip, setuptools, wheel, build tools, compiler headers — and leave it all in the final image. These tools are needed to build packages but not to run them. They add size and attack surface.

A multi-stage build uses two separate `FROM` instructions:
- **Stage 1 (builder):** has all the build tools. Installs everything into `/install`.
- **Stage 2 (runtime):** is a clean fresh image. Only the installed packages are copied in. Build tools never make it to the final image.

### `FROM python:3.11-slim`
`slim` is a minimal Debian-based Python image. It omits documentation, man pages, and many system packages that a full image includes. Smaller image = fewer packages = fewer CVEs = faster pulls.

### `WORKDIR /app`
Sets the working directory inside the container. All subsequent `COPY` and `RUN` commands operate relative to this path. Creates the directory if it does not exist.

### `RUN pip install --no-cache-dir --prefix=/install -r requirements.txt`
- `--no-cache-dir` — does not cache pip's download cache inside the image layer, keeping size down
- `--prefix=/install` — installs packages into `/install` instead of the system Python. This makes it easy to copy just the packages into the next stage with `COPY --from=builder /install /usr/local`

### `RUN useradd --create-home --shell /bin/bash aois`
Creates a non-root user named `aois`. Running as root inside a container means that if an attacker escapes the container, they land as root on the host. A non-root user limits the blast radius. This is one of the most important container security practices.

### `COPY --from=builder /install /usr/local`
Copies the installed Python packages from the builder stage into the runtime stage's Python path. Only the packages — no build tools, no pip cache, no source downloads.

### `RUN pip uninstall -y setuptools wheel 2>/dev/null || true`
`setuptools` and `wheel` are build tools, not needed at runtime. They also carry known CVEs in their vendored dependencies. Removing them from the runtime image eliminates those vulnerabilities entirely. The `|| true` ensures the build does not fail if they are not present.

### `USER aois`
Switches to the non-root user. Everything after this line runs as `aois`, not `root`. Must come after the `COPY` commands because copying files as root is fine — it is the running process that must not be root.

### `EXPOSE 8000`
Documents that the container listens on port 8000. Does not actually open the port — that is done at runtime with `-p 8000:8000`. Think of `EXPOSE` as metadata.

### `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`
The command that runs when the container starts. JSON array format (`["cmd", "arg"]`) is preferred over shell format (`cmd arg`) because it does not spawn a shell process — the process runs directly as PID 1.

---

## Building the image

```bash
docker build -t aois:v4 .
```

- `docker build` — builds an image from a Dockerfile
- `-t aois:v4` — tags the image as `aois:v4`. Tag format is `name:version`.
- `.` — the build context. Docker sends the contents of this directory to the build daemon. Only files in this directory can be used in `COPY` instructions.

To rebuild from scratch without using any cached layers:
```bash
docker build --no-cache -t aois:v4 .
```

Check the image was created and its size:
```bash
docker images aois:v4
```

---

## Scanning with Trivy

```bash
trivy image --severity HIGH,CRITICAL aois:v4
```

- `trivy image` — scans a Docker image
- `--severity HIGH,CRITICAL` — only report HIGH and CRITICAL vulnerabilities. INFO and LOW are noise at this stage.

### Reading the output
Trivy reports vulnerabilities grouped by target (OS packages, Python packages). For each vulnerability:
- **CVE ID** — the unique identifier from the National Vulnerability Database
- **Severity** — CRITICAL, HIGH, MEDIUM, LOW
- **Status** — `fixed` means a patched version exists. `affected` means no fix is available yet.
- **Installed version** — what is in the image
- **Fixed version** — what you need to upgrade to (empty if no fix exists)

### Fixing Python package CVEs
If a Python package shows `fixed` status, add a version pin to `requirements.txt`:
```
jaraco.context>=6.1.0
```
Rebuild with `--no-cache` and scan again.

### Fixing OS CVEs with no available fix
If the status is `affected` with no fixed version, the OS distribution has not released a patch yet. The correct response is to:
1. Document it — note which CVE, which package, and that no fix is available
2. Accept the risk — it is not actionable until a patch exists
3. Re-scan regularly — when a fix ships, it will show as `fixed`

The ncurses (`libncursesw6`) CVEs in this image fall into this category. They are present in Debian's package at the time of this build with no available fix.

### Removing build tools to eliminate embedded CVEs
`setuptools` and `wheel` vendor their own copies of other packages. Those vendored copies can carry CVEs that are not patchable through `requirements.txt`. The fix is to remove these tools from the runtime image entirely:
```dockerfile
RUN pip uninstall -y setuptools wheel 2>/dev/null || true
```
This eliminates the entire class of vulnerabilities from vendored dependencies.

---

## Docker Compose

```yaml
services:
  aois:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - redis
      - postgres
    restart: unless-stopped

  redis:
    image: redis:7-alpine
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
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
```

### Why Compose?
In production, AOIS will need Redis (caching, rate limiting) and Postgres (persistent storage, audit log). Compose lets you define all services in one file and start them all with one command. This is the local development equivalent of what Helm does in Kubernetes.

### `env_file: .env`
Passes all the variables from your `.env` file into the `aois` container as environment variables. The `.env` file never goes into the image — it is injected at runtime. This is the correct pattern: secrets in the environment, not in the image.

### `depends_on`
Tells Compose to start `redis` and `postgres` before starting `aois`. Does not wait for them to be ready — just started. For health-check-based waiting, you add `condition: service_healthy`, covered in later versions.

### `restart: unless-stopped`
Restarts the container automatically if it crashes. Does not restart if you manually stop it with `docker compose stop`.

### `volumes: postgres_data:`
Creates a named Docker volume for Postgres data. Without this, all database data is lost when the container stops. Named volumes persist on the Docker host independently of container lifecycle.

### `-alpine` images
Redis and Postgres use `alpine` variants. Alpine Linux is a minimal distribution (~5MB base) with far fewer packages than Debian. Smaller attack surface and faster pulls.

---

## Running with Docker Compose

Start all services:
```bash
docker compose up
```

Start in detached mode (background):
```bash
docker compose up -d
```

Check what is running:
```bash
docker compose ps
```

View logs for a specific service:
```bash
docker compose logs aois
docker compose logs -f aois   # follow/stream logs
```

Stop all services:
```bash
docker compose down
```

Stop and delete all data volumes (wipes Postgres data):
```bash
docker compose down -v
```

---

## Testing the containerised service

Health check:
```bash
curl -s http://localhost:8000/health
```

Analyze a log via the container:
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "FATAL: pod/payment-service OOMKilled. Memory limit 512Mi exceeded. Restarts: 14."}' \
  | python3 -m json.tool
```

Confirm it is running as a non-root user:
```bash
docker exec aois-test whoami
# expected: aois
```

---

## Running the container directly (without Compose)

```bash
docker run -d \
  --name aois-test \
  --env-file .env \
  -p 8000:8000 \
  aois:v4
```

- `-d` — detached, runs in background
- `--name aois-test` — gives the container a name so you can reference it
- `--env-file .env` — injects environment variables from the file
- `-p 8000:8000` — maps host port 8000 to container port 8000 (host:container)

View logs:
```bash
docker logs aois-test
docker logs -f aois-test   # follow
```

Stop and remove:
```bash
docker stop aois-test && docker rm aois-test
```

---

## Git — committing v4

```bash
git add Dockerfile docker-compose.yml requirements.txt
git commit -m "v4: multi-stage Dockerfile, Docker Compose, Trivy clean"
```

Do not commit `.env`. Do not commit the actual image — images go to a registry (GHCR in v28).

Check what you are staging before committing:
```bash
git diff --staged
```

---

## What v4 does not have (fixed in v5)

| Gap | Fixed in |
|-----|---------|
| No rate limiting — anyone can flood the endpoint | v5 |
| No input sanitisation — any payload size accepted | v5 |
| No prompt injection defence | v5 |
| API keys still in a flat .env file | v5 — Vault |
| No output safety guardrails | v5 — Guardrails AI |
| Image not signed — anyone could produce an identical-looking image | v5 — Cosign |
