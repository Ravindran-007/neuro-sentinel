
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const PANEL = '#0C1322';
const LINE = 'rgba(63,213,255,0.12)';
const SCAN = '#39FF88';
const AMBER = '#FFB020';
const CRIMSON = '#FF3B5C';
const CYAN = '#3FD5FF';
const VIOLET = '#A78BFA';
const INK_TEXT = '#D7E4F2';
const MUTE_TEXT = '#5C7290';

const mono = "'IBM Plex Mono','JetBrains Mono',monospace";

const hex2rgb = (hex) => {
  const n = parseInt(hex.replace('#', ''), 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
};

export const Blip = React.memo(({ color = SCAN, size = 7 }) => (
  <span
    style={{
      position: 'relative',
      display: 'inline-block',
      width: size,
      height: size,
    }}
  >
    <span
      style={{
        position: 'absolute',
        inset: 0,
        borderRadius: '50%',
        background: color,
        boxShadow: `0 0 8px ${color}`,
      }}
    />
    <span
      style={{
        position: 'absolute',
        inset: -4,
        borderRadius: '50%',
        border: `1px solid ${color}`,
        opacity: 0.5,
        animation: 'radarPing 2s ease-out infinite',
      }}
    />
  </span>
));
Blip.displayName = 'Blip';

export const Panel = React.memo(
  ({ children, style = {}, accent }) => (
    <div
      style={{
        background: PANEL,
        border: `1px solid ${
          accent ? `rgba(${hex2rgb(accent)},0.3)` : LINE
        }`,
        borderRadius: '4px',
        position: 'relative',
        ...style,
      }}
    >
      {accent && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '2px',
            background: `linear-gradient(90deg,transparent,${accent},transparent)`,
          }}
        />
      )}
      {children}
    </div>
  )
);
Panel.displayName = 'Panel';

export const Eyebrow = React.memo(
  ({ children, color = MUTE_TEXT }) => (
    <div
      style={{
        fontFamily: mono,
        fontSize: '0.68rem',
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
        color,
        marginBottom: '0.85rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
      }}
    >
      <span
        style={{
          width: 14,
          height: 1,
          background: color,
          opacity: 0.5,
        }}
      />
      {children}
    </div>
  )
);
Eyebrow.displayName = 'Eyebrow';

export const ReadoutCard = React.memo(
  ({ label, value, sub, color = SCAN }) => (
    <Panel accent={color}>
      <div
        style={{
          padding: '1.1rem 1.3rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <div>
          <div
            style={{
              fontFamily: mono,
              fontSize: '0.65rem',
              letterSpacing: '0.14em',
              color: MUTE_TEXT,
              textTransform: 'uppercase',
              marginBottom: '0.5rem',
            }}
          >
            {label}
          </div>
          <div
            style={{
              fontFamily: mono,
              fontSize: '1.5rem',
              fontWeight: 600,
              color,
              lineHeight: 1,
            }}
          >
            {value}
          </div>
          {sub && (
            <div
              style={{
                fontSize: '0.68rem',
                color: MUTE_TEXT,
                marginTop: '0.35rem',
              }}
            >
              {sub}
            </div>
          )}
        </div>
        <Blip color={color} />
      </div>
    </Panel>
  )
);
ReadoutCard.displayName = 'ReadoutCard';

export const Gauge = React.memo(
  ({ value, max, color, size = 86 }) => {
    const pct = Math.min(1, Math.max(0, value / (max || 0.001)));
    const r = size / 2 - 6;
    const circ = 2 * Math.PI * r;

    return (
      <svg
        width={size}
        height={size}
        style={{ transform: 'rotate(-90deg)' }}
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth="5"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - pct)}
          strokeLinecap="round"
          style={{
            filter: `drop-shadow(0 0 5px ${color})`,
            transition: 'stroke-dashoffset 0.6s ease',
          }}
        />
      </svg>
    );
  }
);
Gauge.displayName = 'Gauge';

const statusColor = (status) =>
  status === 'BREACH' || status === 'QUARANTINED'
    ? CRIMSON
    : status === 'AT_RISK'
      ? AMBER
      : SCAN;

