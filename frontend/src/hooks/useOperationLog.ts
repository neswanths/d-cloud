import { useCallback, useRef, useState } from 'react';

export type LogLevel = 'info' | 'success' | 'error' | 'warn' | 'default';

export interface LogEntry {
    id: number;
    timestamp: Date;
    message: string;
    level: LogLevel;
}

let logIdCounter = 0;

export function useOperationLog() {
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const containerRef = useRef<HTMLDivElement | null>(null);

    const addLog = useCallback((message: string, level: LogLevel = 'default') => {
        const entry: LogEntry = { id: ++logIdCounter, timestamp: new Date(), message, level };
        setLogs(prev => [...prev.slice(-200), entry]); // keep last 200 entries
        // auto-scroll
        setTimeout(() => {
            if (containerRef.current) {
                containerRef.current.scrollTop = containerRef.current.scrollHeight;
            }
        }, 30);
    }, []);

    const clearLog = useCallback(() => setLogs([]), []);

    return { logs, addLog, clearLog, containerRef };
}
