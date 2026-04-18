'use client';

import { useState, useEffect, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import {
  Sparkles, Database, TrendingUp, Brain, FileText,
  Zap, LayoutGrid, Settings, ChevronLeft,
  ChevronRight, Layers, Shield, Activity, Info,
  Key, CheckCircle, AlertCircle, Loader2,
  Sun, Moon
} from 'lucide-react';

import ChatInterface from '@/components/ChatInterface';
import CacheStatusPanel from '@/components/CacheStatusPanel';
import ModelStatus from '@/components/ModelStatus';
import {
  fetchHealth, fetchDevToken, setAuthToken, getAuthToken,
  fetchCacheStatus, fetchModelRegistry,
} from '@/lib/api';
import type { CacheStatus, ModelRegistryEntry, UploadedDocument } from '@/lib/types';

// ── Sidebar nav items ─────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: 'chat',    label: 'Query',    icon: Sparkles },
  { id: 'cache',   label: 'Cache',    icon: Zap },
  { id: 'models',  label: 'Models',   icon: Brain },
  { id: 'engines', label: 'Engines',  icon: LayoutGrid },
  { id: 'rbac',    label: 'Security', icon: Shield },
];

const ENGINE_CARDS = [
  { id: 'sql',    name: 'SQL Engine',        color: '#6366f1', icon: Database,   desc: 'NL→SQL with DIN-SQL patterns, schema linking, self-correction loop' },
  { id: 'ana',    name: 'Analytical Engine', color: '#06b6d4', icon: TrendingUp, desc: 'Algorithm brain: trend, causal, comparative, what-if, decomposition' },
  { id: 'pred',   name: 'Predictive Engine', color: '#8b5cf6', icon: Brain,      desc: 'XGBoost/RF/Prophet pool, auto model selection, continual learning' },
  { id: 'rag',    name: 'RAG Engine',        color: '#10b981', icon: FileText,   desc: 'Document Q&A via FAISS vector retrieval + sentence-transformers' },
  { id: 'ragpp',  name: 'RAG++ Engine',      color: '#f59e0b', icon: Layers,     desc: 'Hybrid: live DB data + uploaded documents merged for richer answers' },
  { id: 'cache2', name: 'Cache Layer',       color: '#f43f5e', icon: Zap,        desc: '4-granularity FIFO (hourly/daily/weekly/monthly), LLM hit detection' },
];

const RBAC_ROLES = [
  { role: 'admin',            views: ['*'],                          desc: 'Full schema access — all tables & columns' },
  { role: 'analyst',          views: ['analyst_sales_view', 'analyst_kpi_view'],          desc: 'Aggregated views only, no row-level data or PII' },
  { role: 'regional_manager', views: ['rm_sales_view', 'rm_customer_view'],               desc: 'Region-filtered, no PII columns' },
  { role: 'auditor',          views: ['audit_trail_view'],           desc: 'Audit trail tables only' },
  { role: 'viewer',           views: ['dashboard_summary_view'],     desc: 'Summary dashboards only' },
];

// ── Connection status pill ─────────────────────────────────────────────────────
function StatusPill({ status, model }: { status: 'connected' | 'error' | 'loading'; model?: string }) {
  const configs = {
    connected: { color: '#10b981', bg: 'rgba(16,185,129,0.1)', border: 'rgba(16,185,129,0.25)', label: `Connected · ${model}` },
    error:     { color: '#f43f5e', bg: 'rgba(244,63,94,0.1)',  border: 'rgba(244,63,94,0.25)',  label: 'Backend offline' },
    loading:   { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.25)', label: 'Connecting…' },
  };
  const cfg = configs[status];
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '4px 10px', borderRadius: 99,
      background: cfg.bg, border: `1px solid ${cfg.border}`,
      fontSize: 11, color: cfg.color,
    }}>
      <div style={{ width: 6, height: 6, borderRadius: '50%', background: cfg.color }} />
      {cfg.label}
    </div>
  );
}

