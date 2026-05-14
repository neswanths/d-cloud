/**
 * useSourceChain — session-local Holochain-style Source Chain ledger
 *
 * Tracks every significant action (upload / download / key-rotate) as an
 * immutable linked-list chain entry. Each entry contains:
 *   - seq: monotonic counter (chain position)
 *   - prevHash: SHA-256 of the previous entry's canonical string (or "GENESIS")
 *   - action: action type label
 *   - contentHash: SHA-256 of the related content (file hash, manifest hash, etc.)
 *   - actorPubkey: truncated pubkey hex of the acting identity
 *   - timestamp: unix millis
 *
 * The running chainHead is re-computed on every new entry, mimicking
 * Holochain's source-chain head-hash pattern.
 *
 * Note: this is session-only (in-memory). Entries are NOT persisted across reloads
 * because the goal is to demonstrate the Source Chain pattern visually.
 */

import { useCallback, useState } from 'react';

export type ChainActionType =
    | 'KEY_GENESIS'
    | 'KEY_ROTATE'
    | 'FILE_UPLOAD'
    | 'FILE_DOWNLOAD'
    | 'DHT_REPLICATE';

export interface ChainEntry {
    seq: number;
    prevHash: string;
    hash: string;           // SHA-256 of canonical entry string
    action: ChainActionType;
    contentHash: string;    // manifest hash, file hash, or pubkey
    actorPubkey: string;    // truncated pubkey hex (first 20 chars)
    timestamp: number;      // Date.now()
    label: string;          // human-readable description
}

/** Compute SHA-256 of a plain string and return as hex. */
async function sha256Hex(input: string): Promise<string> {
    const buf = await crypto.subtle.digest(
        'SHA-256',
        new TextEncoder().encode(input),
    );
    return Array.from(new Uint8Array(buf))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
}

export function useSourceChain() {
    const [entries, setEntries] = useState<ChainEntry[]>([]);
    const [chainHead, setChainHead] = useState<string>('GENESIS');

    /**
     * Append a new entry to the chain.
     * Returns the new entry (with its computed hash).
     */
    const addEntry = useCallback(
        async (
            action: ChainActionType,
            contentHash: string,
            actorPubkey: string,
            label: string,
        ): Promise<ChainEntry> => {
            // We capture the current head from the function closure to avoid
            // a stale-closure problem — we compute the hash before the state update.
            let resolvedHead = 'GENESIS';
            let resolvedSeq = 0;

            // Read current chain state via functional updater pattern
            // We achieve this by passing a resolver into setState
            await new Promise<void>(resolve => {
                setEntries(prev => {
                    resolvedHead = prev.length === 0 ? 'GENESIS' : prev[prev.length - 1].hash;
                    resolvedSeq = prev.length;
                    resolve();
                    return prev; // no mutation yet
                });
            });

            const ts = Date.now();
            const canonical = `${resolvedHead}:${resolvedSeq}:${action}:${contentHash}:${actorPubkey}:${ts}`;
            const hash = await sha256Hex(canonical);

            const entry: ChainEntry = {
                seq: resolvedSeq,
                prevHash: resolvedHead,
                hash,
                action,
                contentHash,
                actorPubkey: actorPubkey.slice(0, 20),
                timestamp: ts,
                label,
            };

            setEntries(prev => [...prev, entry]);
            setChainHead(hash);
            return entry;
        },
        [],
    );

    const clearChain = useCallback(() => {
        setEntries([]);
        setChainHead('GENESIS');
    }, []);

    return { entries, chainHead, addEntry, clearChain };
}
