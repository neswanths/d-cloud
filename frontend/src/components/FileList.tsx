import { useState, useCallback } from 'react';
import { Download, FileText, CheckCircle, XCircle, Loader, Shield } from 'lucide-react';
import { downloadFile, type FileEntry } from '../api/bridge';
import { type LogLevel } from '../hooks/useOperationLog';

function formatBytes(b: number): string {
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(2)} MB`;
}

interface Props {
    files: FileEntry[];
    loading: boolean;
    error: string | null;
    onRefresh: () => void;
    addLog: (m: string, l?: LogLevel) => void;
}

type DownloadState = 'idle' | 'fetching' | 'verifying' | 'done' | 'error';

export function FileList({ files, loading, error, onRefresh, addLog }: Props) {
    const [downloadStates, setDownloadStates] = useState<Record<string, DownloadState>>({});
    const [downloadResults, setDownloadResults] = useState<Record<string, { ok: boolean; msg: string }>>({});

    const setDownloadState = (hash: string, state: DownloadState) => {
        setDownloadStates(prev => ({ ...prev, [hash]: state }));
    };

    const handleDownload = useCallback(async (file: FileEntry) => {
        const key = file.action_hash;
        setDownloadState(key, 'fetching');
        addLog(`Downloading "${file.name}"…`, 'info');
        addLog(`→ Querying DHT for chunks (manifest: ${file.action_hash.slice(0, 20)}…)`, 'default');

        try {
            setDownloadState(key, 'fetching');
            const { blob, filename, fileHash } = await downloadFile(file.action_hash);

            setDownloadState(key, 'verifying');
            addLog('→ Verifying SHA-256 hash…', 'default');

            // Compute hash of downloaded blob
            const buf = await blob.arrayBuffer();
            const digest = await crypto.subtle.digest('SHA-256', buf);
            const computedHash = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');

            const serverHash = fileHash || file.file_hash;
            const hashMatch = !serverHash || computedHash === serverHash;

            if (hashMatch) {
                addLog(`✓ Hash verified: ${computedHash.slice(0, 32)}…`, 'success');
            } else {
                addLog(`⚠ Hash mismatch — downloaded file may differ from original`, 'warn');
                addLog(`  Expected: ${serverHash.slice(0, 32)}…`, 'warn');
                addLog(`  Got:      ${computedHash.slice(0, 32)}…`, 'warn');
            }

            // Trigger browser download
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(url);

            setDownloadState(key, 'done');
            setDownloadResults(prev => ({ ...prev, [key]: { ok: hashMatch, msg: hashMatch ? 'Hash verified ✓' : 'Hash mismatch ⚠' } }));
            addLog(`✓ "${filename}" downloaded successfully`, 'success');
        } catch (e) {
            const msg = (e as Error).message;
            setDownloadState(key, 'error');
            setDownloadResults(prev => ({ ...prev, [key]: { ok: false, msg } }));
            addLog(`✗ Download failed: ${msg}`, 'error');
        }
    }, [addLog]);

    if (loading) {
        return (
            <div className="glass p-5">
                <div className="flex items-center gap-2 mb-4">
                    <FileText size={16} className="text-cyan-400" />
                    <span className="section-title">Files</span>
                </div>
                <div className="flex flex-col gap-2">
                    {[1, 2, 3].map(i => <div key={i} className="shimmer h-10 rounded-lg" />)}
                </div>
            </div>
        );
    }

    return (
        <div className="glass p-5 flex flex-col gap-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <FileText size={16} className="text-cyan-400" />
                    <span className="section-title">Stored Files</span>
                    {files.length > 0 && (
                        <span className="badge badge-info">{files.length}</span>
                    )}
                </div>
                <button className="btn-ghost text-xs px-3 py-1" onClick={onRefresh}>
                    Refresh
                </button>
            </div>

            {error && (
                <div className="text-xs text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3">
                    {error}
                </div>
            )}

            {files.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 gap-3">
                    <div className="p-4 rounded-full bg-white/4">
                        <FileText size={24} className="text-slate-500" />
                    </div>
                    <p className="text-sm text-slate-400">No files uploaded yet</p>
                    <p className="text-xs text-slate-600">Upload a file to see it distributed across the DHT</p>
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>File</th>
                                <th>Size</th>
                                <th>Chunks</th>
                                <th>SHA-256</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {files.map((file) => {
                                const dlState = downloadStates[file.action_hash] ?? 'idle';
                                const dlResult = downloadResults[file.action_hash];

                                return (
                                    <tr key={file.action_hash} className="animate-slideUp">
                                        <td>
                                            <div className="flex items-center gap-2">
                                                <FileText size={13} className="text-slate-500 flex-shrink-0" />
                                                <span className="text-slate-200 font-medium text-sm truncate max-w-[140px]" title={file.name}>
                                                    {file.name}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="text-xs">{formatBytes(file.size)}</td>
                                        <td>
                                            <span className="badge badge-info">{file.total_chunks}</span>
                                        </td>
                                        <td>
                                            <span className="hash-pill">{file.file_hash.slice(0, 12)}…</span>
                                        </td>
                                        <td>
                                            <div className="flex items-center gap-2">
                                                {dlResult && (
                                                    <span className={`text-xs ${dlResult.ok ? 'text-green-400' : 'text-yellow-400'}`}>
                                                        {dlResult.ok ? <CheckCircle size={13} className="inline" /> : <XCircle size={13} className="inline" />}
                                                    </span>
                                                )}
                                                <button
                                                    className="btn-primary text-xs px-2 py-1"
                                                    onClick={() => handleDownload(file)}
                                                    disabled={dlState === 'fetching' || dlState === 'verifying'}
                                                >
                                                    {dlState === 'fetching' ? <Loader size={12} className="animate-spin" /> :
                                                        dlState === 'verifying' ? <Shield size={12} className="animate-pulse" /> :
                                                            <Download size={12} />}
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
