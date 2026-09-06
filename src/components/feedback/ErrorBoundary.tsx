import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  /** Reset the boundary when this key changes (e.g. route pathname). */
  resetKey?: unknown;
}
interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) console.error('Render error', error, info.componentStack);
  }

  override componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  override render() {
    if (!this.state.error) return this.props.children;
    if (this.props.fallback) return this.props.fallback;
    return (
      <div
        role="alert"
        className="flex min-h-64 flex-col items-center justify-center p-6 text-center"
      >
        <span className="mb-3 inline-flex size-11 items-center justify-center rounded-full bg-danger-50 text-danger-600">
          <AlertTriangle className="size-5" aria-hidden />
        </span>
        <h2 className="text-sm font-semibold text-brand-950">This screen failed to render</h2>
        <p className="mt-1 max-w-sm text-sm text-ink-500">
          Reloading usually fixes it. If it keeps happening, let support know what you were doing.
        </p>
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => this.setState({ error: null })}>
            Try again
          </Button>
          <Button size="sm" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </div>
      </div>
    );
  }
}
