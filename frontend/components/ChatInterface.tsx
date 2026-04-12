'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Sparkles, Upload, User, Bot, X, ChevronRight, StopCircle } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';
import { streamQuery } from '@/lib/api';
import type { Message, QueryResponse, UploadedDocument } from '@/lib/types';
import ResponseCard from './ResponseCard';
import DocumentUpload from './DocumentUpload';

const EXAMPLE_QUERIES = [
  'Why did sales drop in February?',
  'Show me top 5 customers by revenue',
  'What is the weekly trend in transactions?',
  'Which customers are likely to churn?',
  'Compare North vs South region performance',
  'What makes up total revenue by channel?',
];

interface Props {
  sessionId: string;
  onDocumentUploaded?: (doc: UploadedDocument) => void;
}

// ── Empty state ───────────────────────────────────────────────────────────────
function EmptyState({ onExample }: { onExample: (q: string) => void }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', flex: 1, padding: '40px 24px', gap: 28,
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          width: 72, height: 72, borderRadius: 24,
          background: 'linear-gradient(135deg, rgba(99,102,241,0.25), rgba(139,92,246,0.25))',
          border: '1px solid rgba(99,102,241,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          margin: '0 auto 20px',
          boxShadow: '0 0 40px rgba(99,102,241,0.2)',
        }}>
          <Sparkles size={32} style={{ color: '#818cf8' }} />
        </div>
        <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>Ask anything about your data</h2>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', maxWidth: 400, lineHeight: 1.7 }}>
          Powered by LangGraph — your query is routed intelligently to SQL, Analytics,
          Predictions, or Document engines automatically.
        </p>
      </div>
      <div style={{ width: '100%', maxWidth: 580 }}>
        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12, textAlign: 'center', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Try asking
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {EXAMPLE_QUERIES.map((q) => (
            <button
              key={q}
              onClick={() => onExample(q)}
              style={{
                background: 'rgba(13,13,43,0.6)', border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)', padding: '10px 14px', cursor: 'pointer',
                textAlign: 'left', transition: 'all 0.15s ease',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(99,102,241,0.4)';
                (e.currentTarget as HTMLButtonElement).style.background = 'rgba(99,102,241,0.08)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-subtle)';
                (e.currentTarget as HTMLButtonElement).style.background = 'rgba(13,13,43,0.6)';
              }}
            >
              <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>{q}</span>
              <ChevronRight size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Streaming cursor ──────────────────────────────────────────────────────────
function StreamCursor() {
  return (
    <span style={{
      display: 'inline-block', width: 2, height: '1em',
      background: 'var(--accent-primary)', marginLeft: 2,
      verticalAlign: 'text-bottom',
      animation: 'cursorBlink 0.8s step-end infinite',
    }} />
  );
}

// ── Main ChatInterface ────────────────────────────────────────────────────────
export default function ChatInterface({ sessionId, onDocumentUploaded }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const abortRef = useRef<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
  }, [input]);

  const submit = useCallback(async (query: string) => {
    if (!query.trim() || isStreaming) return;
    const trimmed = query.trim();
    setInput('');
    setIsStreaming(true);
    abortRef.current = false;

    const userMsg: Message = { id: uuidv4(), role: 'user', content: trimmed, timestamp: new Date() };
    const asstId = uuidv4();
    const asstMsg: Message = { id: asstId, role: 'assistant', content: '', timestamp: new Date(), isLoading: true };
    setMessages((prev) => [...prev, userMsg, asstMsg]);

    let streamedText = '';
    let finalMeta: Omit<QueryResponse, 'answer'> | null = null;

    await streamQuery(trimmed, sessionId, {
      onToken: (token) => {
        if (abortRef.current) return;
        streamedText += token;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === asstId
              ? { ...m, content: streamedText, isLoading: false, isStreaming: true }
              : m
          )
        );
      },
      onMetadata: (meta) => {
        finalMeta = meta;
      },
      onDone: () => {
        const fullResponse: QueryResponse = {
          answer: streamedText,
          ...finalMeta,
        } as QueryResponse;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === asstId
              ? { ...m, content: streamedText, response: fullResponse, isLoading: false, isStreaming: false }
              : m
          )
        );
        setIsStreaming(false);
      },
      onError: (err) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === asstId
              ? {
                  ...m,
                  content: `Error: ${err}`,
                  isLoading: false,
                  isStreaming: false,
                  response: {
                    answer: `Error: ${err}`,
                    engine: 'classifier' as const,
                    query_type: 'irrelevant' as const,
                    sources: [], key_metrics: [],
                    from_cache: false, corrected: false,
                    latency_ms: 0, session_id: sessionId,
                  },
                }
              : m
          )
        );
        setIsStreaming(false);
      },
    });
  }, [isStreaming, sessionId]);

  const stopStreaming = () => {
    abortRef.current = true;
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((m) =>
        m.isStreaming ? { ...m, isStreaming: false } : m
      )
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0', scrollbarWidth: 'thin', scrollbarColor: 'var(--bg-elevated) transparent' }}>
        {messages.length === 0 ? (
          <EmptyState onExample={(q) => { setInput(q); textareaRef.current?.focus(); }} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '8px 0 90px' }}>
            {messages.map((msg) => (
              <div
                key={msg.id}
                className="fade-in-up"
                style={{
                  display: 'flex',
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                  alignItems: 'flex-start', gap: 10, padding: '6px 20px',
                }}
              >
                {/* Avatar */}
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                  background: msg.role === 'user'
                    ? 'linear-gradient(135deg, #6366f1, #8b5cf6)'
                    : 'rgba(99,102,241,0.12)',
                  border: '1px solid rgba(99,102,241,0.25)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {msg.role === 'user'
                    ? <User size={14} style={{ color: 'white' }} />
                    : <Bot size={14} style={{ color: '#818cf8' }} />}
                </div>

                {/* Bubble */}
                <div
                  className={msg.role === 'user' ? 'msg-user' : 'msg-assistant'}
                  style={{ maxWidth: '82%', padding: '12px 16px' }}
                >
                  {msg.isLoading ? (
                    <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                      <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 4 }}>
                        Thinking via LangGraph…
                      </span>
                    </div>
                  ) : msg.isStreaming ? (
                    // While streaming — show only text + cursor, no ResponseCard yet
                    <div style={{ fontSize: 14, lineHeight: 1.75, color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                      {msg.content}
                      <StreamCursor />
                    </div>
                  ) : msg.response ? (
                    <ResponseCard response={msg.response} />
                  ) : (
                    <span style={{ fontSize: 14, lineHeight: 1.75 }}>{msg.content}</span>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Upload panel */}
      {showUpload && (
        <div style={{
          position: 'absolute', bottom: 78, left: 20, right: 20, zIndex: 10,
          background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)', padding: 16,
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Upload Document for RAG</span>
            <button className="btn-ghost" style={{ padding: '4px 8px' }} onClick={() => setShowUpload(false)}>
              <X size={14} />
            </button>
          </div>
          <DocumentUpload
            sessionId={sessionId}
            onUploaded={(doc) => { onDocumentUploaded?.(doc); setShowUpload(false); }}
          />
        </div>
      )}

      {/* Input bar */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0, padding: '10px 16px',
        background: 'linear-gradient(to top, var(--bg-base) 75%, transparent)',
      }}>
        <div style={{
          display: 'flex', alignItems: 'flex-end', gap: 8,
          background: 'rgba(13,13,43,0.92)', border: '1.5px solid var(--border-subtle)',
          borderRadius: 'var(--radius-xl)', padding: '8px 8px 8px 14px',
          boxShadow: '0 4px 24px rgba(0,0,0,0.35)', backdropFilter: 'blur(20px)',
          transition: 'border-color 0.2s ease',
        }}>
          <button
            className="btn-ghost"
            style={{ padding: 8, borderRadius: '50%', border: 'none', flexShrink: 0 }}
            onClick={() => setShowUpload(!showUpload)}
            title="Upload document for RAG"
          >
            <Upload size={16} style={{ color: showUpload ? 'var(--accent-primary)' : 'var(--text-muted)' }} />
          </button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(input); }
            }}
            placeholder="Ask anything about your data… (Shift+Enter for new line)"
            disabled={isStreaming}
            rows={1}
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none',
              resize: 'none', color: 'var(--text-primary)', fontSize: 14,
              lineHeight: 1.6, fontFamily: 'Inter, sans-serif',
              paddingTop: 6, paddingBottom: 6, maxHeight: 160, overflowY: 'auto',
            }}
          />

          {isStreaming ? (
            <button
              className="btn-ghost"
              style={{ width: 40, height: 40, borderRadius: '50%', border: '1px solid var(--accent-rose)', padding: 0, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              onClick={stopStreaming}
              title="Stop generation"
            >
              <StopCircle size={16} style={{ color: 'var(--accent-rose)' }} />
            </button>
          ) : (
            <button
              className="btn-primary"
              style={{ width: 40, height: 40, borderRadius: '50%', padding: 0, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              disabled={!input.trim()}
              onClick={() => submit(input)}
            >
              <Send size={15} />
            </button>
          )}
        </div>

        <p style={{ textAlign: 'center', marginTop: 5, fontSize: 10, color: 'var(--text-muted)' }}>
          LangGraph routes to SQL · Analytical · Predictive · RAG · RAG++ automatically
        </p>
      </div>

      {/* Cursor blink animation */}
      <style>{`
        @keyframes cursorBlink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
      `}</style>
    </div>
  );
}
