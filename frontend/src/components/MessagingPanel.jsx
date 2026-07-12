import { useMemo, useState } from "react";
import { Send, Users as UsersIcon, User, MessageSquare, Radio } from "lucide-react";
import { sendMessage, simulateInboundMessage } from "@/lib/api";
import { toast } from "sonner";
import { format } from "date-fns";
import { iconFor } from "@/lib/icons";

export function MessagingPanel({ radios, groups, messages, currentUser, defaultTargetId }) {
  const [target, setTarget] = useState(() => ({ type: "group", id: null }));
  const [draft, setDraft] = useState("");

  // Auto-select first group if none selected
  const selectedGroup =
    target.type === "group" ? groups.find((g) => g.id === target.id) || groups[0] : null;
  const selectedRadio =
    target.type === "radio" ? radios.find((r) => r.dmr_id === target.id) : null;

  const conversation = useMemo(() => {
    if (target.type === "group") {
      const g = selectedGroup;
      if (!g) return [];
      return messages.filter(
        (m) => m.talkgroup_id === g.talkgroup_id || (m.direction === "out" && m.to_dmr_id == null)
      );
    }
    if (target.type === "radio" && selectedRadio) {
      const id = selectedRadio.dmr_id;
      return messages.filter(
        (m) =>
          m.from_dmr_id === id ||
          m.to_dmr_id === id ||
          (m.is_private && (m.from_dmr_id === id || m.to_dmr_id === id))
      );
    }
    return [];
  }, [messages, target, selectedGroup, selectedRadio]);

  const send = async () => {
    if (!draft.trim()) return;
    try {
      if (target.type === "group") {
        const g = selectedGroup;
        if (!g) return toast.error("Select a group first");
        await sendMessage({ text: draft, group_id: g.id });
      } else {
        const r = selectedRadio;
        if (!r) return toast.error("Select a radio first");
        await sendMessage({ text: draft, target_dmr_id: r.dmr_id });
      }
      setDraft("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    }
  };

  const simulateReply = async () => {
    if (!selectedRadio) return;
    await simulateInboundMessage({
      from_dmr_id: selectedRadio.dmr_id,
      text: `Copy ${currentUser?.callsign || "control"}, msg received.`,
      to_dmr_id: 0,
    });
  };

  // Auto-focus target when defaultTargetId passed
  if (defaultTargetId && target.id !== defaultTargetId) {
    setTarget({ type: "radio", id: defaultTargetId });
  }

  return (
    <div
      data-testid="messaging-panel"
      className="flex h-full flex-col bg-[#0a0a0a]"
    >
      <div className="flex items-center justify-between border-b border-[#2a2a2a] px-3 py-2">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-3.5 w-3.5 text-[#00f0ff]" />
          <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500">
            DMR Messaging
          </div>
        </div>
        <div className="mono text-[10px] text-neutral-500">{messages.length} msg</div>
      </div>

      {/* Target selector */}
      <div className="border-b border-[#2a2a2a] p-2 space-y-2">
        <div className="flex gap-1">
          <TypeTab
            testid="msg-target-group"
            icon={<UsersIcon className="h-3 w-3" />}
            label="GROUP"
            active={target.type === "group"}
            onClick={() =>
              setTarget({ type: "group", id: groups[0]?.id ?? null })
            }
          />
          <TypeTab
            testid="msg-target-radio"
            icon={<User className="h-3 w-3" />}
            label="RADIO"
            active={target.type === "radio"}
            onClick={() =>
              setTarget({ type: "radio", id: radios[0]?.dmr_id ?? null })
            }
          />
        </div>
        {target.type === "group" ? (
          <select
            data-testid="msg-group-select"
            value={selectedGroup?.id || ""}
            onChange={(e) => setTarget({ type: "group", id: e.target.value })}
            className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] text-neutral-100 outline-none focus:border-[#00f0ff]"
          >
            {groups.length === 0 && <option value="">— no groups —</option>}
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {`${g.name} · TG ${g.talkgroup_id}`}
              </option>
            ))}
          </select>
        ) : (
          <select
            data-testid="msg-radio-select"
            value={selectedRadio?.dmr_id || ""}
            onChange={(e) =>
              setTarget({ type: "radio", id: parseInt(e.target.value, 10) })
            }
            className="w-full border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] text-neutral-100 outline-none focus:border-[#00f0ff]"
          >
            {radios.length === 0 && <option value="">— no radios —</option>}
            {radios.map((r) => (
              <option key={r.dmr_id} value={r.dmr_id}>
                {r.callsign || `ID ${r.dmr_id}`}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Conversation */}
      <div
        className="flex-1 overflow-y-auto px-2 py-2 mono text-[11px]"
        data-testid="msg-conversation"
      >
        {conversation.length === 0 && (
          <div className="text-neutral-600">// no messages yet</div>
        )}
        {[...conversation].reverse().map((m) => (
          <MessageBubble key={m.id} m={m} />
        ))}
      </div>

      {/* Composer */}
      <div className="border-t border-[#2a2a2a] p-2">
        <div className="flex items-end gap-1">
          <textarea
            data-testid="msg-input"
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send();
            }}
            placeholder="Type message (Ctrl+Enter to send)"
            className="flex-1 border border-[#2a2a2a] bg-black px-2 py-1 mono text-[11px] text-neutral-100 outline-none focus:border-[#00f0ff]"
          />
          <button
            data-testid="msg-send"
            onClick={send}
            disabled={!draft.trim()}
            className="flex h-full min-h-[46px] items-center gap-1 border border-[#39ff14] bg-[#0a1a0a] px-3 mono text-[10px] uppercase tracking-widest text-[#39ff14] hover:bg-[#39ff14] hover:text-black disabled:opacity-40 disabled:hover:bg-[#0a1a0a] disabled:hover:text-[#39ff14]"
          >
            <Send className="h-3 w-3" /> Send
          </button>
        </div>
        {target.type === "radio" && selectedRadio && (
          <button
            data-testid="msg-simulate-reply"
            onClick={simulateReply}
            className="mt-1 mono text-[10px] text-neutral-600 hover:text-neutral-300"
            title="Testing helper: pretend the radio just replied"
          >
            + simulate a reply from {selectedRadio.callsign || `ID ${selectedRadio.dmr_id}`}
          </button>
        )}
      </div>
    </div>
  );
}

function TypeTab({ icon, label, active, onClick, testid }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`flex flex-1 items-center justify-center gap-1 border py-1 mono text-[10px] uppercase tracking-widest ${
        active
          ? "border-[#00f0ff] bg-[#001a1f] text-[#00f0ff]"
          : "border-[#2a2a2a] text-neutral-400 hover:text-neutral-100"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function MessageBubble({ m }) {
  const outbound = m.direction === "out";
  const t = m.timestamp ? format(new Date(m.timestamp), "HH:mm:ss") : "";
  return (
    <div className={`mb-2 flex ${outbound ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] border px-2 py-1 ${
          outbound
            ? "border-[#39ff14]/40 bg-[#0a1a0a] text-neutral-100"
            : "border-[#00f0ff]/40 bg-[#001a1f] text-neutral-100"
        }`}
      >
        <div className="flex items-center justify-between gap-2 text-[9px] text-neutral-500">
          <span>
            {outbound
              ? `→ ${m.is_private ? `ID ${m.to_dmr_id}` : `TG ${m.talkgroup_id}`}`
              : `← ${m.callsign || `ID ${m.from_dmr_id}`}`}
          </span>
          <span>{t}</span>
        </div>
        <div className="whitespace-pre-wrap">{m.text}</div>
        {outbound && (
          <div className="text-[9px] text-neutral-500">
            {m.delivery_status}
            {m.reached_repeaters != null && ` · ${m.reached_repeaters} MMDVM`}
          </div>
        )}
      </div>
    </div>
  );
}
