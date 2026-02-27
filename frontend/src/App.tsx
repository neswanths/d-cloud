import { Database } from 'lucide-react';
import { IdentityProof } from './components/IdentityProof';
import { NodeDashboard } from './components/NodeDashboard';
import { FileUploadUI } from './components/FileUploadUI';
import { FileList } from './components/FileList';
import { FailureSimulator } from './components/FailureSimulator';
import { DHTVisualization } from './components/DHTVisualization';
import { OperationLog } from './components/OperationLog';

import { useAuth } from './hooks/useAuth';
import { useAgentStatus } from './hooks/useAgentStatus';
import { useFileList } from './hooks/useFileList';
import { useOperationLog } from './hooks/useOperationLog';
import { killAgent, restartAgent } from './api/bridge';
import { useEffect, useState } from 'react';

function App() {
    const { logs, addLog, clearLog, containerRef } = useOperationLog();
    const { keyPair, isAuthenticated, generateKeys, authenticate, logout } = useAuth();
    const { agents, loading: agentsLoading, refetch: refetchAgents } = useAgentStatus();
    const { files, loading: filesLoading, error: filesError, fetchFiles } = useFileList();

    // Upload animation state — piped into DHTVisualization
    const [isUploading, setIsUploading] = useState(false);
    const [uploadChunkCount, setUploadChunkCount] = useState(0);

    const handleKill = async (id: string) => {
        try {
            await killAgent(id);
            addLog(`🔴 [DEMO] Node ${id} killed — marked OFFLINE`, 'error');
            refetchAgents();
        } catch (e) {
            addLog(`Failed to kill ${id}: ${(e as Error).message}`, 'error');
        }
    };

    const handleRestart = async (id: string) => {
        try {
            await restartAgent(id);
            addLog(`🟢 [DEMO] Node ${id} revived — back ONLINE`, 'success');
            refetchAgents();
        } catch (e) {
            addLog(`Failed to restart ${id}: ${(e as Error).message}`, 'error');
        }
    };

    useEffect(() => {
        fetchFiles();
    }, [fetchFiles]);

    const connectedCount = agents.filter(a => a.status === 'online').length;
    const chunkCount = files.reduce((acc, f) => acc + f.total_chunks, 0);

    return (
        <div className="min-h-screen bg-navy-900 text-slate-200">
            {/* Navbar */}
            <nav className="border-b border-white/10 bg-black/20 backdrop-blur-md sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-purple-600 flex items-center justify-center shadow-glow-cyan">
                            <Database size={16} className="text-white" />
                        </div>
                        <div>
                            <h1 className="font-bold text-lg tracking-wide text-white">D-Cloud</h1>
                            <p className="text-[0.65rem] text-cyan-400 font-mono tracking-widest uppercase mt-[-2px]">Decentralized Storage</p>
                        </div>
                    </div>

                    <div className="text-xs text-slate-400 font-mono flex items-center gap-2">
                        {connectedCount === 0 ? (
                            <span className="text-red-400 flex items-center gap-1">
                                <span className="w-2 h-2 rounded-full bg-red-400 inline-block" />
                                Network Offline
                            </span>
                        ) : connectedCount < 3 ? (
                            <span className="text-yellow-400 flex items-center gap-1">
                                <span className="w-2 h-2 rounded-full bg-yellow-400 inline-block animate-pulse" />
                                Degraded ({connectedCount}/3 nodes)
                            </span>
                        ) : (
                            <span className="text-green-400 flex items-center gap-1">
                                <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
                                Network Healthy (3/3)
                            </span>
                        )}
                    </div>
                </div>
            </nav>

            {/* Main Grid */}
            <main className="max-w-7xl mx-auto px-6 py-8">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

                    {/* Left Column */}
                    <div className="lg:col-span-8 flex flex-col gap-6">
                        <IdentityProof
                            keyPair={keyPair}
                            isAuthenticated={isAuthenticated}
                            onGenerateKeys={generateKeys}
                            onAuthenticate={authenticate}
                            onLogout={logout}
                            addLog={addLog}
                        />

                        <FileUploadUI
                            isAuthenticated={isAuthenticated}
                            addLog={addLog}
                            onUploadComplete={(result) => {
                                fetchFiles();
                                // Trigger canvas animation
                                setUploadChunkCount(result.total_chunks);
                                setIsUploading(false);
                            }}
                            onUploadStart={(chunkCount) => {
                                setUploadChunkCount(chunkCount);
                                setIsUploading(true);
                            }}
                        />

                        <FileList
                            files={files}
                            loading={filesLoading}
                            error={filesError}
                            onRefresh={fetchFiles}
                            addLog={addLog}
                        />
                    </div>

                    {/* Right Column */}
                    <div className="lg:col-span-4 flex flex-col gap-6">
                        <NodeDashboard
                            agents={agents}
                            loading={agentsLoading}
                            onKill={handleKill}
                            onRestart={handleRestart}
                            connectedCount={connectedCount}
                        />

                        <DHTVisualization
                            fileCount={files.length}
                            chunkCount={chunkCount}
                            totalAgents={3}
                            connectedAgents={connectedCount}
                            agents={agents}
                            isUploading={isUploading}
                            uploadChunkCount={uploadChunkCount}
                        />

                        <FailureSimulator
                            agents={agents}
                            onKill={handleKill}
                            onRestart={handleRestart}
                            addLog={addLog}
                        />

                        <OperationLog
                            logs={logs}
                            containerRef={containerRef}
                            onClear={clearLog}
                        />
                    </div>

                </div>
            </main>
        </div>
    );
}

export default App;
