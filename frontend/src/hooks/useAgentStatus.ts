import { useEffect, useRef, useState, useCallback } from 'react';
import { getAgentStatus, type AgentStatus } from '../api/bridge';

// Default 3-node layout when API is unreachable
const DEFAULT_AGENTS: AgentStatus[] = [
    { agent_id: 'node1', node_id: 'node1', url: 'http://localhost:8001', status: 'offline', chunks_held: 0 },
    { agent_id: 'node2', node_id: 'node2', url: 'http://localhost:8002', status: 'offline', chunks_held: 0 },
    { agent_id: 'node3', node_id: 'node3', url: 'http://localhost:8003', status: 'offline', chunks_held: 0 },
];

export function useAgentStatus(pollMs = 2000) {
    const [agents, setAgents] = useState<AgentStatus[]>(DEFAULT_AGENTS);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const timerRef = useRef<number | null>(null);

    const fetchStatus = useCallback(async () => {
        try {
            const data = await getAgentStatus();
            setAgents(data);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
            // Keep showing last known state — don't reset to defaults
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
        timerRef.current = window.setInterval(fetchStatus, pollMs);
        return () => { if (timerRef.current) clearInterval(timerRef.current); };
    }, [fetchStatus, pollMs]);

    return { agents, loading, error, refetch: fetchStatus };
}
