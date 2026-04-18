# v0.4 — Networking & HTTP: How the Internet Works
⏱ **Estimated time: 2–3 hours**

## What this version is about

Every API call your code makes — to Claude, to OpenAI, to your own FastAPI server — is an HTTP request over a TCP connection. When something goes wrong, knowing the network layer tells you exactly where to look. "Connection refused" means the server is not running. "403 Forbidden" means the server is running but rejecting you. "Timeout" means the server is reachable but not responding.

This version removes all abstraction from API calls. By the end, `curl -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{...}'` will be as readable as English.

---

## Prerequisites

- v0.1-v0.3 complete
- curl is installed (it is in Codespaces)

Verify:
```bash
curl --version
```
Expected:
```
curl 7.81.0 (x86_64-pc-linux-gnu) libcurl/7.81.0 OpenSSL/3.0.2 ...
```

---

## Learning goals

By the end of this version you will:
- Understand IP addresses, ports, and how they identify a specific process on a specific machine
- Know what DNS does and what happens when you type a URL
- Read an HTTP request and response — every line of it
- Use curl to test any API endpoint
- Know every HTTP method and the most important status codes
- Understand what REST means
- Know what JSON is and how to work with it in bash and Python

---

## Part 1 — IP addresses and ports

Every device on a network has an IP address. An IP address identifies a machine. A port number identifies a specific process on that machine.

```
IP address:   192.168.1.10        — which machine
Port:         8000                — which process on that machine
Combined:     192.168.1.10:8000   — exactly one process, on one machine
```

**Special IP addresses:**
- `127.0.0.1` — loopback address, means "this machine". `localhost` is an alias for it.
- `0.0.0.0` — means "all network interfaces". When you run `uvicorn --host 0.0.0.0`, it listens on all interfaces — not just localhost — so external connections can reach it.

**Port ranges:**
- `0–1023` — well-known ports, require root privileges to bind:
  - `22` — SSH
  - `80` — HTTP
  - `443` — HTTPS
  - `5432` — PostgreSQL
  - `6379` — Redis
- `1024–65535` — available for applications:
  - `8000` — your FastAPI server
  - `8080` — common alternative HTTP port

When you run `uvicorn main:app --port 8000`, the uvicorn process claims port 8000. Any connection to `your-machine:8000` goes to uvicorn, which passes it to FastAPI.

Check what is listening on your machine right now:
```bash
ss -tlnp
```
Expected output (abbreviated):
```
State    Recv-Q  Send-Q  Local Address:Port  Peer Address:Port  Process
LISTEN   0       128     0.0.0.0:22          0.0.0.0:*          users:(("sshd",pid=123))
LISTEN   0       128     0.0.0.0:8000        0.0.0.0:*          users:(("uvicorn",pid=456))
```
`Local Address:Port` = `0.0.0.0:8000` means uvicorn is listening on all interfaces on port 8000.

---

## Part 2 — DNS: turning names into addresses

When you type `api.anthropic.com` or call it in code, your machine does not know the IP address. It asks a DNS (Domain Name System) server.

```
Your code                    DNS resolver (8.8.8.8)        Root DNS → .com DNS → anthropic.com DNS
    │                               │                               │
    │── "what IP is api.anthropic.com?" ──→│                        │
    │                               │── queries chain ──────────────→│
    │                               │←── "52.84.x.x" ───────────────│
    │←── "IP is 52.84.x.x" ─────────│
    │
    ├── opens TCP connection to 52.84.x.x:443
    └── sends HTTP request
```

Look up a domain right now:
```bash
nslookup api.anthropic.com
```
Expected:
```
Server:         127.0.0.53
Address:        127.0.0.53#53

Non-authoritative answer:
Name:   api.anthropic.com
Address: 52.84.x.x
```

```bash
dig api.anthropic.com +short
```
Expected: just the IP address(es).

