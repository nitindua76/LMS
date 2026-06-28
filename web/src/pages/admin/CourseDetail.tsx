import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  coursesApi, sectionsApi, contentApi, quizzesApi,
  disciplinesApi, levelsApi, packagesApi,
  Section, ContentItem, Quiz, Question,
} from "../../api/admin";
import { getErrorMessage } from "../../api/client";

const STATUS_BADGE: Record<string, string> = {
  draft: "badge-yellow", published: "badge-green", archived: "badge-gray",
};

export default function CourseDetail() {
  const { id } = useParams<{ id: string }>();
  const courseId = Number(id);
  const qc = useQueryClient();
  const [err, setErr] = useState("");

  // ── Data ──────────────────────────────────────────────────────────────────
  const { data: course, isLoading } = useQuery({
    queryKey: ["course", courseId],
    queryFn: () => coursesApi.get(courseId),
  });
  const { data: sections } = useQuery({
    queryKey: ["sections", courseId],
    queryFn: () => sectionsApi.list(courseId),
    enabled: !!courseId,
  });
  const { data: disciplines } = useQuery({ queryKey: ["disciplines"], queryFn: () => disciplinesApi.list() });
  const { data: levels } = useQuery({ queryKey: ["levels"], queryFn: () => levelsApi.list() });

  // ── Section form ──────────────────────────────────────────────────────────
  const [newSectionTitle, setNewSectionTitle] = useState("");
  const addSectionMut = useMutation({
    mutationFn: () => sectionsApi.create(courseId, {
      order_index: (sections?.length ?? 0) + 1,
      title: newSectionTitle.trim(),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["sections", courseId] }); setNewSectionTitle(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const deleteSectionMut = useMutation({
    mutationFn: (sid: number) => sectionsApi.delete(courseId, sid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sections", courseId] }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  // ── Target form & Bulk Assignments ─────────────────────────────────────────
  const [selectedDisciplines, setSelectedDisciplines] = useState<Record<number, boolean>>({});
  const [selectedLevels, setSelectedLevels] = useState<Record<number, boolean>>({});
  const [bulkPending, setBulkPending] = useState(false);

  const toggleDiscipline = (id: number) => setSelectedDisciplines(p => ({ ...p, [id]: !p[id] }));
  const toggleLevel = (id: number) => setSelectedLevels(p => ({ ...p, [id]: !p[id] }));

  const selectAllDisciplines = () => {
    const next: Record<number, boolean> = {};
    disciplines?.items.forEach(d => { next[d.id] = true; });
    setSelectedDisciplines(next);
  };
  const clearDisciplines = () => setSelectedDisciplines({});

  const selectAllLevels = () => {
    const next: Record<number, boolean> = {};
    levels?.items.forEach(l => { next[l.id] = true; });
    setSelectedLevels(next);
  };
  const clearLevels = () => setSelectedLevels({});

  const removeTargetMut = useMutation({
    mutationFn: (tid: number) => coursesApi.removeTarget(courseId, tid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["course", courseId] }),
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const handleBulkAdd = async () => {
    const checkedDiscs = Object.entries(selectedDisciplines).filter(([_, val]) => val).map(([id]) => Number(id));
    const checkedLvls = Object.entries(selectedLevels).filter(([_, val]) => val).map(([id]) => Number(id));
    if (checkedDiscs.length === 0 || checkedLvls.length === 0) return;

    setBulkPending(true);
    setErr("");
    const existingCombos = new Set(course.targets.map(t => `${t.discipline_id}-${t.level_id}`));
    const promises: Promise<any>[] = [];

    checkedDiscs.forEach(dId => {
      checkedLvls.forEach(lId => {
        if (!existingCombos.has(`${dId}-${lId}`)) {
          promises.push(coursesApi.addTarget(courseId, { discipline_id: dId, level_id: lId }));
        }
      });
    });

    try {
      await Promise.all(promises);
      qc.invalidateQueries({ queryKey: ["course", courseId] });
      setSelectedDisciplines({});
      setSelectedLevels({});
    } catch (e: any) {
      setErr(getErrorMessage(e));
    } finally {
      setBulkPending(false);
    }
  };

  const handleTargetEveryone = async () => {
    if (!disciplines || !levels) return;
    setBulkPending(true);
    setErr("");
    const existingCombos = new Set(course.targets.map(t => `${t.discipline_id}-${t.level_id}`));
    const promises: Promise<any>[] = [];

    disciplines.items.forEach(d => {
      levels.items.forEach(l => {
        if (!existingCombos.has(`${d.id}-${l.id}`)) {
          promises.push(coursesApi.addTarget(courseId, { discipline_id: d.id, level_id: l.id }));
        }
      });
    });

    try {
      await Promise.all(promises);
      qc.invalidateQueries({ queryKey: ["course", courseId] });
    } catch (e: any) {
      setErr(getErrorMessage(e));
    } finally {
      setBulkPending(false);
    }
  };

  const handleClearAllTargets = async () => {
    if (!confirm("Are you sure you want to clear all assignment targets?")) return;
    setBulkPending(true);
    setErr("");
    try {
      const promises = course.targets.map(t => coursesApi.removeTarget(courseId, t.id));
      await Promise.all(promises);
      qc.invalidateQueries({ queryKey: ["course", courseId] });
    } catch (e: any) {
      setErr(getErrorMessage(e));
    } finally {
      setBulkPending(false);
    }
  };

  const handleRemoveDisciplineGroup = async (targetList: typeof course.targets) => {
    if (!confirm("Are you sure you want to remove all targets for this department?")) return;
    setBulkPending(true);
    setErr("");
    try {
      const promises = targetList.map(t => coursesApi.removeTarget(courseId, t.id));
      await Promise.all(promises);
      qc.invalidateQueries({ queryKey: ["course", courseId] });
    } catch (e: any) {
      setErr(getErrorMessage(e));
    } finally {
      setBulkPending(false);
    }
  };

  if (isLoading) return <div className="center"><div className="spinner" /></div>;
  if (!course) return <div>Course not found</div>;

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link to="/admin/courses" style={{ color: "var(--text-muted)" }}>← Courses</Link>
          <h1>{course.title}</h1>
          <span className={`badge ${STATUS_BADGE[course.status]}`}>{course.status}</span>
          {course.mandatory && <span className="badge badge-red">Mandatory</span>}
        </div>
        <Link to={`/admin/courses/${courseId}/edit`}>
          <button className="btn-ghost">Edit Course</button>
        </Link>
      </div>

      {err && <div style={{ color: "var(--danger)", marginBottom: 12 }}>{err}</div>}

      {/* Course Info */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
          <div><span style={{ color: "var(--text-muted)", fontSize: 11 }}>PASSING %</span><div style={{ fontWeight: 600, marginTop: 2 }}>{course.passing_pct}%</div></div>
          <div><span style={{ color: "var(--text-muted)", fontSize: 11 }}>MAX ATTEMPTS</span><div style={{ fontWeight: 600, marginTop: 2 }}>{course.max_attempts}</div></div>
          <div><span style={{ color: "var(--text-muted)", fontSize: 11 }}>DURATION</span><div style={{ fontWeight: 600, marginTop: 2 }}>{course.duration_days ? `${course.duration_days} days` : "—"}</div></div>
        </div>
        {course.description && <p style={{ marginTop: 12, color: "var(--text-muted)", fontSize: 13 }}>{course.description}</p>}
      </div>

      {/* Targets */}
      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginBottom: 12, fontSize: 14, fontWeight: 600 }}>Assignment Targets</h3>
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16 }}>
          Employees matching any of these discipline + level combos will see this course.
        </p>

        {/* Grouped Targets Display */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
          {(() => {
            if (course.targets.length === 0) {
              return <span style={{ color: "var(--text-muted)", fontSize: 12 }}>No targets — course is not visible to any employee.</span>;
            }
            const byDiscipline: Record<string, typeof course.targets> = {};
            course.targets.forEach(t => {
              const name = disciplines?.items.find(d => d.id === t.discipline_id)?.name ?? `Dept ${t.discipline_id}`;
              if (!byDiscipline[name]) byDiscipline[name] = [];
              byDiscipline[name].push(t);
            });

            return Object.entries(byDiscipline).map(([discName, targets]) => (
              <div key={discName} style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 8,
                padding: "8px 12px",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: 6
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ fontWeight: 700, fontSize: 12, color: "var(--text)" }}>{discName}:</span>
                  <button
                    onClick={() => handleRemoveDisciplineGroup(targets)}
                    style={{
                      background: "rgba(239, 68, 68, 0.1)",
                      border: "1px solid rgba(239, 68, 68, 0.2)",
                      color: "var(--danger)",
                      cursor: "pointer",
                      fontSize: 10,
                      fontWeight: 600,
                      padding: "2px 6px",
                      borderRadius: 4,
                      textTransform: "none",
                      letterSpacing: "normal"
                    }}
                    title={`Remove all targets for ${discName}`}
                    disabled={bulkPending || removeTargetMut.isPending}
                  >
                    Remove Department
                  </button>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {targets.map(t => {
                    const code = levels?.items.find(l => l.id === t.level_id)?.code ?? `L${t.level_id}`;
                    return (
                      <span key={t.id} className="badge badge-gray" style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        fontSize: 11
                      }}>
                        {code}
                        <button
                          onClick={() => removeTargetMut.mutate(t.id)}
                          style={{
                            background: "none",
                            border: "none",
                            color: "var(--danger)",
                            padding: 0,
                            cursor: "pointer",
                            fontSize: 10,
                            lineHeight: 1
                          }}
                          title="Remove target combo"
                          disabled={removeTargetMut.isPending}
                        >
                          ✕
                        </button>
                      </span>
                    );
                  })}
                </div>
              </div>
            ));
          })()}
        </div>

        {/* Bulk Target Builder Toolbar */}
        <h4 style={{ margin: "0 0 10px", fontSize: 13, fontWeight: 700 }}>Bulk Assignment Assigner</h4>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, marginBottom: 16 }}>
          
          {/* Disciplines Column */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>Departments</span>
              <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
                <button className="btn-ghost" style={{ padding: "2px 6px", fontSize: 10 }} onClick={selectAllDisciplines}>Select All</button>
                <button className="btn-ghost" style={{ padding: "2px 6px", fontSize: 10 }} onClick={clearDisciplines}>Clear</button>
              </div>
            </div>
            <div style={{
              maxHeight: 150,
              overflowY: "auto",
              border: "1px solid var(--border)",
              padding: "6px",
              borderRadius: 6,
              background: "var(--bg-surface)"
            }}>
              {disciplines?.items.map(d => (
                <label key={d.id} style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  fontSize: "12px",
                  padding: "4px 6px",
                  cursor: "pointer",
                  textTransform: "none",
                  letterSpacing: "normal",
                  fontWeight: "normal",
                  marginBottom: 0
                }} className="hover-row">
                  <input
                    type="checkbox"
                    style={{
                      width: "14px",
                      height: "14px",
                      margin: 0,
                      cursor: "pointer",
                      flexShrink: 0
                    }}
                    checked={!!selectedDisciplines[d.id]}
                    onChange={() => toggleDiscipline(d.id)}
                  />
                  <span style={{ color: "var(--text)" }}>{d.name}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Levels Column */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>Levels</span>
              <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
                <button className="btn-ghost" style={{ padding: "2px 6px", fontSize: 10 }} onClick={selectAllLevels}>Select All</button>
                <button className="btn-ghost" style={{ padding: "2px 6px", fontSize: 10 }} onClick={clearLevels}>Clear</button>
              </div>
            </div>
            <div style={{
              maxHeight: 150,
              overflowY: "auto",
              border: "1px solid var(--border)",
              padding: "6px",
              borderRadius: 6,
              background: "var(--bg-surface)"
            }}>
              {levels?.items.sort((a, b) => a.rank - b.rank).map(l => (
                <label key={l.id} style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  fontSize: "12px",
                  padding: "4px 6px",
                  cursor: "pointer",
                  textTransform: "none",
                  letterSpacing: "normal",
                  fontWeight: "normal",
                  marginBottom: 0
                }} className="hover-row">
                  <input
                    type="checkbox"
                    style={{
                      width: "14px",
                      height: "14px",
                      margin: 0,
                      cursor: "pointer",
                      flexShrink: 0
                    }}
                    checked={!!selectedLevels[l.id]}
                    onChange={() => toggleLevel(l.id)}
                  />
                  <span style={{ color: "var(--text)" }}>{l.code} ({l.name})</span>
                </label>
              ))}
            </div>
          </div>

        </div>

        {/* Command Buttons */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
          {(() => {
            const checkedDiscs = Object.values(selectedDisciplines).filter(Boolean).length;
            const checkedLvls = Object.values(selectedLevels).filter(Boolean).length;
            const comboCount = checkedDiscs * checkedLvls;
            return (
              <button
                className="btn-primary"
                onClick={handleBulkAdd}
                disabled={comboCount === 0 || bulkPending}
              >
                {bulkPending ? "Processing..." : `Add Checked Targets (${comboCount})`}
              </button>
            );
          })()}

          <button
            className="btn-secondary"
            onClick={handleTargetEveryone}
            disabled={bulkPending || !disciplines || !levels}
            title="Assign course to all departments and all levels"
          >
            Target Everyone
          </button>

          {course.targets.length > 0 && (
            <button
              className="btn-danger"
              onClick={handleClearAllTargets}
              disabled={bulkPending}
            >
              Clear All Targets
            </button>
          )}
        </div>
      </div>

      {/* Sections */}
      <div className="card">
        <h3 style={{ marginBottom: 16, fontSize: 14, fontWeight: 600 }}>Sections</h3>
        {sections?.map((s: Section) => (
          <SectionRow key={s.id} section={s} courseId={courseId} onError={setErr} />
        ))}
        {sections?.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: 12 }}>No sections yet.</p>}

        <div style={{ display: "flex", gap: 8, marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
          <input
            placeholder="New section title…"
            value={newSectionTitle}
            onChange={(e) => setNewSectionTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && newSectionTitle.trim() && addSectionMut.mutate()}
          />
          <button className="btn-primary" onClick={() => addSectionMut.mutate()}
            disabled={!newSectionTitle.trim() || addSectionMut.isPending} style={{ whiteSpace: "nowrap" }}>
            Add Section
          </button>
        </div>
      </div>
    </div>
  );
}

