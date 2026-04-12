'use client';

import { Brain, GitBranch, Activity, Clock } from 'lucide-react';
import type { ModelRegistryEntry } from '@/lib/types';

interface Props {
  registry: Record<string, ModelRegistryEntry>;
}

export default function ModelStatus({ registry }: Props) {
  const targets = Object.entries(registry);

  if (targets.length === 0) {
    return (
      <div style={{
        textAlign: 'center', padding: '20px 0',
        fontSize: 12, color: 'var(--text-muted)',
      }}>
        No trained models yet. Upload a dataset to trigger training.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {targets.map(([target, info]) => {
        const primaryMetric = Object.entries(info.metrics)[0];
        const metricLabel = primaryMetric?.[0] ?? '';
        const metricValue = primaryMetric?.[1] ?? 0;

        return (
          <div key={target} style={{
            padding: '12px 14px',
            background: 'rgba(5, 5, 20, 0.5)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-subtle)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 'var(--radius-sm)',
                  background: 'rgba(99,102,241,0.15)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Brain size={14} style={{ color: 'var(--accent-primary)' }} />
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {target.replace(/_/g, ' ')}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>
                    {info.model_type}
                  </div>
                </div>
              </div>

              <span className="badge badge-rag" style={{ fontSize: 9 }}>
                v{info.active_version} active
              </span>
            </div>

            {/* Metric */}
            {primaryMetric && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 16,
                padding: '8px 10px',
                background: 'rgba(99,102,241,0.05)',
                borderRadius: 'var(--radius-sm)',
                marginBottom: 8,
              }}>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 1 }}>
                    {metricLabel.toUpperCase()}
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--accent-primary)', fontFamily: 'JetBrains Mono, monospace' }}>
                    {typeof metricValue === 'number' ? metricValue.toFixed(4) : metricValue}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 1 }}>VERSIONS</div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
                    {info.all_versions.length}
                  </div>
                </div>
              </div>
            )}

            {/* Version pills */}
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
              {info.all_versions.map((v) => (
                <span key={v} style={{
                  fontSize: 10, padding: '2px 8px', borderRadius: 99,
                  background: v === info.active_version
                    ? 'rgba(16,185,129,0.15)'
                    : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${v === info.active_version ? 'rgba(16,185,129,0.3)' : 'var(--border-subtle)'}`,
                  color: v === info.active_version ? '#6ee7b7' : 'var(--text-muted)',
                }}>
                  v{v}{v === info.active_version ? ' ✓' : ''}
                </span>
              ))}
            </div>

            {/* Features */}
            {info.features.length > 0 && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                Features: {info.features.slice(0, 4).join(', ')}{info.features.length > 4 ? ` +${info.features.length - 4}` : ''}
              </div>
            )}

            {/* Trained at */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6, fontSize: 10, color: 'var(--text-muted)' }}>
              <Clock size={10} />
              {info.trained_at ? new Date(info.trained_at).toLocaleString() : 'Unknown'}
            </div>
          </div>
        );
      })}
    </div>
  );
}
