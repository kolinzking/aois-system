import type { Incident } from '../App'

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
}

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
              {timeAgo(incident.created_at)}
            </span>
          </div>
          <p className="text-xs text-gray-300 truncate">{incident.incident}</p>
          <div className="mt-2 flex flex-wrap gap-1">
            <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
              incident.severity === 'P1' ? 'bg-red-900 text-red-300' :
              incident.severity === 'P2' ? 'bg-orange-900 text-orange-300' :
              incident.severity === 'P3' ? 'bg-yellow-900 text-yellow-300' :
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
