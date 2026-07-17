import { Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listSources } from "../api/sources";
import { useCurrentUser } from "../hooks/useAuth";
import { t } from "../i18n";

// First-boot onboarding shows only for an admin with no sources yet (SPEC §7.3);
// everyone else lands on search.
export function HomeRedirect() {
  const { data: user } = useCurrentUser();
  const isAdmin = user?.role === "admin";
  const { data: sources, isLoading } = useQuery({
    queryKey: ["sources"],
    queryFn: listSources,
    enabled: isAdmin,
  });

  if (isAdmin && isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-ink3">{t.common.loading}</div>
    );
  }
  if (isAdmin && sources && sources.length === 0) {
    return <Navigate to="/onboarding" replace />;
  }
  return <Navigate to="/search" replace />;
}
