// MemoizedComponents — Performance-optimized wrappers to prevent unnecessary re-renders
import React from 'react';

const INK     = '#070B14';
const PANEL   = '#0C1322';
const PANEL2  = '#101A2E';
const LINE    = 'rgba(63,213,255,0.12)';
const SCAN    = '#39FF88';
const AMBER   = '#FFB020';
const CRIMSON = '#FF3B5C';
const CYAN    = '#3FD5FF';
const VIOLET  = '#A78BFA';
const INK_TEXT  = '#D7E4F2';
const MUTE_TEXT = '#5C7290';
const mono = "'IBM Plex Mono','JetBrains Mono',monospace";

const hex2rgb = (hex) => {
  const n = parseInt(hex.replace('#',''), 16);
  return `${(n>>16)&255},${(n>>8)&255},${n&255}`;
};

// ── MEMOIZED BLIP ──────────────────────────────────────────────
export const Blip = React.memo(({ color = SCAN, size = 7 }) => (
  <span style={{ position:'relative', display:'inline-block', width:size, height:size }}>
    <span style={{ position:'absolute', inset:0, borderRadius:'50%', background:color, boxShadow:`0 0 8px ${color}` }} />
    <span style={{ position:'absolute', inset:-4, borderRadius:'50%', border:`1px solid ${color}`, opacity:0.5, animation:'radarPing 2s ease-out infinite' }} />
  </span>
));
Blip.displayName = 'Blip';

// ── MEMOIZED PANEL ─────────────────────────────────────────────
export const Panel = React.memo(({ children, style={}, accent }) => (
  <div style={{ background:PANEL, border:`1px solid ${accent?`rgba(${hex2rgb(accent)},0.3)`:LINE}`, borderRadius:'4px', position:'relative', ...style }}>
    {accent && <div style={{ position:'absolute', top:0, left:0, right:0, height:'2px', background:`linear-gradient(90deg,transparent,${accent},transparent)` }} />}
    {children}
  </div>
));
Panel.displayName = 'Panel';

// ── MEMOIZED EYEBROW ───────────────────────────────────────────
export const Eyebrow = React.memo(({ children, color=MUTE_TEXT }) => (
  <div style={{ fontFamily:mono, fontSize:'0.68rem', letterSpacing:'0.18em', textTransform:'uppercase', color, marginBottom:'0.85rem', display:'flex', alignItems:'center', gap:'0.5rem' }}>
    <span style={{ width:14, height:1, background:color, opacity:0.5 }} />
    {children}
  </div>
));
Eyebrow.displayName = 'Eyebrow';

