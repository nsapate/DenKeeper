import { Type } from "@sinclair/typebox";

import { loadExpenseTrackerConfig } from "./src/config.js";
import { postReceiptCommand, postStructuredExpenseCommand } from "./src/worker-client.js";
import type {
  ExpenseAction,
  ExpenseTimeframe,
  ReceiptWorkerRequest,
  StructuredExpenseWorkerRequest
} from "./src/types.js";

interface ExpenseToolParams {
  action: ExpenseAction;
  scope?: string;
  actorName?: string;
  actorId?: string;
  amount?: string;
  merchant?: string;
  category?: string;
  timeframe?: ExpenseTimeframe;
  itemName?: string;
  rawText?: string;
}

interface ReceiptItemParams {
  name: string;
  lineTotal: string;
  quantity?: number;
  unit?: string;
  unitPrice?: string;
}

interface ReceiptToolParams {
  merchant: string;
  items: ReceiptItemParams[];
  rawText?: string;
  scope?: string;
  actorName?: string;
  actorId?: string;
  category?: string;
  receiptTotal?: string;
  purchasedAt?: string;
}

interface PluginApiShape {
  registerTool(tool: {
    name: string;
    description: string;
    parameters: unknown;
    execute(id: string, params: unknown): Promise<{
      content: Array<{
        type: "text";
        text: string;
      }>;
    }>;
  }): void;
  on?: (
    hookName:
      | "before_prompt_build"
      | "tool_result_persist"
      | "before_message_write"
      | "message_sending",
    handler: (event: any, ctx: any) => any
  ) => void;
  config?: {
    plugins?: {
      entries?: Record<
        string,
        {
          config?: {
            workerBaseUrl?: string;
            apiToken?: string;
            defaultScope?: string;
            requestTimeoutMs?: number;
          };
        }
      >;
    };
  };
}

const EXPENSE_ACTIONS = [
  "add_expense",
  "change_last_category",
  "change_last_receipt_item_category",
  "delete_last",
  "delete_last_receipt",
  "undo_last",
  "list_expenses",
  "total",
  "category_breakdown",
  "category_item_breakdown",
  "item_total",
  "item_presence",
  "list_categories"
] as const satisfies readonly ExpenseAction[];

const EXPENSE_CATEGORIES = [
  "Mortgage",
  "Utilities",
  "Groceries",
  "Jambra",
  "Eating Out",
  "Shopping",
  "Baby",
  "Transport",
  "Home Maintenance",
  "Other"
] as const;

const EXPENSE_TIMEFRAMES = [
  "today",
  "yesterday",
  "this week",
  "last week",
  "this month",
  "last month"
] as const satisfies readonly ExpenseTimeframe[];

const EXPENSE_INTENT_PATTERN =
  /\b(expense|expenses|spent|spend|total|totals|receipt|receipts|grocery|groceries|jambra|gas|transport|baby|mortgage|utilities|shopping|takeout|take out|eating out|home maintenance|category|categories|delete|undo|itemized|milk|breakdown|buy|bought)\b/i;
const TOOL_REPLY_TTL_MS = 60_000;
const TOOL_REPLY_PREFIX_RE = /^\s*(\[\[[^\]]+\]\]\s*)/;
const TOOL_NAMES_WITH_EXACT_REPLY = new Set(["denkeeper_expense", "denkeeper_receipt"]);
const pendingToolReplies = new Map<string, { text: string; createdAt: number }>();
const SESSION_KEY_CONVERSATION_RE = /^agent:[^:]+:[^:]+:(?:group|direct|dm):(.+)$/;

const EXPENSE_TOOL_ENFORCEMENT_GUIDANCE = [
  "Expense/receipt safety policy:",
  "- For any expense, category, total, correction, deletion, undo, item-spend, or item-purchase question, call denkeeper_expense before replying.",
  "- For any itemized receipt ingestion request, call denkeeper_receipt before replying.",
  "- For denkeeper_expense, choose a structured action and fill the canonical fields instead of passing the whole request as one raw string.",
  "- Requests containing 'by item', 'itemized', or 'items under <category>' map to category_item_breakdown. Do not use list_expenses for those requests.",
  "- Never answer those requests from memory, prior chat context, or a previous assistant answer in this session.",
  "- Even if the answer appears obvious from earlier messages, you must call the Denkeeper tool again for a fresh ledger-backed result.",
  "- User-facing output must not mention internals (tools, parsers, bugs, or system limitations).",
  "- After denkeeper_expense or denkeeper_receipt returns, your final reply must be exactly that tool text with no extra commentary."
].join("\n");

function isExpenseLike(value: unknown): boolean {
  if (typeof value !== "string") {
    return false;
  }
  return EXPENSE_INTENT_PATTERN.test(value);
}

function cleanupPendingToolReplies(nowMs: number): void {
  for (const [key, pending] of pendingToolReplies) {
    if (nowMs - pending.createdAt > TOOL_REPLY_TTL_MS) {
      pendingToolReplies.delete(key);
    }
  }
}

