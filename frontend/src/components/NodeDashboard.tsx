import { Activity, Zap, RotateCcw, Server } from 'lucide-react';
import { type AgentStatus } from '../api/bridge';

const NODE_STYLES = [
    { label: 'Node 1', color: '#00d4ff', glow: '0 0 16px #00d4ff55', textClass: 'text-cyan-400', bgClass: '#00d4ff12' },
    { label: 'Node 2', color: '#22c55e', glow: '0 0 16px #22c55e55', textClass: 'text-green-400', bgClass: '#22c55e12' },
    { label: 'Node 3', color: '#a78bfa', glow: '0 0 16px #a78bfa55', textClass: 'text-purple-400', bgClass: '#a78bfa12' },
];

interface Props {
    agents: AgentStatus[];
    loading: boolean;
    onKill: (agentId: string) => void;
    onRestart: (agentId: string) => void;
    connectedCount: number;
}

export function NodeDashboard({ agents, loading, onKill, onRestart, connectedCount }: Props) {
    const display = agents.length > 0 ? agents : NODE_STYLES.map((_, i) => ({
        agent_id: `node${i + 1}`,
        node_id: `node${i + 1}`,
        index: i,
        url: `http://?.?.?.?:8001`,
        status: 'offline' as const,
        killed: false,
        chunks_held: 0,
    }));

    const totalNodes = display.length;
    const healthPct = Math.round((connectedCount / Math.max(totalNodes, 1)) * 100);
    const healthColor = connectedCount === 0
        ? '#ef4444'
        : connectedCount < totalNodes
            ? '#eab308'
            : '#00d4ff';

    return (
        <div className="glass p-5 flex flex-col gap-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Activity size={16} className="text-cyan-400" />
                    <span className="section-title">Network Nodes</span>
                </div>
                <div className="flex items-center gap-2">
                    {loading && <span className="w-3 h-3 border border-cyan-400/40 border-t-cyan-400 rounded-full animate-spin" />}
                    <span className="text-xs text-slate-500">
                        <span className="text-white font-semibold">{connectedCount}</span>
                        <span> / {totalNodes} online</span>
                    </span>
                </div>
            </div>

            <hr className="divider" />

            {/* Node Cards */}
            <div className="grid grid-cols-3 gap-3">
                {display.map((agent, idx) => {
                    const style = NODE_STYLES[idx % NODE_STYLES.length];
                    const isOnline = agent.status === 'online';
                    const isDegraded = (agent.status as string) === 'degraded';

                    // Extract IP from URL for display
                    const ipDisplay = agent.url
                        .replace('http://', '')
                        .replace('ws://', '')
                        .replace('localhost', '127.0.0.1');

                    return (
                        <div
                            key={agent.agent_id}
                            className="flex flex-col items-center gap-2 rounded-xl p-3 transition-all duration-500"
                            style={{
                                background: isOnline ? style.bgClass : 'rgba(239,68,68,0.05)',
                                border: `1px solid ${isOnline ? style.color + '30' : '#ef444430'}`,
                                boxShadow: isOnline ? style.glow : '0 0 12px #ef444420',
                            }}
                        >
                            {/* Node icon */}
                            <div
                                className="w-12 h-12 rounded-full flex items-center justify-center relative"
                                style={{
                                    background: isOnline
                                        ? `radial-gradient(circle, ${style.color}44, ${style.color}11)`
                                        : 'radial-gradient(circle, #ef444433, #1f293766)',
                                    border: `2px solid ${isOnline ? style.color + '60' : '#ef444444'}`,
                                }}
                            >
                                <Server size={20} style={{ color: isOnline ? style.color : '#ef4444' }} />
                                {/* Status dot */}
                                <span
                                    className="absolute top-0 right-0 w-3 h-3 rounded-full border-2 border-gray-900"
                                    style={{
                                        background: isOnline ? '#22c55e' : isDegraded ? '#eab308' : '#ef4444',
                                        boxShadow: isOnline ? '0 0 6px #22c55e' : isDegraded ? '0 0 6px #eab308' : '0 0 6px #ef4444',
                                    }}
                                />
                            </div>

                            {/* Label */}
                            <div className="text-center">
                                <p className="text-xs font-bold" style={{ color: isOnline ? style.color : '#ef4444' }}>
                                    {style.label}
                                </p>
                                <span
                                    className="inline-block text-[10px] font-semibold px-2 py-0.5 rounded mt-0.5"
                                    style={{
                                        background: isOnline ? style.color + '22' : '#ef444422',
                                        color: isOnline ? style.color : '#ef4444',
                                    }}
                                >
                                    {isOnline ? '● LIVE' : isDegraded ? '◑ DEGRADED' : '✕ OFFLINE'}
                                </span>
                            </div>

                            {/* IP display */}
                            <p className="text-[9px] text-slate-500 font-mono text-center break-all leading-relaxed px-1" title={agent.url}>
                                {ipDisplay.split(':')[0]}
                            </p>

                            {/* Chunks held */}
                            {(agent as any).chunks_held !== undefined && (
                                <p className="text-[10px] text-slate-400">
                                    {(agent as any).chunks_held} chunks
                                </p>
                            )}

                            {/* Action button */}
                            {isOnline ? (
                                <button
                                    className="btn-danger text-xs px-2 py-1 w-full flex items-center justify-center gap-1"
                                    onClick={() => onKill(agent.agent_id)}
                                    title={`Kill ${style.label}`}
                                >
                                    <Zap size={10} />Kill
                                </button>
                            ) : (
                                <button
                                    className="btn-success text-xs px-2 py-1 w-full flex items-center justify-center gap-1"
                                    onClick={() => onRestart(agent.agent_id)}
                                    title={`Restart ${style.label}`}
                                >
                                    <RotateCcw size={10} />Revive
                                </button>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* Health bar */}
            <div>
                <div className="flex justify-between text-xs text-slate-500 mb-1">
                    <span>Network Health</span>
                    <span style={{ color: healthColor }}>{healthPct}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                    <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                            width: `${healthPct}%`,
                            background: `linear-gradient(90deg, ${healthColor}, ${healthColor}88)`,
                            boxShadow: `0 0 8px ${healthColor}66`,
                        }}
                    />
                </div>
                {connectedCount < totalNodes && connectedCount > 0 && (
                    <p className="text-xs text-yellow-400 mt-1 text-center">
                        ⚠ Degraded — file retrieval still works
                    </p>
                )}
                {connectedCount === 0 && (
                    <p className="text-xs text-red-400 mt-1 text-center">
                        ✕ All nodes offline — cannot serve requests
                    </p>
                )}
            </div>
        </div>
    );
}
