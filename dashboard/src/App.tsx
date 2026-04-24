import { useState, useEffect, useRef } from 'react'
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

type Tab = 'feed' | 'heatmap' | 'actions'

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [connected, setConnected] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('feed')
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    fetch('/api/incidents')
      .then(r => r.json())
      .then(data => setIncidents(data))
      .catch(() => {})

    let retryDelay = 1000

    function connect() {
      const ws = new WebSocket(`ws://${window.location.host}/ws/incidents`)
      wsRef.current = ws

      ws.onopen = () => { setConnected(true); retryDelay = 1000 }
      ws.onclose = () => {
        setConnected(false)
        setTimeout(connect, retryDelay)
        retryDelay = Math.min(retryDelay * 2, 30000)
      }
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === 'incident') {
          setIncidents(prev => [msg.data, ...prev.slice(0, 49)])
        }
      }
    }

    connect()
    return () => wsRef.current?.close()
  }, [])

  const handleApprove = (sessionId: string) => {
    fetch(`/api/approve/${sessionId}`, { method: 'POST' })
      .then(r => r.json())
      .then(() => setIncidents(prev => prev.map(i =>
        i.session_id === sessionId ? { ...i, human_approved: true } : i
      )))
      .catch(console.error)
  }

  const tabClass = (tab: Tab) =>
    `px-4 py-2 rounded text-sm font-medium transition-colors ${
      activeTab === tab
        ? 'bg-gray-700 text-white'
        : 'text-gray-400 hover:text-gray-200'
    }`

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4">
      <header className="mb-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">AOIS Dashboard</h1>
          <span className={`px-2 py-1 rounded text-xs font-mono ${
            connected ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
          }`}>
            {connected ? '● LIVE' : '○ DISCONNECTED'}
          </span>
        </div>
        <p className="text-gray-400 text-sm mt-1">AI Operations Intelligence System — {incidents.length} incidents</p>
      </header>

      <div className="mb-4 flex gap-1 bg-gray-900 p-1 rounded w-fit">
        <button className={tabClass('feed')} onClick={() => setActiveTab('feed')}>Incident Feed</button>
        <button className={tabClass('heatmap')} onClick={() => setActiveTab('heatmap')}>Severity Map</button>
        <button className={tabClass('actions')} onClick={() => setActiveTab('actions')}>Agent Actions</button>
      </div>

      {activeTab === 'feed' && <IncidentFeed incidents={incidents} onApprove={handleApprove} />}
      {activeTab === 'heatmap' && <SeverityHeatmap incidents={incidents} />}
      {activeTab === 'actions' && <AgentActionLog incidents={incidents} />}
    </div>
  )
}