function resolveConversationIdFromSessionKey(sessionKey: string): string | null {
  const match = sessionKey.match(SESSION_KEY_CONVERSATION_RE);
  const conversationId = match?.[1]?.trim();
  return conversationId && conversationId.length > 0 ? conversationId : null;
}

function resolvePendingKeyFromSessionKey(sessionKey: string): string {
  return resolveConversationIdFromSessionKey(sessionKey) ?? sessionKey;
}

function resolvePendingKeyForOutbound(event: any, ctx: any): string | null {
  if (typeof ctx?.conversationId === "string" && ctx.conversationId.trim().length > 0) {
    return ctx.conversationId.trim();
  }
  if (typeof event?.to === "string" && event.to.trim().length > 0) {
    return event.to.trim();
  }
  return null;
}

function extractTextContent(content: unknown): string | null {
  if (!Array.isArray(content)) {
    return null;
  }

  for (const item of content) {
    if (
      item &&
      typeof item === "object" &&
      (item as { type?: unknown }).type === "text" &&
      typeof (item as { text?: unknown }).text === "string"
    ) {
      const text = (item as { text: string }).text.trim();
      if (text.length > 0) {
        return text;
      }
    }
  }

  return null;
}

function extractPendingToolReplyText(event: any): string | null {
  if (!TOOL_NAMES_WITH_EXACT_REPLY.has(String(event?.toolName ?? ""))) {
    return null;
  }

  const persistedText = extractTextContent(event?.message?.content);
  if (persistedText) {
    return persistedText;
  }

  const toolResultText = extractTextContent(event?.result?.content);
  if (toolResultText) {
    return toolResultText;
  }

  return null;
}

function isAssistantTextMessage(message: any): boolean {
  if (!message || typeof message !== "object") {
    return false;
  }
  if (message.role !== "assistant") {
    return false;
  }
  if (!Array.isArray(message.content)) {
    return false;
  }
  return message.content.some(
    (item: unknown) =>
      item &&
      typeof item === "object" &&
      (item as { type?: unknown }).type === "text" &&
      typeof (item as { text?: unknown }).text === "string"
  );
}

function replaceAssistantTextWithToolReply(message: any, replyText: string): any {
  if (!Array.isArray(message.content)) {
    return message;
  }

  const firstTextItem = message.content.find(
    (item: unknown) =>
      item &&
      typeof item === "object" &&
      (item as { type?: unknown }).type === "text" &&
      typeof (item as { text?: unknown }).text === "string"
  ) as { text: string } | undefined;

  const controlPrefix = firstTextItem?.text.match(TOOL_REPLY_PREFIX_RE)?.[1] ?? "";
  let replaced = false;
  const updatedContent = message.content.map((item: unknown) => {
    if (
      !replaced &&
      item &&
      typeof item === "object" &&
      (item as { type?: unknown }).type === "text"
    ) {
      replaced = true;
      return {
        type: "text",
        text: `${controlPrefix}${replyText}`
      };
    }
    return item;
  });

  return {
    ...message,
    content: updatedContent
  };
}

