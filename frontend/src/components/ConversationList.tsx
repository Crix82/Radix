import { NavLink, useNavigate, useParams } from "react-router-dom";

import { useConversations, useDeleteConversation } from "../hooks/useConversations";
import { t } from "../i18n";

const c = t.nav.conversations;

export function ConversationList({ isAdmin }: { isAdmin: boolean }) {
  const { data: conversations = [] } = useConversations();
  const remove = useDeleteConversation();
  const navigate = useNavigate();
  const { conversationId } = useParams<{ conversationId?: string }>();

  const onDelete = (id: number, title: string) => {
    if (!window.confirm(c.deleteConfirm(title))) return;
    remove.mutate(id, {
      // Leaving the thread we just deleted open would show a 404 on the next fetch.
      onSuccess: () => {
        if (conversationId && Number(conversationId) === id) navigate("/chat");
      },
    });
  };

  return (
    <div className="mt-[6px] flex min-h-0 flex-col">
      <button
        type="button"
        onClick={() => navigate("/chat")}
        className="mx-[10px] mb-[6px] rounded-sm border border-white/[.12] px-[8px] py-[5px] text-left text-[11.5px] text-navtext hover:bg-white/5"
      >
        + {c.newChat}
      </button>

      {conversations.length === 0 ? (
        <div className="px-[10px] py-1 text-[11px] text-navmut">{c.empty}</div>
      ) : (
        <ul className="max-h-[34vh] min-h-0 overflow-y-auto">
          {conversations.map((conv) => (
            <li key={conv.id} className="group flex items-center gap-1 pr-[6px]">
              <NavLink
                to={`/chat/${conv.id}`}
                className={({ isActive }) =>
                  `flex-1 truncate rounded-sm px-[10px] py-[5px] text-[12px] ` +
                  (isActive ? "bg-nav-2 font-semibold text-white" : "text-navtext hover:bg-white/5")
                }
                title={conv.title}
              >
                {conv.title}
                {isAdmin && conv.user_email && (
                  <span className="ml-1 font-mono text-[9.5px] text-navmut">{conv.user_email}</span>
                )}
              </NavLink>
              <button
                type="button"
                className="hidden h-5 w-5 flex-none rounded-sm text-navmut hover:bg-white/10 hover:text-navtext group-hover:block"
                onClick={() => onDelete(conv.id, conv.title)}
                aria-label={c.deleteLabel(conv.title)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="px-[10px] pt-[8px] text-[10px] leading-snug text-navmut">{c.adminNotice}</div>
    </div>
  );
}
