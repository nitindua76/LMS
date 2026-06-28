import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { coursesApi } from "../../api/admin";
import { getErrorMessage } from "../../api/client";

const EMPTY = {
  title: "", description: "", intro: "", duration_days: "", mandatory: false,
  passing_pct: 70, max_attempts: 3, start_date: "", enroll_close_date: "", status: "draft" as const,
};

export default function CourseForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = !!id;
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [err, setErr] = useState("");

  const { data: existing } = useQuery({
    queryKey: ["course", id],
    queryFn: () => coursesApi.get(Number(id)),
    enabled: isEdit,
  });

  useEffect(() => {
    if (existing) {
      setForm({
        title: existing.title,
        description: existing.description ?? "",
        intro: existing.intro ?? "",
        duration_days: existing.duration_days?.toString() ?? "",
        mandatory: existing.mandatory,
        passing_pct: existing.passing_pct,
        max_attempts: existing.max_attempts,
        start_date: existing.start_date ?? "",
        enroll_close_date: existing.enroll_close_date ?? "",
        status: existing.status,
      });
    }
  }, [existing]);

  const createMut = useMutation({
    mutationFn: () => coursesApi.create({
      ...form,
      duration_days: form.duration_days ? Number(form.duration_days) : undefined,
      start_date: form.start_date || undefined,
      enroll_close_date: form.enroll_close_date || undefined,
    }),
    onSuccess: (c) => navigate(`/admin/courses/${c.id}`),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const updateMut = useMutation({
    mutationFn: () => coursesApi.update(Number(id), {
      ...form,
      duration_days: form.duration_days ? Number(form.duration_days) : undefined,
      start_date: form.start_date || undefined,
      enroll_close_date: form.enroll_close_date || undefined,
    }),
    onSuccess: () => navigate(`/admin/courses/${id}`),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const isPending = createMut.isPending || updateMut.isPending;
  const F = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [field]: e.target.value }));

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link to={isEdit ? `/admin/courses/${id}` : "/admin/courses"} style={{ color: "var(--text-muted)" }}>←</Link>
          <h1>{isEdit ? "Edit Course" : "New Course"}</h1>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 600 }}>
        <div className="form-group">
          <label>Title *</label>
          <input value={form.title} onChange={F("title")} placeholder="Course title" required />
        </div>
        <div className="form-group">
          <label>Description</label>
          <textarea rows={3} value={form.description} onChange={F("description")} placeholder="Short description" style={{ resize: "vertical" }} />
        </div>
        <div className="form-group">
          <label>Intro (shown on course card)</label>
          <textarea rows={4} value={form.intro} onChange={F("intro")} placeholder="Intro text shown to employees" style={{ resize: "vertical" }} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }} className="form-group">
          <div>
            <label>Duration (days)</label>
            <input type="number" min={1} value={form.duration_days} onChange={F("duration_days")} placeholder="30" />
          </div>
          <div>
            <label>Passing %</label>
            <input type="number" min={0} max={100} value={form.passing_pct} onChange={F("passing_pct")} />
          </div>
          <div>
            <label>Max Attempts</label>
            <input type="number" min={1} value={form.max_attempts} onChange={F("max_attempts")} />
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }} className="form-group">
          <div>
            <label>Start Date</label>
            <input type="date" value={form.start_date} onChange={F("start_date")} />
          </div>
          <div>
            <label>Enroll Close Date</label>
            <input type="date" value={form.enroll_close_date} onChange={F("enroll_close_date")} />
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }} className="form-group">
          <div>
            <label>Status</label>
            <select value={form.status} onChange={F("status")}>
              <option value="draft">Draft</option>
              <option value="published">Published</option>
              <option value="archived">Archived</option>
            </select>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, paddingTop: 20 }}>
            <input type="checkbox" id="mandatory" checked={form.mandatory}
              onChange={(e) => setForm(f => ({ ...f, mandatory: e.target.checked }))}
              style={{ width: "auto" }} />
            <label htmlFor="mandatory" style={{ marginBottom: 0, textTransform: "none", letterSpacing: 0 }}>Mandatory course</label>
          </div>
        </div>

        {err && <p className="error-msg" style={{ marginBottom: 12 }}>{err}</p>}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-primary" onClick={() => isEdit ? updateMut.mutate() : createMut.mutate()} disabled={isPending || !form.title.trim()}>
            {isPending ? "Saving…" : isEdit ? "Save Changes" : "Create Course"}
          </button>
          <Link to={isEdit ? `/admin/courses/${id}` : "/admin/courses"}>
            <button className="btn-ghost">Cancel</button>
          </Link>
        </div>
      </div>
    </div>
  );
}
