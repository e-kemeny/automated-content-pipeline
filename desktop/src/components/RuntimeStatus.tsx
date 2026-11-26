import { useEffect, useState } from 'react'
import { checkWorkerOnce, desktopPresentation, getRuntimeStatus } from '../runtime'
import type { RuntimeStatus as Status, WorkerStatus } from '../runtime'

export function RuntimeStatus() {
 const [status, setStatus] = useState<Status>({ kind: 'checking' })
 const [worker, setWorker] = useState<WorkerStatus>({ kind: 'checking' })
 useEffect(() => {
  let active = true
  void getRuntimeStatus().then(async result => {
   if (!active) return
   setStatus(result)
   if (result.kind === 'ready') {
    const health = await checkWorkerOnce()
    if (active) setWorker(health)
   }
  })
  return () => { active = false }
 }, [])
 const { label, detail } = desktopPresentation(status, worker)
 return <div className="runtime-status">
  <span className="preview-label" tabIndex={0} role="status" aria-live="polite" aria-describedby="runtime-description">{label}</span>
  <span id="runtime-description" role="tooltip" className="runtime-tooltip">{detail}</span>
 </div>
}