// ── MEMOIZED READOUT CARD ──────────────────────────────────────
export const ReadoutCard = React.memo(({ label, value, sub, color=SCAN }) => (
  <Panel accent={color}>
    <div style={{ padding:'1.1rem 1.3rem', display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
      <div>
        <div style={{ fontFamily:mono, fontSize:'0.65rem', letterSpacing:'0.14em', color:MUTE_TEXT, textTransform:'uppercase', marginBottom:'0.5rem' }}>{label}</div>
        <div style={{ fontFamily:mono, fontSize:'1.5rem', fontWeight:600, color, lineHeight:1 }}>{value}</div>
        {sub && <div style={{ fontSize:'0.68rem', color:MUTE_TEXT, marginTop:'0.35rem' }}>{sub}</div>}
      </div>
      <Blip color={color} />
    </div>
  </Panel>
));
ReadoutCard.displayName = 'ReadoutCard';

// ── MEMOIZED GAUGE ─────────────────────────────────────────────
export const Gauge = React.memo(({ value, max, color, size=86 }) => {
  const pct = Math.min(1, value / (max||0.001));
  const r = size/2 - 6;
  const circ = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} style={{ transform:'rotate(-90deg)' }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="5"
        strokeDasharray={circ} strokeDashoffset={circ*(1-pct)} strokeLinecap="round"
        style={{ filter:`drop-shadow(0 0 5px ${color})`, transition:'stroke-dashoffset 0.6s ease' }} />
    </svg>
  );
});
Gauge.displayName = 'Gauge';

// ── MEMOIZED AGENT NODE (SVG) ──────────────────────────────────
const statusColor = (s) =>
  s === 'BREACH' || s === 'QUARANTINED' ? CRIMSON : s === 'AT_RISK' ? AMBER : SCAN;

export const AgentNode = React.memo(({ x, y, label, status, mse }) => {
  const color = statusColor(status);
  const rgb   = hex2rgb(color);
  return (
    <g>
      <circle cx={x} cy={y} r={3} fill={color} opacity={0.4}>
        <animate attributeName="r"       values="3;34;3"   dur="2.8s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.4;0;0.4" dur="2.8s" repeatCount="indefinite" />
      </circle>
      <circle cx={x} cy={y} r={38} fill="none"
        stroke={color} strokeWidth="0.6" strokeDasharray="3 5" opacity="0.4" />
      <circle cx={x} cy={y} r={32}
        fill={`rgba(${rgb},0.09)`} stroke={color} strokeWidth="1.8"
        style={{ filter:`drop-shadow(0 0 10px ${color})` }} />
      <text x={x} y={y-5} textAnchor="middle"
        fill={INK_TEXT} fontSize={9} fontFamily={mono} fontWeight={700} letterSpacing="0.06em">
        {label.toUpperCase()}
      </text>
      <text x={x} y={y+10} textAnchor="middle"
        fill={color} fontSize={9} fontFamily={mono}>
        {mse?.toFixed(4)}
      </text>
    </g>
  );
});
AgentNode.displayName = 'AgentNode';

// ── MEMOIZED FINGERPRINT CARD ──────────────────────────────────
export const FingerprintCard = React.memo(({ agent, node, th, dl }) => {
  const n = node;
  const color = statusColor(n.status);
  return (
    <Panel accent={color} style={{ padding:'1.3rem' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'1rem' }}>
        <span style={{ fontFamily:mono, fontWeight:600, fontSize:'0.95rem', letterSpacing:'0.02em' }}>{agent}</span>
        <span style={{ fontFamily:mono, fontSize:'0.62rem', letterSpacing:'0.1em', padding:'0.2rem 0.6rem', borderRadius:'2px', color, border:`1px solid rgba(${hex2rgb(color)},0.4)`, background:`rgba(${hex2rgb(color)},0.08)` }}>
          {n.status.replace('_',' ')}
        </span>
      </div>
      <div style={{ display:'flex', alignItems:'center', gap:'1.1rem' }}>
        <Gauge value={n.mse} max={(th||0.02)*5} color={color} />
        <div style={{ flex:1 }}>
          <div style={{ marginBottom:'0.55rem' }}>
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:'0.68rem', color:MUTE_TEXT, marginBottom:'0.2rem' }}>
              <span>STRUCTURAL MSE</span>
              <span style={{ fontFamily:mono, color }}>{n.mse.toFixed(6)}</span>
            </div>
          </div>
          <div>
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:'0.68rem', color:MUTE_TEXT, marginBottom:'0.2rem' }}>
              <span>SEMANTIC DRIFT</span>
              <span style={{ fontFamily:mono, color:VIOLET }}>{n.drift.toFixed(6)}</span>
            </div>
            <div style={{ height:'3px', background:'rgba(255,255,255,0.06)', borderRadius:'2px' }}>
              <div style={{ height:'100%', width:`${Math.min(100,n.drift*200)}%`, background:VIOLET, borderRadius:'2px', transition:'width 0.5s' }} />
            </div>
          </div>
        </div>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'0.5rem', marginTop:'1rem', paddingTop:'0.8rem', borderTop:`1px solid ${LINE}`, fontFamily:mono, fontSize:'0.66rem' }}>
        <div><span style={{ color:MUTE_TEXT }}>THRESHOLD </span><span style={{ color:CYAN }}>{th?.toFixed(6)}</span></div>
        <div><span style={{ color:MUTE_TEXT }}>DRIFT LIMIT </span><span style={{ color:VIOLET }}>{dl?.toFixed(6)}</span></div>
      </div>
    </Panel>
  );
});
FingerprintCard.displayName = 'FingerprintCard';

