import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { settingsApi, SystemSetting } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

// Grouped purely for presentation — the backend treats every key the same way.
const GROUPS: { title: string; description: string; keys: string[] }[] = [
  {
    title: "Single Sign-On (CPF login)",
    description:
      "Credential verification against the corporate SSO API. Leave the base URL blank to disable CPF login entirely — existing email/password accounts keep working either way. Enter the full chkCredential endpoint URL, including its path.",
    keys: ["SSO_API_BASE_URL", "SSO_API_TIMEOUT_SECONDS", "SSO_SERVER", "ENABLE_LOCAL_LOGIN_FALLBACK"],
  },
  {
    title: "Employee directory sync",
    description:
      "Fetches profile and reporting-hierarchy details (controlling officer, L1/L2, HR contact) after a successful SSO login. Always runs in the background after sign-in completes, so a slow response here never adds to login time.",
    keys: ["EMPLOYEE_API_BASE_URL", "EMPLOYEE_API_KEY", "EMPLOYEE_API_TIMEOUT_SECONDS", "EMPLOYEE_SYNC_ON_LOGIN"],
  },
  {
    title: "Instant Rooms",
    description:
      "Day-to-day meeting rooms available to every employee. Turn off to immediately stop new rooms from being created — does not end rooms already in progress (use the Live Sessions dashboard for that).",
    keys: ["INSTANT_ROOMS_ENABLED", "FRONTEND_URL"],
  },
  {
    title: "Meeting link auto-mail",
    description:
      "Automatically emails a join link when someone is added to a room, using the corporate mail API. Use the literal placeholders {mailid} (recipient's email), {link} (the actual meeting link), and {name} (the room's display name) anywhere in the URL — all three are substituted at send time. Leave blank to disable auto-mail; the copy-link button keeps working either way.",
    keys: ["MAIL_API_URL_TEMPLATE", "MAIL_API_TIMEOUT_SECONDS"],
  },
];

const LABELS: Record<string, string> = {
  SSO_API_BASE_URL: "SSO API URL (full chkCredential endpoint)",
  SSO_API_TIMEOUT_SECONDS: "SSO request timeout (seconds)",
  SSO_SERVER: "SSO directory server (usually AD)",
  ENABLE_LOCAL_LOGIN_FALLBACK: "Allow local email/password sign-in",
  EMPLOYEE_API_BASE_URL: "Employee API base URL",
  EMPLOYEE_API_KEY: "Employee API key",
  EMPLOYEE_API_TIMEOUT_SECONDS: "Employee API timeout (seconds)",
  EMPLOYEE_SYNC_ON_LOGIN: "Refresh employee details on every login",
  INSTANT_ROOMS_ENABLED: "Instant Rooms enabled",
  FRONTEND_URL: "App URL (used to build shareable join links)",
  MAIL_API_URL_TEMPLATE: "Mail API URL template",
  MAIL_API_TIMEOUT_SECONDS: "Mail API timeout (seconds)",
};

const PLACEHOLDERS: Record<string, string> = {
  MAIL_API_URL_TEMPLATE:
    "https://host:8089/MailApi/mail?mailid={mailid}&msg=...&subject=...&template=LMS_LINK&templateparams=templateBody::{link},,templateHeader::...",
};

function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="settings-toggle"
      data-on={checked}
    >
      <span className="settings-toggle-knob" />
    </button>
  );
}

function SettingRow({ setting, onSave }: { setting: SystemSetting; onSave: (key: string, value: string) => void }) {
  const [value, setValue] = useState(setting.value);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setValue(setting.value);
    setDirty(false);
  }, [setting.value]);

  const label = LABELS[setting.key] ?? setting.key;

  if (setting.is_bool) {
    return (
      <div className="settings-row">
        <div>
          <div className="settings-row-label">{label}</div>
        </div>
        <Toggle
          checked={value.toLowerCase() === "true"}
          onChange={(v) => { const next = String(v); setValue(next); onSave(setting.key, next); }}
        />
      </div>
    );
  }

  return (
    <div className="settings-row">
      <div style={{ flex: 1 }}>
        <div className="settings-row-label">{label}</div>
        <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
          <input
            type={setting.is_secret ? "password" : "text"}
            value={value}
            onChange={(e) => { setValue(e.target.value); setDirty(true); }}
            placeholder={PLACEHOLDERS[setting.key] ?? (setting.is_secret ? "Not set" : "Not set — feature disabled")}
            style={{ flex: 1, maxWidth: 480 }}
          />
          {dirty && (
            <>
              <button className="btn-primary" style={{ padding: "6px 14px" }}
                onClick={() => { onSave(setting.key, value); setDirty(false); }}>
                Save
              </button>
              <button className="btn-ghost" style={{ padding: "6px 14px" }}
                onClick={() => { setValue(setting.value); setDirty(false); }}>
                Cancel
              </button>
            </>
          )}
        </div>
        {setting.is_secret && setting.is_set && !dirty && (
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            A key is currently saved. Type a new value to replace it.
          </div>
        )}
      </div>
    </div>
  );
}

export default function Settings() {
  const qc = useQueryClient();
  const [err, setErr] = useState("");
  const [savedKey, setSavedKey] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: () => settingsApi.list(),
  });

  const updateMut = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => settingsApi.update(key, value),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] });
      setErr("");
      setSavedKey(vars.key);
      setTimeout(() => setSavedKey((k) => (k === vars.key ? null : k)), 2000);
    },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const byKey = new Map((data ?? []).map((s) => [s.key, s]));

  return (
    <div>
      <div className="page-header">
        <h1>System Settings</h1>
        <p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
          Changes apply immediately across the app — no restart required.
        </p>
      </div>

      {err && <p className="error-msg" style={{ marginBottom: 16 }}>{err}</p>}

      {isLoading ? (
        <div className="center"><div className="spinner" /></div>
      ) : (
        GROUPS.map((group) => (
          <div className="card" key={group.title} style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{group.title}</h3>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 16, maxWidth: 640, lineHeight: 1.5 }}>
              {group.description}
            </p>
            <div className="settings-group">
              {group.keys.map((key) => {
                const setting = byKey.get(key);
                if (!setting) return null;
                return (
                  <div key={key} style={{ position: "relative" }}>
                    <SettingRow
                      setting={setting}
                      onSave={(k, v) => updateMut.mutate({ key: k, value: v })}
                    />
                    {savedKey === key && <span className="settings-saved-pill">Saved</span>}
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
