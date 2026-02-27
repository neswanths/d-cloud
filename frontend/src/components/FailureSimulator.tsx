import { Zap, RotateCcw, AlertTriangle } from 'lucide-react';
import { type AgentStatus } from '../api/bridge';
import { type LogLevel } from '../hooks/useOperationLog';

const AGENT_NAMES = ['Agent 1', 'Agent 2', 'Agent 3'];
const AGENT_IDS = ['node1', 'node2', 'node3'];

interface Props {
    agents: AgentStatus[];
    onKill: (agentId: string) => void;
    onRestart: (agentId: string) => void;
    addLog: (m: string, l?: LogLevel) => void;
}

export function FailureSimulator({ agents, onKill, onRestart, addLog }: Props) {
    const getAgent = (id: string) => agents.find(a => a.agent_id === id);

    const handleKill = (id: string, idx: number) => {
        addLog(`☠ Killing ${AGENT_NAMES[idx]}…`, 'warn');
        onKill(id);
    };

    const handleRestart = (id: string, idx: number) => {
        addLog(`↩ Restarting ${AGENT_NAMES[idx]}…`, 'info');
        onRestart(id);
    };

    const offlineCount = AGENT_IDS.filter(id => getAgent(id)?.status === 'offline' || !getAgent(id)).length;

    return (
        <div className="glass p-5 flex flex-col gap-4">
            {/* Header */}
            <div className="flex items-center gap-2">
                <Zap size={16} className="text-yellow-500" />
                <span className="section-title">Fault Simulator</span>
                {offlineCount > 0 && (
                    <span className="badge badge-offline ml-auto">{offlineCount} offline</span>
                )}
            </div>

            <hr className="divider" />

            {offlineCount > 0 && (
                <div className="flex items-start gap-2 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                    <AlertTriangle size={13} className="text-yellow-500 flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-yellow-400">
                        {offlineCount === 1
                            ? 'Network running at 66% capacity — fault tolerance active'
                            : offlineCount === 2
                                ? 'Network running at 33% capacity — file retrieval still possible'
                                : 'All nodes offline — system unavailable'}
                    </p>
                </div>
            )}

            {/* Agent Kill/Restart Buttons */}
            <div className="grid grid-cols-3 gap-3">
                {AGENT_IDS.map((id, idx) => {
                    const agent = getAgent(id);
                    const isOnline = agent?.status === 'online';

                    return (
                        <div key={id} className="flex flex-col gap-2">
                            <div className="flex items-center gap-2 mb-1">
                                <div
                                    className="w-2 h-2 rounded-full flex-shrink-0"
                                    style={{
                                        background: isOnline ? '#22c55e' : '#ef4444',
                                        boxShadow: `0 0 6px ${isOnline ? '#22c55e' : '#ef4444'}`,
                                    }}
                                />
                                <span className="text-xs font-semibold text-slate-300">{AGENT_NAMES[idx]}</span>
                            </div>

                            {isOnline ? (
                                <button
                                    className="btn-danger text-xs px-2 py-1.5 flex items-center justify-center gap-1"
                                    onClick={() => handleKill(id, idx)}
                                >
                                    <Zap size={11} /> Kill
                                </button>
                            ) : (
                                <button
                                    className="btn-success text-xs px-2 py-1.5 flex items-center justify-center gap-1"
                                    onClick={() => handleRestart(id, idx)}
                                >
                                    <RotateCcw size={11} /> Restart
                                </button>
                            )}
                        </div>
                    );
                })}
            </div>

            <p className="text-xs text-slate-600 text-center">
                Kill nodes during a demo to show fault tolerance in action
            </p>
        </div>
    );
}