export const AgentNode = React.memo(
  ({ x, y, label, status, mse }) => {
    const color = statusColor(status);
    const rgb = hex2rgb(color);

    return (
      <g>
        <circle cx={x} cy={y} r={3} fill={color} opacity={0.4}>
          <animate
            attributeName="r"
            values="3;34;3"
            dur="2.8s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.4;0;0.4"
            dur="2.8s"
            repeatCount="indefinite"
          />
        </circle>

        <circle
          cx={x}
          cy={y}
          r={38}
          fill="none"
          stroke={color}
          strokeWidth="0.6"
          strokeDasharray="3 5"
          opacity="0.4"
        />

        <circle
          cx={x}
          cy={y}
          r={32}
          fill={`rgba(${rgb},0.09)`}
          stroke={color}
          strokeWidth="1.8"
          style={{ filter: `drop-shadow(0 0 10px ${color})` }}
        />

        <text
          x={x}
          y={y - 5}
          textAnchor="middle"
          fill={INK_TEXT}
          fontSize={9}
          fontFamily={mono}
          fontWeight={700}
          letterSpacing="0.06em"
        >
          {label.toUpperCase()}
        </text>

        <text
          x={x}
          y={y + 10}
          textAnchor="middle"
          fill={color}
          fontSize={9}
          fontFamily={mono}
        >
          {mse?.toFixed(4)}
        </text>
      </g>
    );
  }
);
AgentNode.displayName = 'AgentNode';

export const PresetButton = React.memo(
  ({ label, color, onClick, disabled }) => (
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
        fontFamily: mono,
      }}
    >
      {label}
    </button>
  )
);
PresetButton.displayName = 'PresetButton';

