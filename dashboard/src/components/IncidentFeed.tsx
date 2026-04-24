import type { Incident } from '../App'

const SEVERITY_COLORS: Record<string, string> = {
  P1: 'bg-red-950 border border-red-600 text-red-300',
  P2: 'bg-orange-950 border border-orange-600 text-orange-300',
  P3: 'bg-yellow-950 border border-yellow-600 text-yellow-300',
  P4: 'bg-gray-900 border border-gray-700 text-gray-300',
}

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
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
          className={`rounded-lg p-4 ${SEVERITY_COLORS[incident.severity] ?? SEVERITY_COLORS.P4}`}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-bold text-sm">{incident.severity}</span>
                <span className="text-xs text-gray-400">{timeAgo(incident.created_at)}</span>
                <span className="text-xs text-gray-500 font-mono">${incident.cost_usd?.toFixed(6)}</span>
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
                  className="px-3 py-1 bg-green-800 hover:bg-green-700 text-green-200 text-xs rounded font-medium transition-colors"
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
