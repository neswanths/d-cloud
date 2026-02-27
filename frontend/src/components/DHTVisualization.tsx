import { useEffect, useRef, useState } from 'react';
import { Wifi, WifiOff, Activity } from 'lucide-react';
import { type AgentStatus } from '../api/bridge';

/* ── Types ─────────────────────────────────────────────────────────────── */

interface Packet {
    id: number;
    fromX: number;
    fromY: number;
    toX: number;
    toY: number;
    color: string;
    progress: number; // 0-1
    speed: number;
}

interface NodePos {
    x: number;
    y: number;
    label: string;
    color: string;
    glowColor: string;
}

/* ── Props ─────────────────────────────────────────────────────────────── */

interface Props {
    fileCount: number;
    chunkCount: number;
    totalAgents: number;
    connectedAgents: number;
    agents?: AgentStatus[];
    // Called by FileUploadUI to trigger animation
    uploadChunkCount?: number;
    isUploading?: boolean;
}

/* ── Constants ─────────────────────────────────────────────────────────── */

const W = 340;
const H = 220;
const FILE_X = W / 2;
const FILE_Y = 36;

const NODE_POSITIONS: NodePos[] = [
    { x: 55, y: 170, label: 'Node 1', color: '#00d4ff', glowColor: 'rgba(0,212,255,0.4)' },
    { x: W / 2, y: 190, label: 'Node 2', color: '#22c55e', glowColor: 'rgba(34,197,94,0.4)' },
    { x: W - 55, y: 170, label: 'Node 3', color: '#a78bfa', glowColor: 'rgba(167,139,250,0.4)' },
];

let _packetId = 0;

/* ── Component ─────────────────────────────────────────────────────────── */

