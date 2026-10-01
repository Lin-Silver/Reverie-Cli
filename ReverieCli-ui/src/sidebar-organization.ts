import { useState } from "react";
import { ownerKey } from "./execution-state";

interface Organization { projects: string[]; sessions: string[]; order: Record<string, string[]> }
export function useSidebarOrganization() {
  const [value, setValue] = useState<Organization>(() => {
    try { return JSON.parse(localStorage.getItem("reverie.sidebar.v1") ?? '{"projects":[],"sessions":[],"order":{}}'); }
    catch { return { projects: [], sessions: [], order: {} }; }
  });
  const [error, setError] = useState("");
  function save(next: Organization) {
    try { localStorage.setItem("reverie.sidebar.v1", JSON.stringify(next)); setValue(next); setError(""); }
    catch (reason) { setError(String(reason)); }
  }
  return {
    value, error,
    pinProject(root: string) { save({ ...value, projects: value.projects.includes(root) ? value.projects.filter(item => item !== root) : [...value.projects, root] }); },
    pinSession(root: string, id: string) { const key = ownerKey(root, id); save({ ...value, sessions: value.sessions.includes(key) ? value.sessions.filter(item => item !== key) : [...value.sessions, key] }); },
    move(root: string, ids: string[], id: string, delta: number) { const next = [...ids]; const index = next.indexOf(id); const target = Math.max(0, Math.min(next.length - 1, index + delta)); if (index < 0) return; next.splice(index, 1); next.splice(target, 0, id); save({ ...value, order: { ...value.order, [root]: next } }); },
  };
}
