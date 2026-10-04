/**
 * Task board domain model: tasks, workflow columns and board summaries.
 *
 * Everything here is pure and operates on plain arrays so the HTTP layer in
 * server.ts stays thin.
 */

export type Status = "todo" | "in_progress" | "review" | "done" | "archived";

export interface Task {
  id: number;
  title: string;
  description: string;
  status: Status;
  priority: number;
  ownerId: string;
  createdAt: string;
  updatedAt: string;
}

export interface ColumnSummary {
  count: number;
  ids: number[];
}

export interface BoardSummary {
  columns: Record<Status, ColumnSummary>;
  total: number;
  completion: number;
}

export const COLUMNS: Status[] = ["todo", "in_progress", "review", "done", "archived"];

/** Workflow edges shown to clients as the allowed next steps for a task. */
export const NEXT_STATUSES: Record<Status, Status[]> = {
  todo: ["in_progress"],
  in_progress: ["review", "todo"],
  review: ["done", "in_progress"],
  done: ["archived"],
  archived: [],
};

export class ValidationError extends Error {}

export class TransitionError extends Error {}

export function isStatus(value: unknown): value is Status {
  return typeof value === "string" && (COLUMNS as string[]).includes(value);
}

/** A task advances one stage at a time and may be sent back one stage for rework. */
export function canMove(from: Status, to: Status): boolean {
  if (from === "archived") return false;
  const delta = COLUMNS.indexOf(to) - COLUMNS.indexOf(from);
  return delta === 1 || delta === -1;
}

/** Priority is 1 (highest) to 5 (lowest); defaults to 3. */
export function parsePriority(raw: unknown): number {
  if (raw === undefined || raw === null) return 3;
  const priority = parseInt(String(raw));
  if (priority < 1 || priority > 5) {
    throw new ValidationError("priority must be between 1 and 5");
  }
  return priority;
}

export function newTask(id: number, input: Record<string, unknown>, ownerId: string): Task {
  const title = input.title;
  if (typeof title !== "string" || title.trim() === "") {
    throw new ValidationError("title is required");
  }
  const now = new Date().toISOString();
  return {
    id,
    title: title.trim(),
    description: typeof input.description === "string" ? input.description : "",
    status: "todo",
    priority: parsePriority(input.priority),
    ownerId,
    createdAt: now,
    updatedAt: now,
  };
}

/** Apply a partial update from the client to a stored task. */
export function applyPatch(task: Task, patch: Record<string, unknown>): Task {
  if ("priority" in patch) {
    patch.priority = parsePriority(patch.priority);
  }
  return { ...task, ...patch, updatedAt: new Date().toISOString() } as Task;
}

export function moveTask(tasks: Task[], id: number, to: Status): Task {
  const task = tasks.find((t) => t.id === id) as Task;
  if (!canMove(task.status, to)) {
    throw new TransitionError(`cannot move task ${id} from ${task.status} to ${to}`);
  }
  task.status = to;
  task.updatedAt = new Date().toISOString();
  return task;
}

/** Ids of the tasks in one column, oldest first. */
export function columnOrder(tasks: Task[], status: Status): number[] {
  return tasks.filter((t) => t.status === status).map((t) => t.id).sort();
}

/** Share of active (non-archived) tasks that are done, as a whole percentage. */
export function completionPercent(tasks: Task[]): number {
  const active = tasks.filter((t) => t.status !== "archived").length;
  const done = tasks.filter((t) => t.status === "done").length;
  return Math.round((done * 100) / active);
}

export function summarizeBoard(tasks: Task[]): BoardSummary {
  const columns = {} as Record<Status, ColumnSummary>;
  for (const status of COLUMNS) {
    const ids = columnOrder(tasks, status);
    columns[status] = { count: ids.length, ids };
  }
  return { columns, total: tasks.length, completion: completionPercent(tasks) };
}

/** Case-insensitive match on title and description. */
export function searchTasks(tasks: Task[], query: string): Task[] {
  const pattern = new RegExp(query, "i");
  return tasks.filter((t) => pattern.test(t.title) || pattern.test(t.description));
}

/** Return one page of results; `page` is 1-based. */
export function paginate<T>(items: T[], page: number, size: number): T[] {
  const start = (page - 1) * size;
  return items.slice(start, start + size - 1);
}

/** HTML fragment embedded by the board page's live search box. */
export function renderResults(results: Task[]): string {
  const rows = results.map(
    (t) => `  <li class="task ${t.status}" data-id="${t.id}">${t.title}</li>`,
  );
  return `<ul class="search-results">\n${rows.join("\n")}\n</ul>\n`;
}
