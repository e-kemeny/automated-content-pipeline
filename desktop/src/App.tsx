import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Brand } from './components/Brand'
import { Icon } from './components/Icons'
import { Studio, Review, Exports } from './components/Workspaces'
import type { SelectedFile } from './components/Workspaces'
const screens = [{ id: 'studio', label: 'Studio' }, { id: 'review', label: 'Review' }, { id: 'exports', label: 'Exports' }] as const
type Screen = typeof screens[number]['id']
export default function App() {
 const [screen, setScreen] = useState<Screen>('studio')
 const workspace = useRef<HTMLElement>(null)
 useLayoutEffect(() => { workspace.current?.scrollTo({ top: 0, left: 0, behavior: 'instant' }) }, [screen])
 const [file, setFile] = useState<SelectedFile | null>(null)
 const [motion, setMotion] = useState(true)
 const [visible, setVisible] = useState(!document.hidden)
 useEffect(()=>{ const update=()=>setVisible(!document.hidden); document.addEventListener('visibilitychange',update); return ()=>document.removeEventListener('visibilitychange',update) },[])
 return <div className="studio-app" data-motion={motion && visible ? 'on' : 'off'}>
  <a className="skip-link" href="#workspace">Skip to workspace</a>
  <header className="app-header"><Brand/><span className="preview-label" aria-describedby="preview-description">Preview mode</span><span id="preview-description" className="sr-only">Frontend only. File selection shows metadata. No ingestion, analysis or exports are connected.</span></header>
  <aside className="navigation-rail"><nav aria-label="Main navigation">{screens.map(item=><button className="nav-button" key={item.id} onClick={()=>setScreen(item.id)} aria-current={screen===item.id?'page':undefined}><Icon name={item.id}/><span>{item.label}</span></button>)}</nav><button className="motion-button" aria-label={motion?'Pause decorative motion':'Enable decorative motion'} aria-pressed={!motion} onClick={()=>setMotion(!motion)} title={motion?'Pause decorative motion':'Enable decorative motion'}><Icon name={motion?'pause':'spark'}/><span>Motion</span></button></aside>
  <main ref={workspace} id="workspace" tabIndex={-1}>
   <div className="workspace-heading"><h1>{screens.find(s=>s.id===screen)?.label}</h1></div>
   <div className="screen-transition" key={screen}>{screen==='studio'?<Studio selected={file} onSelect={setFile}/>:screen==='review'?<Review/>:<Exports/>}</div>

  </main>
 </div>
}
