import { useRef, useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import { Icon } from './Icons'
import { TimelineArtwork } from './SignalAperture'
export type SelectedFile = { name: string; size: number; type: string }

export function Studio({ selected, onSelect, sourceControls }: { sourceControls?: ReactNode; selected: SelectedFile | null; onSelect: (file: SelectedFile | null) => void }) {
 const input = useRef<HTMLInputElement>(null)
 const [error, setError] = useState('')
 function choose(event: ChangeEvent<HTMLInputElement>) {
  const file = event.target.files?.[0]
  if (!file) return
  if (!(file.type.startsWith('video/') || /\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(file.name))) { setError('Choose a video file.'); event.target.value = ''; return }
  onSelect({ name: file.name, size: file.size, type: file.type || 'Type not provided' })
  setError(''); event.target.value = ''
 }
 return <div className="studio-layout">
  <section className="stage-panel" aria-label="Decorative timeline illustration"><TimelineArtwork /></section>
  <section className="source-panel" aria-labelledby="source-title">
   <div className="panel-heading"><span id="source-title">Source</span><Icon name="file"/></div>
   {sourceControls ?? <>
   <div className="source-content">
    <div className="import-symbol"><Icon name="plus" width="30" height="30"/></div>
    <h2>{selected ? 'Selected file' : 'No video selected'}</h2>

    <input ref={input} type="file" accept="video/*,.mkv,.avi,.m4v" onChange={choose} tabIndex={-1} hidden />
    <button className="primary-button" aria-describedby="file-scope" onClick={()=>input.current?.click()}><Icon name="plus"/>{selected ? 'Change video' : 'Import video'}<Icon name="arrow"/></button>
    <span className="file-hint">MP4 · MOV · MKV · WEBM</span>
    {error && <p className="file-error" role="alert">{error}</p>}
    {selected && <div className="file-selection" role="status"><span className="file-name">{selected.name}</span><span className="technical">{(selected.size/1024/1024).toFixed(2)} MiB · {selected.type}</span><button className="text-button" onClick={()=>onSelect(null)}>Clear selection</button></div>}
   </div>
   <div className="source-note" id="file-scope">File metadata only<span className="sr-only">. Nothing is uploaded, saved or processed.</span></div>
   </>}
  </section>

 </div>
}

export function Review() {
 return <div className="review-layout">
  <section className="candidate-panel"><div className="panel-heading"><span>Candidates</span><Icon name="film"/></div><div className="candidate-empty"><span className="empty-outline" aria-hidden="true"/><p>No clips yet</p></div></section>
  <section className="viewer-panel" aria-label="Empty review viewer"><div className="panel-heading"><span>Clip viewer</span></div><div className="viewer-empty"><Icon name="review" width="38" height="38"/><h2>No clip selected</h2></div><div className="viewer-controls"><Icon name="film"/><span className="technical">Playback unavailable</span></div></section>
  <section className="inspector-panel"><div className="panel-heading">Inspector</div><div className="inspector-content"><dl><div><dt>Source</dt><dd>Not selected</dd></div><div><dt>Boundaries</dt><dd>Unavailable</dd></div></dl><label htmlFor="rating">Human rating</label><select id="rating" disabled aria-describedby="review-locked"><option>No clip selected</option></select><label htmlFor="notes">Review notes</label><textarea id="notes" disabled placeholder="Select a clip first"/><p id="review-locked" className="sr-only">Review tools are not connected.</p></div></section>
  <section className="review-timeline"><div className="panel-heading"><span>Timeline</span></div><div className="timeline-empty"><span/><p>No timing data</p></div></section>
 </div>
}

export function Exports() {
 return <div className="exports-layout">
  <section className="delivery-panel"><h2>Formats</h2><div className="format-art" aria-hidden="true"><div className="landscape-frame"><span/></div><div className="portrait-frame"><span/></div></div><div className="format-labels"><span>SHORT FORM</span><span>LONG FORM</span></div></section>
  <section className="export-history"><div className="panel-heading"><span>Export library</span></div><div className="export-columns" aria-hidden="true"><span>Output</span><span>Format</span><span>Status</span></div><div className="export-empty"><Icon name="exports" width="34" height="34"/><h2>No exports yet</h2></div><div className="destination"><Icon name="folder"/><div><span>Output location</span><p>No folder connected</p></div></div></section>
 </div>
}
