import { useState } from 'react';
import { Download, Fingerprint } from 'lucide-react';
import { downloadFile } from '../api/bridge';
import { type LogLevel } from '../hooks/useOperationLog';

interface Props {
    addLog: (m: string, l?: LogLevel) => void;
    onDownloadComplete?: (hash: string) => void;
}

export function RetrievalProtocol({ addLog, onDownloadComplete }: Props) {
    const [hash, setHash] = useState('');
    const [retrieving, setRetrieving] = useState(false);

    const handleRetrieve = async () => {
        if (!hash.trim()) {
            addLog('ERROR: NO MANIFEST HASH PROVIDED.', 'error');
            return;
        }

        setRetrieving(true);
        addLog(`LOCATING MANIFEST [${hash.slice(0, 16)}...] ON DHT...`, 'info');

        try {
            // bridge.ts already handles the failover cascade locally
            const { blob, filename } = await downloadFile(hash);

            // Create a temporary link to download it, default name since we don't fetch metadata separately first
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename || `dcloud_retrieved_${hash.slice(0, 8)}.bin`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            addLog(`✅ FILE REASSEMBLED. ZERO DATA LOSS.`, 'success');
            if (onDownloadComplete) onDownloadComplete(hash);
            setHash('');
        } catch (e) {
            addLog(`RESTORE FAILED: Nodes are down or Manifest Hash is invalid.`, 'error');
        } finally {
            setRetrieving(false);
        }
    };

    return (
        <div className="glass p-6">
            <div className="flex items-center gap-2 mb-1">
                <Download size={18} className="text-purple-400" />
                <h2 className="section-title text-sm tracking-[0.2em]">Retrieval Protocol</h2>
            </div>
            <p className="text-[10px] text-slate-500 font-mono tracking-widest uppercase mb-4">
                P2P HASH RESOLUTION & REASSEMBLY
            </p>

            <hr className="divider mb-4" />

            <div className="flex flex-col gap-3">
                <div className="relative">
                    <Fingerprint className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                    <input
                        type="text"
                        placeholder="ENTER MANIFEST HASH [dcl...]"
                        value={hash}
                        onChange={(e) => setHash(e.target.value)}
                        className="w-full bg-black/40 border border-purple-500/30 rounded-lg py-2.5 pl-10 pr-4 text-sm font-mono text-purple-300 placeholder-slate-600 focus:outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-400 transition-all"
                        disabled={retrieving}
                    />
                </div>
                <button
                    onClick={handleRetrieve}
                    disabled={!hash.trim() || retrieving}
                    className="btn px-4 py-2.5 text-xs font-bold tracking-widest uppercase w-full flex justify-center items-center gap-2"
                    style={{
                        background: 'linear-gradient(135deg, rgba(168,85,247,0.2), rgba(168,85,247,0.05))',
                        borderColor: 'rgba(168,85,247,0.4)',
                        color: retrieving ? '#a855f788' : '#e9d5ff'
                    }}
                >
                    {retrieving ? (
                        <>
                            <span className="w-3 h-3 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin" />
                            Reconstructing...
                        </>
                    ) : (
                        'Initiate P2P Retrieval'
                    )}
                </button>
            </div>
        </div>
    );
}
