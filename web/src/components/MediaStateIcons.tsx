// Shared camera/mic/screen-share glyphs — used by both the admin Live
// Sessions dashboard (Instant Rooms + live LiveSessions) and the per-course
// session attendance history panel, so the same "who's on camera/sharing
// their screen" visual language appears everywhere this data shows up.
export function MediaStateIcon({ path, active }: { path: string; active: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
      stroke={active ? "var(--success)" : "var(--text-muted)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      style={{ opacity: active ? 1 : 0.4 }}>
      <path d={path} />
    </svg>
  );
}

export const CAMERA_ICON_PATH = "M23 7l-7 5 7 5V7zM1 5h15a2 2 0 012 2v10a2 2 0 01-2 2H1a2 2 0 01-2-2V7a2 2 0 012-2z";
export const MIC_ICON_PATH = "M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3zM19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8";
export const SCREEN_ICON_PATH = "M3 4h18v12H3zM8 21h8M12 16v5";