export default function register(api: PluginApiShape) {
  const config = loadExpenseTrackerConfig(api);

  if (typeof api.on === "function") {
    api.on("before_prompt_build", async (event: { prompt?: string }) => {
      if (!isExpenseLike(event?.prompt)) {
        return;
      }
      return {
        appendSystemContext: EXPENSE_TOOL_ENFORCEMENT_GUIDANCE
      };
    });

    api.on("tool_result_persist", (event: any, ctx: any) => {
      if (typeof ctx?.sessionKey !== "string" || ctx.sessionKey.trim().length === 0) {
        return;
      }

      cleanupPendingToolReplies(Date.now());
      const replyText = extractPendingToolReplyText(event);
      if (!replyText) {
        return;
      }

      pendingToolReplies.set(resolvePendingKeyFromSessionKey(ctx.sessionKey), {
        text: replyText,
        createdAt: Date.now()
      });
    });

    api.on("before_message_write", (event: any, ctx: any) => {
      if (typeof ctx?.sessionKey !== "string" || ctx.sessionKey.trim().length === 0) {
        return;
      }

      cleanupPendingToolReplies(Date.now());
      const pending = pendingToolReplies.get(resolvePendingKeyFromSessionKey(ctx.sessionKey));
      if (!pending) {
        return;
      }

      if (!isAssistantTextMessage(event?.message)) {
        return;
      }

      return {
        message: replaceAssistantTextWithToolReply(event.message, pending.text)
      };
    });

    api.on("message_sending", (event: any, ctx: any) => {
      cleanupPendingToolReplies(Date.now());
      const pendingKey = resolvePendingKeyForOutbound(event, ctx);
      if (!pendingKey) {
        return;
      }

      const pending = pendingToolReplies.get(pendingKey);
      if (!pending) {
        return;
      }

      pendingToolReplies.delete(pendingKey);
      return {
        content: pending.text
      };
    });
  }

  api.registerTool({
    name: "denkeeper_expense",
    description:
      "Use this for every Kyoto expense request. Choose a structured action and fill the matching fields. Supported actions: add_expense, change_last_category, change_last_receipt_item_category, delete_last, delete_last_receipt, undo_last, list_expenses, total, category_breakdown, category_item_breakdown, item_total, item_presence, list_categories. list_expenses is for expense-entry listings only. Use category_item_breakdown for requests like 'break down Baby purchases by item this week' or 'items under Baby category from recent expenses'. Use canonical categories only: Mortgage, Utilities, Groceries, Jambra, Eating Out, Shopping, Baby, Transport, Home Maintenance, Other.",
    parameters: Type.Object({
      action: Type.Union(
        EXPENSE_ACTIONS.map((value) => Type.Literal(value)),
        {
          description:
            "Structured expense action. Example: total for overall/category totals, category_breakdown for grouped spend by category, category_item_breakdown for itemized line-item totals within a category, item_presence for yes/no item purchase questions."
        }
      ),
      amount: Type.Optional(
        Type.String({
          description: "Dollar amount for add_expense, for example '41.50'."
        })
      ),
      merchant: Type.Optional(
        Type.String({
          description: "Merchant/store label for add_expense, for example 'Trader Joe's'."
        })
      ),
      category: Type.Optional(
        Type.Union(EXPENSE_CATEGORIES.map((value) => Type.Literal(value)), {
          description:
            "Canonical category when the user explicitly references a category or asks for a category total/correction."
        })
      ),
      timeframe: Type.Optional(
        Type.Union(EXPENSE_TIMEFRAMES.map((value) => Type.Literal(value)), {
          description:
            "Supported time window for totals, breakdowns, item queries, or expense lists."
        })
      ),
      itemName: Type.Optional(
        Type.String({
          description:
            "Receipt line item name for item_total, item_presence, or change_last_receipt_item_category, for example 'milk'."
        })
      ),
      rawText: Type.Optional(
        Type.String({
          description:
            "Optional original user wording for audit readability. Omit if not needed."
        })
      ),
      scope: Type.Optional(
        Type.String({
          description:
            "Optional logical scope for expense data. Omit to use the configured default scope."
        })
      ),
      actorName: Type.Optional(
        Type.String({
          description: "Optional human-readable actor name."
        })
      ),
      actorId: Type.Optional(
        Type.String({
          description: "Optional stable actor identifier."
        })
      )
    }),
    async execute(_id, params: ExpenseToolParams) {
      const request: StructuredExpenseWorkerRequest = {
        action: params.action,
        scope: params.scope ?? config.defaultScope,
        actor_name: params.actorName ?? null,
        actor_id: params.actorId ?? null,
        amount: params.amount ?? null,
        merchant: params.merchant ?? null,
        category: params.category ?? null,
        timeframe: params.timeframe ?? null,
        item_name: params.itemName ?? null,
        raw_text: params.rawText ?? null
      };

      const response = await postStructuredExpenseCommand(config, request);

      return {
        content: [
          {
            type: "text",
            text: response.reply_text
          }
        ]
      };
    }
  });

  api.registerTool({
    name: "denkeeper_receipt",
    description:
      "Use this for itemized receipt ingestion. Extract receipt items and totals, then call this tool to persist an itemized expense record. After tool execution, include the full returned itemized breakdown in your user reply and do not compress it to a one-line summary.",
    parameters: Type.Object({
      merchant: Type.String({
        description: "Merchant/store on the receipt."
      }),
      items: Type.Array(
        Type.Object({
          name: Type.String({ description: "Line item name, for example 'Organic Milk'." }),
          lineTotal: Type.String({ description: "Line total amount in dollars, for example '4.99'." }),
          quantity: Type.Optional(Type.Number()),
          unit: Type.Optional(Type.String()),
          unitPrice: Type.Optional(Type.String())
        }),
        {
          minItems: 1,
          description: "Itemized receipt lines."
        }
      ),
      rawText: Type.Optional(Type.String()),
      scope: Type.Optional(Type.String()),
      actorName: Type.Optional(Type.String()),
      actorId: Type.Optional(Type.String()),
      category: Type.Optional(Type.String()),
      receiptTotal: Type.Optional(Type.String()),
      purchasedAt: Type.Optional(
        Type.String({
          description: "Optional ISO datetime for purchase time."
        })
      )
    }),
    async execute(_id, params: ReceiptToolParams) {
      const request: ReceiptWorkerRequest = {
        scope: params.scope ?? config.defaultScope,
        merchant: params.merchant,
        items: params.items.map((item) => ({
          name: item.name,
          line_total: item.lineTotal,
          quantity: item.quantity ?? null,
          unit: item.unit ?? null,
          unit_price: item.unitPrice ?? null
        })),
        actor_name: params.actorName ?? null,
        actor_id: params.actorId ?? null,
        category: params.category ?? null,
        receipt_total: params.receiptTotal ?? null,
        purchased_at: params.purchasedAt ?? null,
        raw_text: params.rawText ?? null
      };

      const response = await postReceiptCommand(config, request);

      return {
        content: [
          {
            type: "text",
            text: response.reply_text
          }
        ]
      };
    }
  });
}
