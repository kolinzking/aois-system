# v26 — React Dashboard: Real-Time Incident Feed with Streaming AI

⏱ **Estimated time: 8–10 hours**

---

## Prerequisites

v25 complete. Node.js 20+ installed. AOIS FastAPI running.

```bash
# Node.js 20+
node --version
# v20.x.x

# npm available
npm --version
# 10.x.x

# AOIS FastAPI running locally
curl -s http://localhost:8000/health | jq .
# {"status": "ok"}
```

---

## Learning Goals

By the end you will be able to:

- Scaffold a React + Vite application and connect it to the AOIS FastAPI backend
- Implement WebSocket streaming so incident analyses appear in real-time as the LLM generates them
- Build a severity heatmap component showing P1–P4 incident distribution over time
- Build an approve/reject remediation interface that calls `approve_and_continue()` on the LangGraph agent
- Serve the production build via nginx, co-located with the FastAPI backend in the Helm chart
- Explain the Vercel AI SDK pattern and when to use it over a raw WebSocket

---

## The Architecture

```
Browser                   FastAPI (AOIS)            Kafka
   │                           │                      │
   │  WebSocket /ws/incidents   │                      │
   │ ←────────────────────────  │                      │
   │                           │  ← kafka/consumer.py  │
   │  POST /api/approve/{id}   │                      │
   │ ────────────────────────→ │                      │
   │                           │
   │  GET /api/incidents       │
   │ ────────────────────────→ │
```

The WebSocket pushes incident analyses to the browser as they are written to the database by `kafka/consumer.py`. The approve endpoint triggers `approve_and_continue()` on the LangGraph agent.

---

## Setting Up the React App

```bash
cd /home/collins/aois-system
npm create vite@latest dashboard -- --template react-ts
cd dashboard
npm install
npm install lucide-react @radix-ui/react-tabs date-fns
```

Expected output:
```
> dashboard@0.0.0 dev
> vite

  VITE v5.x.x  ready in 312 ms
  ➜  Local:   http://localhost:5173/
```

---

## The WebSocket Backend Endpoint

Add to `main.py`:

```python
# WebSocket endpoint — pushes incidents to dashboard in real-time
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json

_connected_clients: list[WebSocket] = []


@app.websocket("/ws/incidents")
async def incident_websocket(websocket: WebSocket):
    await websocket.accept()
    _connected_clients.append(websocket)
    try:
        while True:
            await asyncio.sleep(30)  # keep-alive ping
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        _connected_clients.remove(websocket)


async def broadcast_incident(incident_data: dict):
    """Called by kafka/consumer.py after each analysis completes."""
    dead = []
    for client in _connected_clients:
        try:
            await client.send_json({"type": "incident", "data": incident_data})
        except Exception:
            dead.append(client)
    for client in dead:
        _connected_clients.remove(client)


@app.post("/api/approve/{session_id}")
async def approve_remediation(session_id: str):
    """Trigger LangGraph approve_and_continue for a pending remediation."""
    from langgraph_agent.graph import approve_and_continue
    result = await approve_and_continue(session_id)
    return {"status": "approved", "result": result.get("remediation_result", "")}


@app.get("/api/incidents")
async def list_incidents(limit: int = 50):
    """Fetch recent incidents from investigation_reports."""
    import asyncpg, os
    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    rows = await db.fetch(
        "SELECT session_id, incident, severity, hypothesis, proposed_action, "
        "human_approved, remediation_result, cost_usd, created_at "
        "FROM investigation_reports ORDER BY created_at DESC LIMIT $1",
        limit,
    )
    await db.close()
    return [dict(r) for r in rows]
```

---

## ▶ STOP — do this now

Test the WebSocket endpoint before building the UI:

```bash
# Install wscat
npm install -g wscat

# Connect to the WebSocket
wscat -c ws://localhost:8000/ws/incidents
Connected (press CTRL+C to quit)
< {"type": "ping"}
```

Keep the connection open. In another terminal, post an incident to the analyze endpoint. The WebSocket client should receive the analysis once the consumer processes it.

---

## The React Components

### App.tsx — Root with Tabs