// ── MEMOIZED PRESET BUTTON ─────────────────────────────────────
export const PresetButton = React.memo(({ label, color, onClick, disabled }) => (
  <button 
    onClick={onClick} 
    disabled={disabled}
    style={{ 
      background: `rgba(${hex2rgb(color)},0.1)`, 
      border: `1px solid ${color}`, 
      color, 
      borderRadius: '4px', 
      padding: '0.4rem 1rem', 
      fontSize: '0.65rem', 
      letterSpacing: '0.06em', 
      fontWeight: 600,
      opacity: disabled ? 0.4 : 1,
      transition: 'all 0.15s',
      whiteSpace: 'nowrap',
      fontFamily: mono
    }}
  >
    {label}
  </button>
));
PresetButton.displayName = 'PresetButton';

// ── MEMOIZED RESULT DISPLAY ────────────────────────────────────
export const ResultDisplay = React.memo(({ result, isCustom }) => {
  if (!result) return null;
  if (result.error) {
    return (
      <div style={{ marginTop:'1rem', padding:'0.75rem 1rem', background:`rgba(${hex2rgb(CRIMSON)},0.08)`, border:`1px solid rgba(${hex2rgb(CRIMSON)},0.3)`, borderRadius:'4px', color:CRIMSON, fontFamily:mono, fontSize:'0.75rem' }}>
        ◢ ERROR: {result.error}
      </div>
    );
  }
  
  const isClean = result.overall_status === 'CLEAN';
  const statusCol = isClean ? SCAN : CRIMSON;
  
  return (
    <div style={{ marginTop:'1.1rem', padding:'1rem 1.1rem', background:`rgba(${hex2rgb(statusCol)},0.06)`, border:`1px solid rgba(${hex2rgb(statusCol)},0.35)`, borderRadius:'4px', animation: 'fadeIn 0.3s ease-in' }}>
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'0.75rem' }}>
        <span style={{ fontFamily:mono, fontWeight:700, fontSize:'0.85rem', color:statusCol, letterSpacing:'0.05em' }}>
          ◢ {result.overall_status}
          {isClean && ' ✅'}
        </span>
        <span style={{ fontFamily:mono, fontSize:'0.65rem', color:MUTE_TEXT }}>{result.request_id}</span>
      </div>
      
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(130px,1fr))', gap:'0.6rem' }}>
        {[
          ['STRUCTURAL', result.structural_score?.toFixed(6), result.structural_status==='ALERT'?CRIMSON:SCAN],
          ['THRESHOLD',  result.structural_threshold?.toFixed(6), CYAN],
          ['DRIFT',      result.semantic_drift?.toFixed(6), result.semantic_status==='ALERT'?CRIMSON:SCAN],
          ['DRIFT LIMIT',result.semantic_threshold?.toFixed(6), VIOLET],
          ['CONFIDENCE', (result.confidence*100)?.toFixed(1)+'%', AMBER],
          ['LATENCY',    result.execution_time_ms?.toFixed(0)+'ms', CYAN],
        ].map(([k,v,c]) => (
          <div key={k} style={{ background:'rgba(0,0,0,0.3)', padding:'0.5rem 0.7rem', borderRadius:'3px' }}>
            <div style={{ fontFamily:mono, fontSize:'0.6rem', color:MUTE_TEXT, marginBottom:'0.2rem' }}>{k}</div>
            <div style={{ fontFamily:mono, fontSize:'0.82rem', color:c, fontWeight:600 }}>{v}</div>
          </div>
        ))}
      </div>
      
      {result.agent_output && (
        <div style={{ marginTop:'0.75rem', paddingTop:'0.75rem', borderTop:`1px solid ${LINE}` }}>
          <div style={{ fontFamily:mono, fontSize:'0.6rem', color:MUTE_TEXT, marginBottom:'0.3rem' }}>AGENT OUTPUT</div>
          <div style={{ fontFamily:mono, fontSize:'0.7rem', color:INK_TEXT, maxHeight:'100px', overflow:'auto', background:'rgba(0,0,0,0.2)', padding:'0.5rem', borderRadius:'3px' }}>
            {result.agent_output}
          </div>
        </div>
      )}
    </div>
  );
});
ResultDisplay.displayName = 'ResultDisplay';
