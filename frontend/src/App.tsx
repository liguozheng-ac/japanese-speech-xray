import { useEffect, useLayoutEffect, useState } from "react";
import { Page0Landing } from "./Page0Landing";
import { WorkspaceEmpty } from "./WorkspaceEmpty";

const isWorkspaceHash = () => window.location.hash.split("?")[0] === "#/workspace";

export function App() {
  const [workspace, setWorkspace] = useState(isWorkspaceHash);

  useEffect(() => {
    const onHashChange = () => setWorkspace(isWorkspaceHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useLayoutEffect(() => {
    if (workspace) {
      window.scrollTo({ top: 0, behavior: "instant" });
      document.getElementById("workspace-main")?.focus({ preventScroll: true });
    } else {
      // Restore Landing anchors after a browser Back or a return from Workspace.
      const target = document.getElementById(window.location.hash.slice(1) || "top");
      target?.scrollIntoView({ behavior: "instant" });
    }
  }, [workspace]);

  return workspace ? <WorkspaceEmpty /> : <Page0Landing />;
}