export const ResultDisplay = React.memo(({ result, isCustom }) => {
  if (!result) return null;

  if (result.error) {
    return (
      <div
        style={{
          marginTop: '1rem',
          padding: '0.75rem 1rem',
          background: `rgba(${hex2rgb(CRIMSON)},0.08)`,
          border: `1px solid rgba(${hex2rgb(CRIMSON)},0.3)`,
          borderRadius: '4px',
          color: CRIMSON,
          fontFamily: mono,
          fontSize: '0.75rem',
        }}
      >
        ◢ ERROR: {result.error}
      </div>
    );
  }

  const isClean = result.overall_status === 'CLEAN';
  const isQuarantined = result.overall_status === 'QUARANTINED';
  const statusCol = isClean ? SCAN : CRIMSON;

  const output =
    typeof result.agent_output === 'string'
      ? result.agent_output
      : result.agent_output != null
        ? JSON.stringify(result.agent_output, null, 2)
        : '';

  return (
    <div
      style={{
        marginTop: '1.1rem',
        padding: '1rem 1.1rem',
        background: `rgba(${hex2rgb(statusCol)},0.06)`,
        border: `1px solid rgba(${hex2rgb(statusCol)},0.35)`,
        borderRadius: '4px',
        animation: 'fadeIn 0.3s ease-in',
        minWidth: 0,
      }}
    >
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .ns-agent-output h1,
        .ns-agent-output h2,
        .ns-agent-output h3 {
          color: ${CYAN};
          font-family: ${mono};
          line-height: 1.5;
          margin: 0.8rem 0 0.45rem;
        }

        .ns-agent-output h1 { font-size: 1rem; }
        .ns-agent-output h2 { font-size: 0.9rem; }
        .ns-agent-output h3 { font-size: 0.82rem; }

        .ns-agent-output p {
          margin: 0.45rem 0;
        }

        .ns-agent-output ul,
        .ns-agent-output ol {
          padding-left: 1.4rem;
          margin: 0.55rem 0;
        }

        .ns-agent-output li {
          margin: 0.3rem 0;
        }

        .ns-agent-output strong {
          color: #FFFFFF;
          font-weight: 700;
        }

        .ns-agent-output blockquote {
          margin: 0.7rem 0;
          padding: 0.4rem 0.8rem;
          border-left: 2px solid ${CYAN};
          background: rgba(63,213,255,0.05);
        }

        .ns-agent-output pre {
          white-space: pre-wrap;
          overflow-wrap: anywhere;
          background: rgba(0,0,0,0.35);
          padding: 0.75rem;
          border-radius: 3px;
          overflow-x: auto;
        }

        .ns-agent-output code {
          font-family: ${mono};
          font-size: 0.92em;
          overflow-wrap: anywhere;
          color: ${CYAN};
        }

        .ns-agent-output table {
          display: block;
          width: 100%;
          overflow-x: auto;
          border-collapse: collapse;
          margin: 0.7rem 0;
        }

        .ns-agent-output th,
        .ns-agent-output td {
          border: 1px solid ${LINE};
          padding: 0.5rem 0.65rem;
          text-align: left;
          vertical-align: top;
        }

        .ns-agent-output th {
          color: ${CYAN};
          background: rgba(63,213,255,0.06);
        }

        .ns-agent-output a {
          color: ${CYAN};
          overflow-wrap: anywhere;
        }

        .ns-agent-output hr {
          border: 0;
          border-top: 1px solid ${LINE};
          margin: 0.8rem 0;
        }
      `}</style>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '0.75rem',
          flexWrap: 'wrap',
          marginBottom: '0.75rem',
        }}
      >
        <span
          style={{
            fontFamily: mono,
            fontWeight: 700,
            fontSize: '0.85rem',
            color: statusCol,
            letterSpacing: '0.05em',
          }}
        >
          ◢ {result.overall_status}
          {isClean && ' ✅'}
        </span>

        <span
          style={{
            fontFamily: mono,
            fontSize: '0.65rem',
            color: MUTE_TEXT,
            overflowWrap: 'anywhere',
          }}
        >
          {result.request_id || ''}
        </span>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))',
          gap: '0.6rem',
        }}
      >
        {[
          [
            'STRUCTURAL',
            result.structural_score?.toFixed(6),
            result.structural_status === 'ALERT' ? CRIMSON : SCAN,
          ],
          ['THRESHOLD', result.structural_threshold?.toFixed(6), CYAN],
          [
            'DRIFT',
            result.semantic_drift?.toFixed(6),
            result.semantic_status === 'ALERT' ? CRIMSON : SCAN,
          ],
          ['DRIFT LIMIT', result.semantic_threshold?.toFixed(6), VIOLET],
          [
            'CONFIDENCE',
            Number.isFinite(result.confidence)
              ? `${(result.confidence * 100).toFixed(1)}%`
              : 'N/A',
            AMBER,
          ],
          [
            'LATENCY',
            Number.isFinite(result.execution_time_ms)
              ? `${result.execution_time_ms.toFixed(0)}ms`
              : 'N/A',
            CYAN,
          ],
        ].map(([key, value, color]) => (
          <div
            key={key}
            style={{
              background: 'rgba(0,0,0,0.3)',
              padding: '0.5rem 0.7rem',
              borderRadius: '3px',
              minWidth: 0,
            }}
          >
            <div
              style={{
                fontFamily: mono,
                fontSize: '0.6rem',
                color: MUTE_TEXT,
                marginBottom: '0.2rem',
              }}
            >
              {key}
            </div>
            <div
              style={{
                fontFamily: mono,
                fontSize: '0.82rem',
                color,
                fontWeight: 600,
                overflowWrap: 'anywhere',
              }}
            >
              {value ?? 'N/A'}
            </div>
          </div>
        ))}
      </div>

      {isQuarantined ? (
        <div
          role="status"
          style={{
            marginTop: '0.85rem',
            padding: '0.75rem',
            border: `1px solid rgba(${hex2rgb(CRIMSON)},0.3)`,
            borderRadius: '3px',
            background: `rgba(${hex2rgb(CRIMSON)},0.07)`,
            color: INK_TEXT,
            fontSize: '0.78rem',
            lineHeight: 1.6,
          }}
        >
          <strong style={{ color: CRIMSON }}>
            SECURITY POLICY — OUTPUT QUARANTINED
          </strong>
          <p style={{ margin: '0.45rem 0 0' }}>
            The request was quarantined by the security service. The
            potentially unsafe agent response is not displayed.
          </p>
          {result.reason && (
            <p style={{ margin: '0.45rem 0 0' }}>
              <strong>Reason: </strong>
              {String(result.reason)}
            </p>
          )}
        </div>
      ) : result.agent_output ? (
        <div
          style={{
            marginTop: '0.85rem',
            paddingTop: '0.75rem',
            borderTop: `1px solid ${LINE}`,
            minWidth: 0,
          }}
        >
          <div
            style={{
              fontFamily: mono,
              fontSize: '0.65rem',
              color: MUTE_TEXT,
              letterSpacing: '0.08em',
              marginBottom: '0.5rem',
            }}
          >
            AGENT OUTPUT
          </div>

          <div
            className="ns-agent-output"
            style={{
              fontFamily: "'Inter',-apple-system,sans-serif",
              fontSize: '0.82rem',
              lineHeight: 1.7,
              color: INK_TEXT,
              maxHeight: '360px',
              overflowY: 'auto',
              overflowX: 'auto',
              overflowWrap: 'anywhere',
              background: 'rgba(0,0,0,0.2)',
              padding: '0.85rem 1rem',
              borderRadius: '3px',
            }}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              skipHtml
            >
              {output}
            </ReactMarkdown>
          </div>
        </div>
      ) : !isQuarantined ? (
        <div
          style={{
            marginTop: '0.85rem',
            paddingTop: '0.75rem',
            borderTop: `1px solid ${LINE}`,
            color: MUTE_TEXT,
            fontSize: '0.75rem',
          }}
        >
          No agent output was returned by the backend.
        </div>
      ) : null}
    </div>
  );
});
ResultDisplay.displayName = 'ResultDisplay';
