import type { SVGProps } from 'react'
export type IconName = 'studio' | 'review' | 'exports' | 'plus' | 'arrow' | 'file' | 'close' | 'film' | 'audio' | 'spark' | 'folder' | 'pause'
const paths: Record<IconName, string> = {
 studio: 'M4 8V4h4m8 0h4v4m0 8v4h-4M8 20H4v-4M8 8h8v8H8z',
 review: 'M4 5h16v12H4zM8 21h8M9 8l6 3-6 3z',
 exports: 'M12 15V3m-4 4 4-4 4 4M4 13v7h16v-7',
 plus: 'M12 5v14M5 12h14', arrow: 'M5 12h14m-6-6 6 6-6 6',
 file: 'M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6',
 close: 'm6 6 12 12M6 18 18 6', film: 'M3 5h18v14H3zM7 5v14m10-14v14M3 10h4m10 0h4M3 14h4m10 0h4',
 audio: 'M4 10v4m4-7v10m4-13v16m4-13v10m4-7v4',
 spark: 'm12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3z',
 folder: 'M3 7V5h7l2 2h9v12H3z', pause: 'M9 5v14M15 5v14',
}
export function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: IconName }) {
 return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name]} /></svg>
}
