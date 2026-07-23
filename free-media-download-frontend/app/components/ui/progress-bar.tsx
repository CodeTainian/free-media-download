export function ProgressBar({
  value,
  label,
}: {
  value: number;
  label: string;
}) {
  const normalized = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      className="progress-bar"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={normalized}
    >
      <span style={{ width: `${normalized}%` }} />
    </div>
  );
}
