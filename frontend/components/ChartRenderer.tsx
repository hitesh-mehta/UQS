'use client';

import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import type { ChartData, Prediction } from '@/lib/types';

interface Props {
  type: string;
  data: ChartData;
}

const COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#f43f5e'];

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string }>;
  label?: string;
}) => {
  if (active && payload && payload.length) {
    return (
      <div style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-sm)',
        padding: '10px 14px',
        fontSize: 12,
      }}>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 4, fontSize: 11 }}>{label}</p>
        {payload.map((p, i) => (
          <p key={i} style={{ color: p.color, fontFamily: 'JetBrains Mono, monospace' }}>
            {p.name}: {typeof p.value === 'number' ? p.value.toLocaleString() : p.value}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

// ── Bar/Line chart from labels + datasets ─────────────────────────────────────
function LabeledChart({ data, type }: { data: ChartData; type: string }) {
  const { labels = [], datasets = [] } = data;
  if (!labels.length || !datasets.length) return null;

  const chartData = labels.map((label, i) => {
    const entry: Record<string, string | number> = { name: label };
    datasets.forEach((ds) => { entry[ds.label] = ds.data[i] ?? 0; });
    return entry;
  });

  const ChartEl = type === 'line' ? LineChart : BarChart;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ChartEl data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {datasets.map((ds, i) =>
          type === 'line' ? (
            <Line
              key={ds.label}
              type="monotone"
              dataKey={ds.label}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3, fill: COLORS[i % COLORS.length] }}
              activeDot={{ r: 5 }}
            />
          ) : (
            <Bar
              key={ds.label}
              dataKey={ds.label}
              fill={COLORS[i % COLORS.length]}
              radius={[4, 4, 0, 0]}
            />
          )
        )}
      </ChartEl>
    </ResponsiveContainer>
  );
}

// ── Data table ────────────────────────────────────────────────────────────────
function DataTable({ data }: { data: ChartData }) {
  const { columns = [], rows = [] } = data;
  if (!columns.length || !rows.length) return null;

  return (
    <div style={{ overflowX: 'auto', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
      <table className="uqs-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col}>{col.replace(/_/g, ' ')}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td key={col}>{String(row[col] ?? '—')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 20 && (
        <div style={{
          padding: '8px 14px',
          fontSize: 11,
          color: 'var(--text-muted)',
          borderTop: '1px solid var(--border-subtle)',
        }}>
          Showing 20 of {rows.length} rows
        </div>
      )}
    </div>
  );
}

// ── Predictions table ─────────────────────────────────────────────────────────
function PredictionsTable({ predictions }: { predictions: Prediction[] }) {
  return (
    <div style={{ overflowX: 'auto', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
      <table className="uqs-table">
        <thead>
          <tr>
            <th>Entity</th>
            <th>Prediction</th>
            <th>Label</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>
          {predictions.slice(0, 20).map((p, i) => (
            <tr key={i}>
              <td>{p.entity}</td>
              <td style={{ color: 'var(--accent-cyan)' }}>
                {typeof p.prediction === 'number' ? p.prediction.toLocaleString() : p.prediction}
              </td>
              <td>
                {p.label && (
                  <span className={`badge ${p.label.toLowerCase().includes('high') || p.label.toLowerCase().includes('suspicious') ? 'badge-irrelevant' : 'badge-rag'}`}
                    style={{ fontSize: 10 }}>
                    {p.label}
                  </span>
                )}
              </td>
              <td>
                {p.confidence !== undefined && p.confidence !== null ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{
                      width: 60, height: 4,
                      background: 'rgba(255,255,255,0.08)',
                      borderRadius: 99, overflow: 'hidden',
                    }}>
                      <div style={{
                        width: `${Math.round(p.confidence * 100)}%`,
                        height: '100%',
                        background: p.confidence > 0.7 ? '#10b981' : '#f59e0b',
                        borderRadius: 99,
                      }} />
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {Math.round(p.confidence * 100)}%
                    </span>
                  </div>
                ) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main ChartRenderer ────────────────────────────────────────────────────────
export default function ChartRenderer({ type, data }: Props) {
  if (!data || !type || type === 'none') return null;

  return (
    <div style={{
      marginTop: 16,
      padding: 16,
      background: 'rgba(5, 5, 20, 0.5)',
      borderRadius: 'var(--radius-md)',
      border: '1px solid var(--border-subtle)',
    }}>
      {type === 'table' ? (
        <DataTable data={data} />
      ) : type === 'predictions' ? (
        <PredictionsTable predictions={data.predictions || []} />
      ) : type === 'pie' ? (
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie
              data={(data.labels || []).map((l, i) => ({
                name: l,
                value: data.datasets?.[0]?.data[i] ?? 0,
              }))}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={100}
              label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
            >
              {(data.labels || []).map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      ) : (
        <LabeledChart data={data} type={type} />
      )}
    </div>
  );
}
