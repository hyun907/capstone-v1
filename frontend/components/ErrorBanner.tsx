interface Props {
  message: string;
  recoverable: boolean;
}

export function ErrorBanner({ message, recoverable }: Props) {
  return (
    <div className={`error-banner ${recoverable ? "error-banner-warning" : "error-banner-critical"}`}
      role={recoverable ? "status" : "alert"}>
      <span aria-hidden="true">{recoverable ? "⚠" : "✕"}</span>
      <span>{message}</span>
    </div>
  );
}
