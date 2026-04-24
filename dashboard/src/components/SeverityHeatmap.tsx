import type { Incident } from '../App'

interface SeverityHeatmapProps {
  incidents: Incident[]
}

export function SeverityHeatmap({ incidents }: SeverityHeatmapProps) {
  const counts = incidents.reduce(
    (acc, inc) => { const s = inc.severity ?? 'P4'; acc[s] = (acc[s] ?? 0) + 1; return acc },
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
  const recent10 = incidents.slice(0, 10)
  const avgCostRecent10 = recent10.length > 0
    ? recent10.reduce((sum, i) => sum + (i.cost_usd ?? 0), 0) / recent10.length
    : 0

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
                className={`h-2 rounded-full ${bar.color} transition-all`}
                style={{ width: `${(bar.count / total) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
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
        <div className="bg-gray-900 rounded-lg p-4">
          <div className="text-sm text-gray-400">Avg cost (last 10)</div>
          <div className="text-2xl font-bold text-white mt-1">${avgCostRecent10.toFixed(6)}</div>
        </div>
      </div>
    </div>
  )
}
