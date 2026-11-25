import { useEffect, useState } from 'react'
import { getRuntimeStatus, runtimePresentation } from '../runtime'
import type { RuntimeStatus as Status } from '../runtime'

export function RuntimeStatus() {
 const [status, setStatus] = useState<Status>({ kind: 'checking' })
 useEffect(() => {
  let active = true
  void getRuntimeStatus().then(result => { if (active) setStatus(result) })
  return () => { active = false }
 }, [])
 const { label, detail } = runtimePresentation(status)
 return <div className="runtime-status">
  <span className="preview-label" tabIndex={0} role="status" aria-live="polite" aria-describedby="runtime-description">{label}</span>
  <span id="runtime-description" role="tooltip" className="runtime-tooltip">{detail}</span>
 </div>
}