Test connectivity without DNS:
```bash
ping -c 4 8.8.8.8       # ping Google's DNS server directly by IP
```
Expected:
```
PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=12.4 ms
```

If `ping 8.8.8.8` works but `ping google.com` fails, it is a DNS problem. The network is fine.

---

> **▶ STOP — do this now**
>
> Diagnose the network path to the Anthropic API:
> ```bash
> # Resolve the DNS name
> nslookup api.anthropic.com
>
> # Check if the port is reachable
> curl -sv https://api.anthropic.com 2>&1 | head -20
>
> # What port does HTTPS use?
> # What port does HTTP use?
> # If you can reach the IP but not the hostname — what is broken?
> ```
> Understanding this means when an API call fails with "connection refused" vs "SSL error" vs "timeout", you know exactly which layer is broken and where to look.

---

## Part 3 — HTTP: the protocol of the web

HTTP is a text-based protocol. Every API call — to Claude, to your FastAPI server, to GitHub — is an HTTP request. Understanding the raw format removes all abstraction.

### HTTP request structure

```
METHOD /path HTTP/1.1\r\n
Header-Name: value\r\n
Another-Header: value\r\n
\r\n                              ← blank line: headers end here
{body here}
```

Real POST request to your AOIS server:
```
POST /analyze HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Content-Length: 58

{"log": "OOMKilled pod/payment-service memory_limit=512Mi"}
```

Every part:
- `POST` — the HTTP method
- `/analyze` — the path (which endpoint)
- `HTTP/1.1` — protocol version
- `Host: localhost:8000` — which server (required in HTTP/1.1)
- `Content-Type: application/json` — tells server the body is JSON
- `Content-Length: 58` — how many bytes the body is
- blank line — separates headers from body
- `{...}` — the body (your log data)

### HTTP response structure

```
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 142

{
    "summary": "Payment service OOMKilled — exceeded memory limit",
    "severity": "P2",
    "suggested_action": "Increase memory limit to 1Gi",
    "confidence": 0.95
}
```

Every part:
- `HTTP/1.1` — protocol version
- `200 OK` — status code + reason phrase
- `Content-Type` — body format
- `Content-Length` — body size
- blank line — separates headers from body
- `{...}` — the body (the analysis result)

---

## Part 4 — HTTP methods

| Method | Meaning | Has body? | Typical AOIS use |
|--------|---------|-----------|-----------------|
| GET | Retrieve something | No | `GET /health` |
| POST | Submit data for processing | Yes | `POST /analyze` |
| PUT | Replace a resource entirely | Yes | Replace an incident record |
| PATCH | Partially update a resource | Yes | Update severity only |
| DELETE | Remove a resource | No | Delete an incident |

For AOIS, `POST /analyze` is the right method because you are submitting data (a log) for the server to process and return a result. You are not retrieving an existing resource.

---

## Part 5 — HTTP status codes

These are the first thing you check when a request fails.

**2xx — Success:**
```
200 OK                 Request succeeded, response body contains result
201 Created            Resource was created (POST that creates something)
204 No Content         Succeeded, no body to return (DELETE)
```

**4xx — Client errors (your fault):**
```
400 Bad Request        Malformed request (invalid JSON, missing field)
401 Unauthorized       No authentication or invalid credentials
403 Forbidden          Authenticated but not permitted to do this
404 Not Found          That path doesn't exist on this server
405 Method Not Allowed Using GET when the endpoint requires POST
413 Payload Too Large  Request body too big (v5 rate limiting)
422 Unprocessable      Valid syntax but business logic rejected it (FastAPI validation errors)
429 Too Many Requests  Rate limited (v5)
```

