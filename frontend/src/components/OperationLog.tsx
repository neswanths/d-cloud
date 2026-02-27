import { Terminal, Trash2 } from 'lucide-react';
import { type LogEntry } from '../hooks/useOperationLog';

const LEVEL_CLASS: Record<string, string> = {
    success: 'log-success',
    error: 'log-error',
    warn: 'log-warn',
    info: 'log-info',
    default: 'log-default',
};

interface Props {
    logs: LogEntry[];
    containerRef: React.RefObject<HTMLDivElement | null>;
    onClear: () => void;
}

function pad2(n: number) { return String(n).padStart(2, '0'); }

function fmtTime(d: Date) {
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

export function OperationLog({ logs, containerRef, onClear }: Props) {
    return (
        <div className="glass p-4 flex flex-col gap-3" style={{ minHeight: '180px' }}>
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Terminal size={14} className="text-cyan-400" />
                    <span className="section-title">Operation Log</span>
                    {logs.length > 0 && (
                        <span className="text-xs text-slate-600 mono">{logs.length} entries</span>
                    )}
                </div>
                <button className="btn-ghost text-xs px-2 py-1" onClick={onClear}>
                    <Trash2 size={11} className="inline mr-1" />Clear
                </button>
            </div>

            {/* Log Output */}
            <div
                ref={containerRef as React.RefObject<HTMLDivElement>}
                className="flex-1 overflow-y-auto"
                style={{ maxHeight: '200px', scrollBehavior: 'smooth' }}
            >
                {logs.length === 0 ? (
                    <p className="text-xs text-slate-600 mono py-2">Waiting for operations…</p>
                ) : (
                    logs.map(entry => (
                        <div key={entry.id} className={`log-entry ${LEVEL_CLASS[entry.level] ?? 'log-default'}`}>
                            <span className="text-slate-600 select-none">[{fmtTime(entry.timestamp)}] </span>
                            {entry.message}
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
