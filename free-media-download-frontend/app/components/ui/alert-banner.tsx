import type { ApiError } from "../../lib/api/types";

export function AlertBanner({
  error,
  onDismiss,
  dismissLabel,
}: {
  error: ApiError;
  onDismiss?: () => void;
  dismissLabel?: string;
}) {
  return (
    <div className="alert-banner" role="alert">
      <span className="alert-icon" aria-hidden="true">
        !
      </span>
      <div>
        <strong>{error.code.replaceAll("_", " ")}</strong>
        <p>{error.message}</p>
      </div>
      {onDismiss ? (
        <button type="button" onClick={onDismiss} aria-label={dismissLabel}>
          ×
        </button>
      ) : null}
    </div>
  );
}