**5xx — Server errors (server's fault):**
```
500 Internal Server Error  Unhandled exception in your code
502 Bad Gateway           Upstream service returned invalid response
503 Service Unavailable   Server is down, overloaded, or both providers failed
504 Gateway Timeout       Upstream took too long to respond
```

What each means in practice for AOIS:
- You get `422` → FastAPI's Pydantic validation rejected your input (missing `log` field, wrong type)
- You get `429` → slowapi's rate limiter triggered (too many requests per minute)
- You get `503` → both Claude and OpenAI failed (check your API keys)
- You get `500` → an unhandled exception — check the server logs

---

> **▶ STOP — do this now**
>
> Start the AOIS server and deliberately trigger each error type:
> ```bash
> # Terminal 1: start server
> cd /workspaces/aois-system && uvicorn main:app --port 8000
>
> # Terminal 2: trigger each status code
> curl -s http://localhost:8000/health                          # expect 200
> curl -s -X POST http://localhost:8000/analyze -d '{}'        # expect 422 (missing log field)
> curl -s http://localhost:8000/nonexistent                    # expect 404
> curl -s -X POST http://localhost:8000/analyze \
>   -H "Content-Type: application/json" \
>   -d '{"log": "test"}'                                       # expect 200 or 503
> ```
> Before running each command, predict the status code. Then run it and compare.
> The ability to predict HTTP status codes from the request tells you you understand the protocol.

---

## Part 6 — curl: your API testing tool

curl sends HTTP requests from the terminal. You will use this to test every endpoint you build for the rest of this project.

### Basic usage

```bash
# GET request
curl http://localhost:8000/health
```
Expected:
```
{"status":"ok"}
```

```bash
# GET with formatted JSON output
curl -s http://localhost:8000/health | python3 -m json.tool
```
Expected:
```json
{
    "status": "ok"
}
```

```bash
# POST with JSON body
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service"}'
```

### See everything: verbose mode

```bash
curl -v http://localhost:8000/health
```
Expected output (read every line):
```
* Trying 127.0.0.1:8000...         ← DNS resolved, attempting connection
* Connected to localhost port 8000  ← TCP connection established
> GET /health HTTP/1.1              ← request line (> = request going out)
> Host: localhost:8000              ← request headers
> User-Agent: curl/7.81.0
> Accept: */*
>                                   ← blank line: end of request
< HTTP/1.1 200 OK                   ← response status (< = response coming in)
< Content-Type: application/json    ← response headers
< Content-Length: 15
<                                   ← blank line: end of response headers
{"status": "ok"}                    ← response body
```

This is the full HTTP exchange. Everything your Python code does when calling `anthropic_client.messages.create()` is this same exchange — just with different headers, a bigger body, and over HTTPS.

### curl flag reference

```bash
-s              # silent: no progress bar (use almost always)
-v              # verbose: show full request/response headers
-X POST         # set HTTP method (default is GET)
-H "Key: val"   # add a request header
-d '{"key":"val"}' # request body
-d @file.json   # request body from a file
-o output.json  # save response body to file
-I              # HEAD request (response headers only, no body)
-L              # follow redirects
-w "%{http_code}" # write status code after response
-o /dev/null    # discard response body (use with -w to get just status code)
```

### Get just the status code

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
```
Expected:
```
200
```

Useful for scripts where you want to check if an endpoint is up:
```bash
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ "$STATUS" = "200" ]; then
    echo "Server is healthy"
else
    echo "Server returned: $STATUS"
fi
```

### curl with authentication

```bash
# API key in header
curl -H "x-api-key: sk-ant-..." https://api.anthropic.com/v1/messages

# Bearer token
curl -H "Authorization: Bearer your-token" http://api.example.com/data
```

---

## Part 7 — JSON: the language APIs speak

JSON is the format almost all APIs use for request and response bodies.

```json
{
    "string_field": "hello",
    "number": 42,
    "float": 0.95,
    "boolean": true,
    "null_value": null,
    "array": ["P1", "P2", "P3"],
    "object": {
        "nested": "value"
    }
}
```

Rules:
- Keys must be quoted strings
- Strings must use double quotes (not single quotes)
- No trailing commas
- `true`/`false`/`null` are lowercase

**Parse JSON in bash with Python:**
```bash
# Pretty print
echo '{"severity":"P1","confidence":0.95}' | python3 -m json.tool

