# v0.4 — Networking & HTTP: How the Internet Works

## What this version builds

You will use curl to hit real APIs, read the raw HTTP request and response, and understand exactly what happens when your FastAPI server receives a request. By the end, `curl -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{...}'` will have no mystery in it.

---

## IP addresses and ports

Every machine on a network has an IP address. Every process that wants to receive network connections listens on a port number.

```
IP address: 192.168.1.10        (which machine)
Port:       8000                (which process on that machine)
Together:   192.168.1.10:8000   (exactly one process, on one machine)
```

Port ranges:
- `0–1023` — well-known ports, require root (80=HTTP, 443=HTTPS, 22=SSH, 5432=Postgres, 6379=Redis)
- `1024–49151` — registered ports, common for applications
- `49152–65535` — dynamic/private ports

When you run `uvicorn main:app --port 8000`, you are binding port 8000 on your machine. Anything connecting to `localhost:8000` reaches your process.

`localhost` = `127.0.0.1` = "this machine". When running in Codespaces, `0.0.0.0` means "all interfaces" — required so the Codespaces forwarding layer can reach your server from outside.

---

## DNS — turning names into addresses

When you type `api.anthropic.com`, your computer does not know the IP address. It asks a DNS resolver.

```
Your code                  DNS resolver              Anthropic's server
    |                           |                           |
    |--- "what is the IP of --->|                           |
    |    api.anthropic.com?"    |                           |
    |                           |--- queries DNS chain ---->|
    |                           |<--- returns IP address ---|
    |<-- "IP is 52.84.x.x" ----|                           |
    |                                                       |
    |------------- connects to 52.84.x.x:443 ------------->|
```

```bash
nslookup api.anthropic.com      # DNS lookup
dig api.anthropic.com           # detailed DNS lookup
ping google.com                 # connectivity check (ICMP, not HTTP)
traceroute google.com           # trace the network path
```

---

## HTTP — the language of the web

HTTP is a text protocol. Every API call you make — to Claude, to OpenAI, to your own FastAPI server — is an HTTP request. Understanding the raw format removes all abstraction.

### Request structure

```
METHOD /path HTTP/1.1
Header-Name: header-value
Header-Name: header-value
                            <-- blank line separates headers from body
{
    "body": "here"
}
```

Real example:
```
POST /analyze HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Authorization: Bearer sk-ant-...
Content-Length: 45

{"log": "OOMKilled on pod/payment-service"}
```

### Response structure

```
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 142

{
    "summary": "...",
    "severity": "P1",
    ...
}
```

---

## HTTP methods

| Method | Purpose | Has body? | Common use |
|--------|---------|-----------|------------|
| GET | Retrieve a resource | No | Fetch data |
| POST | Create or submit | Yes | Send log for analysis, create resource |
| PUT | Replace a resource | Yes | Full update |
| PATCH | Partial update | Yes | Partial update |
| DELETE | Remove a resource | No | Delete resource |

For AOIS: `POST /analyze` because you are submitting data for processing, not retrieving an existing resource.

---

## HTTP status codes

These tell you what happened. Every API you build and every API you call uses these.

