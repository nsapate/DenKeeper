export type ExpenseAction =
  | "add_expense"
  | "change_last_category"
  | "change_last_receipt_item_category"
  | "delete_last"
  | "delete_last_receipt"
  | "undo_last"
  | "list_expenses"
  | "total"
  | "category_breakdown"
  | "category_item_breakdown"
  | "item_total"
  | "item_presence"
  | "list_categories";

export type ExpenseTimeframe =
  | "today"
  | "yesterday"
  | "this week"
  | "last week"
  | "this month"
  | "last month";

export interface StructuredExpenseWorkerRequest {
  action: ExpenseAction;
  scope: string;
  actor_name: string | null;
  actor_id: string | null;
  amount?: string | null;
  merchant?: string | null;
  category?: string | null;
  timeframe?: ExpenseTimeframe | null;
  item_name?: string | null;
  raw_text?: string | null;
}

export interface ReceiptLineItem {
  name: string;
  line_total: string;
  quantity?: number | null;
  unit?: string | null;
  unit_price?: string | null;
}

export interface ReceiptWorkerRequest {
  scope: string;
  merchant: string;
  items: ReceiptLineItem[];
  actor_name: string | null;
  actor_id: string | null;
  category?: string | null;
  receipt_total?: string | null;
  purchased_at?: string | null;
  raw_text?: string | null;
}

export interface ExpenseWorkerResponse {
  action: string;
  reply_text: string;
  metadata: Record<string, unknown>;
}