# Extract a field
echo '{"severity":"P1","confidence":0.95}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['severity'])"
```
Expected:
```
P1
```

**Parse JSON in Python:**
```python
import json

# String to Python dict
text = '{"severity": "P1", "confidence": 0.95}'
data = json.loads(text)
print(data["severity"])    # P1
print(data["confidence"])  # 0.95

# Python dict to JSON string
result = {"summary": "OOMKilled", "severity": "P2"}
json_text = json.dumps(result)              # compact
json_pretty = json.dumps(result, indent=2)  # readable

# Read JSON file
with open("response.json") as f:
    data = json.load(f)

# Write JSON file
with open("output.json", "w") as f:
    json.dump(result, f, indent=2)
```

---

> **▶ STOP — do this now**
>
> Save a real API response and inspect it:
> ```bash
> # Hit the GitHub API and save the response
> curl -s https://api.github.com/users/kolinzking > /tmp/github_response.json
>
> # Now extract specific fields
> cat /tmp/github_response.json | python3 -m json.tool | head -20
> cat /tmp/github_response.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['public_repos'])"
> cat /tmp/github_response.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['login'])"
> ```
> This is how you call any REST API: send a request with curl, parse the JSON response with Python. The AOIS `/analyze` endpoint works exactly the same way — it receives JSON, returns JSON.

---

## Part 8 — REST conventions

REST is not a protocol or a standard. It is a set of conventions that most APIs follow to be predictable.

```
GET    /incidents          → list all incidents
GET    /incidents/123      → get a specific incident
POST   /incidents          → create/submit a new incident
PUT    /incidents/123      → replace incident 123 entirely
PATCH  /incidents/123      → update specific fields of incident 123
DELETE /incidents/123      → delete incident 123
```

AOIS follows REST:
```
POST   /analyze            → submit a log, get back analysis
GET    /health             → check if server is alive
GET    /docs               → auto-generated API documentation
```

---

## Part 9 — Hit real APIs

### GitHub API (no authentication needed for public data)

```bash
# Get your GitHub profile
curl -s https://api.github.com/users/kolinzking | python3 -m json.tool | head -30
```
Expected:
```json
{
    "login": "kolinzking",
    "id": 12345678,
    "avatar_url": "https://avatars.githubusercontent.com/...",
    "public_repos": 5,
    ...
}
```

```bash
# List your repositories
curl -s "https://api.github.com/users/kolinzking/repos?sort=updated" | \
  python3 -c "import sys,json; repos=json.load(sys.stdin); [print(r['name'], r['updated_at']) for r in repos]"
```

```bash
# Check GitHub API rate limit status
curl -s -I https://api.github.com/users/kolinzking | grep -i "x-rate"
```
Expected:
```
x-ratelimit-limit: 60
x-ratelimit-remaining: 58
x-ratelimit-reset: 1713362400
```
GitHub allows 60 unauthenticated requests per hour.

### What is actually happening under the hood

Look at the full HTTPS connection to GitHub:
```bash
curl -v https://api.github.com/users/kolinzking 2>&1 | head -40
```
You will see:
1. DNS lookup for `api.github.com`
2. TCP connection to the IP address on port 443
3. TLS handshake (HTTPS is HTTP over TLS encryption)
4. HTTP request sent
5. HTTP response received

This exact sequence happens every time your Python code calls `anthropic_client.messages.create()`. The Anthropic SDK wraps it so you do not see the raw HTTP, but it is the same thing underneath.

---

## Part 10 — Trace a full request through AOIS

Start the AOIS server (if it is not already running):
```bash
cd /workspaces/aois-system
uvicorn main:app --host 0.0.0.0 --port 8000 &
```

Watch the server logs in real time in a second terminal:
```bash
# In a second terminal window
cd /workspaces/aois-system
# The uvicorn logs will appear as you send requests
```

Send a request and watch it:
```bash
curl -v -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service memory_limit=512Mi restarts=14"}' \
  2>&1
