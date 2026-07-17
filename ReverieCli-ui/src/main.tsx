import { Component, ErrorInfo, ReactNode, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import { applyTheme, normalizeTheme, THEME_STORAGE_KEY } from "./theme";
import { applyUiPreferences, DEFAULT_UI_PREFERENCES } from "./preferences";

applyTheme(
  normalizeTheme(localStorage.getItem(THEME_STORAGE_KEY)),
  window.matchMedia("(prefers-color-scheme: dark)").matches,
);
applyUiPreferences(DEFAULT_UI_PREFERENCES);

class RendererErrorBoundary extends Component<{ children: ReactNode }, { error: string }> {
  state = { error: "" };

  static getDerivedStateFromError(error: Error): { error: string } {
    return { error: error.message || String(error) };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Reverie renderer error", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="loading-screen error-screen">
        <h1>Reverie encountered a display error</h1>
        <p>{this.state.error}</p>
        <button type="button" className="primary-button" onClick={() => window.location.reload()}>
          Reload interface
        </button>
      </div>
    );
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RendererErrorBoundary>
      <App />
    </RendererErrorBoundary>
  </StrictMode>,
);
