import { useEffect, useState } from "react";
import { useDataChannel } from "@livekit/components-react";

/**
 * Listens on the "admin_notice" data-channel topic (see
 * api/app/routers/admin/rooms.py's broadcast endpoint) and shows a
 * dismissible, clearly-labeled banner when an admin sends one. This is the
 * visible-intervention path — an admin flagging a session as off-topic or
 * asking people to wrap up — used instead of ever silently joining a call.
 * Shared between LiveSessionRoom.tsx (training sessions) and RoomCall.tsx
 * (Instant Rooms), since both are LiveKit rooms an admin can moderate.
 */
export default function AdminNoticeBanner() {
  const [notice, setNotice] = useState<string | null>(null);

  const { message } = useDataChannel("admin_notice");

  useEffect(() => {
    if (!message) return;
    try {
      const decoded = new TextDecoder().decode(message.payload);
      const parsed = JSON.parse(decoded);
      if (parsed?.type === "admin_notice" && typeof parsed.message === "string") {
        setNotice(parsed.message);
      }
    } catch {
      // malformed payload — ignore rather than crash the call
    }
  }, [message]);

  if (!notice) return null;

  return (
    <div className="admin-notice-banner" role="alert">
      <span className="admin-notice-banner-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          <path d="M12 9v4M12 17h.01" />
        </svg>
      </span>
      <div>
        <div className="admin-notice-banner-title">Message from an administrator</div>
        <div className="admin-notice-banner-text">{notice}</div>
      </div>
      <button className="admin-notice-banner-dismiss" onClick={() => setNotice(null)} aria-label="Dismiss">✕</button>
    </div>
  );
}
