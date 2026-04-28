import { useState } from 'react'
import { triggerConsolidation, type ConsolidationReport } from '../api'

export default function ConsolidationPanel() {
  const [running, setRunning] = useState(false)
  const [report, setReport] = useState<ConsolidationReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  const trigger = async () => {
    setRunning(true)
    setError(null)
    try {
      const r = await triggerConsolidation()
      setReport(r.report)
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="consolidation-panel">
      <div style={{ color: '#94a3b8', fontSize: 12, lineHeight: 1.6 }}>
        Consolidation promotes high-salience episodic memories to semantic and
        autobiographical stores, applies exponential decay, and extracts patterns.
      </div>

      <button className="trigger-btn" onClick={trigger} disabled={running}>
        {running ? 'Running…' : 'Trigger Consolidation'}
      </button>

      {error && (
        <div style={{ color: '#f43f5e', fontSize: 12 }}>{error}</div>
      )}

      {report && (
        <div className="report-card">
          <div style={{ fontWeight: 600, color: '#e2e8f0', marginBottom: 8, fontSize: 12 }}>
            Last Report
          </div>
          <div className="report-row">
            <span className="report-key">Processed</span>
            <span className="report-val">{report.memories_processed}</span>
          </div>
          <div className="report-row">
            <span className="report-key">Promoted</span>
            <span className="report-val">{report.memories_promoted}</span>
          </div>
          <div className="report-row">
            <span className="report-key">Pruned</span>
            <span className="report-val">{report.memories_pruned}</span>
          </div>
          <div className="report-row">
            <span className="report-key">Patterns</span>
            <span className="report-val">{report.patterns_found.length}</span>
          </div>
          {report.patterns_found.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 10, color: '#475569', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Extracted Patterns
              </div>
              {report.patterns_found.map((p, i) => (
                <div key={i} style={{ fontSize: 11, color: '#94a3b8', padding: '3px 0', borderBottom: '1px solid #1e293b' }}>
                  {p}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
