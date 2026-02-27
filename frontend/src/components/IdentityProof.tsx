import { QRCodeSVG } from 'qrcode.react';
import { Key, ShieldCheck, LogOut, Copy, CheckCircle } from 'lucide-react';
import { useState } from 'react';
import { type LogLevel } from '../hooks/useOperationLog';
import { type KeyPair } from '../hooks/useAuth';

interface Props {
    keyPair: KeyPair | null;
    isAuthenticated: boolean;
    onGenerateKeys: () => void;
    onAuthenticate: (addLog: (m: string, l?: LogLevel) => void) => Promise<boolean>;
    onLogout: () => void;
    addLog: (m: string, l?: LogLevel) => void;
}

export function IdentityProof({ keyPair, isAuthenticated, onGenerateKeys, onAuthenticate, onLogout, addLog }: Props) {
    const [loading, setLoading] = useState(false);
    const [copied, setCopied] = useState(false);

    const handleGenerate = () => {
        onGenerateKeys();
        addLog('Ed25519 keypair generated', 'info');
    };

    const handleAuth = async () => {
        setLoading(true);
        await onAuthenticate(addLog);
        setLoading(false);
    };

    const handleCopy = () => {
        if (keyPair) {
            navigator.clipboard.writeText(keyPair.publicKeyHex);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        }
    };

    return (
        <div className="glass p-5 flex flex-col gap-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Key size={16} className="text-cyan-400" />
                    <span className="section-title">Identity &amp; Authentication</span>
                </div>
                {isAuthenticated && (
                    <div className="flex items-center gap-3">
                        <span className="badge badge-online flex items-center gap-1">
                            <CheckCircle size={10} /> Authenticated
                        </span>
                        <button className="btn-ghost text-xs px-3 py-1" onClick={onLogout}>
                            <LogOut size={12} className="inline mr-1" />Logout
                        </button>
                    </div>
                )}
            </div>

            <hr className="divider" />

            {!keyPair ? (
                /* Step 1: Generate Keys */
                <div className="flex flex-col items-center gap-4 py-4">
                    <div className="w-16 h-16 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-600/20 border border-cyan-500/20 flex items-center justify-center">
                        <Key size={28} className="text-cyan-400" />
                    </div>
                    <div className="text-center">
                        <p className="text-sm text-slate-300 font-medium mb-1">Generate your cryptographic identity</p>
                        <p className="text-xs text-slate-500">Creates an Ed25519 keypair for signing all operations</p>
                    </div>
                    <button className="btn-primary" onClick={handleGenerate}>
                        Generate Ed25519 Keypair
                    </button>
                </div>
            ) : (
                <div className="flex gap-4 flex-wrap">
                    {/* QR Code */}
                    <div className="flex-shrink-0">
                        <div className="p-3 bg-white rounded-xl inline-block">
                            <QRCodeSVG value={keyPair.publicKeyHex} size={96} level="M" />
                        </div>
                    </div>

                    {/* Key Details */}
                    <div className="flex-1 min-w-0 flex flex-col gap-3">
                        <div>
                            <p className="text-xs text-slate-500 mb-1">Public Key (Ed25519)</p>
                            <div className="flex items-center gap-2">
                                <span className="hash-pill text-xs flex-1 truncate">{keyPair.publicKeyHex}</span>
                                <button className="btn-ghost px-2 py-1" onClick={handleCopy}>
                                    {copied ? <CheckCircle size={13} className="text-green-400" /> : <Copy size={13} />}
                                </button>
                            </div>
                        </div>

                        <div className="flex items-center gap-2 text-xs text-slate-500">
                            <ShieldCheck size={12} className="text-purple-400" />
                            <span>256-bit Ed25519 · NaCl cryptography · Private key never leaves browser</span>
                        </div>

                        {!isAuthenticated ? (
                            <button className="btn-primary self-start" onClick={handleAuth} disabled={loading}>
                                {loading ? (
                                    <span className="flex items-center gap-2">
                                        <span className="w-3 h-3 border border-white/40 border-t-white rounded-full animate-spin" />
                                        Authenticating…
                                    </span>
                                ) : (
                                    <span className="flex items-center gap-2">
                                        <ShieldCheck size={14} /> Authenticate
                                    </span>
                                )}
                            </button>
                        ) : (
                            <div className="flex items-center gap-2 text-sm text-green-400">
                                <CheckCircle size={16} />
                                <span>Identity verified — all operations unlocked</span>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