```tsx
// dashboard/src/App.tsx
import { useState, useEffect, useRef } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@radix-ui/react-tabs'
import { IncidentFeed } from './components/IncidentFeed'
import { SeverityHeatmap } from './components/SeverityHeatmap'
import { AgentActionLog } from './components/AgentActionLog'

export interface Incident {
  session_id: string
  incident: string
  severity: string
  hypothesis: string
  proposed_action: string
  human_approved: boolean
  remediation_result: string
  cost_usd: number
  created_at: string
}

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    // Load existing incidents
    fetch('/api/incidents')
      .then(r => r.json())
      .then(data => setIncidents(data))

    // Connect WebSocket for real-time updates
    const ws = new WebSocket(`ws://${window.location.host}/ws/incidents`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'incident') {
        setIncidents(prev => [msg.data, ...prev.slice(0, 49)])
      }
    }

    return () => ws.close()
  }, [])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4">
      <header className="mb-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">AOIS Dashboard</h1>
          <span className={`px-2 py-1 rounded text-xs font-mono ${connected ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}`}>
            {connected ? '● LIVE' : '○ DISCONNECTED'}
          </span>
        </div>
        <p className="text-gray-400 text-sm mt-1">AI Operations Intelligence System</p>
      </header>

      <Tabs defaultValue="feed">
        <TabsList className="mb-4 bg-gray-900 p-1 rounded flex gap-1">
          <TabsTrigger value="feed" className="px-4 py-2 rounded text-sm">Incident Feed</TabsTrigger>
          <TabsTrigger value="heatmap" className="px-4 py-2 rounded text-sm">Severity Map</TabsTrigger>
          <TabsTrigger value="actions" className="px-4 py-2 rounded text-sm">Agent Actions</TabsTrigger>
        </TabsList>

        <TabsContent value="feed">
          <IncidentFeed incidents={incidents} onApprove={(id) => {
            fetch(`/api/approve/${id}`, { method: 'POST' })
              .then(r => r.json())
              .then(() => setIncidents(prev => prev.map(i =>
                i.session_id === id ? { ...i, human_approved: true } : i
              )))
          }} />
        </TabsContent>

        <TabsContent value="heatmap">
          <SeverityHeatmap incidents={incidents} />
        </TabsContent>

        <TabsContent value="actions">
          <AgentActionLog incidents={incidents} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
```

---

### IncidentFeed — Real-time Incident List with Approve/Reject

```tsx
// dashboard/src/components/IncidentFeed.tsx
import { formatDistanceToNow } from 'date-fns'
import type { Incident } from '../App'

const SEVERITY_COLORS: Record<string, string> = {
  P1: 'bg-red-900 border-red-500 text-red-300',
  P2: 'bg-orange-900 border-orange-500 text-orange-300',
  P3: 'bg-yellow-900 border-yellow-500 text-yellow-300',
  P4: 'bg-gray-800 border-gray-500 text-gray-300',
}

interface IncidentFeedProps {
  incidents: Incident[]
  onApprove: (sessionId: string) => void
}

