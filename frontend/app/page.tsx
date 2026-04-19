'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import {
  Sparkles, Database, TrendingUp, Brain, FileText, Zap,
  LayoutGrid, Shield, Activity, ChevronLeft, ChevronRight,
  Layers, Key, CheckCircle, AlertCircle, Loader2, Sun, Moon,
  Lock, Mail, LogOut, Eye, EyeOff, Building2, Copy, ExternalLink,
  RefreshCw, ArrowUpRight, ArrowDownRight, Minus, AlertTriangle,
  Settings, Users, BarChart3, ChevronDown, ChevronUp, PlayCircle,
  Info, Trash2,
} from 'lucide-react';

import ChatInterface from '@/components/ChatInterface';
import ModelStatus from '@/components/ModelStatus';
import {
  fetchHealth, loginToSupabase, setAuthToken, getAuthToken, clearAuthToken,
  fetchCacheStatus, fetchModelRegistry, fetchRBACRoles,
  generateCacheReport, flushCache, registerTenant,
} from '@/lib/api';
import type {
  CacheStatus, CacheSummary, CachedReportDetail,
  ModelRegistryEntry, UploadedDocument, LoginResult,
} from '@/lib/types';

// ── Helpers ───────────────────────────────────────────────────────────────────
const ADMIN_ROLES = new Set(['admin', 'manager']);

function getRoleBadgeClass(role: string): string {
  const map: Record<string, string> = {
    admin: 'role-badge-admin',
    manager: 'role-badge-manager',
    analyst: 'role-badge-analyst',
    auditor: 'role-badge-auditor',
    viewer: 'role-badge-viewer',
    regional_manager: 'role-badge-regional_manager',
  };
  return map[role] || 'role-badge-viewer';
}

// ── Nav items ─────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: 'chat',    label: 'Query',      icon: Sparkles },
  { id: 'cache',   label: 'Cache',      icon: Zap },
  { id: 'models',  label: 'Models',     icon: Brain },
  { id: 'engines', label: 'Engines',    icon: LayoutGrid },
  { id: 'rbac',    label: 'Security',   icon: Shield },
  { id: 'admin',   label: 'Admin',      icon: Settings, adminOnly: true },
];

const ENGINE_CARDS = [
  { id: 'sql',    name: 'SQL Engine',         color: '#6366f1', icon: Database,   desc: 'NL→SQL with DIN-SQL patterns, schema linking, self-correction loop' },
  { id: 'ana',    name: 'Analytical Engine',  color: '#06b6d4', icon: TrendingUp, desc: 'Algorithm brain: trend, causal, comparative, what-if, decomposition' },
  { id: 'pred',   name: 'Predictive Engine',  color: '#8b5cf6', icon: Brain,      desc: 'XGBoost/RF/Prophet pool, auto model selection, continual learning' },
  { id: 'rag',    name: 'RAG Engine',         color: '#10b981', icon: FileText,   desc: 'Document Q&A via FAISS vector retrieval + sentence-transformers' },
  { id: 'ragpp',  name: 'RAG++ Engine',       color: '#f59e0b', icon: Layers,     desc: 'Hybrid: live DB + uploaded documents merged for richer answers' },
  { id: 'cache2', name: 'Cache Layer',        color: '#f43f5e', icon: Zap,        desc: '4-granularity FIFO (hourly/daily/weekly/monthly), LLM hit detection' },
];

const GRAN_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  hourly:  { label: 'Hourly',  color: '#6366f1', icon: <Activity size={12} /> },
  daily:   { label: 'Daily',   color: '#06b6d4', icon: <BarChart3 size={12} /> },
  weekly:  { label: 'Weekly',  color: '#8b5cf6', icon: <TrendingUp size={12} /> },
  monthly: { label: 'Monthly', color: '#f59e0b', icon: <Zap size={12} /> },
};

// ── StatusPill ────────────────────────────────────────────────────────────────
function StatusPill({ status, model }: { status: 'connected' | 'error' | 'loading'; model?: string }) {
  const cfg = {
    connected: { color: '#10b981', bg: 'rgba(16,185,129,0.1)', border: 'rgba(16,185,129,0.25)', label: `Connected · ${model}` },
    error:     { color: '#f43f5e', bg: 'rgba(244,63,94,0.1)',  border: 'rgba(244,63,94,0.25)',  label: 'Backend offline' },
    loading:   { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.25)', label: 'Connecting…' },
  }[status];
  return (
    <div style={{ display:'flex', alignItems:'center', gap:6, padding:'4px 10px', borderRadius:99, background:cfg.bg, border:`1px solid ${cfg.border}`, fontSize:11, color:cfg.color }}>
      <div style={{ width:6, height:6, borderRadius:'50%', background:cfg.color }} />
      {cfg.label}
    </div>
  );
}

