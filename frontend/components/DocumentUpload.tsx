'use client';

import { useState, useCallback } from 'react';
import { Upload, X, FileText, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { uploadDocument } from '@/lib/api';
import type { UploadedDocument } from '@/lib/types';

interface Props {
  sessionId: string;
  onUploaded?: (doc: UploadedDocument) => void;
}

type UploadState = 'idle' | 'uploading' | 'success' | 'error';

export default function DocumentUpload({ sessionId, onUploaded }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [state, setState] = useState<UploadState>('idle');
  const [message, setMessage] = useState('');
  const [lastDoc, setLastDoc] = useState<UploadedDocument | null>(null);

  const handleFile = useCallback(async (file: File) => {
    setState('uploading');
    setMessage('');
    try {
      const result = await uploadDocument(file, sessionId);
      setLastDoc(result);
      setState('success');
      setMessage(result.message);
      onUploaded?.(result);
      setTimeout(() => setState('idle'), 4000);
    } catch (err) {
      setState('error');
      setMessage(err instanceof Error ? err.message : 'Upload failed');
      setTimeout(() => setState('idle'), 4000);
    }
  }, [sessionId, onUploaded]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = '';
  }, [handleFile]);

  return (
    <div>
      <label
        className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '20px 16px',
          cursor: state === 'uploading' ? 'default' : 'pointer',
          gap: 8,
          position: 'relative',
          overflow: 'hidden',
        }}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept=".pdf,.docx,.doc,.txt,.md"
          onChange={handleChange}
          disabled={state === 'uploading'}
          style={{ display: 'none' }}
        />

        {state === 'uploading' ? (
          <>
            <Loader2 size={24} style={{ color: 'var(--accent-primary)' }} className="animate-spin" />
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Uploading & indexing…</span>
          </>
        ) : state === 'success' ? (
          <>
            <CheckCircle size={24} style={{ color: 'var(--accent-emerald)' }} />
            <span style={{ fontSize: 12, color: 'var(--accent-emerald)', textAlign: 'center' }}>
              {lastDoc?.chunks_added} chunks indexed from {lastDoc?.filename}
            </span>
          </>
        ) : state === 'error' ? (
          <>
            <AlertCircle size={24} style={{ color: 'var(--accent-rose)' }} />
            <span style={{ fontSize: 12, color: 'var(--accent-rose)', textAlign: 'center' }}>
              {message}
            </span>
          </>
        ) : (
          <>
            <div style={{
              width: 40, height: 40,
              borderRadius: '50%',
              background: 'rgba(99, 102, 241, 0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Upload size={18} style={{ color: 'var(--accent-primary)' }} />
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 500 }}>
                Drop a document or click to upload
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>
                PDF · DOCX · TXT · MD (max 50MB)
              </div>
            </div>
          </>
        )}
      </label>
    </div>
  );
}
