export function ContentSkeleton() {
  return (
    <div className="content-skeleton" aria-hidden="true">
      <span className="skeleton-line skeleton-line-short" />
      <span className="skeleton-line skeleton-line-title" />
      <div className="skeleton-card">
        <span className="skeleton-line" />
        <span className="skeleton-line" />
        <span className="skeleton-line skeleton-line-medium" />
      </div>
      <div className="skeleton-grid">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}