function SectionRow({ section, courseId, onError }: { section: Section; courseId: number; onError: (e: string) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editTitle, setEditTitle] = useState(false);
  const [title, setTitle] = useState(section.title);
  const [newContent, setNewContent] = useState({ type: "video", url: "", video_duration_sec: "" });
  const [showQuiz, setShowQuiz] = useState(false);

  const updateMut = useMutation({
    mutationFn: () => sectionsApi.update(courseId, section.id, { title }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["sections", courseId] }); setEditTitle(false); },
    onError: (e) => onError(getErrorMessage(e)),
  });
  const deleteMut = useMutation({
    mutationFn: () => sectionsApi.delete(courseId, section.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sections", courseId] }),
    onError: (e) => onError(getErrorMessage(e)),
  });
  const addContentMut = useMutation({
    mutationFn: () => contentApi.create(courseId, section.id, {
      order_index: (section.content_items.length ?? 0) + 1,
      type: newContent.type as "video" | "pdf",
      url: newContent.url,
      video_duration_sec: newContent.video_duration_sec ? Number(newContent.video_duration_sec) : undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["sections", courseId] }); setNewContent({ type: "video", url: "", video_duration_sec: "" }); },
    onError: (e) => onError(getErrorMessage(e)),
  });
  const deleteContentMut = useMutation({
    mutationFn: (itemId: number) => contentApi.delete(courseId, section.id, itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sections", courseId] }),
    onError: (e) => onError(getErrorMessage(e)),
  });

  const uploadPackageMut = useMutation({
    mutationFn: ({ itemId, file }: { itemId: number; file: File }) => packagesApi.import(itemId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sections", courseId] });
      alert("Package uploaded and registered successfully!");
    },
    onError: (e) => onError(getErrorMessage(e)),
  });

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 4, marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", padding: "10px 14px", gap: 8, cursor: "pointer" }}
        onClick={() => setOpen(o => !o)}>
        <span style={{ color: "var(--text-muted)", fontSize: 12, minWidth: 24 }}>#{section.order_index}</span>
        {editTitle ? (
          <input value={title} onChange={(e) => setTitle(e.target.value)} onClick={(e) => e.stopPropagation()} autoFocus style={{ flex: 1 }} />
        ) : (
          <span style={{ flex: 1, fontWeight: 500 }}>{section.title}</span>
        )}
        <div style={{ display: "flex", gap: 4 }} onClick={(e) => e.stopPropagation()}>
          {editTitle ? (
            <>
              <button className="btn-primary" style={{ padding: "3px 8px" }} onClick={() => updateMut.mutate()}>Save</button>
              <button className="btn-ghost" style={{ padding: "3px 8px" }} onClick={() => setEditTitle(false)}>Cancel</button>
            </>
          ) : (
            <button className="btn-ghost" style={{ padding: "3px 8px" }} onClick={() => setEditTitle(true)}>Rename</button>
          )}
          <button className="btn-danger" style={{ padding: "3px 8px" }}
            onClick={() => { if (confirm("Delete section?")) deleteMut.mutate(); }}>Del</button>
        </div>
        <span style={{ color: "var(--text-muted)" }}>{open ? "▲" : "▼"}</span>
      </div>

      {open && (
        <div style={{ padding: "0 14px 14px", borderTop: "1px solid var(--border)" }}>
          {/* Content items */}
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>Content</div>
            {section.content_items.map((ci: ContentItem) => (
              <div key={ci.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                <span className={`badge ${
                  ci.type === "video" ? "badge-blue" :
                  ci.type === "pdf" ? "badge-gray" :
                  ci.type === "scorm" ? "badge-green" :
                  "badge-yellow" // cmi5
                }`}>{ci.type}</span>
                <span style={{ flex: 1, fontSize: 12, color: "var(--text-muted)", wordBreak: "break-all" }}>{ci.url}</span>
                {ci.video_duration_sec && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{Math.round(ci.video_duration_sec / 60)}m</span>}
                
                {/* SCORM/cmi5 package zip upload */}
                <label className="btn-ghost" style={{ padding: "2px 8px", fontSize: 11, cursor: "pointer", display: "inline-flex", alignItems: "center", margin: 0 }}>
                  {uploadPackageMut.isPending && uploadPackageMut.variables?.itemId === ci.id ? "Uploading..." : "Upload ZIP"}
                  <input
                    type="file"
                    accept=".zip"
                    style={{ display: "none" }}
                    disabled={uploadPackageMut.isPending}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        uploadPackageMut.mutate({ itemId: ci.id, file });
                      }
                    }}
                  />
                </label>

                <button onClick={() => deleteContentMut.mutate(ci.id)} style={{ background: "none", color: "var(--danger)", fontSize: 12, padding: "2px 4px" }}>✕</button>
              </div>
            ))}
            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              <select value={newContent.type} onChange={(e) => setNewContent(c => ({ ...c, type: e.target.value }))} style={{ width: 90 }}>
                <option value="video">Video</option>
                <option value="pdf">PDF</option>
              </select>
              <input placeholder="URL / path" value={newContent.url} onChange={(e) => setNewContent(c => ({ ...c, url: e.target.value }))} />
              {newContent.type === "video" && (
                <input type="number" placeholder="Duration (sec)" value={newContent.video_duration_sec}
                  onChange={(e) => setNewContent(c => ({ ...c, video_duration_sec: e.target.value }))} style={{ width: 120 }} />
              )}
              <button className="btn-primary" onClick={() => addContentMut.mutate()} disabled={!newContent.url.trim()} style={{ whiteSpace: "nowrap" }}>Add</button>
            </div>
          </div>

          {/* Quiz */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>Quiz</div>
            <QuizSection courseId={courseId} sectionId={section.id} onError={onError} />
          </div>
        </div>
      )}
    </div>
  );
}

