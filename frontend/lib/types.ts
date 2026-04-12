// Shared TypeScript types for UQS frontend

export type EngineType = 'sql' | 'analytical' | 'predictive' | 'rag' | 'rag++' | 'cache' | 'classifier';

export type QueryType =
  | 'sql'
  | 'analytical'
  | 'predictive'
  | 'rag'
  | 'rag++'
  | 'cache'
  | 'irrelevant'
  | 'trend_analysis'
  | 'causal_diagnostic'
  | 'comparative'
  | 'what_if'
  | 'time_series'
  | 'decomposition'
  | 'forecast'
  | 'clustering'
  | 'anomaly';

export interface KeyMetric {
  label: string;
  value: string;
  change?: string;
}

export interface ChartData {
  labels?: string[];
  datasets?: Array<{ label: string; data: number[] }>;
  columns?: string[];
  rows?: Record<string, unknown>[];
  predictions?: Prediction[];
}

export interface Prediction {
  entity: string;
  prediction: number | string;
  confidence?: number;
  label?: string;
}

export interface QueryResponse {
  answer: string;
  engine: EngineType;
  query_type: QueryType;
  sources: string[];
  key_metrics: KeyMetric[];
  chart?: ChartData;
  chart_type?: 'bar' | 'line' | 'pie' | 'table' | 'predictions' | 'none';
  from_cache: boolean;
  corrected: boolean;
  latency_ms: number;
  model_version?: number;
  session_id: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  response?: QueryResponse;
  isLoading?: boolean;
  isStreaming?: boolean;
}

export interface UploadedDocument {
  filename: string;
  source_key: string;
  chunks_added: number;
  pages_processed: number;
  uploadedAt: Date;
}

export interface CacheStatus {
  reports: Record<string, string[]>;
  summaries: CacheSummary[];
}

export interface CacheSummary {
  granularity: string;
  period: string;
  coverage: string;
  metrics: string[];
  summary: string;
}

export interface ModelRegistryEntry {
  active_version: number;
  all_versions: number[];
  metrics: Record<string, number>;
  model_type: string;
  trained_at: string;
  features: string[];
}
