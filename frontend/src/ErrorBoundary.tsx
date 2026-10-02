import { Component, type ErrorInfo, type ReactNode } from 'react'

export class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Do not forward component state or candidate data to third parties.
  }
  render() {
    if (this.state.failed)
      return (
        <main className="login-shell">
          <section className="login-panel">
            <h1>Something went wrong</h1>
            <p>
              Reload the workspace to try again. If the problem continues,
              contact your administrator.
            </p>
            <button
              className="button primary"
              onClick={() => window.location.reload()}
            >
              Reload workspace
            </button>
          </section>
        </main>
      )
    return this.props.children
  }
}