```

Watch the flow:
1. `curl` opens TCP connection to `127.0.0.1:8000`
2. `curl` sends HTTP POST
3. `uvicorn` receives and passes to FastAPI
4. FastAPI validates the JSON body against `LogInput` (Pydantic)
5. FastAPI calls `analyze_endpoint()`
6. `analyze_endpoint()` calls Anthropic's API (another HTTP request, outbound)
7. Claude responds
8. `IncidentAnalysis` object created, serialized to JSON
9. FastAPI sends HTTP 200 response
10. `curl` receives and prints it

---

## Common Mistakes

**Binding to `127.0.0.1` instead of `0.0.0.0`.**
```bash
uvicorn main:app --host 127.0.0.1 --port 8000   # only reachable from localhost
uvicorn main:app --host 0.0.0.0  --port 8000    # reachable from any interface
```
`127.0.0.1` is the loopback address — only processes on the same machine can connect. `0.0.0.0` means "listen on all interfaces." In containers and VMs, you almost always want `0.0.0.0` or the service is invisible to the outside world. This is the most common cause of "I can curl from inside but not from outside."

**Confusing HTTP 401 and 403.**
`401 Unauthorized` means: you did not provide credentials (or they are invalid). The server does not know who you are.
`403 Forbidden` means: the server knows who you are (authenticated) but you do not have permission to do this.
The error name `401 Unauthorized` is historically misleading — it really means "unauthenticated." `403` is the actual "unauthorized" in the real meaning of the word.

**Missing `Content-Type: application/json` on POST requests.**
```bash
# This will fail — server receives the body as a string, not parsed JSON
curl -X POST http://localhost:8000/analyze -d '{"log": "error"}'

# This works — server knows to parse body as JSON
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "error"}'
```
FastAPI returns `422 Unprocessable Entity` when the body cannot be parsed. Always include `-H "Content-Type: application/json"` when sending JSON.

**Debugging without `-v` in curl.**
When a request fails, `curl url` only shows the response body. You cannot see the status code, the response headers, or the request headers being sent. Always debug with `curl -v` or at minimum `curl -I` (headers only). The status code and response headers explain 90% of failures.

**Assuming DNS resolution is the same inside containers.**
`localhost` inside a Docker container resolves to the container itself, not your host machine. If your AOIS container tries to reach a service at `localhost:5432` (Postgres), it fails — Postgres is on the host or another container. In Docker Compose, services are reachable by their service name: `postgres:5432`. This is the most common networking confusion when moving from local to containerized development.

---

## Troubleshooting

**"Connection refused" when hitting localhost:8000:**
The server is not running. Fix:
```bash
lsof -ti:8000          # check if anything is on port 8000 (empty = nothing)
uvicorn main:app --host 0.0.0.0 --port 8000 &    # start it
curl http://localhost:8000/health                 # test it
```

**"Could not connect to server" / DNS error:**
```bash
ping -c 1 8.8.8.8           # test raw network (no DNS)
nslookup api.anthropic.com  # test DNS
```
If `ping 8.8.8.8` works but `nslookup` fails — DNS issue in your environment.

**curl returns HTML instead of JSON:**
You are hitting the wrong endpoint or a proxy. Check the URL exactly. Use `-v` to see the full response.

**"Recv failure: Connection reset by peer":**
The server closed the connection unexpectedly. Check server logs for the exception.

**FastAPI returns 422 when you POST:**
```bash
curl -v -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "test"}'
```
Read the response body — FastAPI's 422 includes the exact field that failed validation:
```json
{
    "detail": [
        {
            "loc": ["body", "log"],
            "msg": "field required",
            "type": "value_error.missing"
        }
    ]
}
```

---

## Connection to later phases

- **Phase 1 (v1)**: Every `curl` command in the test cases uses exactly these flags. You will know what you are looking at.
- **Phase 2 (v4)**: Docker container networking uses the same concepts — ports, IP addresses, how services find each other
- **Phase 3 (v6)**: Kubernetes networking is layers built on top of this — pods have IPs, Services expose ports, Ingress handles routing
- **Phase 6 (v16)**: OpenTelemetry traces show you HTTP request spans — you will read them because you understand the request lifecycle
- **Phase 7 (v20)**: When AOIS uses tools like `get_pod_logs`, those tools make HTTP calls to the Kubernetes API — same mechanism

---

## Mastery Checkpoint

HTTP is how every service in this project communicates. These exercises prove you understand the protocol, not just the tool.

**1. Read a full -v output with no confusion**
Run:
```bash
curl -v https://api.github.com/users/kolinzking 2>&1 | head -50
```
For every line in the output, explain what it means. Identify: the DNS resolution line, the TCP connection line, the TLS handshake summary, each request header you sent, the response status line, each response header. You should be able to read this output like reading English.

**2. Understand every HTTP status code you will encounter**
Without looking them up, explain what these status codes mean and when AOIS returns each one:
- `200 OK` — 
- `201 Created` — 
- `400 Bad Request` — 
- `401 Unauthorized` — 
- `403 Forbidden` — 
- `404 Not Found` — 
- `422 Unprocessable Entity` — 
- `429 Too Many Requests` — 
- `500 Internal Server Error` — 
- `503 Service Unavailable` — 
Then verify by deliberately triggering some of these from AOIS (try sending a request with a missing `log` field to get 422; try sending to a non-existent endpoint to get 404).

**3. Parse a JSON response from the GitHub API**
Run:
```bash
curl -s "https://api.github.com/users/kolinzking/repos?sort=updated" | \
  python3 -c "
