// ClockDisplay — Lightweight memoized clock to prevent full dashboard re-renders
import React, { useState, useEffect } from 'react';

const MUTE_TEXT = '#5C7290';
const mono = "'IBM Plex Mono','JetBrains Mono',monospace";

const ClockDisplay = React.memo(() => {
  const [clock, setClock] = useState(new Date().toLocaleTimeString());

  useEffect(() => {
    const t = setInterval(() => setClock(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <span style={{ fontFamily: mono, fontSize: '0.75rem', color: MUTE_TEXT }}>
      {clock}
    </span>
  );
});

ClockDisplay.displayName = 'ClockDisplay';
export default ClockDisplay;

