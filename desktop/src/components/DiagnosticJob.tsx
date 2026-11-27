import { useEffect, useState } from 'react'
import { isTauri } from '@tauri-apps/api/core'
import { cancelDiagnosticJob, getDiagnosticJob, jobActive, newerJobState, startDiagnosticJob, watchDiagnosticJob } from '../runtime'
import type { JobSnapshot } from '../runtime'

function message(error: unknown) {
 if (error && typeof error === 'object' && 'message' in error && typeof error.message === 'string') return error.message
 return typeof error === 'string' ? error : 'Diagnostic connection unavailable'
}

export function DiagnosticJob({ visible }: { visible: boolean }) {
 const native = isTauri()
 const [snapshot, setSnapshot] = useState<JobSnapshot | null>(null)
 const [error, setError] = useState('')
 const [pending, setPending] = useState(false)
 useEffect(() => {
  let active = true
  let cleanup: (() => void) | undefined
  const update = (next: JobSnapshot) => {
   if (active) { setSnapshot(old => newerJobState(old, next)); setError('') }
  }
  const failure = (e: unknown) => { if (active) setError(message(e)) }
  void watchDiagnosticJob(update, failure).then(stop => { if (active) cleanup = stop; else stop() }).catch(failure)
  const reconcile = () => { void getDiagnosticJob().then(s => { if (s) update(s) }).catch(failure) }
  window.addEventListener('focus', reconcile)
  return () => { active = false; cleanup?.(); window.removeEventListener('focus', reconcile) }
 }, [])
 async function act(cancel: boolean) {
  setPending(true)
  try {
   const next = cancel && snapshot?.jobId ? await cancelDiagnosticJob(snapshot.jobId) : await startDiagnosticJob()
   if (next) setSnapshot(old => newerJobState(old, next))
   setError('')
  } catch (e) {
   setError(message(e))
   // A rejected duplicate start or a stale cancellation still reconciles native state.
   try { const current = await getDiagnosticJob(); if (current) setSnapshot(old => newerJobState(old,current)) } catch { /* retain actionable error */ }
  } finally { setPending(false) }
 }
 const active = snapshot ? jobActive(snapshot.state) : false
 return <section className="diagnostic-control" hidden={!visible} aria-label="Diagnostic job" data-state={snapshot?.state}>
  <div className="diagnostic-caption"><span>Diagnostic</span><span className="technical">No video processing</span></div>
  <div className="diagnostic-status" role="status" aria-live="polite">
   {!native ? 'Browser preview' : !snapshot ? 'Connecting' : snapshot.stage === snapshot.state ? snapshot.state : `${snapshot.state} · ${snapshot.stage}`}
   {snapshot && snapshot.state !== 'Idle' && <span className="technical"> {snapshot.progress.completed}/{snapshot.progress.total} checks</span>}
  </div>
  <progress aria-label="Diagnostic checks completed" max={12} value={snapshot?.progress.completed ?? 0}/>
  <div className="diagnostic-actions">
   <button className="text-button" disabled={!native || !snapshot || active || pending} onClick={() => void act(false)}>Run diagnostic</button>
   <button className="text-button" disabled={!active || snapshot?.state === 'Cancelling' || pending} onClick={() => void act(true)}>Cancel diagnostic</button>
  </div>
  {(error || snapshot?.error) && <p className="file-error" role="alert">{error || snapshot?.error?.message}</p>}
 </section>
}