import sys, json
repos = json.load(sys.stdin)
print(f'Total repos: {len(repos)}')
for r in repos[:3]:
    print(f'  {r[\"name\"]} — last updated: {r[\"updated_at\"]}')
"
```
Now modify the Python to also print the language field for each repo. The point: you can navigate any JSON API response.

**4. Understand headers by manipulating them**
Send a request to AOIS without the `Content-Type: application/json` header. What happens? Why? Now send it with the wrong content type (`Content-Type: text/plain`). What changes?
```bash
# No Content-Type
curl -s -X POST http://localhost:8000/analyze -d '{"log": "test"}'

# Wrong Content-Type
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: text/plain" \
  -d '{"log": "test"}'
```
FastAPI's response tells you exactly what is wrong. Read it.

**5. Measure API latency**
Use curl's timing output to measure how long each part of an AOIS request takes:
```bash
curl -s -o /dev/null -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service"}' \
  -w "DNS: %{time_namelookup}s | Connect: %{time_connect}s | TTFB: %{time_starttransfer}s | Total: %{time_total}s\n"
```
TTFB (Time To First Byte) is how long before the server started responding. Total minus TTFB is how long the response took to transfer. The difference between Claude with cache and without cache should be visible here.

**6. The full trace: from curl to Claude and back**
With AOIS running, send a request while watching the server logs. Write down the complete journey of one byte of your log data: starting from the moment you press Enter, through TCP, HTTP parsing, FastAPI routing, Pydantic validation, the outbound Claude API call (another TCP connection, another HTTP request), the response parsing, the JSON serialization, and back to your terminal. If you can narrate this journey without gaps, you understand network programming.

**The mastery bar**: HTTP is the plumbing of everything you build. When something breaks in Phase 3 (Kubernetes Ingress not routing), Phase 4 (Bedrock endpoint not responding), or Phase 6 (OTel trace not showing), HTTP knowledge is what lets you diagnose it. A curl command with `-v` is often the fastest debugging tool you have.
