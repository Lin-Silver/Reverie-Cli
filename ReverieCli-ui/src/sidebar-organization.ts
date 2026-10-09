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
  };
}
