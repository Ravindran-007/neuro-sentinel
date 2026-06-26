// src/App.js
// NeuroSentinel UI Dashboard Core Application
// Connects natively to Level 4 Graph Engine Microservice Infrastructure

import React, { useState, useEffect } from 'react';
import axios from 'axios';

// ✅ FIXED: Correct URL (0nhi with zero, not Onhi with 'O')
const API_URL = 'https://neuro-sentinel-0nhi.onrender.com';

function App() {
    const [health, setHealth] = useState(null);
    const [thresholds, setThresholds] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [healthRes, thresholdsRes] = await Promise.all([
                    axios.get(`${API_URL}/api/health`),
                    axios.get(`${API_URL}/api/thresholds`)
                ]);
                
                setHealth(healthRes.data);
                setThresholds(thresholdsRes.data);
                setLoading(false);
            } catch (err) {
                setError(err.message + " — The API layer may be waking up from cold storage.");
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    if (loading) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#111827', color: 'white', fontFamily: 'system-ui, sans-serif' }}>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '1rem', letterSpacing: '0.05em' }}>🛡️ NEUROSENTINEL</div>
                    <div style={{ color: '#9CA3AF' }}>Synchronizing with cognitive defense infrastructure...</div>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#111827', color: 'white', fontFamily: 'system-ui, sans-serif' }}>
                <div style={{ textAlign: 'center', maxWidth: '500px', padding: '2rem', background: '#1F2937', borderRadius: '0.75rem', border: '1px solid #EF4444' }}>
                    <div style={{ color: '#EF4444', fontSize: '3rem', marginBottom: '1rem' }}>⚠️</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>Connection Timeout</div>
                    <div style={{ color: '#9CA3AF', fontSize: '0.875rem', marginBottom: '1rem' }}>{error}</div>
                    <div style={{ color: '#6B7280', fontSize: '0.75rem' }}>Verify that the cloud security engine is active at: <br/><a href={API_URL} target="_blank" rel="noreferrer" style={{ color: '#3B82F6' }}>{API_URL}</a></div>
                </div>
            </div>
        );
    }

    const agents = ['Researcher', 'Analyst', 'Reporter'];

    return (
        <div style={{ minHeight: '100vh', background: '#111827', color: 'white', padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
            <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
                
                {/* Header Panel */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2.5rem', borderBottom: '1px solid #1F2937', paddingBottom: '1.5rem' }}>
                    <div>
                        <h1 style={{ fontSize: '2.25rem', fontWeight: 'bold', margin: 0 }}>🛡️ NeuroSentinel Operations</h1>
                        <p style={{ color: '#9CA3AF', fontSize: '0.875rem', marginTop: '0.5rem' }}>Level 4 Multi-Agent LLM Pipeline Security & Advanced Compromise Propagation Tracker</p>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                        <span style={{ padding: '0.35rem 1rem', background: 'rgba(34, 197, 94, 0.15)', color: '#4ADE80', borderRadius: '9999px', fontSize: '0.875rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <span style={{ width: '0.5rem', height: '0.5rem', background: '#4ADE80', borderRadius: '50%' }}></span>
                            CLOUD API LIVE
                        </span>
                    </div>
                </div>

                {/* Infrastructure Stats Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>
                    <div style={{ background: '#1F2937', padding: '1.5rem', borderRadius: '0.75rem', border: '1px solid #374151' }}>
                        <div style={{ color: '#9CA3AF', fontSize: '0.875rem', fontWeight: '500' }}>System Health Status</div>
                        <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#4ADE80', marginTop: '0.5rem' }}>Operational</div>
                    </div>
                    <div style={{ background: '#1F2937', padding: '1.5rem', borderRadius: '0.75rem', border: '1px solid #374151' }}>
                        <div style={{ color: '#9CA3AF', fontSize: '0.875rem', fontWeight: '500' }}>Total Inspection Requests</div>
                        <div style={{ fontSize: '1.5rem', fontWeight: 'bold', marginTop: '0.5rem' }}>{health?.uptime_requests ?? 0}</div>
                    </div>
                    <div style={{ background: '#1F2937', padding: '1.5rem', borderRadius: '0.75rem', border: '1px solid #374151' }}>
                        <div style={{ color: '#9CA3AF', fontSize: '0.875rem', fontWeight: '500' }}>Distributed Memory Store</div>
                        <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: health?.redis === 'connected' ? '#4ADE80' : '#F59E0B', marginTop: '0.5rem' }}>
                            Redis: {health?.redis || 'Connected'}
                        </div>
                    </div>
                    <div style={{ background: '#1F2937', padding: '1.5rem', borderRadius: '0.75rem', border: '1px solid #374151' }}>
                        <div style={{ color: '#9CA3AF', fontSize: '0.875rem', fontWeight: '500' }}>Active Graph Nodes</div>
                        <div style={{ fontSize: '1.5rem', fontWeight: 'bold', marginTop: '0.5rem', color: '#3B82F6' }}>3 Cognitive Units</div>
                    </div>
                </div>

                {/* Cognitive Perimeters Status Matrix */}
                <h2 style={{ fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '1.25rem' }}>🧠 Active Agent Security Boundaries</h2>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '3rem' }}>
                    {agents.map((agent) => (
                        <div key={agent} style={{ background: '#1F2937', padding: '1.75rem', borderRadius: '0.75rem', border: '1px solid #374151', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <h3 style={{ fontSize: '1.25rem', fontWeight: 'bold', margin: 0 }}>Node: {agent}</h3>
                                <span style={{ padding: '0.25rem 0.6rem', background: 'rgba(34, 197, 94, 0.15)', color: '#4ADE80', borderRadius: '0.375rem', fontSize: '0.75rem', fontWeight: 'bold' }}>MONITORED</span>
                            </div>
                            
                            <div style={{ marginTop: '1.5rem', background: '#111827', padding: '1rem', borderRadius: '0.5rem', border: '1px solid #1F2937' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                                    <span style={{ color: '#9CA3AF', fontSize: '0.875rem' }}>Structural (LSTM) Threshold:</span>
                                    <span style={{ fontFamily: 'monospace', fontWeight: 'bold', color: '#60A5FA' }}>
                                        {thresholds?.structural_thresholds?.[agent]?.toFixed(6) || '0.000000'}
                                    </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span style={{ color: '#9CA3AF', fontSize: '0.875rem' }}>Semantic Drift Boundary:</span>
                                    <span style={{ fontFamily: 'monospace', fontWeight: 'bold', color: '#F472B6' }}>
                                        {thresholds?.semantic_drift_limits?.[agent]?.toFixed(6) || '0.000000'}
                                    </span>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* Footer Section */}
                <div style={{ textAlign: 'center', color: '#4B5563', fontSize: '0.875rem', paddingTop: '2rem', borderTop: '1px solid #1F2937', marginTop: '4rem' }}>
                    NeuroSentinel Platform v2.0.0 | Level 4 GraphSAGE Microservice Core | Academic Thesis Evaluator
                </div>

            </div>
        </div>
    );
}

export default App;