export function DHTVisualization({
    fileCount,
    chunkCount,
    connectedAgents,
    agents = [],
    uploadChunkCount = 0,
    isUploading = false,
}: Props) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const packetsRef = useRef<Packet[]>([]);
    const rafRef = useRef<number>(0);
    const [receivedNodes, setReceivedNodes] = useState<Set<number>>(new Set());

    /* ── Build node status map ──────────────────────────────────────────── */
    const nodeOnline = NODE_POSITIONS.map((_, i) => {
        if (agents.length > 0) {
            return agents[i]?.status === 'online';
        }
        return i < connectedAgents;
    });

    /* ── Spawn chunk packets during upload ─────────────────────────────── */
    useEffect(() => {
        if (!isUploading && uploadChunkCount === 0) return;
        setReceivedNodes(new Set());

        let chunksSent = 0;
        const total = Math.max(1, uploadChunkCount);

        const spawnRound = () => {
            if (chunksSent >= total) return;
            chunksSent++;

            // Spray a packet to every live node
            NODE_POSITIONS.forEach((node, idx) => {
                if (!nodeOnline[idx]) return;
                packetsRef.current.push({
                    id: _packetId++,
                    fromX: FILE_X,
                    fromY: FILE_Y,
                    toX: node.x,
                    toY: node.y,
                    color: node.color,
                    progress: 0,
                    speed: 0.016 + Math.random() * 0.008,
                });
            });

            // Mark node as "received" when a chunk arrives
            setTimeout(() => {
                setReceivedNodes(prev => {
                    const next = new Set(prev);
                    NODE_POSITIONS.forEach((_, idx) => { if (nodeOnline[idx]) next.add(idx); });
                    return next;
                });
            }, 900);

            if (chunksSent < total) {
                setTimeout(spawnRound, 300);
            }
        };

        spawnRound();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isUploading, uploadChunkCount]);

    /* ── Idle ambient packets ───────────────────────────────────────────── */
    useEffect(() => {
        if (isUploading) return;
        const iv = setInterval(() => {
            if (chunkCount === 0) return;
            // Random inter-node pulse
            const a = Math.floor(Math.random() * 3);
            const b = (a + 1 + Math.floor(Math.random() * 2)) % 3;
            if (!nodeOnline[a] || !nodeOnline[b]) return;
            packetsRef.current.push({
                id: _packetId++,
                fromX: NODE_POSITIONS[a].x,
                fromY: NODE_POSITIONS[a].y,
                toX: NODE_POSITIONS[b].x,
                toY: NODE_POSITIONS[b].y,
                color: NODE_POSITIONS[a].color,
                progress: 0,
                speed: 0.006 + Math.random() * 0.004,
            });
        }, 1800);
        return () => clearInterval(iv);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isUploading, chunkCount, connectedAgents]);

    /* ── Animation loop ─────────────────────────────────────────────────── */
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const draw = () => {
            ctx.clearRect(0, 0, W, H);

            /* Connection lines */
            NODE_POSITIONS.forEach((node, i) => {
                ctx.beginPath();
                ctx.moveTo(FILE_X, FILE_Y);
                ctx.lineTo(node.x, node.y);
                ctx.strokeStyle = nodeOnline[i] ? `${node.color}22` : '#ffffff08';
                ctx.lineWidth = 1;
                ctx.setLineDash([4, 8]);
                ctx.stroke();
                ctx.setLineDash([]);
            });

            // Lines between nodes
            for (let i = 0; i < NODE_POSITIONS.length; i++) {
                for (let j = i + 1; j < NODE_POSITIONS.length; j++) {
                    ctx.beginPath();
                    ctx.moveTo(NODE_POSITIONS[i].x, NODE_POSITIONS[i].y);
                    ctx.lineTo(NODE_POSITIONS[j].x, NODE_POSITIONS[j].y);
                    ctx.strokeStyle = nodeOnline[i] && nodeOnline[j] ? '#ffffff0a' : '#ffffff05';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([3, 10]);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }
            }

            /* File icon at top */
            ctx.beginPath();
            ctx.arc(FILE_X, FILE_Y, 14, 0, Math.PI * 2);
            const fileGrad = ctx.createRadialGradient(FILE_X, FILE_Y, 0, FILE_X, FILE_Y, 14);
            fileGrad.addColorStop(0, '#7c3aed');
            fileGrad.addColorStop(1, '#4f46e5');
            ctx.fillStyle = fileGrad;
            ctx.fill();
            ctx.strokeStyle = '#a78bfa60';
            ctx.lineWidth = 1.5;
            ctx.stroke();
            // File label
            ctx.fillStyle = '#e2e8f0';
            ctx.font = 'bold 9px monospace';
            ctx.textAlign = 'center';
            ctx.fillText('FILE', FILE_X, FILE_Y + 3);

            /* Packets */
            packetsRef.current = packetsRef.current.filter(p => p.progress < 1);
            for (const p of packetsRef.current) {
                p.progress = Math.min(1, p.progress + p.speed);
                const px = p.fromX + (p.toX - p.fromX) * p.progress;
                const py = p.fromY + (p.toY - p.fromY) * p.progress;
                ctx.beginPath();
                ctx.arc(px, py, 3.5, 0, Math.PI * 2);
                ctx.fillStyle = p.color;
                ctx.shadowColor = p.color;
                ctx.shadowBlur = 10;
                ctx.fill();
                ctx.shadowBlur = 0;

                // Trailing glow
                for (let t = 1; t <= 4; t++) {
                    const tp = Math.max(0, p.progress - t * 0.03);
                    const tx = p.fromX + (p.toX - p.fromX) * tp;
                    const ty = p.fromY + (p.toY - p.fromY) * tp;
                    ctx.beginPath();
                    ctx.arc(tx, ty, 3.5 - t * 0.7, 0, Math.PI * 2);
                    ctx.fillStyle = p.color + (60 - t * 14).toString(16).padStart(2, '0');
                    ctx.fill();
                }
            }

            /* Node circles */
            NODE_POSITIONS.forEach((node, i) => {
                const online = nodeOnline[i];
                const received = receivedNodes.has(i);

                // Outer glow ring (when received a chunk)
                if (received && online) {
                    ctx.beginPath();
                    ctx.arc(node.x, node.y, 22, 0, Math.PI * 2);
                    ctx.fillStyle = node.glowColor;
                    ctx.fill();
                }

                // Main circle
                ctx.beginPath();
                ctx.arc(node.x, node.y, 16, 0, Math.PI * 2);
                const grad = ctx.createRadialGradient(node.x - 4, node.y - 4, 0, node.x, node.y, 16);
                if (online) {
                    grad.addColorStop(0, node.color + 'cc');
                    grad.addColorStop(1, node.color + '44');
                } else {
                    grad.addColorStop(0, '#374151');
                    grad.addColorStop(1, '#1f2937');
                }
                ctx.fillStyle = grad;
                ctx.fill();
                ctx.strokeStyle = online ? node.color + '80' : '#4b5563';
                ctx.lineWidth = 1.5;
                ctx.stroke();

                // Node number
                ctx.fillStyle = online ? '#fff' : '#6b7280';
                ctx.font = 'bold 10px system-ui';
                ctx.textAlign = 'center';
                ctx.fillText(`N${i + 1}`, node.x, node.y + 4);

                // Label below
                ctx.fillStyle = online ? node.color : '#4b5563';
                ctx.font = '8px system-ui';
                ctx.fillText(node.label, node.x, node.y + 30);

                // Status dot
                ctx.beginPath();
                ctx.arc(node.x + 10, node.y - 11, 4, 0, Math.PI * 2);
                ctx.fillStyle = online ? '#22c55e' : '#ef4444';
                ctx.fill();
            });

            rafRef.current = requestAnimationFrame(draw);
        };

        rafRef.current = requestAnimationFrame(draw);
        return () => cancelAnimationFrame(rafRef.current);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [connectedAgents, agents, receivedNodes, isUploading]);

    return (
        <div className="glass p-5 flex flex-col gap-3">
            {/* Header */}
            <div className="flex items-center gap-2">
                <Activity size={16} className="text-cyan-400" />
                <span className="section-title">Live Network</span>
                {isUploading && (
                    <span className="ml-auto text-xs text-cyan-400 font-mono animate-pulse">
                        ⟳ distributing chunks…
                    </span>
                )}
            </div>

            <hr className="divider" />

            {/* Canvas */}
            <div className="flex justify-center">
                <canvas
                    ref={canvasRef}
                    width={W}
                    height={H}
                    style={{ borderRadius: 8, background: 'rgba(255,255,255,0.02)' }}
                />
            </div>

            {/* Stats row */}
            <div className="grid grid-cols-3 gap-2 text-center">
                {NODE_POSITIONS.map((node, i) => (
                    <div key={i} className="rounded-lg p-2" style={{ background: `${node.color}10`, border: `1px solid ${node.color}22` }}>
                        <div className="text-xs font-bold" style={{ color: node.color }}>{node.label}</div>
                        <div className="flex items-center justify-center gap-1 mt-1">
                            {nodeOnline[i]
                                ? <Wifi size={10} style={{ color: node.color }} />
                                : <WifiOff size={10} className="text-red-500" />
                            }
                            <span className="text-[10px] text-slate-400">
                                {nodeOnline[i] ? 'online' : 'OFFLINE'}
                            </span>
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                            {agents[i]?.chunks_held ?? '–'} chunks
                        </div>
                    </div>
                ))}
            </div>

            {/* Summary */}
            <div className="flex justify-between text-xs text-slate-500 px-1">
                <span>{fileCount} file{fileCount !== 1 ? 's' : ''} stored</span>
                <span>{chunkCount} chunks distributed</span>
                <span className={connectedAgents === 3 ? 'text-green-400' : connectedAgents > 0 ? 'text-yellow-400' : 'text-red-400'}>
                    {connectedAgents}/3 nodes live
                </span>
            </div>
        </div>
    );
}
