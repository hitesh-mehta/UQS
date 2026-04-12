'use client';

import { Database, FileText } from 'lucide-react';

interface Props {
  sources: string[];
}

export default function SourceBadge({ sources }: Props) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5 mt-3">
      <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginRight: 2 }}>
        Sources:
      </span>
      {sources.map((src) => {
        const isFile = src.includes('.pdf') || src.includes('.docx') || src.includes('.txt');
        return (
          <span key={src} className="source-chip">
            {isFile ? <FileText size={10} /> : <Database size={10} />}
            {src.length > 30 ? src.slice(0, 28) + '…' : src}
          </span>
        );
      })}
    </div>
  );
}