// ── Tenant Registration Modal ─────────────────────────────────────────────────
function TenantRegisterModal({ onDone, onBack }: { onDone: (tenantId: string, link: string) => void; onBack: () => void }) {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ tenant_id: string; access_url: string; name: string } | null>(null);
  const [form, setForm] = useState({ name: '', supabase_url: '', anon_key: '', service_key: '', db_url: '', contact_email: '' });
  const [copied, setCopied] = useState(false);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.supabase_url || !form.anon_key || !form.db_url) {
      setError('Please fill all required fields.'); return;
    }
    setLoading(true); setError('');
    try {
      const res = await registerTenant(form);
      setResult(res);
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally { setLoading(false); }
  };

  const copy = () => {
    if (result) {
      navigator.clipboard.writeText(window.location.origin + result.access_url);
      setCopied(true); setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div style={{ position:'fixed', inset:0, zIndex:200, background:'rgba(0,0,0,0.7)', backdropFilter:'blur(20px)', display:'flex', alignItems:'center', justifyContent:'center', padding:24 }}>
      <div className="glass-bright fade-in-up" style={{ borderRadius:'var(--radius-xl)', padding:'40px 36px', maxWidth:520, width:'100%', maxHeight:'90vh', overflow:'auto' }}>

        {/* Header */}
        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:28 }}>
          <div style={{ width:44, height:44, borderRadius:14, background:'linear-gradient(135deg, var(--accent-secondary), var(--accent-primary))', display:'flex', alignItems:'center', justifyContent:'center' }}>
            <Building2 size={22} color="#fff" />
          </div>
          <div>
            <h2 style={{ fontSize:18, fontWeight:700 }}>Register Your Organization</h2>
            <p style={{ fontSize:12, color:'var(--text-muted)', marginTop:2 }}>Connect your Supabase project to UQS</p>
          </div>
        </div>

        {/* Steps */}
        <div style={{ display:'flex', gap:8, marginBottom:28 }}>
          {[{n:1,label:'Connect DB'},{n:2,label:'Get Link'}].map(({n,label}) => (
            <div key={n} className={`wizard-step ${step===n?'active':step>n?'done':'pending'}`} style={{ flex:1, justifyContent:'center' }}>
              <div className="wizard-step-circle">{step>n?<CheckCircle size={13}/>:n}</div>
              {label}
            </div>
          ))}
        </div>

        {step === 1 && (
          <form onSubmit={handleSubmit} style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {[
              { key:'name',          label:'Organization Name *',  placeholder:'Acme Corp / NatWest Analytics',  type:'text' },
              { key:'contact_email', label:'Contact Email *',      placeholder:'admin@company.com',              type:'email' },
              { key:'supabase_url',  label:'Supabase Project URL *', placeholder:'https://xxxx.supabase.co',    type:'url' },
              { key:'anon_key',      label:'Supabase Anon Key *',  placeholder:'eyJh…',                          type:'text' },
              { key:'service_key',   label:'Supabase Service Key', placeholder:'eyJh… (for admin ops)',          type:'text' },
              { key:'db_url',        label:'Database URL *',       placeholder:'postgresql://user:pass@host:5432/db', type:'text' },
            ].map(({ key, label, placeholder, type }) => (
              <div key={key}>
                <label style={{ fontSize:12, color:'var(--text-secondary)', display:'block', marginBottom:5, fontWeight:500 }}>{label}</label>
                <input type={type} placeholder={placeholder} value={(form as any)[key]} onChange={set(key)} className="uqs-input" style={{ width:'100%', padding:'10px 14px' }} />
              </div>
            ))}

            {error && (
              <div style={{ padding:'10px 14px', background:'rgba(244,63,94,0.1)', border:'1px solid rgba(244,63,94,0.25)', borderRadius:'var(--radius-sm)', fontSize:12, color:'var(--accent-rose)', display:'flex', gap:8, alignItems:'center' }}>
                <AlertCircle size={14} />{error}
              </div>
            )}

            <div style={{ display:'flex', gap:10, marginTop:4 }}>
              <button type="button" onClick={onBack} className="btn-ghost" style={{ flex:1, padding:'11px' }}>← Back to Login</button>
              <button type="submit" className="btn-primary" style={{ flex:2, padding:'11px' }} disabled={loading}>
                {loading ? <><Loader2 size={15} className="animate-spin" style={{ marginRight:6 }} />Registering…</> : 'Register Organization'}
              </button>
            </div>
          </form>
        )}

        {step === 2 && result && (
          <div className="fade-in-up" style={{ display:'flex', flexDirection:'column', gap:16 }}>
            <div style={{ textAlign:'center', padding:'16px 0' }}>
              <div style={{ width:56, height:56, borderRadius:'50%', background:'rgba(16,185,129,0.15)', border:'2px solid var(--accent-emerald)', display:'flex', alignItems:'center', justifyContent:'center', margin:'0 auto 14px' }}>
                <CheckCircle size={28} color="var(--accent-emerald)" />
              </div>
              <h3 style={{ fontSize:18, fontWeight:700, marginBottom:6 }}>🎉 {result.name} registered!</h3>
              <p style={{ fontSize:13, color:'var(--text-muted)' }}>Share this unique link with your team:</p>
            </div>

            <div style={{ background:'var(--bg-elevated)', border:'1px solid var(--border-strong)', borderRadius:'var(--radius-md)', padding:'12px 14px' }}>
              <div style={{ fontSize:11, color:'var(--text-muted)', marginBottom:6, fontWeight:600, textTransform:'uppercase', letterSpacing:'0.05em' }}>Team Access URL</div>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <code style={{ flex:1, fontSize:11, fontFamily:'JetBrains Mono', color:'var(--accent-cyan)', wordBreak:'break-all' }}>
                  {typeof window !== 'undefined' ? window.location.origin : ''}{result.access_url}
                </code>
                <button onClick={copy} className="btn-ghost" style={{ padding:'5px 10px', flexShrink:0, fontSize:11 }}>
                  {copied ? <CheckCircle size={13} /> : <Copy size={13} />}
                </button>
              </div>
            </div>

            <div style={{ fontSize:12, color:'var(--text-muted)', background:'rgba(99,102,241,0.06)', border:'1px solid var(--border-subtle)', borderRadius:'var(--radius-sm)', padding:'10px 14px' }}>
              <strong>Next step:</strong> Go to your Supabase dashboard → Authentication → Users → click your user → Edit → set <code style={{ fontFamily:'JetBrains Mono' }}>app_metadata</code> to <code style={{ fontFamily:'JetBrains Mono' }}>{`{"role":"manager"}`}</code>
            </div>

            <button className="btn-primary" style={{ padding:'12px' }} onClick={() => onDone(result.tenant_id, result.access_url)}>
              Continue to Login →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Auth Modal ────────────────────────────────────────────────────────────────
function AuthModal({ onDone }: { onDone: (result: LoginResult) => void }) {
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showTenant, setShowTenant] = useState(false);

  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!email || !password) { setError('Please enter both email and password.'); return; }
    setLoading(true); setError('');
    try {
      const result = await loginToSupabase(email, password);
      setAuthToken(result.access_token);
      if (typeof window !== 'undefined') {
        localStorage.setItem('uqs_user_role', result.role);
        localStorage.setItem('uqs_user_email', result.email);
        localStorage.setItem('uqs_display_name', result.display_name);
        localStorage.setItem('uqs_is_admin', String(result.is_admin));
      }
      onDone(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid credentials or backend offline.');
    } finally { setLoading(false); }
  };

  if (showTenant) {
    return (
      <TenantRegisterModal
        onDone={() => setShowTenant(false)}
        onBack={() => setShowTenant(false)}
      />
    );
  }

  return (
    <div style={{ position:'fixed', inset:0, zIndex:100, background:'rgba(0,0,0,0.65)', backdropFilter:'blur(28px)', display:'flex', alignItems:'center', justifyContent:'center', padding:24 }}>
      <div className="glass-bright fade-in-up" style={{ borderRadius:'var(--radius-xl)', padding:'48px 44px', maxWidth:420, width:'100%', boxShadow:'var(--shadow-md)' }}>

        {/* Logo */}
        <div style={{ textAlign:'center', marginBottom:36 }}>
          <div style={{ width:68, height:68, borderRadius:22, background:'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))', display:'flex', alignItems:'center', justifyContent:'center', margin:'0 auto 20px', boxShadow:'var(--glow-primary)' }}>
            <Sparkles size={32} color="#fff" />
          </div>
          <h1 className="gradient-text" style={{ fontSize:26, fontWeight:800, marginBottom:8, letterSpacing:'-0.03em' }}>UQS Platform</h1>
          <p style={{ fontSize:13, color:'var(--text-muted)' }}>Universal Query Solver — AI-Driven BI</p>
        </div>

        <form onSubmit={handleLogin} style={{ display:'flex', flexDirection:'column', gap:16 }}>
          {/* Email */}
          <div>
            <label style={{ fontSize:12, color:'var(--text-secondary)', display:'block', marginBottom:6, fontWeight:500 }}>Email Address</label>
            <div style={{ position:'relative' }}>
              <Mail size={15} style={{ position:'absolute', left:13, top:'50%', transform:'translateY(-50%)', color:'var(--text-muted)' }} />
              <input type="text" placeholder="you@company.com" value={email} onChange={e => setEmail(e.target.value)} autoFocus className="uqs-input" style={{ width:'100%', padding:'11px 14px 11px 40px' }} />
            </div>
          </div>

          {/* Password */}
          <div>
            <label style={{ fontSize:12, color:'var(--text-secondary)', display:'block', marginBottom:6, fontWeight:500 }}>Password</label>
            <div style={{ position:'relative' }}>
              <Key size={15} style={{ position:'absolute', left:13, top:'50%', transform:'translateY(-50%)', color:'var(--text-muted)' }} />
              <input type={showPassword ? 'text' : 'password'} placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} className="uqs-input" style={{ width:'100%', padding:'11px 42px 11px 40px' }} />
              <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ position:'absolute', right:13, top:'50%', transform:'translateY(-50%)', background:'none', border:'none', cursor:'pointer', color:'var(--text-muted)', padding:0, display:'flex' }}>
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {error && (
            <div style={{ padding:'10px 14px', background:'rgba(244,63,94,0.1)', border:'1px solid rgba(244,63,94,0.25)', borderRadius:'var(--radius-sm)', fontSize:13, color:'var(--accent-rose)', display:'flex', gap:8, alignItems:'center' }}>
              <AlertCircle size={14} style={{ flexShrink:0 }} />{error}
            </div>
          )}

          <button type="submit" className="btn-primary" style={{ width:'100%', padding:'14px', fontSize:15, marginTop:4 }} disabled={loading}>
            {loading ? <span style={{ display:'flex', alignItems:'center', justifyContent:'center', gap:8 }}><Loader2 size={17} className="animate-spin" />Authenticating…</span> : 'Sign In →'}
          </button>
        </form>

        <div style={{ marginTop:20, paddingTop:20, borderTop:'1px solid var(--border-subtle)', textAlign:'center' }}>
          <p style={{ fontSize:12, color:'var(--text-muted)', marginBottom:12 }}>New organization? Register your Supabase project</p>
          <button className="btn-ghost" style={{ width:'100%', padding:'10px', fontSize:13, display:'flex', alignItems:'center', justifyContent:'center', gap:8 }} onClick={() => setShowTenant(true)}>
            <Building2 size={14} /> Register Organization
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Cache Report Card ─────────────────────────────────────────────────────────
function CacheReportCard({ summary, onExpand }: { summary: CacheSummary; onExpand: (gran: string, period: string) => void }) {
  const cfg = GRAN_CONFIG[summary.granularity] || GRAN_CONFIG.daily;
  return (
    <div className="cache-report-card fade-in-up">
      <div className="cache-report-header" onClick={() => onExpand(summary.granularity, summary.period)}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div style={{ width:32, height:32, borderRadius:10, background:`${cfg.color}15`, border:`1px solid ${cfg.color}30`, display:'flex', alignItems:'center', justifyContent:'center' }}>
            <span style={{ color: cfg.color }}>{cfg.icon}</span>
          </div>
          <div>
            <div style={{ fontSize:12, fontWeight:600, color:'var(--text-primary)' }}>{cfg.label} Report</div>
            <div style={{ fontSize:11, color:'var(--text-muted)' }}>{summary.coverage}</div>
          </div>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:11, color:'var(--text-muted)' }}>{summary.metrics.length} metrics</span>
          <ChevronDown size={13} color="var(--text-muted)" />
        </div>
      </div>
      <div style={{ padding:'12px 18px', borderTop:'1px solid var(--border-subtle)' }}>
        <p style={{ fontSize:12, color:'var(--text-secondary)', lineHeight:1.65, marginBottom:10 }}>
          {summary.summary.slice(0, 200)}{summary.summary.length > 200 ? '…' : ''}
        </p>
        <div style={{ display:'flex', flexWrap:'wrap', gap:5 }}>
          {summary.metrics.slice(0, 6).map(m => (
            <span key={m} style={{ fontSize:10, padding:'2px 8px', borderRadius:99, background:'rgba(99,102,241,0.08)', color:'var(--text-muted)', border:'1px solid rgba(99,102,241,0.12)' }}>
              {m.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Report Detail Modal ───────────────────────────────────────────────────────
function ReportDetailModal({ detail, onClose }: { detail: CachedReportDetail; onClose: () => void }) {
  const cfg = GRAN_CONFIG[detail.granularity] || GRAN_CONFIG.daily;
  return (
    <div style={{ position:'fixed', inset:0, zIndex:150, background:'rgba(0,0,0,0.6)', backdropFilter:'blur(16px)', display:'flex', alignItems:'center', justifyContent:'center', padding:24 }} onClick={onClose}>
      <div className="glass-bright fade-in-up" style={{ borderRadius:'var(--radius-xl)', padding:32, maxWidth:680, width:'100%', maxHeight:'85vh', overflow:'auto' }} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:24 }}>
          <div style={{ display:'flex', alignItems:'center', gap:12 }}>
            <div style={{ width:40, height:40, borderRadius:12, background:`${cfg.color}18`, border:`1px solid ${cfg.color}33`, display:'flex', alignItems:'center', justifyContent:'center' }}>
              <span style={{ color:cfg.color }}>{cfg.icon}</span>
            </div>
            <div>
              <div style={{ fontSize:15, fontWeight:700 }}>{cfg.label} Intelligence Report</div>
              <div style={{ fontSize:11, color:'var(--text-muted)' }}>{detail.coverage} · {detail.generated_at.slice(0,16).replace('T',' ')} UTC</div>
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost" style={{ padding:'6px 12px', fontSize:12 }}>Close ✕</button>
        </div>

        {/* Narrative */}
        <div style={{ background:'var(--bg-elevated)', borderRadius:'var(--radius-md)', padding:'16px 18px', marginBottom:20, border:'1px solid var(--border-subtle)' }}>
          <div className="section-label" style={{ marginBottom:8 }}>Executive Summary</div>
          <p style={{ fontSize:13, color:'var(--text-secondary)', lineHeight:1.75 }}>{detail.summary_narrative}</p>
        </div>

        {/* Key Metrics */}
        {detail.key_metrics.length > 0 && (
          <div style={{ marginBottom:20 }}>
            <div className="section-label" style={{ marginBottom:12 }}>Key Metrics</div>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(160px, 1fr))', gap:10 }}>
              {detail.key_metrics.map((m, i) => (
                <div key={i} className="stat-card">
                  <div style={{ fontSize:10, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.05em', marginBottom:4 }}>{m.label}</div>
                  <div style={{ fontSize:18, fontWeight:700, color:'var(--text-primary)' }}>{m.value}</div>
                  {m.change && <div style={{ fontSize:11, color:'var(--accent-emerald)', marginTop:2 }}>{m.change}</div>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Trend Analysis */}
        {Object.keys(detail.trend_analysis).length > 0 && (
          <div style={{ marginBottom:20 }}>
            <div className="section-label" style={{ marginBottom:12 }}>Trend Analysis</div>
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {Object.entries(detail.trend_analysis).map(([metric, tr]) => (
                <div key={metric} style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 14px', background:'var(--bg-elevated)', borderRadius:'var(--radius-sm)', border:'1px solid var(--border-subtle)' }}>
                  <div style={{ flexShrink:0 }}>
                    {tr.direction === 'up'     && <ArrowUpRight size={16} color="var(--accent-emerald)" />}
                    {tr.direction === 'down'   && <ArrowDownRight size={16} color="var(--accent-rose)" />}
                    {tr.direction === 'stable' && <Minus size={16} color="var(--accent-amber)" />}
                  </div>
                  <div>
                    <div style={{ fontSize:12, fontWeight:600, color:'var(--text-primary)' }}>{metric.replace(/_/g,' ')}</div>
                    {tr.insight && <div style={{ fontSize:11, color:'var(--text-muted)' }}>{tr.insight}</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Anomaly Flags */}
        {detail.anomaly_flags.length > 0 && (
          <div>
            <div className="section-label" style={{ marginBottom:12 }}>Anomaly Flags</div>
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {detail.anomaly_flags.map((a, i) => (
                <div key={i} className={`severity-${a.severity}`} style={{ display:'flex', gap:10, padding:'10px 14px', borderRadius:'var(--radius-sm)', alignItems:'flex-start' }}>
                  <AlertTriangle size={14} style={{ flexShrink:0, marginTop:2 }} />
                  <div>
                    <div style={{ fontSize:12, fontWeight:600 }}>{a.metric}</div>
                    <div style={{ fontSize:11, marginTop:2, opacity:0.8 }}>{a.description}</div>
                  </div>
                  <span style={{ marginLeft:'auto', fontSize:10, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.05em', flexShrink:0 }}>{a.severity}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Cache Intelligence Tab ────────────────────────────────────────────────────
function CacheTab({ cacheData, userRole, onRefresh }: {
  cacheData: CacheStatus | null;
  userRole: string;
  onRefresh: () => void;
}) {
  const [generating, setGenerating] = useState<string | null>(null);
  const [expandedReport, setExpandedReport] = useState<CachedReportDetail | null>(null);
  const [genError, setGenError] = useState('');
  const isAdmin = ADMIN_ROLES.has(userRole);

  const handleGenerate = async (gran: string) => {
    setGenerating(gran); setGenError('');
    try {
      await generateCacheReport(gran);
      onRefresh();
    } catch (err) {
      setGenError(err instanceof Error ? err.message : 'Generation failed');
    } finally { setGenerating(null); }
  };

  const handleExpand = async (gran: string, period: string) => {
    try {
      const { getCacheReportDetail } = await import('@/lib/api');
      const detail = await getCacheReportDetail(gran, period);
      setExpandedReport(detail);
    } catch { /* silently fail */ }
  };

  const reports = cacheData?.reports || {};
  const summaries = cacheData?.summaries || [];
  const totalReports = Object.values(reports).reduce((a, b) => a + b.length, 0);

  return (
    <div style={{ flex:1, padding:'28px 32px', overflow:'auto' }}>
      {expandedReport && <ReportDetailModal detail={expandedReport} onClose={() => setExpandedReport(null)} />}

      <div style={{ maxWidth:860 }}>
        {/* Header */}
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:24 }}>
          <div>
            <h2 style={{ fontSize:18, fontWeight:700, marginBottom:4 }}>Cache Intelligence Layer</h2>
            <p style={{ fontSize:13, color:'var(--text-muted)' }}>
              {totalReports} reports cached · 4-granularity FIFO (10 per level)
            </p>
          </div>
          <button onClick={onRefresh} className="btn-ghost" style={{ padding:'8px 14px', fontSize:12, display:'flex', alignItems:'center', gap:6 }}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>

        {/* Granularity Stats */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:12, marginBottom:28 }}>
          {Object.entries(GRAN_CONFIG).map(([gran, cfg]) => {
            const count = reports[gran]?.length ?? 0;
            const pct = (count / 10) * 100;
            return (
              <div key={gran} className="stat-card" style={{ position:'relative', overflow:'hidden' }}>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:12 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:7 }}>
                    <span style={{ color: cfg.color }}>{cfg.icon}</span>
                    <span style={{ fontSize:12, fontWeight:600, color:'var(--text-secondary)' }}>{cfg.label}</span>
                  </div>
                  <span style={{ fontSize:12, color: count > 0 ? cfg.color : 'var(--text-muted)', fontWeight:700 }}>{count}/10</span>
                </div>
                <div className="progress-bar-track" style={{ marginBottom:12 }}>
                  <div className="progress-bar-fill" style={{ width:`${pct}%`, background:cfg.color }} />
                </div>
                {isAdmin && (
                  <button
                    onClick={() => handleGenerate(gran)}
                    disabled={!!generating}
                    className="btn-ghost"
                    style={{ width:'100%', padding:'7px', fontSize:11, display:'flex', alignItems:'center', justifyContent:'center', gap:5, borderColor:`${cfg.color}40`, color: cfg.color }}
                  >
                    {generating === gran ? <><Loader2 size={11} className="animate-spin" /> Generating…</> : <><PlayCircle size={11} /> Generate Now</>}
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {genError && (
          <div style={{ marginBottom:16, padding:'10px 14px', background:'rgba(244,63,94,0.1)', border:'1px solid rgba(244,63,94,0.25)', borderRadius:'var(--radius-sm)', fontSize:12, color:'var(--accent-rose)', display:'flex', gap:8, alignItems:'center' }}>
            <AlertCircle size={13} />{genError}
          </div>
        )}

        {!isAdmin && (
          <div style={{ marginBottom:16, padding:'10px 14px', background:'rgba(99,102,241,0.07)', border:'1px solid var(--border-subtle)', borderRadius:'var(--radius-sm)', fontSize:12, color:'var(--text-muted)', display:'flex', gap:8, alignItems:'center' }}>
            <Info size={13} />Only manager or admin roles can manually generate reports.
          </div>
        )}

        {/* Report Cards */}
        {summaries.length > 0 ? (
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            <div className="section-label" style={{ marginBottom:4 }}>Cached Reports — click to expand full detail</div>
            {summaries.map((s, i) => (
              <CacheReportCard key={i} summary={s} onExpand={handleExpand} />
            ))}
          </div>
        ) : (
          <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', padding:'60px 20px', textAlign:'center', background:'var(--bg-surface)', borderRadius:'var(--radius-lg)', border:'1px solid var(--border-subtle)' }}>
            <div style={{ width:56, height:56, borderRadius:20, background:'rgba(245,158,11,0.1)', border:'1px solid rgba(245,158,11,0.25)', display:'flex', alignItems:'center', justifyContent:'center', marginBottom:16 }}>
              <Zap size={24} color="var(--accent-amber)" />
            </div>
            <h3 style={{ fontSize:15, fontWeight:600, marginBottom:8 }}>No Cached Reports Yet</h3>
            <p style={{ fontSize:12, color:'var(--text-muted)', lineHeight:1.6, maxWidth:320, marginBottom:20 }}>
              Reports are generated automatically by scheduled cron jobs. {isAdmin ? 'Use the Generate Now buttons above to create your first reports immediately.' : 'Ask your admin to generate the first reports.'}
            </p>
            {isAdmin && (
              <button onClick={() => handleGenerate('daily')} className="btn-primary" style={{ padding:'10px 24px', fontSize:13 }}>
                <PlayCircle size={14} style={{ marginRight:7, display:'inline' }} />Generate Daily Report Now
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Admin Tab ─────────────────────────────────────────────────────────────────
function AdminTab({ userRole }: { userRole: string }) {
  const [flushGran, setFlushGran] = useState('');
  const [flushing, setFlushing] = useState(false);
  const [flushMsg, setFlushMsg] = useState('');

  const handleFlush = async () => {
    if (!confirm(`Flush ${flushGran || 'ALL'} cache? This cannot be undone.`)) return;
    setFlushing(true); setFlushMsg('');
    try {
      const res = await flushCache(flushGran || undefined) as any;
      setFlushMsg(`✅ Flushed: ${JSON.stringify(res.flushed)}`);
    } catch (err) {
      setFlushMsg(`❌ ${err instanceof Error ? err.message : 'Failed'}`);
    } finally { setFlushing(false); }
  };

  return (
    <div style={{ flex:1, padding:'28px 32px', overflow:'auto' }}>
      <div style={{ maxWidth:720 }}>
        <h2 style={{ fontSize:18, fontWeight:700, marginBottom:4 }}>Admin Control Center</h2>
        <p style={{ fontSize:13, color:'var(--text-muted)', marginBottom:28 }}>System management and operations — {userRole} access</p>

        {/* Cache management */}
        <div className="glass-card" style={{ padding:'20px 22px', marginBottom:16 }}>
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:16 }}>
            <Zap size={16} color="var(--accent-amber)" />
            <span style={{ fontSize:14, fontWeight:600 }}>Cache Management</span>
          </div>
          <div style={{ display:'flex', gap:10, alignItems:'center' }}>
            <select value={flushGran} onChange={e => setFlushGran(e.target.value)} className="uqs-input" style={{ padding:'8px 12px', flex:1, cursor:'pointer' }}>
              <option value="">All granularities</option>
              <option value="hourly">Hourly only</option>
              <option value="daily">Daily only</option>
              <option value="weekly">Weekly only</option>
              <option value="monthly">Monthly only</option>
            </select>
            <button onClick={handleFlush} disabled={flushing} className="btn-danger" style={{ padding:'8px 16px', flexShrink:0 }}>
              {flushing ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              {' '}Flush Cache
            </button>
          </div>
          {flushMsg && <div style={{ marginTop:10, fontSize:12, color:'var(--text-secondary)', fontFamily:'JetBrains Mono' }}>{flushMsg}</div>}
        </div>

        {/* Platform info */}
        <div className="glass-card" style={{ padding:'20px 22px' }}>
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:16 }}>
            <Info size={16} color="var(--accent-cyan)" />
            <span style={{ fontSize:14, fontWeight:600 }}>Role Information</span>
          </div>
          <div style={{ fontSize:13, color:'var(--text-secondary)', lineHeight:1.7 }}>
            <p>You are signed in as <strong style={{ color:'var(--text-primary)' }}>{userRole}</strong>.</p>
            <p style={{ marginTop:6 }}>
              {userRole === 'manager' && '✅ Manager role has full admin access: cache generation, RBAC invalidation, model registry. Destructive ops (rollback/retrain) require strict admin.'}
              {userRole === 'admin' && '✅ Admin role has full unrestricted access to all operations.'}
            </p>
          </div>
        </div>
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
  const [userInfo, setUserInfo] = useState<LoginResult | null>(null);

  const [health, setHealth] = useState<{ status: string; llm_model: string; database: string } | null>(null);
  const [healthStatus, setHealthStatus] = useState<'loading' | 'connected' | 'error'>('loading');
  const [cacheData, setCacheData] = useState<CacheStatus | null>(null);
  const [modelData, setModelData] = useState<Record<string, ModelRegistryEntry> | null>(null);
  const [rbacRoles, setRbacRoles] = useState<{ role: string; desc: string; views: string[] }[] | null>(null);
  const [uploadedDocs, setUploadedDocs] = useState<UploadedDocument[]>([]);
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');

  // Theme
  useEffect(() => {
    const saved = localStorage.getItem('uqs-theme') || 'dark';
    setTheme(saved as 'light' | 'dark');
  }, []);
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('uqs-theme', theme);
  }, [theme]);

  // Check auth on mount — restore user info from localStorage
  useEffect(() => {
    const token = getAuthToken();
    if (token) {
      const role = localStorage.getItem('uqs_user_role') || 'viewer';
      const email = localStorage.getItem('uqs_user_email') || '';
      const display_name = localStorage.getItem('uqs_display_name') || email;
      const is_admin = localStorage.getItem('uqs_is_admin') === 'true';
      setUserInfo({ access_token: token, token_type: 'bearer', role, email, display_name, is_admin });
      setIsAuthed(true);
    }
    setCheckingAuth(false);
  }, []);

  // Poll health
  useEffect(() => {
    if (!isAuthed) return;
    const check = async () => {
      try {
        const h = await fetchHealth();
        setHealth(h);
        setHealthStatus(h.status === 'healthy' ? 'connected' : 'error');
      } catch { setHealthStatus('error'); }
    };
    check();
    const iv = setInterval(check, 30000);
    return () => clearInterval(iv);
  }, [isAuthed]);

  const loadCacheData = useCallback(async () => {
    try { setCacheData(await fetchCacheStatus()); } catch {}
  }, []);
  const loadModelData = useCallback(async () => {
    try { setModelData(await fetchModelRegistry()); } catch {}
  }, []);
  const loadRBACRoles = useCallback(async () => {
    try { const d = await fetchRBACRoles(); setRbacRoles(d.roles); } catch {}
  }, []);

  useEffect(() => {
    if (!isAuthed) return;
    if (activeTab === 'cache') loadCacheData();
    if (activeTab === 'models') loadModelData();
    if (activeTab === 'rbac') loadRBACRoles();
  }, [activeTab, isAuthed, loadCacheData, loadModelData, loadRBACRoles]);

  const handleLogout = () => { clearAuthToken(); setIsAuthed(false); setUserInfo(null); };
  const userRole = userInfo?.role || 'viewer';
  const isAdmin = ADMIN_ROLES.has(userRole);

  const visibleNav = NAV_ITEMS.filter(item => !item.adminOnly || isAdmin);

  if (checkingAuth) return null;

  return (
    <>
      {/* Ambient */}
      <div className="ambient-bg">
        <div className="ambient-blob ambient-blob-1" />
        <div className="ambient-blob ambient-blob-2" />
        <div className="ambient-blob ambient-blob-3" />
      </div>

      {!isAuthed && (
        <AuthModal onDone={(result) => { setUserInfo(result); setIsAuthed(true); }} />
      )}

      <div style={{ display:'flex', height:'100vh', position:'relative', zIndex:1, overflow:'hidden' }}>

        {/* ── Sidebar ──────────────────────────────────────────────────────── */}
        <div className="layout-sidebar" style={{ width: sidebarOpen ? 224 : 64, flexShrink:0, display:'flex', flexDirection:'column', overflow:'hidden' }}>

          {/* Logo */}
          <div style={{ padding: sidebarOpen ? '18px 16px 14px' : '18px 14px 14px', borderBottom:'1px solid var(--border-subtle)', display:'flex', alignItems:'center', gap:10, justifyContent: sidebarOpen ? 'flex-start' : 'center' }}>
            <div style={{ width:34, height:34, borderRadius:10, flexShrink:0, background:'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))', display:'flex', alignItems:'center', justifyContent:'center', boxShadow:'var(--glow-sm)' }}>
              <Sparkles size={17} color="white" />
            </div>
            {sidebarOpen && (
              <div>
                <div style={{ fontSize:14, fontWeight:800, lineHeight:1.1, letterSpacing:'-0.02em' }}>UQS</div>
                <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:1 }}>AI BI Platform</div>
              </div>
            )}
          </div>

          {/* User info */}
          {sidebarOpen && isAuthed && userInfo && (
            <div style={{ padding:'12px 16px', borderBottom:'1px solid var(--border-subtle)' }}>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <div style={{ width:30, height:30, borderRadius:'50%', background:'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0, fontSize:13, fontWeight:700, color:'white' }}>
                  {(userInfo.display_name || userInfo.email || '?')[0].toUpperCase()}
                </div>
                <div style={{ minWidth:0 }}>
                  <div style={{ fontSize:12, fontWeight:600, color:'var(--text-primary)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{userInfo.display_name || userInfo.email}</div>
                  <span className={`badge ${getRoleBadgeClass(userRole)}`} style={{ fontSize:9, marginTop:2, display:'inline-flex' }}>{userRole}</span>
                </div>
              </div>
            </div>
          )}

          {/* Nav */}
          <nav style={{ flex:1, padding:'10px 8px', overflow:'hidden' }}>
            {visibleNav.map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => setActiveTab(id)} className={`sidebar-item ${activeTab===id?'active':''}`} style={{ justifyContent: sidebarOpen ? 'flex-start' : 'center', marginBottom:2 }} title={!sidebarOpen ? label : undefined}>
                <Icon size={16} style={{ flexShrink:0 }} />
                {sidebarOpen && <span>{label}</span>}
              </button>
            ))}
          </nav>

          {/* Health */}
          {sidebarOpen && isAuthed && (
            <div style={{ padding:'10px 16px', borderTop:'1px solid var(--border-subtle)' }}>
              <StatusPill status={healthStatus} model={health?.llm_model} />
            </div>
          )}

          {/* Collapse toggle */}
          <button className="btn-ghost" style={{ margin:'0 8px 12px', padding:'8px', display:'flex', alignItems:'center', justifyContent:'center' }} onClick={() => setSidebarOpen(!sidebarOpen)}>
            {sidebarOpen ? <ChevronLeft size={13} /> : <ChevronRight size={13} />}
          </button>
        </div>

        {/* ── Main Content ──────────────────────────────────────────────────── */}
        <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

          {/* Top bar */}
          <div className="layout-header" style={{ height:54, flexShrink:0, display:'flex', alignItems:'center', justifyContent:'space-between', padding:'0 24px' }}>
            <div>
              <h1 style={{ fontSize:14, fontWeight:700 }}>
                {activeTab==='chat'    && 'Data Query Interface'}
                {activeTab==='cache'   && 'Cache Intelligence'}
                {activeTab==='models'  && 'ML Model Registry'}
                {activeTab==='engines' && 'Engine Architecture'}
                {activeTab==='rbac'    && 'Security & RBAC'}
                {activeTab==='admin'   && 'Admin Control Center'}
              </h1>
              <p style={{ fontSize:11, color:'var(--text-muted)' }}>
                {activeTab==='chat'    && `Session: ${sessionId.slice(0,8)}…`}
                {activeTab==='cache'   && '4-granularity pre-generated smart report cache'}
                {activeTab==='models'  && 'Versioned ML models with auto-promote & rollback'}
                {activeTab==='engines' && '5 specialized AI engines for every query type'}
                {activeTab==='rbac'    && 'Database-level role-based access control'}
                {activeTab==='admin'   && 'System operations (manager + admin)'}
              </p>
            </div>
            <div style={{ display:'flex', gap:6, alignItems:'center' }}>
              {activeTab==='chat' && (
                <button className="btn-ghost" style={{ padding:'5px 11px', fontSize:12, display:'flex', alignItems:'center', gap:5 }} onClick={() => setRightOpen(!rightOpen)}>
                  <Activity size={12} />{rightOpen ? 'Hide' : 'Panel'}
                </button>
              )}
              <button className="btn-icon" onClick={() => setTheme(theme==='dark'?'light':'dark')} title="Toggle Theme">
                {theme==='dark' ? <Sun size={14} /> : <Moon size={14} />}
              </button>
              <div style={{ width:1, height:22, background:'var(--border-subtle)', margin:'0 2px' }} />
              <button className="btn-icon" onClick={handleLogout} title="Log Out">
                <LogOut size={14} />
              </button>
            </div>
          </div>

          {/* Content area */}
          <div style={{ flex:1, display:'flex', overflow:'hidden' }}>

            {/* Chat */}
            {activeTab==='chat' && (
              <>
                <div style={{ flex:1, position:'relative', overflow:'hidden' }}>
                  <ChatInterface sessionId={sessionId} onDocumentUploaded={doc => setUploadedDocs(p => [doc,...p])} />
                </div>
                {rightOpen && (
                  <div className="layout-panel-right" style={{ width:280, flexShrink:0, padding:16, overflow:'auto', display:'flex', flexDirection:'column', gap:14 }}>
                    {uploadedDocs.length > 0 && (
                      <div>
                        <div className="section-label" style={{ marginBottom:8 }}>Indexed Documents</div>
                        {uploadedDocs.map((doc,i) => (
                          <div key={i} style={{ padding:'8px 10px', marginBottom:6, background:'var(--bg-elevated)', border:'1px solid var(--border-subtle)', borderRadius:'var(--radius-sm)' }}>
                            <div style={{ fontSize:12, color:'var(--text-primary)', marginBottom:2 }}>{doc.filename}</div>
                            <div style={{ fontSize:11, color:'var(--text-muted)' }}>{doc.chunks_added} chunks</div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div>
                      <div className="section-label" style={{ marginBottom:8 }}>System Pillars</div>
                      {[
                        { label:'Clarity',  desc:'Plain-English answers',         color:'#818cf8' },
                        { label:'Trust',    desc:'Every response cites its data', color:'#6ee7b7' },
                        { label:'Speed',    desc:'Cache for instant re-queries',  color:'#fcd34d' },
                      ].map(({ label, desc, color }) => (
                        <div key={label} style={{ padding:'8px 10px', marginBottom:6, background:'var(--bg-surface)', borderRadius:'var(--radius-sm)', border:'1px solid var(--border-subtle)', display:'flex', gap:10 }}>
                          <div style={{ width:3, borderRadius:99, background:color, alignSelf:'stretch', minHeight:24, flexShrink:0 }} />
                          <div>
                            <div style={{ fontSize:12, fontWeight:600, color }}>{label}</div>
                            <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:2 }}>{desc}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* Cache */}
            {activeTab==='cache' && (
              <CacheTab cacheData={cacheData} userRole={userRole} onRefresh={loadCacheData} />
            )}

            {/* Models */}
            {activeTab==='models' && (
              <div style={{ flex:1, padding:'28px 32px', overflow:'auto' }}>
                <div style={{ maxWidth:700 }}>
                  {modelData ? (
                    <ModelStatus registry={modelData} />
                  ) : (
                    <div style={{ display:'flex', gap:10, color:'var(--text-muted)', fontSize:13, alignItems:'center' }}>
                      <Loader2 size={15} className="animate-spin" />Loading model registry…
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Engines */}
            {activeTab==='engines' && (
              <div style={{ flex:1, padding:'28px 32px', overflow:'auto' }}>
                <h2 style={{ fontSize:18, fontWeight:700, marginBottom:6 }}>5-Engine AI Architecture</h2>
                <p style={{ fontSize:13, color:'var(--text-muted)', marginBottom:24 }}>Each query is classified and routed to the most appropriate engine automatically</p>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(280px,1fr))', gap:14, maxWidth:900 }}>
                  {ENGINE_CARDS.map(eng => {
                    const Icon = eng.icon;
                    return (
                      <div key={eng.id} className="glass-card" style={{ padding:22, border:`1px solid ${eng.color}22` }}
                        onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.borderColor = `${eng.color}55`; (e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 32px ${eng.color}22`; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.borderColor = `${eng.color}22`; (e.currentTarget as HTMLDivElement).style.boxShadow = ''; }}
                      >
                        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:12 }}>
                          <div style={{ width:40, height:40, borderRadius:12, background:`${eng.color}15`, border:`1px solid ${eng.color}30`, display:'flex', alignItems:'center', justifyContent:'center' }}>
                            <Icon size={18} style={{ color:eng.color }} />
                          </div>
                          <span style={{ fontSize:14, fontWeight:700 }}>{eng.name}</span>
                        </div>
                        <p style={{ fontSize:12, color:'var(--text-muted)', lineHeight:1.65 }}>{eng.desc}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* RBAC */}
            {activeTab==='rbac' && (
              <div style={{ flex:1, padding:'28px 32px', overflow:'auto' }}>
                <div style={{ maxWidth:720 }}>
                  <h2 style={{ fontSize:18, fontWeight:700, marginBottom:4 }}>Security & RBAC</h2>
                  <p style={{ fontSize:13, color:'var(--text-muted)', marginBottom:20 }}>Role-based access control enforced at the database view level</p>

                  <div style={{ padding:'12px 16px', background:'rgba(99,102,241,0.07)', border:'1px solid var(--border-subtle)', borderRadius:'var(--radius-md)', fontSize:12, color:'var(--text-secondary)', lineHeight:1.6, display:'flex', gap:10, marginBottom:20 }}>
                    <Info size={15} style={{ color:'var(--accent-primary)', flexShrink:0, marginTop:1 }} />
                    RBAC is enforced at the <strong>database view level</strong> — the LLM only ever receives the schema for views the current role can access. No role can INSERT, UPDATE, or DELETE.
                  </div>

                  {/* Current user role highlight */}
                  <div style={{ padding:'14px 18px', background:'var(--bg-surface)', border:`2px solid ${userRole==='manager'||userRole==='admin'?'rgba(139,92,246,0.3)':'var(--border-subtle)'}`, borderRadius:'var(--radius-md)', marginBottom:20, display:'flex', alignItems:'center', gap:12 }}>
                    <Shield size={18} color="var(--accent-primary)" />
                    <div>
                      <div style={{ fontSize:13, fontWeight:600 }}>Your Role: <span style={{ color:'var(--accent-primary)' }}>{userRole}</span></div>
                      <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:2 }}>{userInfo?.email}</div>
                    </div>
                    <span className={`badge ${getRoleBadgeClass(userRole)}`} style={{ marginLeft:'auto' }}>{userRole}</span>
                  </div>

                  <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                    {rbacRoles ? (
                      rbacRoles.length > 0 ? rbacRoles.map(({ role, views, desc }) => (
                        <div key={role} className="glass-card" style={{ padding:'16px 18px', border: role===userRole ? '1px solid var(--border-strong)' : '1px solid var(--border-subtle)' }}>
                          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:8 }}>
                            <Shield size={14} style={{ color:'var(--accent-primary)' }} />
                            <span style={{ fontSize:13, fontWeight:700, fontFamily:'JetBrains Mono, monospace', color:'var(--accent-primary)' }}>{role}</span>
                            {role===userRole && <span style={{ fontSize:10, background:'rgba(99,102,241,0.12)', border:'1px solid var(--border-strong)', color:'var(--accent-primary)', padding:'1px 7px', borderRadius:99, fontWeight:600 }}>YOU</span>}
                          </div>
                          <p style={{ fontSize:12, color:'var(--text-muted)', marginBottom:10 }}>{desc}</p>
                          <div style={{ display:'flex', flexWrap:'wrap', gap:5 }}>
                            {views.length > 0 ? views.map(v => (
                              <span key={v} className="source-chip" style={{ fontSize:10 }}>{v}</span>
                            )) : (
                              <span style={{ fontSize:11, color:'var(--text-muted)' }}>(No views assigned)</span>
                            )}
                          </div>
                        </div>
                      )) : (
                        <div style={{ padding:24, textAlign:'center', color:'var(--text-muted)', fontSize:13 }}>
                          No roles found. Run <code style={{ fontFamily:'JetBrains Mono' }}>python -m scripts.init_db</code> to initialize.
                        </div>
                      )
                    ) : (
                      <div style={{ display:'flex', gap:10, color:'var(--text-muted)', fontSize:13, alignItems:'center' }}>
                        <Loader2 size={15} className="animate-spin" />Fetching roles from Supabase…
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Admin */}
            {activeTab==='admin' && isAdmin && (
              <AdminTab userRole={userRole} />
            )}

          </div>
        </div>
      </div>
    </>
  );
}
