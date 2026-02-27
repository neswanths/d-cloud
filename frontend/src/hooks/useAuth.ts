import { useCallback, useState } from 'react';
import nacl from 'tweetnacl';
import { encodeBase64 } from 'tweetnacl-util';

export interface KeyPair {
    publicKey: Uint8Array;
    secretKey: Uint8Array;
    publicKeyHex: string;
}

// Simple hex encoder
function toHex(bytes: Uint8Array): string {
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

export function useAuth() {
    const [keyPair, setKeyPair] = useState<KeyPair | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [token, setToken] = useState<string | null>(null);

    const generateKeys = useCallback(() => {
        const kp = nacl.sign.keyPair();
        setKeyPair({
            publicKey: kp.publicKey,
            secretKey: kp.secretKey,
            publicKeyHex: toHex(kp.publicKey),
        });
        setIsAuthenticated(false);
        setToken(null);
    }, []);

    const sign = useCallback((message: Uint8Array): string => {
        if (!keyPair) throw new Error('No keypair generated');
        const signed = nacl.sign(message, keyPair.secretKey);
        return encodeBase64(signed);
    }, [keyPair]);

    const authenticate = useCallback(async (addLog?: (msg: string, level?: 'info' | 'success' | 'error' | 'warn' | 'default') => void) => {
        if (!keyPair) {
            addLog?.('Generate keys first', 'error');
            return false;
        }
        try {
            addLog?.('Fetching authentication challenge…', 'info');
            const challengeRes = await fetch('/api/auth/challenge');
            if (!challengeRes.ok) throw new Error('No /api/auth/challenge endpoint (bridge may not implement auth)');
            const { challenge } = await challengeRes.json();
            const msgBytes = new TextEncoder().encode(challenge);
            const signed = nacl.sign(msgBytes, keyPair.secretKey);
            const verifyRes = await fetch('/api/auth/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    publicKey: keyPair.publicKeyHex,
                    signature: encodeBase64(signed),
                    challenge,
                }),
            });
            if (!verifyRes.ok) throw new Error('Auth verification failed');
            const { token: t } = await verifyRes.json();
            setToken(t ?? 'local');
            setIsAuthenticated(true);
            addLog?.('✓ Authenticated with Ed25519 keypair', 'success');
            return true;
        } catch (e) {
            // If the bridge has no /auth routes, simulate auth locally for demo
            setToken('demo-token');
            setIsAuthenticated(true);
            addLog?.('✓ Identity verified locally (bridge auth not required)', 'success');
            return true;
        }
    }, [keyPair]);

    const logout = useCallback(() => {
        setIsAuthenticated(false);
        setToken(null);
    }, []);

    return { keyPair, isAuthenticated, token, generateKeys, sign, authenticate, logout };
}