function QuizSection({ courseId, sectionId, onError }: { courseId: number; sectionId: number; onError: (e: string) => void }) {
  const qc = useQueryClient();
  const [addQuestion, setAddQuestion] = useState(false);
  const [qForm, setQForm] = useState({ type: "mcq_single", text: "", marks: 1, timer_sec: 60, options: [{ text: "", is_correct: false }, { text: "", is_correct: false }] });

  const { data: quiz, isLoading } = useQuery({
    queryKey: ["quiz", courseId, sectionId],
    queryFn: () => quizzesApi.get(courseId, sectionId),
    retry: false,
  });

  const createQuizMut = useMutation({
    mutationFn: () => quizzesApi.create(courseId, sectionId, { passing_pct: 70, max_attempts: 3 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quiz", courseId, sectionId] }),
    onError: (e) => onError(getErrorMessage(e)),
  });
  const deleteQuizMut = useMutation({
    mutationFn: () => quizzesApi.delete(courseId, sectionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quiz", courseId, sectionId] }),
    onError: (e) => onError(getErrorMessage(e)),
  });
  const addQuestionMut = useMutation({
    mutationFn: () => quizzesApi.createQuestion(courseId, sectionId, {
      ...qForm,
      order_index: (quiz?.questions.length ?? 0) + 1,
      options: qForm.options.map((o, i) => ({ order_index: i + 1, text: o.text, is_correct: o.is_correct })),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["quiz", courseId, sectionId] }); setAddQuestion(false); },
    onError: (e) => onError(getErrorMessage(e)),
  });
  const deleteQuestionMut = useMutation({
    mutationFn: (qid: number) => quizzesApi.deleteQuestion(courseId, sectionId, qid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quiz", courseId, sectionId] }),
    onError: (e) => onError(getErrorMessage(e)),
  });

  if (isLoading) return <div className="spinner" style={{ width: 16, height: 16 }} />;

  if (!quiz) {
    return (
      <button className="btn-ghost" style={{ fontSize: 12 }} onClick={() => createQuizMut.mutate()} disabled={createQuizMut.isPending}>
        + Add Quiz to this section
      </button>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 12 }}>Passing: <strong>{quiz.passing_pct}%</strong> · Max attempts: <strong>{quiz.max_attempts}</strong></span>
        <button className="btn-danger" style={{ padding: "2px 8px", fontSize: 11 }}
          onClick={() => { if (confirm("Delete quiz and all questions?")) deleteQuizMut.mutate(); }}>Delete Quiz</button>
      </div>
      {quiz.questions.map((q: Question) => (
        <div key={q.id} style={{ background: "var(--bg-elevated)", borderRadius: 4, padding: "8px 12px", marginBottom: 6 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div style={{ fontSize: 13 }}><span className="badge badge-gray">{q.type}</span> {q.text}</div>
            <button onClick={() => deleteQuestionMut.mutate(q.id)} style={{ background: "none", color: "var(--danger)", fontSize: 12, padding: 2 }}>✕</button>
          </div>
          <div style={{ marginTop: 6 }}>
            {q.options.map((o) => (
              <div key={o.id} style={{ fontSize: 12, color: o.is_correct ? "var(--success)" : "var(--text-muted)", padding: "2px 0" }}>
                {o.is_correct ? "✓" : "○"} {o.text}
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{q.marks}pt · {q.timer_sec}s</div>
        </div>
      ))}

      {addQuestion ? (
        <div style={{ background: "var(--bg-elevated)", borderRadius: 4, padding: 12, marginTop: 8 }}>
          <div className="form-group">
            <label>Type</label>
            <select value={qForm.type} onChange={(e) => setQForm(f => ({ ...f, type: e.target.value }))}>
              <option value="mcq_single">MCQ (single answer)</option>
              <option value="mcq_multi">MCQ (multi answer)</option>
              <option value="true_false">True / False</option>
            </select>
          </div>
          <div className="form-group">
            <label>Question Text</label>
            <textarea rows={2} value={qForm.text} onChange={(e) => setQForm(f => ({ ...f, text: e.target.value }))} style={{ resize: "vertical" }} />
          </div>
          <div style={{ display: "flex", gap: 8 }} className="form-group">
            <div style={{ flex: 1 }}><label>Marks</label><input type="number" min={1} value={qForm.marks} onChange={(e) => setQForm(f => ({ ...f, marks: Number(e.target.value) }))} /></div>
            <div style={{ flex: 1 }}><label>Timer (sec)</label><input type="number" min={5} value={qForm.timer_sec} onChange={(e) => setQForm(f => ({ ...f, timer_sec: Number(e.target.value) }))} /></div>
          </div>
          <div className="form-group">
            <label>Options (mark correct ones)</label>
            {qForm.options.map((opt, i) => (
              <div key={i} style={{ display: "flex", gap: 6, marginBottom: 4, alignItems: "center" }}>
                <input type="checkbox" checked={opt.is_correct}
                  onChange={(e) => setQForm(f => ({ ...f, options: f.options.map((o, j) => j === i ? { ...o, is_correct: e.target.checked } : (qForm.type === "mcq_single" ? { ...o, is_correct: false } : o)) }))}
                  style={{ width: "auto", flex: "none" }} />
                <input value={opt.text} onChange={(e) => setQForm(f => ({ ...f, options: f.options.map((o, j) => j === i ? { ...o, text: e.target.value } : o) }))} placeholder={`Option ${i + 1}`} />
                {qForm.type !== "true_false" && qForm.options.length > 2 && (
                  <button onClick={() => setQForm(f => ({ ...f, options: f.options.filter((_, j) => j !== i) }))} style={{ background: "none", color: "var(--danger)", padding: 0, flex: "none" }}>✕</button>
                )}
              </div>
            ))}
            {qForm.type !== "true_false" && (
              <button className="btn-ghost" style={{ fontSize: 11, marginTop: 4 }}
                onClick={() => setQForm(f => ({ ...f, options: [...f.options, { text: "", is_correct: false }] }))}>
                + Add option
              </button>
            )}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn-primary" onClick={() => addQuestionMut.mutate()} disabled={addQuestionMut.isPending || !qForm.text.trim()}>Add Question</button>
            <button className="btn-ghost" onClick={() => setAddQuestion(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <button className="btn-ghost" style={{ fontSize: 12, marginTop: 8 }} onClick={() => setAddQuestion(true)}>+ Add Question</button>
      )}
    </div>
  );
}
