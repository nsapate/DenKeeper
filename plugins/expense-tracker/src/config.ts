export interface ExpenseTrackerConfig {
  workerBaseUrl: string;
  apiToken: string | null;
  defaultScope: string;
  requestTimeoutMs: number;
}

interface PluginConfigShape {
  workerBaseUrl?: string;
  apiToken?: string;
  defaultScope?: string;
  requestTimeoutMs?: number;
}

interface RuntimeApiShape {
  config?: {
    plugins?: {
      entries?: Record<
        string,
        {
          config?: PluginConfigShape;
        }
      >;
    };
  };
}

export function loadExpenseTrackerConfig(api: RuntimeApiShape): ExpenseTrackerConfig {
  const raw = api.config?.plugins?.entries?.["expense-tracker"]?.config ?? {};

  return {
    workerBaseUrl: raw.workerBaseUrl?.trim() || "http://127.0.0.1:8765",
    apiToken: raw.apiToken?.trim() || null,
    defaultScope: raw.defaultScope?.trim() || "the-den",
    requestTimeoutMs: raw.requestTimeoutMs ?? 5000
  };
}
