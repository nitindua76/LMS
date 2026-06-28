import { useState, useEffect, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { employeeApi, SectionDetail } from "../../api/employee";
import QuizRunner from "../../components/QuizRunner";

export default function SectionPlayer() {
  const { courseId, enrollmentId, sectionId } = useParams<{
    courseId: string;
    enrollmentId: string;
    sectionId: string;
  }>();
  const cId = Number(courseId);
  const eId = Number(enrollmentId);
  const sId = Number(sectionId);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data: course } = useQuery({
    queryKey: ["my-course", cId],
    queryFn: () => employeeApi.courseDetail(cId),
  });

  const section: SectionDetail | undefined = course?.sections.find((s) => s.id === sId);
  const item = section?.content_items[0];

  const getPackageId = () => {
    if (!item?.url) return null;
    try {
      const urlObj = new URL(item.url);
      return Number(urlObj.searchParams.get("pkg"));
    } catch {
      return null;
    }
  };
  const packageId = getPackageId();

  const { data: progress, refetch: refetchProgress } = useQuery({
    queryKey: ["scorm-progress", eId, packageId],
    queryFn: () => employeeApi.scormProgress(eId, packageId!),
    enabled: !!eId && !!packageId,
  });

  const [phase, setPhase] = useState<"content" | "quiz" | "done">("content");
  const [contentDone, setContentDone] = useState(false);
  const [pdfDwell, setPdfDwell] = useState(0);
  const [pdfSubmitted, setPdfSubmitted] = useState(false);
  const [scormComplete, setScormComplete] = useState(false);
  const [quizResult, setQuizResult] = useState<{ passed: boolean; score: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showMobileToc, setShowMobileToc] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toc, setToc] = useState<any[]>([]);
  const [activeSco, setActiveSco] = useState<string | null>(null);

  const isActiveScoQuiz = activeSco?.includes("assessmenttemplate.html");
  const activeScoProgress = activeSco ? progress?.[activeSco] : null;
  const isQuizCompleted = activeScoProgress?.completion_status === "completed";
  const quizScore = activeScoProgress?.score_raw;
  const successStatus = activeScoProgress?.success_status;
  const videoRef = useRef<HTMLVideoElement>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pdfTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Dynamic layout locking to remove duplicate page scrollbars and maximize player viewport
  useEffect(() => {
    const layoutMain = document.querySelector(".layout-main") as HTMLElement;
    if (layoutMain) {
      const originalOverflow = layoutMain.style.overflow;
      const originalPadding = layoutMain.style.padding;
      
      layoutMain.style.overflow = "hidden";
      layoutMain.style.padding = "16px 24px"; // Tighter padding to maximize SCORM player viewport size
      
      return () => {
        layoutMain.style.overflow = originalOverflow;
        layoutMain.style.padding = originalPadding;
      };
    }
  }, []);

  // Sync state from API
  useEffect(() => {
    if (section) {
      setContentDone(section.content_done);
      if (section.content_done && !section.has_quiz) {
        setPhase("done");
      } else if (section.content_done && section.has_quiz) {
        if (section.quiz_passed) {
          setPhase("done");
        } else {
          setPhase("quiz");
        }
      }
    }
  }, [section?.id]);

  // VIDEO HEARTBEAT
  useEffect(() => {
    if (!item || item.type !== "video" || !item.url) return;

    heartbeatRef.current = setInterval(async () => {
      const video = videoRef.current;
      if (!video || !eId || !sId || !item.id) return;
      try {
        const res = await employeeApi.videoProgress(eId, sId, item.id, Math.floor(video.currentTime));
        if (res.content_done && !contentDone) {
          setContentDone(true);
          queryClient.invalidateQueries({ queryKey: ["my-course", cId] });
          if (section?.has_quiz) {
            setPhase("quiz");
          } else {
            setPhase("done");
          }
        }
      } catch {}
    }, 15_000);

    return () => {
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    };
  }, [item?.id]);

  // PDF DWELL TIMER
  useEffect(() => {
    if (!item || item.type !== "pdf") return;
    pdfTimerRef.current = setInterval(() => setPdfDwell((d) => d + 1), 1000);
    return () => {
      if (pdfTimerRef.current) clearInterval(pdfTimerRef.current);
    };
  }, [item?.id]);

  // Fetch and parse SCORM manifest to build the Table of Contents
  useEffect(() => {
    if (!item || item.type !== "scorm" || !item.url) {
      setToc([]);
      setActiveSco(null);
      return;
    }

    const fetchManifest = async () => {
      try {
        const urlObj = new URL(item.url);
        const contentOrigin = urlObj.origin;
        const manifestUrl = `${contentOrigin}/pkg/${item.id}/imsmanifest.xml`;

        const res = await fetch(manifestUrl);
        if (!res.ok) throw new Error("Manifest not found");
        const xmlText = await res.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");

        // Find organizations and items
        const defaultOrg = xmlDoc.querySelector("organizations")?.getAttribute("default");
        let org = defaultOrg ? xmlDoc.querySelector(`organization[identifier="${defaultOrg}"]`) : null;
        if (!org) {
          org = xmlDoc.querySelector("organization");
        }

        if (org) {
          const parseItems = (parentEl: Element): any[] => {
            const list: any[] = [];
            const children = parentEl.children;
            for (let i = 0; i < children.length; i++) {
              const child = children[i];
              if (child.tagName.toLowerCase().endsWith("item")) {
                const titleEl = child.querySelector("title");
                const identifier = child.getAttribute("identifier") || "";
                const identifierref = child.getAttribute("identifierref") || "";

                let href = "";
                if (identifierref) {
                  const resEl = xmlDoc.querySelector(`resource[identifier="${identifierref}"]`);
                  if (resEl) {
                    href = resEl.getAttribute("href") || "";
                    const parameters = child.getAttribute("parameters") || "";
                    if (parameters) {
                      href += parameters;
                    }
                  }
                }

                list.push({
                  identifier,
                  title: titleEl?.textContent || "Untitled",
                  href,
                  children: parseItems(child),
                });
              }
            }
            return list;
          };

          const parsedToc = parseItems(org);
          setToc(parsedToc);

          // Find first launchable item
          const findFirstSco = (list: any[]): string | null => {
            for (const x of list) {
              if (x.href) return x.href;
              if (x.children && x.children.length > 0) {
                const h = findFirstSco(x.children);
                if (h) return h;
              }
            }
            return null;
          };

          const firstSco = findFirstSco(parsedToc);
          if (firstSco) {
            setActiveSco(firstSco);
          }
        }
      } catch (err) {
        console.error("Failed to parse SCORM manifest:", err);
      }
    };

    fetchManifest();
  }, [item?.id]);

  // SCORM postMessage listener
  useEffect(() => {
    if (!item || (item.type !== "scorm" && item.type !== "cmi5")) return;
    const handler = (e: MessageEvent) => {
      if (e.data?.type === "scorm_terminated") {
        refetchProgress();
        if (e.data.section_complete) {
          queryClient.invalidateQueries({ queryKey: ["my-course", cId] });
          setScormComplete(true);
          if (section?.has_quiz) setPhase("quiz");
          else setPhase("done");
        }
      } else if (e.data?.type === "scorm_commit_quiz") {
        refetchProgress();
        queryClient.invalidateQueries({ queryKey: ["my-course", cId] });
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [item?.id, refetchProgress, cId, section?.has_quiz, queryClient]);

  const handleMarkPdfRead = async () => {
    if (!item || !eId || !sId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await employeeApi.markPdfRead(eId, sId, item.id, pdfDwell);
      setPdfSubmitted(true);
      setContentDone(true);
      queryClient.invalidateQueries({ queryKey: ["my-course", cId] });
      if (res.section_complete || !section?.has_quiz) {
        setPhase(res.section_complete ? "done" : "quiz");
      } else {
        setPhase("quiz");
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to mark as read");
    } finally {
      setLoading(false);
    }
  };

  const handleLaunchCmi5 = async () => {
    if (!eId || !sId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await employeeApi.cmi5Launch(eId, sId);
      window.open(res.launch_url, "_blank", "noopener,noreferrer");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to launch cmi5 content");
    } finally {
      setLoading(false);
    }
  };

  const handleRetakeQuiz = async () => {
    if (!eId || !packageId || !activeSco) return;
    setLoading(true);
    try {
      await employeeApi.resetScoProgress(eId, packageId, activeSco);
      refetchProgress();
      queryClient.invalidateQueries({ queryKey: ["my-course", cId] });
      if (iframeRef.current) {
        iframeRef.current.src = getIframeUrl();
      }
    } catch (err) {
      console.error("Failed to reset quiz progress:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleQuizComplete = (passed: boolean, score: number) => {
    setQuizResult({ passed, score });
    setPhase("done");
    queryClient.invalidateQueries({ queryKey: ["my-course", cId] });
  };

  const getIframeUrl = () => {
    if (!item?.url) return "";
    if (!activeSco) return item.url;
    try {
      const urlObj = new URL(item.url);
      urlObj.searchParams.set("sco", activeSco);
      return urlObj.toString();
    } catch {
      return item.url;
    }
  };

  const renderTocNodes = (nodes: any[], depth = 0): React.ReactNode => {
    return nodes.map((node) => {
      const isFolder = !node.href;
      const isActive = activeSco === node.href;
      const scoProgress = progress?.[node.href];
      const isCompleted = scoProgress?.completion_status === "completed";
      const scoreRaw = scoProgress?.score_raw;
      const scoreStr = (scoreRaw !== null && scoreRaw !== undefined) ? ` (${scoreRaw}%)` : "";

      return (
        <div key={node.identifier} style={{ marginLeft: depth * 12 }}>
          {isFolder ? (
            <div style={{ fontWeight: 600, color: "var(--text-muted)", padding: "6px 4px", marginTop: depth === 0 ? 8 : 4 }}>
              {node.title}
            </div>
          ) : (
            <div
              onClick={() => {
                setActiveSco(node.href);
                refetchProgress();
                queryClient.invalidateQueries({ queryKey: ["my-course", cId] });
                setShowMobileToc(false);
              }}
              style={{
                cursor: "pointer",
                padding: "6px 8px",
                borderRadius: 4,
                color: isActive ? "var(--primary)" : "var(--text)",
                background: isActive ? "var(--bg-elevated)" : "transparent",
                fontWeight: isActive ? 600 : "normal",
                transition: "all 0.15s ease",
                display: "block",
                marginBottom: 2,
                opacity: isCompleted ? 0.6 : 1.0,
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.background = "var(--bg-elevated)";
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.background = "transparent";
              }}
            >
              {isCompleted ? "✓ " : "📄 "} {node.title}{scoreStr}
            </div>
          )}
          {node.children && node.children.length > 0 && renderTocNodes(node.children, depth + 1)}
        </div>
      );
    });
  };

  if (!course || !section) {
    return <div className="center"><div className="spinner" /></div>;
  }

  if (section.locked) {
    return (
      <div style={{ maxWidth: 768, margin: "0 auto", width: "100%" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 20 }}>
          <Link to={`/my/courses/${cId}`} style={{ color: "var(--text-muted)", fontSize: 13, textDecoration: "none" }}>
            ← Back to {course.title}
          </Link>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginTop: 4, letterSpacing: "-0.02em" }}>{section.title}</h1>
        </div>
        <div className="card" style={{ padding: "20px", borderColor: "var(--danger)" }}>
          <p style={{ color: "var(--danger)", fontWeight: 500 }}>🔒 This section is locked. Please complete previous sections first.</p>
        </div>
      </div>
    );
  }

  const isScorm = item?.type === "scorm";

  return (
    <div style={{ maxWidth: isScorm ? 1360 : 768, margin: "0 auto", width: "100%", display: isScorm ? "flex" : "block", flexDirection: "column", flex: isScorm ? 1 : "none", minHeight: 0 }}>
      {/* Dynamic unified header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20, gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <Link to={`/my/courses/${cId}`} style={{ color: "var(--text-muted)", fontSize: 13, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
            ← Back to {course.title}
          </Link>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <h1 style={{ fontSize: 24, fontWeight: 700, marginTop: 4, letterSpacing: "-0.02em" }}>{section.title}</h1>
            {phase === "done" && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                <span className="badge badge-green" style={{ textTransform: "none", fontSize: 11, padding: "3px 8px" }}>✓ Complete</span>
                {quizResult && (
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    (Quiz: {quizResult.score}% — {quizResult.passed ? "Passed" : "Failed"})
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {phase === "done" && (
            <Link to={`/my/courses/${cId}`} style={{ display: "inline-flex" }}>
              <button className="btn-primary" style={{ padding: "6px 12px", fontSize: 12 }}>Back to Course</button>
            </Link>
          )}
          {isScorm && toc.length > 0 && (
            <button 
              className="btn-secondary mobile-toc-toggle"
              onClick={() => setShowMobileToc(prev => !prev)}
              style={{ fontSize: 12, padding: "6px 12px", height: "fit-content" }}
            >
              {showMobileToc ? "✕ Close Index" : "☰ Course Index"}
            </button>
          )}
        </div>
      </div>

      {/* Content player area */}
      {(phase === "content" || phase === "done") && item && (
        <div className={isScorm ? "" : "card"} style={{ marginBottom: isScorm ? 0 : 24, display: isScorm ? "flex" : "block", flexDirection: "column", flex: isScorm ? 1 : "none", minHeight: 0 }}>
          {item.type === "video" && item.url && (
            <div>
              <video
                ref={videoRef}
                src={item.url}
                controls
                style={{ width: "100%", borderRadius: 8, maxHeight: 400, background: "#000" }}
              />
              <p style={{ marginTop: 12, fontSize: 13, color: "var(--text-muted)" }}>
                Watch at least 90% of the video to continue.
              </p>
            </div>
          )}

          {item.type === "pdf" && item.url && (
            <div>
              <iframe
                src={item.url}
                style={{ width: "100%", height: 500, border: "none", borderRadius: 8 }}
                title="PDF Viewer"
              />
              <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
                  Time spent: {pdfDwell}s {pdfDwell < 20 && `(need ${20 - pdfDwell}s more)`}
                </span>
                <button
                  className="btn-primary"
                  disabled={pdfDwell < 20 || pdfSubmitted || contentDone || loading}
                  onClick={handleMarkPdfRead}
                >
                  {loading ? "Marking…" : (pdfSubmitted || contentDone) ? "Marked as Read" : "Mark as Read"}
                </button>
              </div>
              {error && <p style={{ color: "var(--danger)", fontSize: 12, marginTop: 8 }}>{error}</p>}
            </div>
          )}

          {item.type === "scorm" && (
            <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
              {phase !== "done" && (
                <p style={{ marginBottom: 12, color: "var(--text-muted)", fontSize: 13.5 }}>
                  The SCORM module will open in a sandboxed frame below.
                  Complete all activities in the module to progress.
                </p>
              )}
              <div className="player-layout" style={{ flex: 1, minHeight: 0 }}>
                {/* Table of Contents Sidebar */}
                {toc.length > 0 && (
                  <div className={`card player-sidebar ${showMobileToc ? "open" : ""}`} style={{ padding: "16px 12px" }}>
                    <h3 style={{ fontSize: 12, fontWeight: 700, marginBottom: 12, paddingBottom: 8, borderBottom: "1px solid var(--border)", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)" }}>
                      Course Contents
                    </h3>
                    <div style={{ flex: 1, overflowY: "auto" }}>
                      {renderTocNodes(toc)}
                    </div>
                  </div>
                )}

                {/* Content Iframe */}
                <div className="player-content">
                  {isActiveScoQuiz && isQuizCompleted ? (
                    <div className="card" style={{ padding: "40px 20px", textAlign: "center", border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg-elevated)", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
                      <span style={{ fontSize: 48 }}>📊</span>
                      <h2 style={{ marginTop: 16, color: "var(--primary)" }}>Quiz Results</h2>
                      <div style={{ margin: "24px 0" }}>
                        <div style={{ fontSize: 42, fontWeight: 700 }}>{quizScore}%</div>
                        <div style={{ fontSize: 14, color: successStatus === "passed" ? "var(--success)" : "var(--danger)", fontWeight: 600, marginTop: 4 }}>
                          {successStatus === "passed" ? "PASSED" : "FAILED"}
                        </div>
                      </div>
                      <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 20, maxWidth: 360 }}>
                        Your attempt has been saved. You can review your score here or retake the quiz.
                      </p>
                      <button className="btn-primary" onClick={handleRetakeQuiz} disabled={loading}>
                        {loading ? "Resetting..." : "Retake Quiz"}
                      </button>
                    </div>
                  ) : getIframeUrl() ? (
                    <iframe
                      ref={iframeRef}
                      src={getIframeUrl()}
                      allow="fullscreen"
                      sandbox="allow-scripts allow-forms allow-same-origin allow-popups"
                      style={{ width: "100%", height: "100%", border: "1px solid var(--border)", borderRadius: 8, background: "#fff", flex: 1, display: "block" }}
                      title="SCORM Content"
                    />
                  ) : (
                    <p style={{ color: "var(--text-muted)" }}>SCORM launch URL not available.</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {item.type === "cmi5" && (
            <div>
              <p style={{ marginBottom: 16, color: "var(--text-muted)", fontSize: 14 }}>
                Click the button below to launch the cmi5 learning activity in a new window.
                Return here when finished.
              </p>
              <button className="btn-primary" onClick={handleLaunchCmi5} disabled={loading}>
                {loading ? "Launching…" : "Launch Activity"}
              </button>
              {error && <p style={{ color: "var(--danger)", fontSize: 12, marginTop: 8 }}>{error}</p>}
            </div>
          )}

          {!item && (
            <p style={{ color: "var(--text-muted)" }}>No content available for this section.</p>
          )}
        </div>
      )}

      {/* Quiz phase */}
      {phase === "quiz" && (
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Section Quiz</h2>
          <QuizRunner
            enrollmentId={eId}
            sectionId={sId}
            onComplete={handleQuizComplete}
          />
        </div>
      )}
    </div>
  );
}
