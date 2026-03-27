import { Component, ReactNode } from "react";

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    console.error("route_error", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <section className="panel error-panel">
          <p className="eyebrow">Unexpected UI Error</p>
          <h3>Something broke on this screen.</h3>
          <p className="muted-copy">Refresh the page or sign in again. The backend state is still safe.</p>
        </section>
      );
    }
    return this.props.children;
  }
}
