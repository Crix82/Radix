import { useEffect, useState } from "react";

import type { Collection, UserRole } from "../api/users";
import { useInviteUser } from "../hooks/useUsers";
import { t } from "../i18n";

const m = t.pages.users.modal;

export function InviteUserModal({
  collections,
  onClose,
}: {
  collections: Collection[];
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const invite = useInviteUser();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const submit = () => {
    invite.mutate(
      { email, name, role, collection_ids: [...selected] },
      { onSuccess: onClose },
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(20,38,45,.45)] p-5"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="card w-full max-w-[480px] px-6 py-[22px]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="invite-title"
      >
        <h3 id="invite-title" className="mb-1 text-[16px] font-semibold">
          {m.title}
        </h3>
        <div className="mb-4 text-[12.5px] text-ink2">{m.subtitle}</div>

        <div className="mb-3">
          <label className="field-label" htmlFor="inv-email">
            {m.email}
          </label>
          <input
            id="inv-email"
            type="email"
            className="field-input"
            value={email}
            placeholder={m.emailPlaceholder}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
          />
        </div>

        <div className="mb-3">
          <label className="field-label" htmlFor="inv-name">
            {m.name}
          </label>
          <input
            id="inv-name"
            type="text"
            className="field-input"
            value={name}
            placeholder={m.namePlaceholder}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="mb-3">
          <label className="field-label" htmlFor="inv-role">
            {m.role}
          </label>
          <select
            id="inv-role"
            className="field-input"
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
          >
            <option value="user">{t.pages.users.roleUser}</option>
            <option value="admin">{t.pages.users.roleAdmin}</option>
          </select>
        </div>

        <div className="mb-3">
          <label className="field-label">{m.collections}</label>
          {collections.length === 0 ? (
            <div className="text-[12px] text-ink3">{m.noCollections}</div>
          ) : (
            <div className="flex flex-wrap gap-[14px]">
              {collections.map((c) => (
                <label key={c.id} className="flex items-center gap-[6px] text-[12.5px]">
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={() => toggle(c.id)}
                  />
                  {c.name}
                </label>
              ))}
            </div>
          )}
        </div>

        <p className="mb-4 font-mono text-[10.5px] text-ink3">{m.note}</p>
        {invite.isError && <p className="mb-3 text-[12px] text-err">{m.error}</p>}

        <div className="flex justify-end gap-[10px]">
          <button type="button" className="btn-plain" onClick={onClose}>
            {m.cancel}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={submit}
            disabled={invite.isPending || !email.trim()}
          >
            {m.submit}
          </button>
        </div>
      </div>
    </div>
  );
}
