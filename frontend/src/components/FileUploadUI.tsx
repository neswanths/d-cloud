import { useState, useCallback, useRef } from 'react';
import { Upload, FileIcon, Hash, Database } from 'lucide-react';
import { uploadFile, type UploadResponse } from '../api/bridge';
import { type LogLevel } from '../hooks/useOperationLog';

const CHUNK_COLORS = [
    { bg: 'rgba(0,212,255,0.15)', border: '#00d4ff', text: '#00d4ff', label: 'Agent 1' },
    { bg: 'rgba(34,197,94,0.15)', border: '#22c55e', text: '#22c55e', label: 'Agent 2' },
    { bg: 'rgba(167,139,250,0.15)', border: '#a78bfa', text: '#a78bfa', label: 'Agent 3' },
];

function formatBytes(b: number): string {
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(2)} MB`;
}

interface Props {
    isAuthenticated: boolean;
    addLog: (m: string, l?: LogLevel) => void;
    onUploadComplete: (result: UploadResponse) => void;
    onUploadStart?: (estimatedChunkCount: number) => void;
}

export function FileUploadUI({ isAuthenticated, addLog, onUploadComplete, onUploadStart }: Props) {
    const [dragOver, setDragOver] = useState(false);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [fileHash, setFileHash] = useState<string>('');
    const [progress, setProgress] = useState(0);
    const [uploading, setUploading] = useState(false);
    const [chunkAnim, setChunkAnim] = useState<boolean[]>([]);
    const [success, setSuccess] = useState<UploadResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    const computeHash = useCallback(async (file: File): Promise<string> => {
        const buf = await file.arrayBuffer();
        const digest = await crypto.subtle.digest('SHA-256', buf);
        return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
    }, []);

    const handleFile = useCallback(async (file: File) => {
        setSelectedFile(file);
        setSuccess(null);
        setError(null);
        setProgress(0);
        setChunkAnim([]);
        const h = await computeHash(file);
        setFileHash(h);
        addLog(`Selected: ${file.name} (${formatBytes(file.size)})`, 'default');
        addLog(`SHA-256: ${h.slice(0, 32)}…`, 'info');
    }, [computeHash, addLog]);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer.files[0];
        if (f) handleFile(f);
    }, [handleFile]);

    const handleUpload = async () => {
        if (!selectedFile) return;
        setUploading(true);
        setError(null);
        setProgress(5);
        addLog(`Uploading "${selectedFile.name}"…`, 'info');

        const estimatedChunks = Math.ceil(selectedFile.size / 65536);
        if (onUploadStart) onUploadStart(estimatedChunks);

        try {
            // Simulate chunking animation phases
            setProgress(20);
            addLog('Splitting into 64 KB chunks…', 'default');
            await delay(400);

            setProgress(40);
            addLog('Encrypting chunks with AES-256-GCM…', 'default');
            await delay(400);

            // Show chunk fly animation
            const totalChunks = Math.ceil(selectedFile.size / 65536);
            const animChunks = Math.min(totalChunks, 3);
            for (let i = 0; i < animChunks; i++) {
                setChunkAnim(prev => [...prev, true]);
                addLog(`Chunk ${i + 1} → ${CHUNK_COLORS[i % 3].label}`, 'info');
                await delay(300);
            }

            setProgress(65);
            addLog('Broadcasting to all conductors…', 'default');

            const result = await uploadFile(selectedFile);
            setProgress(90);
            addLog('Creating FileManifest on DHT…', 'default');
            await delay(300);

            setProgress(100);
            setSuccess(result);
            onUploadComplete(result);
            addLog(`✓ File uploaded! Manifest: ${result.manifest_hash.slice(0, 24)}…`, 'success');
            addLog(`  ${result.total_chunks} chunks · ${result.redundancy_factor}× redundancy · ${result.dek_algorithm}`, 'success');

            // Reset form after short delay
            await delay(1200);
            setSelectedFile(null);
            setFileHash('');
            setChunkAnim([]);
            setProgress(0);
        } catch (e) {
            const msg = (e as Error).message;
            setError(msg);
            addLog(`✗ Upload failed: ${msg}`, 'error');
            setProgress(0);
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="glass p-5 flex flex-col gap-4">
            {/* Header */}
            <div className="flex items-center gap-2">
                <Upload size={16} className="text-cyan-400" />
                <span className="section-title">Upload File</span>
                {!isAuthenticated && (
                    <span className="ml-auto badge badge-degraded text-xs">Authenticate first</span>
                )}
            </div>

            <hr className="divider" />

            {/* Drop Zone */}
            {!selectedFile || success ? (
                <div
                    className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    onClick={() => inputRef.current?.click()}
                >
                    <input
                        ref={inputRef}
                        type="file"
                        className="hidden"
                        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                    />
                    <div className="flex flex-col items-center gap-3 py-2">
                        <div className="p-3 rounded-full bg-cyan-500/10">
                            <Upload size={24} className="text-cyan-400" />
                        </div>
                        <div>
                            <p className="text-sm text-slate-300 font-medium">Drop file here or click to browse</p>
                            <p className="text-xs text-slate-500 mt-1">Any file type · Max size depends on conductor</p>
                        </div>
                    </div>
                    {success && (
                        <p className="text-xs text-green-400 mt-2 text-center">
                            ✓ Upload complete — drop another file to continue
                        </p>
                    )}
                </div>
            ) : (
                <div className="flex flex-col gap-4 animate-fadeIn">
                    {/* File Info */}
                    <div className="flex items-center gap-3 p-3 rounded-xl bg-white/4 border border-white/8">
                        <div className="p-2 rounded-lg bg-cyan-500/10">
                            <FileIcon size={20} className="text-cyan-400" />
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-slate-200 truncate">{selectedFile.name}</p>
                            <p className="text-xs text-slate-500">{formatBytes(selectedFile.size)}</p>
                        </div>
                        {!uploading && (
                            <button className="btn-ghost text-xs px-2 py-1" onClick={() => { setSelectedFile(null); setChunkAnim([]); }}>
                                Change
                            </button>
                        )}
                    </div>

                    {/* Hash */}
                    {fileHash && (
                        <div className="flex items-center gap-2">
                            <Hash size={12} className="text-slate-500 flex-shrink-0" />
                            <span className="hash-pill">{fileHash.slice(0, 32)}…</span>
                        </div>
                    )}

                    {/* Chunk Distribution Animation */}
                    {chunkAnim.length > 0 && (
                        <div className="flex items-center justify-around gap-3 py-2">
                            {chunkAnim.map((_, i) => (
                                <div
                                    key={i}
                                    className="flex flex-col items-center gap-2 animate-slideUp"
                                    style={{ animationDelay: `${i * 0.15}s` }}
                                >
                                    <div
                                        className="w-14 h-9 rounded-lg flex items-center justify-center text-xs font-bold"
                                        style={{ background: CHUNK_COLORS[i % 3].bg, border: `1.5px solid ${CHUNK_COLORS[i % 3].border}`, color: CHUNK_COLORS[i % 3].text }}
                                    >
                                        <Database size={14} />
                                    </div>
                                    <p className="text-xs font-medium" style={{ color: CHUNK_COLORS[i % 3].text }}>
                                        {CHUNK_COLORS[i % 3].label}
                                    </p>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Progress */}
                    {uploading && (
                        <div>
                            <div className="flex justify-between text-xs text-slate-400 mb-1.5">
                                <span>{progress < 40 ? 'Chunking & encrypting…' : progress < 70 ? 'Distributing to DHT…' : 'Creating manifest…'}</span>
                                <span>{progress}%</span>
                            </div>
                            <div className="progress-bar">
                                <div className="progress-fill" style={{ width: `${progress}%` }} />
                            </div>
                        </div>
                    )}

                    {/* Error */}
                    {error && (
                        <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                            {error}
                        </div>
                    )}

                    {/* Upload Button */}
                    {!uploading && (
                        <button
                            className="btn-primary self-stretch"
                            onClick={handleUpload}
                            disabled={!isAuthenticated}
                        >
                            <Upload size={14} className="inline mr-2" />Upload to D-Cloud
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

function delay(ms: number) { return new Promise(r => setTimeout(r, ms)); }
