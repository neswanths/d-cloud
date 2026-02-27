import { useCallback, useRef, useState } from 'react';
import { listFiles, type FileEntry } from '../api/bridge';

export function useFileList() {
    const [files, setFiles] = useState<FileEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const fetchedRef = useRef(false);

    const fetchFiles = useCallback(async () => {
        setLoading(true);
        try {
            const data = await listFiles();
            setFiles(data ?? []);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
            fetchedRef.current = true;
        }
    }, []);

    const addFile = useCallback((file: FileEntry) => {
        setFiles(prev => {
            if (prev.some(f => f.action_hash === file.action_hash)) return prev;
            return [file, ...prev];
        });
    }, []);

    const removeFile = useCallback((actionHash: string) => {
        setFiles(prev => prev.filter(f => f.action_hash !== actionHash));
    }, []);

    return { files, loading, error, fetchFiles, addFile, removeFile };
}