| Code | Meaning | When you see it |
|------|---------|----------------|
| 200 | OK | Request succeeded |
| 201 | Created | Resource was created (POST) |
| 204 | No Content | Succeeded, no body returned |
| 400 | Bad Request | Your request was malformed |
| 401 | Unauthorized | No valid authentication |
| 403 | Forbidden | Authenticated but not allowed |
| 404 | Not Found | That path doesn't exist |
| 422 | Unprocessable Entity | Valid syntax but bad data (FastAPI's validation error) |
| 429 | Too Many Requests | Rate limited |
| 500 | Internal Server Error | Bug in the server |
| 503 | Service Unavailable | Server is down or overloaded |

When AOIS returns 422, FastAPI's Pydantic validation rejected the input — the `log` field was missing or wrong type. When it returns 429, slowapi's rate limiter triggered. When Claude's API returns 429, you hit their rate limit.

---

## curl — your API debugging tool

You will use curl to test every endpoint you build. Master it.

```bash
# Basic GET
curl http://localhost:8000/health

# GET with formatted output
curl -s http://localhost:8000/health | python3 -m json.tool

# POST with JSON body
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"log": "OOMKilled pod/payment-service"}'

# Show response headers
curl -I http://localhost:8000/health        # HEAD request — headers only
curl -v http://localhost:8000/health        # verbose — see full request and response

# With authentication header
curl -H "Authorization: Bearer your-token" http://api.example.com/endpoint

# See the status code only
curl -o /dev/null -s -w "%{http_code}" http://localhost:8000/health

# Follow redirects
curl -L http://example.com

# Save response to file
curl -o response.json http://localhost:8000/health

# POST with file as body
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d @payload.json
```

**Flags reference:**
- `-s` — silent (no progress bar)
- `-X` — HTTP method
- `-H` — add a header
- `-d` — request body
- `-v` — verbose (shows request + response headers)
- `-I` — HEAD only (response headers, no body)
- `-o` — save output to file
- `-L` — follow redirects
- `-w` — write out format (useful for status codes)

---

## Headers you will see constantly

```
Content-Type: application/json        # body is JSON
Content-Type: text/plain              # body is plain text
Authorization: Bearer <token>         # auth token
X-API-Key: sk-ant-...                # API key authentication
Accept: application/json             # client wants JSON response
Content-Length: 234                  # body size in bytes
Cache-Control: no-cache              # caching directive
```

In FastAPI, when you send a request without `Content-Type: application/json`, the server cannot parse your JSON body and returns 422.

---

## JSON — the language APIs speak

JSON (JavaScript Object Notation) is the standard format for API request and response bodies.

```json
{
    "string_field": "hello world",
    "number_field": 42,
    "float_field": 0.95,
    "boolean_field": true,
    "null_field": null,
    "array_field": ["P1", "P2", "P3"],
    "object_field": {
        "nested_key": "nested_value"
    }
}
```

In Python:
```python
import json

# Parse JSON string to Python dict
data = json.loads('{"severity": "P1", "confidence": 0.95}')
print(data["severity"])    # P1

# Convert Python dict to JSON string
payload = {"log": "OOMKilled pod/payment"}
json_string = json.dumps(payload)
print(json_string)         # {"log": "OOMKilled pod/payment"}

# Pretty print
print(json.dumps(data, indent=2))
```

---

## Hit a real API

Hit the GitHub API — no authentication needed for public endpoints:

```bash
# Get your own GitHub profile
curl -s https://api.github.com/users/kolinzking | python3 -m json.tool

# See rate limit info
curl -s -I https://api.github.com/users/kolinzking | grep -i "x-rate"

# List repos
curl -s https://api.github.com/users/kolinzking/repos | python3 -m json.tool | head -50
```

Now look at the verbose output of a real HTTPS connection:
```bash
curl -v https://api.github.com/users/kolinzking 2>&1 | head -40
```

You will see:
- TLS handshake
- Request headers curl sent
- Response status and headers
- Body

This is exactly what happens when your Python code calls `anthropic_client.messages.create(...)` — the SDK wraps this same HTTP request.

---

## REST conventions

REST is not a protocol. It is a set of conventions for designing URLs and using HTTP methods consistently.

```
GET    /incidents          → list all incidents
GET    /incidents/123      → get incident with ID 123
POST   /incidents          → create a new incident
PUT    /incidents/123      → replace incident 123
PATCH  /incidents/123      → update parts of incident 123
DELETE /incidents/123      → delete incident 123
```

For AOIS:
```
POST /analyze              → analyze a log (submit for processing, get result back)
GET  /health               → liveness check
GET  /docs                 → FastAPI auto-generated OpenAPI docs
```

---

## What happens when you curl localhost:8000/analyze

Walking through every step:

1. curl resolves `localhost` to `127.0.0.1`
2. curl opens a TCP connection to `127.0.0.1:8000`
3. curl sends the HTTP request (method, headers, body) over that connection
4. uvicorn (listening on port 8000) accepts the connection
5. uvicorn passes the request to FastAPI
6. FastAPI reads the path (`/analyze`), finds the matching route
7. FastAPI reads the body, runs Pydantic validation on it
8. If validation passes: FastAPI calls your `analyze()` function with the validated `LogInput` object
9. Your function calls `analyze_with_claude()` which calls Anthropic's API (another HTTP request, outbound)
10. Claude responds with the structured analysis
11. Your function returns an `IncidentAnalysis` object
12. FastAPI serializes it to JSON
13. FastAPI sends the HTTP response back to curl
14. curl receives and prints it

Every step in that chain is something you can debug when something goes wrong.

---

## Checking network in the terminal

```bash
ss -tlnp                    # what ports are listening (replaces netstat)
ss -tlnp | grep 8000        # is something on port 8000?
netstat -tlnp               # older alternative
curl -v http://localhost:8000/health   # is the server actually responding?
lsof -i :8000               # what process owns port 8000
```

These commands diagnose the most common "why isn't my server reachable" problems:
- Not listening: `ss -tlnp` shows nothing on that port — server isn't running
- Wrong host: bound to `127.0.0.1` instead of `0.0.0.0` — not reachable externally
- Port conflict: another process is on that port
- Firewall: port is open but traffic is blocked
