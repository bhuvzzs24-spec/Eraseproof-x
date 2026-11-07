import { Component, useRef, useId, type ReactNode } from "react";
import { AlertTriangle, ArrowRight, Inbox, LoaderCircle } from "lucide-react";
import { outcome, date } from "./api";
import type { TimelineEvent } from "./types";
export function Badge({ value }: { value: string }) {
  const [label, tone] = outcome(value);
  return (
    <span className={`badge ${tone}`}>
      <span aria-hidden="true" className="status-dot" />
      {label}
    </span>
  );
}
export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
}: {
  title?: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title ? (
        <header className="panel-head">
          <div>
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            <h2>{title}</h2>
          </div>
          {action}
        </header>
      ) : null}
      {children}
    </section>
  );
}
export function PageTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function ErrorNotice({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <AlertTriangle size={18} />
      <div>
        <strong>Connection or request problem</strong>
        <p>{error instanceof Error ? error.message : String(error)}</p>
        {retry ? (
          <button className="text-button" onClick={retry}>
            Try read again <ArrowRight size={14} />
          </button>
        ) : null}
      </div>
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={20} className="spin" />
      <span>Reading source data…</span>
    </div>
  );
}
export function Empty({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={30} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function Json({ value }: { value: unknown }) {
  return (
    <pre className="json" tabIndex={0}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
export function Metric({
  label,
  value,
  detail,
  tone = "",
}: {
  label: string;
  value: ReactNode;
  detail: string;
  tone?: string;
}) {
  return (
    <div className={`metric ${tone}`}>
      <p>{label}</p>
      <strong>{value}</strong>
      <span>{detail}</span>
    </div>
  );
}
export function Pager({
  page,
  total,
  limit,
  onChange,
}: {
  page: number;
  total?: number;
  limit: number;
  onChange: (page: number) => void;
}) {
  return (
    <div className="pager">
      <span>
        Page {page + 1}
        {total !== undefined ? ` · ${total} records` : ""}
      </span>
      <div>
        <button disabled={page === 0} onClick={() => onChange(page - 1)}>
          Previous
        </button>
        <button
          disabled={total !== undefined ? (page + 1) * limit >= total : false}
          onClick={() => onChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
export function Confirm({
  label,
  title,
  description,
  onConfirm,
  disabled = false,
  children,
}: {
  label: string;
  title: string;
  description: string;
  onConfirm: () => void;
  disabled?: boolean;
  children?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  return (
    <>
      <button
        className="button"
        disabled={disabled}
        onClick={() => ref.current?.showModal()}
      >
        {label}
      </button>
      <dialog ref={ref} className="dialog" aria-labelledby={headingId}>
        <form method="dialog">
          <p className="eyebrow">Explicit authorization</p>
          <h2 id={headingId}>{title}</h2>
          <p>{description}</p>
          {children}
          <div className="dialog-actions">
            <button value="cancel">Cancel</button>
            <button
              className="button danger-button"
              type="button"
              value="confirm"
              onClick={() => {
                onConfirm();
                ref.current?.close();
              }}
            >
              Confirm {label.toLowerCase()}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
export function Timeline({ items }: { items: TimelineEvent[] }) {
  return items.length ? (
    <ol className="timeline">
      {items.map((item, i) => (
        <li key={`${item.sequence || i}-${item.kind}`}>
          <span className="timeline-point" />
          <div>
            <strong>{item.kind.replaceAll(".", " / ")}</strong>
            <p>
              {item.code ||
                item.to_state ||
                item.state ||
                item.source ||
                "Recorded event"}
            </p>
          </div>
          <time>{date(item.occurred_at)}</time>
        </li>
      ))}
    </ol>
  ) : (
    <Empty
      title="No recorded events"
      description="Events will appear after the backend records an operation."
    />
  );
}
export function Table({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="table-wrap" role="region" aria-label={label} tabIndex={0}>
      <table>{children}</table>
    </div>
  );
}
export function ReadOnly() {
  return (
    <p className="subtle">
      Read-only session. Operator authorization is required for changes.
    </p>
  );
}

export class WorkspaceBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    return this.state.error ? (
      <ErrorNotice
        error={
          new Error(
            "This workspace could not render its data. Other workspaces remain available. Refresh source data and reopen this view.",
          )
        }
        retry={() => this.setState({ error: null })}
      />
    ) : (
      this.props.children
    );
  }
}
