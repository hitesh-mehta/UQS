'use client';

import { useState } from 'react';
import { Copy, Check, ChevronDown, ChevronUp, Clock, Cpu } from 'lucide-react';
import type { QueryResponse } from '@/lib/types';
import QueryTypeIndicator from './QueryTypeIndicator';
import SourceBadge from './SourceBadge';
import ChartRenderer from './ChartRenderer';

interface Props {
  response: QueryResponse;
}

function MetricGrid({ metrics }: { metrics: QueryResponse['key_metrics'] }) {
  if (!metrics || metrics.length === 0) return null;
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: `repeat(auto-fill, minmax(140px, 1fr))`,
      gap: 8,
      margin: '14px 0',
    }}>
      {metrics.slice(0, 6).map((m, i) => (
        <div key={i} className="metric-card" style={{ padding: '10px 12px' }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {m.label}
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'JetBrains Mono, monospace' }}>
            {m.value}
          </div>
          {m.change && (
            <div style={{
              fontSize: 11, marginTop: 3,
              color: m.change.startsWith('+') ? 'var(--accent-emerald)' : m.change.startsWith('-') ? 'var(--accent-rose)' : 'var(--text-muted)',
            }}>
              {m.change}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function ResponseCard({ response }: Props) {
  const [copied, setCopied] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  const copyAnswer = async () => {
    await navigator.clipboard.writeText(response.answer).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const hasChart = response.chart && response.chart_type && response.chart_type !== 'none';
  const hasMetrics = response.key_metrics && response.key_metrics.length > 0;

  return (
    <div className="fade-in-up" style={{ width: '100%' }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <QueryTypeIndicator
          engine={response.engine}
          queryType={response.query_type}
          fromCache={response.from_cache}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {response.corrected && (
            <span className="badge" style={{
              background: 'rgba(245,158,11,0.1)',
              color: '#fcd34d',
              border: '1px solid rgba(245,158,11,0.2)',
              fontSize: 10,
            }}>
              SQL Self-Corrected
            </span>
          )}
          {response.model_version !== undefined && response.model_version !== null && (
            <span className="badge badge-predictive" style={{ fontSize: 10 }}>
              <Cpu size={9} /> Model v{response.model_version}
            </span>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-muted)' }}>
            <Clock size={11} />
            {response.latency_ms < 1000
              ? `${Math.round(response.latency_ms)}ms`
              : `${(response.latency_ms / 1000).toFixed(1)}s`}
          </div>
          <button
            className="btn-ghost"
            style={{ padding: '4px 8px', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}
            onClick={copyAnswer}
          >
            {copied ? <Check size={11} style={{ color: '#10b981' }} /> : <Copy size={11} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>

      {/* Main answer text */}
      <div style={{
        fontSize: 14,
        lineHeight: 1.75,
        color: 'var(--text-primary)',
        whiteSpace: 'pre-wrap',
      }}>
        {response.answer}
      </div>

      {/* Key metrics */}
      {hasMetrics && <MetricGrid metrics={response.key_metrics} />}

      {/* Chart */}
      {hasChart && (
        <ChartRenderer type={response.chart_type!} data={response.chart!} />
      )}

      {/* Source badges */}
      <SourceBadge sources={response.sources} />

      {/* Raw JSON toggle (dev use) */}
      <button
        className="btn-ghost"
        style={{ padding: '4px 8px', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4, marginTop: 12 }}
        onClick={() => setShowRaw(!showRaw)}
      >
        {showRaw ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        {showRaw ? 'Hide' : 'Show'} raw response
      </button>

      {showRaw && (
        <div className="code-block" style={{ marginTop: 8, maxHeight: 200, overflowY: 'auto' }}>
          {JSON.stringify(response, null, 2)}
        </div>
      )}
    </div>
  );
}