// ── Auth setup modal ──────────────────────────────────────────────────────────
function AuthModal({ onDone }: { onDone: () => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [role, setRole] = useState('analyst');

  const handleDevLogin = async () => {
    setLoading(true);
    setError('');
    try {
      const token = await fetchDevToken(role);
      setAuthToken(token);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to get token. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100,
      background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(12px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
    }}>
      <div className="glass-bright" style={{
        borderRadius: 'var(--radius-xl)', padding: 40, maxWidth: 440, width: '100%',
        boxShadow: '0 24px 80px rgba(0,0,0,0.6)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{
            width: 60, height: 60, borderRadius: 20,
            background: 'linear-gradient(135deg, var(--border-subtle), var(--border-strong))',
            border: '1px solid var(--border-strong)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
          }}>
            <Key size={28} style={{ color: '#818cf8' }} />
          </div>
          <h1 className="gradient-text" style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>
            Universal Query Solver
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Development mode — connect to your local backend to get started.
          </p>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
            Login as role (dev only)
          </label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            style={{
              width: '100%', background: 'var(--bg-surface)', border: '1.5px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)', padding: '10px 14px', color: 'var(--text-primary)',
              fontSize: 14, fontFamily: 'Inter, sans-serif', outline: 'none',
            }}
          >
            <option value="admin">Admin</option>
            <option value="analyst">Analyst</option>
            <option value="regional_manager">Regional Manager</option>
            <option value="auditor">Auditor</option>
            <option value="viewer">Viewer</option>
          </select>
        </div>

        {error && (
          <div style={{
            marginBottom: 14, padding: '10px 14px',
            background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.25)',
            borderRadius: 'var(--radius-sm)', fontSize: 12, color: '#fda4af',
            display: 'flex', gap: 8, alignItems: 'flex-start',
          }}>
            <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
            {error}
          </div>
        )}

        <button
          className="btn-primary"
          style={{ width: '100%', padding: '12px 20px', fontSize: 15 }}
          onClick={handleDevLogin}
          disabled={loading}
        >
          {loading ? (
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <Loader2 size={16} className="animate-spin" /> Connecting…
            </span>
          ) : 'Connect & Enter →'}
        </button>

        <p style={{ textAlign: 'center', marginTop: 16, fontSize: 11, color: 'var(--text-muted)' }}>
          Make sure <code style={{ color: '#818cf8' }}>uvicorn backend.main:app</code> is running on port 8000
        </p>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function Home() {
  const [sessionId] = useState(() => uuidv4());
  const [activeTab, setActiveTab] = useState('chat');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(false);
  const [isAuthed, setIsAuthed] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [health, setHealth] = useState<{ status: string; llm_model: string; database: string } | null>(null);
  const [healthStatus, setHealthStatus] = useState<'loading' | 'connected' | 'error'>('loading');
  const [cacheData, setCacheData] = useState<CacheStatus | null>(null);
  const [modelData, setModelData] = useState<Record<string, ModelRegistryEntry> | null>(null);
  const [uploadedDocs, setUploadedDocs] = useState<UploadedDocument[]>([]);
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');

  // ── Handle Theme ───────────────────────────────────────────────────────────
  useEffect(() => {
    const saved = localStorage.getItem('uqs-theme') || 'dark';
    setTheme(saved as 'light' | 'dark');
  }, []);

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
    localStorage.setItem('uqs-theme', theme);
  }, [theme]);

  // ── Check auth on mount ────────────────────────────────────────────────────
  useEffect(() => {
    const token = getAuthToken();
    setIsAuthed(!!token);
    setCheckingAuth(false);
  }, []);

  // ── Poll backend health ────────────────────────────────────────────────────
  useEffect(() => {
    if (!isAuthed) return;
    const check = async () => {
      try {
        const h = await fetchHealth();
        setHealth(h);
        setHealthStatus(h.status === 'healthy' ? 'connected' : 'error');
      } catch {
        setHealthStatus('error');
      }
    };
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, [isAuthed]);

  // ── Load cache / model data when tab opens ─────────────────────────────────
  const loadCacheData = useCallback(async () => {
    try {
      const data = await fetchCacheStatus();
      setCacheData(data);
    } catch {}
  }, []);

  const loadModelData = useCallback(async () => {
    try {
      const data = await fetchModelRegistry();
      setModelData(data);
    } catch {}
  }, []);

  useEffect(() => {
    if (!isAuthed) return;
    if (activeTab === 'cache') loadCacheData();
    if (activeTab === 'models') loadModelData();
  }, [activeTab, isAuthed, loadCacheData, loadModelData]);

  if (checkingAuth) return null;

  return (
    <>
      {/* Ambient background */}
      <div className="ambient-bg">
        <div className="ambient-blob ambient-blob-1" />
        <div className="ambient-blob ambient-blob-2" />
        <div className="ambient-blob ambient-blob-3" />
      </div>

      {/* Auth modal */}
      {!isAuthed && <AuthModal onDone={() => setIsAuthed(true)} />}

      {/* Main layout */}
      <div style={{
        display: 'flex', height: '100vh', position: 'relative', zIndex: 1, overflow: 'hidden',
      }}>
        {/* ── Left Sidebar ─────────────────────────────────────────────────── */}
        <div className="layout-sidebar" style={{
          width: sidebarOpen ? 220 : 64,
          flexShrink: 0,
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
        }}>
          {/* Logo */}
          <div style={{
            padding: sidebarOpen ? '20px 16px 16px' : '20px 16px 16px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex', alignItems: 'center', gap: 10,
            justifyContent: sidebarOpen ? 'flex-start' : 'center',
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10, flexShrink: 0,
              background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: 'var(--glow-sm)',
            }}>
              <Sparkles size={18} style={{ color: 'white' }} />
            </div>
            {sidebarOpen && (
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, lineHeight: 1.2 }}>UQS</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Query Solver</div>
              </div>
            )}
          </div>

          {/* Nav */}
          <nav style={{ flex: 1, padding: '12px 8px', overflow: 'hidden' }}>
            {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`sidebar-item ${activeTab === id ? 'active' : ''}`}
                style={{
                  width: '100%', border: 'none', cursor: 'pointer',
                  justifyContent: sidebarOpen ? 'flex-start' : 'center',
                  marginBottom: 2,
                }}
                title={!sidebarOpen ? label : undefined}
              >
                <Icon size={16} style={{ flexShrink: 0 }} />
                {sidebarOpen && <span>{label}</span>}
              </button>
            ))}
          </nav>

          {/* Health */}
          {sidebarOpen && isAuthed && (
            <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border-subtle)' }}>
              <StatusPill
                status={healthStatus}
                model={health?.llm_model}
              />
            </div>
          )}

          {/* Collapse toggle */}
          <button
            className="btn-ghost"
            style={{
              margin: '0 8px 12px',
              padding: '8px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            {sidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>

        {/* ── Main Content ───────────────────────────────────────────────────── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Top bar */}
          <div className="layout-header" style={{
            height: 56, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '0 20px',
          }}>
            <div>
              <h1 style={{ fontSize: 15, fontWeight: 600 }}>
                {activeTab === 'chat'    && 'Data Query Interface'}
                {activeTab === 'cache'   && 'Cache Intelligence Layer'}
                {activeTab === 'models'  && 'ML Model Registry'}
                {activeTab === 'engines' && 'Engine Architecture'}
                {activeTab === 'rbac'    && 'Security & RBAC'}
              </h1>
              <p style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                {activeTab === 'chat'    && `Session: ${sessionId.slice(0, 8)}…`}
                {activeTab === 'cache'   && '4-granularity pre-generated report cache'}
                {activeTab === 'models'  && 'Versioned ML models with auto-promote & rollback'}
                {activeTab === 'engines' && '5 specialized AI engines for every query type'}
                {activeTab === 'rbac'    && 'Database-level role-based access control'}
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {activeTab === 'chat' && (
                <button
                  className="btn-ghost"
                  style={{ padding: '6px 12px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 5 }}
                  onClick={() => setRightOpen(!rightOpen)}
                >
                  <Activity size={13} />
                  {rightOpen ? 'Hide Panel' : 'Show Panel'}
                </button>
              )}
              <button
                className="btn-icon"
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                title="Toggle Theme"
              >
                {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
              </button>
            </div>
          </div>

          {/* Content */}
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
            {/* ── Chat tab ──────────────────────────────────────────────────── */}
            {activeTab === 'chat' && (
              <>
                <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
                  <ChatInterface
                    sessionId={sessionId}
                    onDocumentUploaded={(doc) => setUploadedDocs((prev) => [doc, ...prev])}
                  />
                </div>
                {/* Right panel */}
                {rightOpen && (
                  <div className="layout-panel-right" style={{
                    width: 300, flexShrink: 0,
                    padding: 16,
                    overflow: 'auto',
                    display: 'flex', flexDirection: 'column', gap: 16,
                  }}>
                    {/* Uploaded docs */}
                    {uploadedDocs.length > 0 && (
                      <div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          Indexed Documents
                        </div>
                        {uploadedDocs.map((doc, i) => (
                          <div key={i} style={{
                            padding: '8px 10px', marginBottom: 6,
                            background: 'var(--border-subtle)', border: '1px solid var(--border-strong)',
                            borderRadius: 'var(--radius-sm)',
                          }}>
                            <div style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 3 }}>{doc.filename}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{doc.chunks_added} chunks indexed</div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Three pillars */}
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Three Pillars
                      </div>
                      {[
                        { label: 'Clarity',  desc: 'Plain-English answers, no SQL jargon', color: '#818cf8' },
                        { label: 'Trust',    desc: 'Every response cites its source data', color: '#6ee7b7' },
                        { label: 'Speed',    desc: 'Cache serves repeat queries instantly', color: '#fcd34d' },
                      ].map(({ label, desc, color }) => (
                        <div key={label} style={{
                          padding: '8px 10px', marginBottom: 6,
                          background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--border-subtle)',
                          display: 'flex', gap: 10, alignItems: 'flex-start',
                        }}>
                          <div style={{ width: 3, borderRadius: 99, background: color, alignSelf: 'stretch', minHeight: 24, flexShrink: 0 }} />
                          <div>
                            <div style={{ fontSize: 12, fontWeight: 600, color }}>{label}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{desc}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ── Cache tab ─────────────────────────────────────────────────── */}
            {activeTab === 'cache' && (
              <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
                {cacheData ? (
                  <div style={{ maxWidth: 700 }}>
                    <CacheStatusPanel
                      summaries={cacheData.summaries}
                      reports={cacheData.reports}
                      onRefresh={loadCacheData}
                    />
                  </div>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 13 }}>
                    <Loader2 size={16} className="animate-spin" />
                    Loading cache status…
                  </div>
                )}
              </div>
            )}

            {/* ── Models tab ────────────────────────────────────────────────── */}
            {activeTab === 'models' && (
              <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
                <div style={{ maxWidth: 700 }}>
                  {modelData ? (
                    <ModelStatus registry={modelData} />
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 13 }}>
                      <Loader2 size={16} className="animate-spin" />
                      Loading model registry…
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Engines tab ───────────────────────────────────────────────── */}
            {activeTab === 'engines' && (
              <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, maxWidth: 900 }}>
                  {ENGINE_CARDS.map((eng) => {
                    const Icon = eng.icon;
                    return (
                      <div key={eng.id} className="glass" style={{
                        padding: 20, borderRadius: 'var(--radius-lg)',
                        border: `1px solid ${eng.color}22`,
                        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                      }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-3px)';
                          (e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 32px ${eng.color}22`;
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLDivElement).style.transform = '';
                          (e.currentTarget as HTMLDivElement).style.boxShadow = '';
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                          <div style={{
                            width: 40, height: 40, borderRadius: 12,
                            background: `${eng.color}18`,
                            border: `1px solid ${eng.color}33`,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                          }}>
                            <Icon size={18} style={{ color: eng.color }} />
                          </div>
                          <span style={{ fontSize: 14, fontWeight: 600 }}>{eng.name}</span>
                        </div>
                        <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6 }}>{eng.desc}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── RBAC tab ──────────────────────────────────────────────────── */}
            {activeTab === 'rbac' && (
              <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
                <div style={{ maxWidth: 700 }}>
                  <div style={{
                    marginBottom: 20, padding: '14px 16px',
                    background: 'var(--border-subtle)', border: '1px solid var(--border-strong)',
                    borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6,
                    display: 'flex', gap: 10,
                  }}>
                    <Info size={16} style={{ color: 'var(--accent-primary)', flexShrink: 0, marginTop: 1 }} />
                    RBAC is enforced at the <strong>database view level</strong> — not the application layer.
                    The LLM only ever receives the schema for views the current role can access.
                    No role can perform INSERT, UPDATE, or DELETE.
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {RBAC_ROLES.map(({ role, views, desc }) => (
                      <div key={role} className="glass" style={{ padding: '16px 18px', borderRadius: 'var(--radius-md)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                          <Shield size={15} style={{ color: 'var(--accent-primary)' }} />
                          <span style={{ fontSize: 14, fontWeight: 600, fontFamily: 'JetBrains Mono, monospace', color: '#818cf8' }}>
                            {role}
                          </span>
                        </div>
                        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>{desc}</p>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {views.map((v) => (
                            <span key={v} className="source-chip" style={{ fontSize: 10 }}>{v}</span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Spinner override for framer-motion compatibility */}
      <style>{`
        .animate-spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </>
  );
}
