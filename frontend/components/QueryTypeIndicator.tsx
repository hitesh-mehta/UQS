'use client';

import { EngineType, QueryType } from '@/lib/types';
import {
  Database,
  TrendingUp,
  Brain,
  FileText,
  Layers,
  Zap,
  HelpCircle,
} from 'lucide-react';

interface Props {
  engine: EngineType;
  queryType?: QueryType;
  fromCache?: boolean;
}

const ENGINE_CONFIG: Record<string, {
  label: string;
  icon: React.ReactNode;
  className: string;
}> = {
  sql: {
    label: 'SQL',
    icon: <Database size={10} />,
    className: 'badge-sql',
  },
  analytical: {
    label: 'Analytical',
    icon: <TrendingUp size={10} />,
    className: 'badge-analytical',
  },
  predictive: {
    label: 'Predictive',
    icon: <Brain size={10} />,
    className: 'badge-predictive',
  },
  rag: {
    label: 'RAG',
    icon: <FileText size={10} />,
    className: 'badge-rag',
  },
  'rag++': {
    label: 'RAG++',
    icon: <Layers size={10} />,
    className: 'badge-rag',
  },
  cache: {
    label: 'Cache',
    icon: <Zap size={10} />,
    className: 'badge-cache',
  },
  classifier: {
    label: 'Classifier',
    icon: <HelpCircle size={10} />,
    className: 'badge-irrelevant',
  },
};

const SUB_TYPE_LABELS: Partial<Record<QueryType, string>> = {
  trend_analysis: 'Trend',
  causal_diagnostic: 'Causal',
  comparative: 'Compare',
  what_if: 'What-If',
  time_series: 'Time-Series',
  decomposition: 'Decompose',
  forecast: 'Forecast',
  clustering: 'Cluster',
  anomaly: 'Anomaly',
};

export default function QueryTypeIndicator({ engine, queryType, fromCache }: Props) {
  const config = ENGINE_CONFIG[engine] || ENGINE_CONFIG.classifier;
  const subLabel = queryType ? SUB_TYPE_LABELS[queryType] : undefined;

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className={`badge ${config.className}`}>
        {config.icon}
        {fromCache ? 'Cache Hit' : config.label}
      </span>
      {subLabel && !fromCache && (
        <span className="badge" style={{
          background: 'rgba(255,255,255,0.04)',
          color: 'var(--text-muted)',
          border: '1px solid rgba(255,255,255,0.06)',
        }}>
          {subLabel}
        </span>
      )}
    </div>
  );
}
