import { Navigate, Outlet } from "react-router-dom";

import { useCurrentUser } from "../hooks/useAuth";
import { t } from "../i18n";
import { Sidebar } from "./Sidebar";

export function Layout() {
  const { data: user, isLoading } = useCurrentUser();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-ink3">{t.common.loading}</div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="relative flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1020px] px-9 pb-[60px] pt-[30px]">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

export function PageHead({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-5">
      <h1 className="text-[21px] font-semibold tracking-[-.01em]">{title}</h1>
      <div className="mt-[3px] text-[12.5px] text-ink2">{subtitle}</div>
    </div>
  );
}
