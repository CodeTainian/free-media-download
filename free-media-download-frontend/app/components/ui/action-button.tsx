import type { ButtonHTMLAttributes, ReactNode } from "react";

export function ActionButton({
  children,
  variant = "primary",
  loading = false,
  className = "",
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: "primary" | "secondary" | "quiet" | "danger";
  loading?: boolean;
}) {
  return (
    <button
      className={`action-button action-button-${variant} ${className}`.trim()}
      disabled={disabled || loading}
      aria-busy={loading}
      {...props}
    >
      {loading ? <span className="button-spinner" aria-hidden="true" /> : null}
      <span>{children}</span>
    </button>
  );
}
