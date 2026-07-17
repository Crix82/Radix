import { useState } from "react";

import type { Collection, UserDetail } from "../api/users";
import { InviteUserModal } from "../components/InviteUserModal";
import { PageHead } from "../components/Layout";
import { useCollections, useUsers } from "../hooks/useUsers";
import { t } from "../i18n";

const u = t.pages.users;

function roleChip(role: UserDetail["role"]) {
  return role === "admin" ? (
    <span className="chip-petrol">{u.roleAdmin}</span>
  ) : (
    <span className="chip-neutral">{u.roleUser}</span>
  );
}

function statusChip(status: UserDetail["status"]) {
  if (status === "active") return <span className="chip-ok">{u.statusActive}</span>;
  if (status === "invited") return <span className="chip-neutral">{u.statusInvited}</span>;
  return <span className="chip-neutral">{u.statusDisabled}</span>;
}

function collectionsLabel(user: UserDetail, collections: Collection[]): string {
  if (user.role === "admin") return u.allCollections;
  if (user.collection_ids.length === 0) return u.noCollections;
  const byId = new Map(collections.map((c) => [c.id, c.name]));
  return user.collection_ids
    .map((id) => byId.get(id) ?? `#${id}`)
    .join(" · ");
}

export function UsersPage() {
  const { data: users, isLoading } = useUsers();
  const { data: collections } = useCollections();
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHead title={u.title} subtitle={u.subtitle} />
        <button
          type="button"
          className="btn-primary mt-1 flex-none"
          onClick={() => setModalOpen(true)}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            aria-hidden="true"
            className="h-4 w-4"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          {u.invite}
        </button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="th">{u.colName}</th>
              <th className="th">{u.colRole}</th>
              <th className="th">{u.colCollections}</th>
              <th className="th">{u.colStatus}</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="td text-ink3" colSpan={4}>
                  {u.loading}
                </td>
              </tr>
            )}
            {(users ?? []).map((user) => (
              <tr key={user.id}>
                <td className="td">
                  <div className="font-semibold">{user.name}</div>
                  <div className="mt-[2px] font-mono text-[11px] text-ink2">{user.email}</div>
                </td>
                <td className="td">{roleChip(user.role)}</td>
                <td className="td text-[13px]">{collectionsLabel(user, collections ?? [])}</td>
                <td className="td">{statusChip(user.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <InviteUserModal collections={collections ?? []} onClose={() => setModalOpen(false)} />
      )}
    </>
  );
}