export function IncidentFeed({ incidents, onApprove }: IncidentFeedProps) {
  if (incidents.length === 0) {
    return (
      <div className="text-gray-500 text-center py-12 text-sm">
        No incidents yet. Post to /analyze to generate one.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {incidents.map((incident) => (
        <div
          key={incident.session_id}
          className={`border rounded-lg p-4 ${SEVERITY_COLORS[incident.severity] ?? SEVERITY_COLORS.P4}`}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-bold text-sm">{incident.severity}</span>
                <span className="text-xs text-gray-400">
                  {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
                </span>
                <span className="text-xs text-gray-500 font-mono">
                  ${incident.cost_usd.toFixed(6)}
                </span>
              </div>
              <p className="text-sm font-mono truncate">{incident.incident}</p>
              {incident.hypothesis && (
                <p className="text-xs mt-2 text-gray-300">
                  <span className="font-semibold">Root cause: </span>
                  {incident.hypothesis.slice(0, 200)}
                </p>
              )}
              {incident.proposed_action && (
                <p className="text-xs mt-1 text-gray-400 font-mono bg-black/30 p-2 rounded">
                  {incident.proposed_action.slice(0, 300)}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-2 shrink-0">
              {!incident.human_approved && incident.proposed_action && (
                <button
                  onClick={() => onApprove(incident.session_id)}
                  className="px-3 py-1 bg-green-800 hover:bg-green-700 text-green-200 text-xs rounded font-medium"
                >
                  Approve
                </button>
              )}
              {incident.human_approved && (
                <span className="px-3 py-1 bg-green-900/50 text-green-400 text-xs rounded font-medium">
                  ✓ Approved
                </span>
              )}
            </div>
          </div>

          {incident.remediation_result && (
            <div className="mt-2 p-2 bg-black/30 rounded text-xs font-mono text-gray-300">
              {incident.remediation_result.slice(0, 200)}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
```

---

### SeverityHeatmap — Incident Distribution

```tsx
// dashboard/src/components/SeverityHeatmap.tsx
import type { Incident } from '../App'

interface SeverityHeatmapProps {
  incidents: Incident[]
}

export function SeverityHeatmap({ incidents }: SeverityHeatmapProps) {
  const counts = incidents.reduce(
    (acc, inc) => {
      const sev = inc.severity ?? 'P4'
      acc[sev] = (acc[sev] ?? 0) + 1
      return acc
    },
    {} as Record<string, number>
  )

  const total = incidents.length || 1
  const bars = [
    { label: 'P1', color: 'bg-red-500', count: counts.P1 ?? 0 },
    { label: 'P2', color: 'bg-orange-500', count: counts.P2 ?? 0 },
    { label: 'P3', color: 'bg-yellow-500', count: counts.P3 ?? 0 },
    { label: 'P4', color: 'bg-gray-500', count: counts.P4 ?? 0 },
  ]

  const totalCost = incidents.reduce((sum, i) => sum + (i.cost_usd ?? 0), 0)
  const pendingApproval = incidents.filter(i => i.proposed_action && !i.human_approved).length

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {bars.map(bar => (
          <div key={bar.label} className="bg-gray-900 rounded-lg p-4">
            <div className="text-3xl font-bold text-white">{bar.count}</div>
            <div className="flex items-center gap-2 mt-1">
              <div className={`w-3 h-3 rounded-sm ${bar.color}`} />
              <span className="text-sm text-gray-400">{bar.label} incidents</span>
            </div>
            <div className="mt-3 bg-gray-800 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${bar.color}`}
                style={{ width: `${(bar.count / total) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-gray-900 rounded-lg p-4">
          <div className="text-sm text-gray-400">Total investigation cost</div>
          <div className="text-2xl font-bold text-white mt-1">${totalCost.toFixed(4)}</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-4">
          <div className="text-sm text-gray-400">Pending approval</div>
          <div className={`text-2xl font-bold mt-1 ${pendingApproval > 0 ? 'text-yellow-400' : 'text-green-400'}`}>
            {pendingApproval}
          </div>
        </div>
      </div>
    </div>
  )
}
```

---

### AgentActionLog — Tool Call Timeline

```tsx
// dashboard/src/components/AgentActionLog.tsx
import { formatDistanceToNow } from 'date-fns'
import type { Incident } from '../App'

interface AgentActionLogProps {
  incidents: Incident[]
}

export function AgentActionLog({ incidents }: AgentActionLogProps) {
  const recentWithActions = incidents.filter(i => i.proposed_action).slice(0, 20)

  return (
    <div className="space-y-2">
      {recentWithActions.length === 0 && (
        <div className="text-gray-500 text-center py-12 text-sm">
          No agent actions yet.
        </div>
      )}
      {recentWithActions.map(incident => (
        <div key={incident.session_id} className="bg-gray-900 rounded p-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-mono text-gray-400">
              {incident.session_id.slice(0, 8)}...
            </span>
            <span className="text-xs text-gray-500">
              {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
            </span>
          </div>
          <p className="text-xs text-gray-300 truncate">{incident.incident}</p>
          <div className="mt-2 flex flex-wrap gap-1">
            <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
              incident.severity === 'P1' ? 'bg-red-900 text-red-300' :
              incident.severity === 'P2' ? 'bg-orange-900 text-orange-300' :
              'bg-gray-800 text-gray-400'
            }`}>{incident.severity}</span>
            {incident.human_approved && (
              <span className="px-1.5 py-0.5 rounded text-xs bg-green-900 text-green-300">approved</span>
            )}
            <span className="px-1.5 py-0.5 rounded text-xs bg-gray-800 text-gray-400 font-mono">
              ${incident.cost_usd?.toFixed(6)}
            </span>
          </div>
          {incident.proposed_action && (
            <p className="mt-1 text-xs font-mono text-gray-500 truncate">
              → {incident.proposed_action.slice(0, 100)}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}
```

---

## ▶ STOP — do this now

Build and run the dashboard:

```bash
cd dashboard
npm run dev
```

Open http://localhost:5173. You should see:
- Header with "AOIS Dashboard" and live connection indicator
- Three tabs: Incident Feed, Severity Map, Agent Actions
- Empty state in each tab (no incidents yet)

In another terminal, run a test incident through the AOIS consumer. Confirm the incident appears in the dashboard within 2 seconds without page refresh.

---

## The Vercel AI SDK Pattern

For the `investigate` flow where you want the LLM response to stream word-by-word into the UI (not appear all at once after the full analysis is complete), the Vercel AI SDK is the right tool.

```bash
npm install ai @ai-sdk/anthropic
```

```tsx
// dashboard/src/components/StreamingAnalysis.tsx
import { useChat } from 'ai/react'

export function StreamingAnalysis({ incident }: { incident: string }) {
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: '/api/chat',  // FastAPI endpoint that returns a streaming response
    initialMessages: [
      { id: '1', role: 'user', content: `Analyze this incident: ${incident}` }
    ],
  })

  return (
    <div className="space-y-2">
      {messages.map(m => (
        <div key={m.id} className={`p-3 rounded text-sm ${
          m.role === 'assistant' ? 'bg-blue-950 text-blue-200' : 'bg-gray-900 text-gray-300'
        }`}>
          <span className="font-bold text-xs text-gray-500">{m.role}: </span>
          {m.content}
          {isLoading && m.role === 'assistant' && <span className="animate-pulse">▋</span>}
        </div>
      ))}
    </div>
  )
}
```

The FastAPI streaming endpoint:

```python
from fastapi.responses import StreamingResponse
import anthropic
import json

@app.post("/api/chat")
async def chat_stream(body: dict):
    """Stream Claude analysis to the dashboard."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def generate():
        with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=body.get("messages", []),
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

When to use Vercel AI SDK vs raw WebSocket:
- **Vercel AI SDK**: user-initiated chat interactions, where you want streaming text and the SDK handles SSE parsing, message state, and re-renders automatically
- **Raw WebSocket**: server-pushed events (Kafka consumer results appearing in real-time without user interaction), where the server decides when to push

AOIS uses both: WebSocket for the real-time incident feed (server-pushed), Vercel AI SDK for the on-demand chat-style investigation view.

---

## ▶ STOP — do this now

Test the streaming endpoint directly:

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "auth-service OOMKilled exit code 137"}]}' \
  | head -20
```

Expected:
```
data: {"type": "text", "text": "This"}
data: {"type": "text", "text": " is"}
data: {"type": "text", "text": " a"}
...
data: [DONE]
```

Each line arrives as the LLM generates tokens.

---

## Production Build and nginx

```bash
# Build the React app
cd dashboard
npm run build
# Output: dist/

# Copy build to nginx serve location
# (in production this is in the Helm chart)
cp -r dist/ /var/www/aois-dashboard/
```

nginx config (added to Helm chart):

```nginx
# k8s/nginx/aois-dashboard.conf
server {
    listen 80;
    server_name _;

    # Serve React app
    location / {
        root /var/www/aois-dashboard;
        try_files $uri /index.html;  # React Router SPA fallback
    }

    # Proxy API calls to FastAPI
    location /api/ {
        proxy_pass http://aois-api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket proxy
    location /ws/ {
        proxy_pass http://aois-api:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## Common Mistakes

### 1. WebSocket not reconnecting after server restart

The dashboard's WebSocket closes when the server restarts. Without reconnect logic, the user sees "DISCONNECTED" permanently.

```tsx
// Add reconnect with exponential backoff
useEffect(() => {
  let ws: WebSocket
  let retryDelay = 1000

  function connect() {
    ws = new WebSocket(`ws://${window.location.host}/ws/incidents`)
    ws.onopen = () => { setConnected(true); retryDelay = 1000 }
    ws.onclose = () => {
      setConnected(false)
      setTimeout(connect, retryDelay)
      retryDelay = Math.min(retryDelay * 2, 30000)
    }
    ws.onmessage = (event) => { /* ... */ }
  }

  connect()
  return () => ws?.close()
}, [])
```

---

### 2. React state not updating after WebSocket message

Common cause: the `incidents` state is captured in a stale closure inside `ws.onmessage`.

```tsx
// Wrong — stale closure, incidents is empty forever
ws.onmessage = () => {
  setIncidents([...incidents, newIncident])  // 'incidents' is always []
}

// Correct — use functional update
ws.onmessage = () => {
  setIncidents(prev => [newIncident, ...prev.slice(0, 49)])
}
```

---

### 3. nginx WebSocket upgrade headers missing

```
WebSocket connection failed: Error during WebSocket handshake
```

The nginx WebSocket proxy requires two headers:

```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

Without both, nginx does not forward the HTTP → WebSocket upgrade and the connection fails.

---

## Troubleshooting

### Vite dev server not proxying to FastAPI

By default, `fetch('/api/incidents')` goes to `localhost:5173` (Vite), not `localhost:8000` (FastAPI). Add a proxy in `vite.config.ts`:

```typescript
export default {
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
}
```

---

### `CORS error` in browser console

FastAPI is rejecting requests from the Vite dev server origin. Add CORS middleware:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

In production (nginx proxy), CORS is not needed — the browser sees one origin.

---

## Connection to Later Phases

### To v27 (Auth)
The dashboard has no auth in v26. In v27, a login page is added, JWT tokens are stored, and every API call includes an Authorization header. RBAC determines which tabs a user can see and whether the Approve button is enabled.

### To v28 (CI/CD)
The React build is added to the GitHub Actions pipeline. On every push, `npm run build` runs, the dist/ is copied into the Docker image, and the Helm chart deploys the updated image. The dashboard ships as part of AOIS, not as a separate deployment.

### To v34.5 (Capstone)
The dashboard is the operator's window into the capstone game day. During the 1-hour chaos event, the operator watches P1 incidents appear in real-time, approves remediations, and measures MTTR from the agent action log timestamps.

---


## Build-It-Blind Challenge

Close the notes. From memory: write the FastAPI WebSocket endpoint that streams AOIS analysis results to the dashboard — connection management, JSON serialisation of `AnalysisResult`, broadcast to all connected clients, graceful disconnection handling. 20 minutes.

```javascript
// Client connects and receives:
// {"severity": "P1", "summary": "...", "suggested_action": "..."}
// within 2 seconds of Kafka consumer processing the incident
```

---

## Failure Injection

Connect 10 WebSocket clients simultaneously and kill the AOIS pod:

```bash
# Open 10 browser tabs on the dashboard
kubectl delete pod -n aois -l app=aois
# All 10 connections drop simultaneously
# Pod restarts — clients attempt to reconnect
```

Does the React dashboard handle the reconnection automatically? What is the user experience during the 10-15 second pod restart? This is the UX impact of your Kubernetes pod disruption budget — measure it.

---

## Osmosis Check

1. The dashboard displays severity distribution as a heatmap. The data comes from Prometheus (v16) via a Grafana panel, not directly from AOIS. Why is it architecturally correct to pull historical aggregations from Prometheus rather than from the WebSocket stream? (v16 Prometheus + v26 real-time vs historical distinction)
2. The React dashboard sends a JWT in the WebSocket upgrade request. The FastAPI WebSocket handler must validate it. Does the standard JWT middleware (v27) apply to WebSocket connections the same way it applies to HTTP requests? What is different about WebSocket authentication?

---

## Mastery Checkpoint

1. Run `npm run dev` and open the dashboard. Post 3 incidents with different severities via the analyze endpoint. Confirm all 3 appear in the Incident Feed without page refresh, and the Severity Heatmap shows the correct counts.

2. Click "Approve" on a pending incident. Confirm the button changes to "✓ Approved" and the FastAPI `approve_remediation` endpoint is called. Check the `investigation_reports` table for `human_approved=true`.

3. Add a new metric card to the SeverityHeatmap: "Avg investigation cost per incident (last 10)." Write the computation and render it alongside the existing cards.

4. Open the browser DevTools Network tab. Identify the WebSocket connection. What messages are exchanged during the keep-alive ping? What does a real incident message look like?

5. Explain to a non-technical person what the Severity Heatmap communicates. Why does a P1 bar being tall indicate a problem even if the total incident count is low?

6. Explain to a junior engineer why the WebSocket uses a functional state update (`prev => [newIncident, ...prev]`) instead of a direct update. What bug does this prevent?

7. Explain to a senior engineer: when does a WebSocket make sense over Server-Sent Events (SSE) for this use case? What does the bidirectionality of WebSocket add for AOIS specifically?

**The mastery bar:** you have a live React dashboard that shows AOIS incidents in real-time, streams AI analysis as it generates, and lets operators approve remediations with one click — no page refresh, no polling.

---

## 4-Layer Tool Understanding

### React + Vite

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | AOIS outputs JSON to a terminal. No one except you can interact with it. React + Vite turns that JSON into a web UI where any operator can see incidents in real-time, read analyses, and approve actions — without touching a terminal. |
| **System Role** | Where does it sit in AOIS? | The operator interface layer. React connects to FastAPI via WebSocket (real-time push) and REST (approve/list). Vite is the build tool that bundles the React app into static files served by nginx. In production, the dashboard is bundled inside the Helm chart — same deployment, one URL. |
| **Technical** | What is it, precisely? | React is a JavaScript UI library for building component-based interfaces. Vite is a build tool that compiles TypeScript/JSX to browser-ready JavaScript with hot module replacement during development. The production build (`npm run build`) outputs a `dist/` directory of static files that nginx serves. |
| **Remove it** | What breaks, and how fast? | Remove the dashboard → operators interact with AOIS via terminal only. The approve gate cannot be used without running Python scripts. P1 incidents are invisible unless someone checks the database. The human-in-the-loop approval that makes AOIS safe becomes a friction-filled process that people skip. |

### WebSocket

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | Without WebSocket, the dashboard would have to refresh the page or poll every few seconds to check for new incidents. WebSocket lets the server push new incidents to the browser the moment they are ready — instantly, without the browser asking. |
| **System Role** | Where does it sit in AOIS? | Between FastAPI and the React dashboard. The Kafka consumer calls `broadcast_incident()` after each analysis. FastAPI pushes the JSON payload to all connected WebSocket clients. The dashboard renders the new incident without any user action. |
| **Technical** | What is it, precisely? | A full-duplex TCP connection between browser and server, established via HTTP upgrade. Once connected, either side can send frames at any time without the other side having to request them. In FastAPI, implemented with `@app.websocket()` and `WebSocket.send_json()`. The browser uses `new WebSocket(url)` and `ws.onmessage`. |
| **Remove it** | What breaks, and how fast? | Remove WebSocket → incidents appear only on page load or manual refresh. A P1 incident that fires at 3am is invisible until someone opens the dashboard. Real-time becomes "eventually consistent with the operator's browser refresh cadence." Operator reaction time degrades from seconds to minutes. |

### Vercel AI SDK

| Layer | Question | Answer |
|---|---|---|
| **Plain English** | What problem does this solve? | When an operator asks "why is auth-service slow?" and the LLM is generating a 500-word analysis, they should see words appear in real-time — not wait 10 seconds for the full response to load. The Vercel AI SDK handles the SSE streaming, message state, loading indicators, and re-renders automatically. |
| **System Role** | Where does it sit in AOIS? | Inside the React dashboard's on-demand investigation view. The operator types a question, the SDK sends it to `/api/chat`, and tokens stream back word by word. Complements the WebSocket (which handles server-pushed events); the SDK handles user-initiated chat interactions. |
| **Technical** | What is it, precisely? | A TypeScript/React SDK (`ai` package) that wraps Server-Sent Events for streaming LLM responses. The `useChat` hook manages message state, handles streaming via `EventSource`, and triggers re-renders as new tokens arrive. The FastAPI side uses a `StreamingResponse` with `text/event-stream` content type. |
| **Remove it** | What breaks, and how fast? | Remove Vercel AI SDK → implement SSE parsing manually, manage message state manually, handle loading states manually, handle errors manually. Takes hours to reimplement correctly. Or use polling — each message takes the full LLM latency before appearing, and long analyses look like the app is hanging. |
