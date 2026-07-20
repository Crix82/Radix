import { NavLink } from "react-router-dom";

import { useCurrentUser, useLogout } from "../hooks/useAuth";
import { t } from "../i18n";
import { ConversationList } from "./ConversationList";

const icons = {
  search: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  ),
  chat: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z" />
    </svg>
  ),
  sources: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
  ),
  indexing: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="m12 2 9 5-9 5-9-5z" />
      <path d="m3 12 9 5 9-5" />
      <path d="m3 17 9 5 9-5" />
    </svg>
  ),
  users: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M15.5 14.5a5 5 0 0 1 6 4.9" />
    </svg>
  ),
};

function NavItem({ to, icon, label }: { to: string; icon: JSX.Element; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `relative flex w-full items-center gap-[10px] rounded-sm px-[10px] py-2 text-left text-[13px] ` +
        (isActive
          ? "bg-nav-2 font-semibold text-white before:absolute before:-left-3 before:bottom-[6px] before:top-[6px] before:w-[3px] before:rounded-r-[3px] before:bg-petrol-mid [&_svg]:opacity-100"
          : "text-navtext hover:bg-white/5")
      }
    >
      <span className="h-4 w-4 flex-none opacity-75 [&_svg]:h-4 [&_svg]:w-4">{icon}</span>
      <span>{label}</span>
    </NavLink>
  );
}

function NavLabel({ children }: { children: string }) {
  return (
    <div className="px-[10px] pb-[6px] pt-[14px] text-[10.5px] uppercase tracking-[.09em] text-navmut">
      {children}
    </div>
  );
}

export function Sidebar() {
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  return (
    <nav
      className="flex w-[236px] min-w-[236px] flex-col bg-nav px-3 pb-[14px] pt-[18px] text-navtext"
      aria-label="Navigazione principale"
    >
      <div className="flex items-center gap-[10px] px-2 pb-[18px] pt-1">
        <div className="flex h-8 w-8 items-center justify-center rounded-sm bg-gradient-to-br from-petrol to-petrol-mid text-base font-bold text-white">
          R
        </div>
        <div>
          <div className="text-[15px] font-semibold text-white">{t.app.name}</div>
          <div className="mt-[1px] font-mono text-[10px] text-navmut">{t.app.tagline}</div>
        </div>
      </div>

      <NavLabel>{t.nav.consultation}</NavLabel>
      <NavItem to="/search" icon={icons.search} label={t.nav.search} />
      <NavItem to="/chat" icon={icons.chat} label={t.nav.chat} />
      <ConversationList isAdmin={user?.role === "admin"} />

      {user?.role === "admin" && (
        <>
          <NavLabel>{t.nav.administration}</NavLabel>
          <NavItem to="/sources" icon={icons.sources} label={t.nav.sources} />
          <NavItem to="/indexing" icon={icons.indexing} label={t.nav.indexing} />
          <NavItem to="/users" icon={icons.users} label={t.nav.users} />
        </>
      )}

      <div className="mt-auto">
        {user && (
          <button
            className="mb-2 w-full rounded-sm px-[10px] py-2 text-left text-[12px] text-navmut hover:bg-white/5 hover:text-navtext"
            onClick={() => logout.mutate()}
          >
            {t.common.logout} · {user.email}
          </button>
        )}
        <div className="rounded-sm border border-white/[.07] bg-white/[.04] px-3 py-[10px]">
          <div className="flex items-center gap-[7px] text-[11.5px]">
            <span className="h-[7px] w-[7px] flex-none rounded-full bg-[#4CC38A]" />
            {t.app.footPrivacy}
          </div>
          <div className="mt-1 font-mono text-[10px] text-navmut">{t.app.footNoExternal}</div>
        </div>
      </div>
    </nav>
  );
}
