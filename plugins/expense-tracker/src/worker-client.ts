import type {
  ExpenseTrackerConfig
} from "./config.js";
import type {
  StructuredExpenseWorkerRequest,
  ReceiptWorkerRequest,
  ExpenseWorkerResponse
} from "./types.js";

export async function postStructuredExpenseCommand(
  config: ExpenseTrackerConfig,
  request: StructuredExpenseWorkerRequest
): Promise<ExpenseWorkerResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.requestTimeoutMs);

  try {
    const response = await fetch(`${config.workerBaseUrl}/v1/expenses/handle-structured`, {
      method: "POST",
      headers: buildHeaders(config),
      body: JSON.stringify(request),
      signal: controller.signal
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Expense worker returned ${response.status}: ${body}`);
    }

    return (await response.json()) as ExpenseWorkerResponse;
  } finally {
    clearTimeout(timeout);
  }
}

export async function postReceiptCommand(
  config: ExpenseTrackerConfig,
  request: ReceiptWorkerRequest
): Promise<ExpenseWorkerResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.requestTimeoutMs);

  try {
    const response = await fetch(`${config.workerBaseUrl}/v1/expenses/receipt`, {
      method: "POST",
      headers: buildHeaders(config),
      body: JSON.stringify(request),
      signal: controller.signal
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Expense worker returned ${response.status}: ${body}`);
    }

    return (await response.json()) as ExpenseWorkerResponse;
  } finally {
    clearTimeout(timeout);
  }
}

function buildHeaders(config: ExpenseTrackerConfig): Record<string, string> {
  const headers: Record<string, string> = {
    "content-type": "application/json"
  };

  if (config.apiToken) {
    headers["x-denkeeper-token"] = config.apiToken;
  }

  return headers;
}
