import type { ReactNode } from "react";

export function EmptyState({
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
    <section className="empty-state">
      <div className="empty-orbit" aria-hidden="true">
        <span />
        <span />
      </div>
      <p className="section-kicker">{eyebrow}</p>
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </section>
  );
}
