import type { CSSProperties } from 'react'
// Illustrative editing composition only. No media or observation input.
const bars = Array.from({ length: 92 }, (_, i) => 5 + Math.abs(Math.sin(i * 1.7) * Math.cos(i * .31)) * 27)
const clips = [{ x: 126, width: 100, offset: -18 }, { x: 290, width: 124, offset: 0 }, { x: 492, width: 88, offset: 20 }]
export function TimelineArtwork() {
 return <div className="timeline-art" role="img" aria-label="Decorative editing illustration: selected regions of an abstract recording separate into clips. This is not source footage or processing progress.">
  <svg viewBox="0 0 720 380" fill="none" aria-hidden="true">
   <path className="art-rule" d="M54 90h612M54 285h612"/>
   {Array.from({length:31},(_,i)=><path key={i} className="art-tick" d={`M${60+i*20} 82v${i%5===0?-8:-4}`}/>)}
   <rect x="54" y="112" width="612" height="100" rx="6" className="source-strip"/>
   {Array.from({length:12},(_,i)=><g key={i}><path className="frame-divider" d={`M${60+i*50} 119v55`}/><path className="frame-contour" d={`M${64+i*50} 161l12 -${10+i%3*5} 12 7 15 -13`}/></g>)}
   {bars.map((height,i)=><path key={i} className="art-wave" d={`M${65+i*6.4} ${190-height/2}v${height}`}/>)}
   {clips.map((clip,i)=><g key={clip.x}>
    <rect x={clip.x} y="112" width={clip.width} height="100" rx="4" className="moment-outline"/>
    <path className="clip-guide" d={`M${clip.x+clip.width/2} 216v58`}/>
    <g className={`separated-clip clip-${i}`} style={{'--clip-shift': `${clip.offset}px`} as CSSProperties}>
     <rect x={clip.x} y="112" width={clip.width} height="66" rx="4" className="clip-body"/>
     <path d={`M${clip.x+10} 158l18 -20 19 10 17 -17`} className="clip-contour"/>
     <path d={`M${clip.x+10} 167h${clip.width-20}`} className="clip-detail"/>
    </g>
   </g>)}
   <g className="art-playhead"><path d="M60 100v124"/><path d="m55 94 5 6 5-6z"/></g>
  </svg>
 </div>
}
