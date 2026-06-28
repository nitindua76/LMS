import { useState, useEffect, useCallback } from "react";
import { employeeApi, QuizQuestion } from "../api/employee";

interface Props {
  enrollmentId: number;
  sectionId: number;
  onComplete: (passed: boolean, scorePct: number) => void;
}

export default function QuizRunner({ enrollmentId, sectionId, onComplete }: Props) {
  const [attemptId, setAttemptId] = useState<number | null>(null);
  const [question, setQuestion] = useState<QuizQuestion | null>(null);
  const [questionNumber, setQuestionNumber] = useState(1);
  const [totalQuestions, setTotalQuestions] = useState(0);
  const [secondsRemaining, setSecondsRemaining] = useState(0);
  const [selectedOptions, setSelectedOptions] = useState<number[]>([]);
  const [selectedBool, setSelectedBool] = useState<boolean | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Timer countdown
  useEffect(() => {
    if (!question || secondsRemaining <= 0) return;
    const t = setInterval(() => {
      setSecondsRemaining((s) => {
        if (s <= 1) {
          clearInterval(t);
          // Auto-submit on timeout
          handleSubmit(true);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [question?.id]);

  const startAttempt = useCallback(async () => {
    setError(null);
    setTimedOut(false);
    try {
      const res = await employeeApi.startQuizAttempt(enrollmentId, sectionId);
      if (res.complete) {
        onComplete(res.passed ?? false, res.score_pct ?? 0);
        return;
      }
      setAttemptId(res.attempt_id!);
      setQuestion(res.question!);
      setQuestionNumber(1);
      setTotalQuestions(res.total_questions ?? 1);
      setSecondsRemaining(res.question!.timer_sec);
      setSelectedOptions([]);
      setSelectedBool(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to start quiz");
    }
  }, [enrollmentId, sectionId]);

  useEffect(() => {
    startAttempt();
  }, [startAttempt]);

  const handleSubmit = async (autoTimeout = false) => {
    if (!attemptId || !question || submitting) return;
    setSubmitting(true);
    try {
      const body: { option_ids?: number[]; value?: boolean } =
        question.type === "true_false"
          ? { value: selectedBool ?? false }
          : { option_ids: selectedOptions };

      const res = await employeeApi.answerQuestion(enrollmentId, sectionId, attemptId, body);

      if (res.complete) {
        onComplete(res.passed ?? false, res.score_pct ?? 0);
        return;
      }

      setQuestion(res.question!);
      setQuestionNumber(res.question_number ?? questionNumber + 1);
      setSecondsRemaining(res.question!.timer_sec);
      setSelectedOptions([]);
      setSelectedBool(null);
      setTimedOut(res.timed_out ?? false);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to submit answer");
    } finally {
      setSubmitting(false);
    }
  };

  if (error) {
    return (
      <div className="card" style={{ borderColor: "var(--danger)" }}>
        <p style={{ color: "var(--danger)" }}>{error}</p>
        <button className="btn-secondary" style={{ marginTop: 12 }} onClick={startAttempt}>
          Retry
        </button>
      </div>
    );
  }

  if (!question) {
    return <div className="center"><div className="spinner" /></div>;
  }

  const pct = totalQuestions > 0 ? (questionNumber / totalQuestions) * 100 : 0;
  const timerColor = secondsRemaining <= 5 ? "var(--danger)" : secondsRemaining <= 15 ? "var(--warning)" : "var(--success)";

  return (
    <div className="card" style={{ maxWidth: 640, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Question {questionNumber} of {totalQuestions}
        </span>
        <span style={{
          fontSize: 14, fontWeight: 700, color: timerColor,
          background: "var(--bg-elevated)", padding: "4px 10px", borderRadius: 6,
        }}>
          {secondsRemaining}s
        </span>
      </div>

      {/* Progress bar */}
      <div style={{ height: 4, background: "var(--border)", borderRadius: 2, marginBottom: 20 }}>
        <div style={{ height: "100%", width: `${pct}%`, background: "var(--primary)", borderRadius: 2, transition: "width 0.3s" }} />
      </div>

      {timedOut && (
        <div style={{ marginBottom: 12, padding: "8px 12px", background: "var(--bg-elevated)", borderRadius: 6, fontSize: 12, color: "var(--text-muted)" }}>
          Previous question timed out — moving on.
        </div>
      )}

      {/* Question */}
      <p style={{ fontWeight: 600, fontSize: 16, marginBottom: 20, lineHeight: 1.5 }}>{question.text}</p>

      {/* Options */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {question.type === "true_false" ? (
          ["true", "false"].map((val) => {
            const boolVal = val === "true";
            const selected = selectedBool === boolVal;
            return (
              <button
                key={val}
                onClick={() => setSelectedBool(boolVal)}
                style={{
                  padding: "12px 16px", borderRadius: 8, textAlign: "left",
                  border: `2px solid ${selected ? "var(--primary)" : "var(--border)"}`,
                  background: selected ? "rgba(var(--primary-rgb, 99,102,241),.08)" : "var(--bg-surface)",
                  color: "var(--text-primary)", cursor: "pointer", fontWeight: selected ? 600 : 400,
                  transition: "border-color 0.15s",
                }}
              >
                {val.charAt(0).toUpperCase() + val.slice(1)}
              </button>
            );
          })
        ) : (
          question.options.map((opt) => {
            const selected = selectedOptions.includes(opt.id);
            return (
              <button
                key={opt.id}
                onClick={() => {
                  if (question.type === "mcq_single") {
                    setSelectedOptions([opt.id]);
                  } else {
                    setSelectedOptions((prev) =>
                      prev.includes(opt.id) ? prev.filter((x) => x !== opt.id) : [...prev, opt.id]
                    );
                  }
                }}
                style={{
                  padding: "12px 16px", borderRadius: 8, textAlign: "left",
                  border: `2px solid ${selected ? "var(--primary)" : "var(--border)"}`,
                  background: selected ? "rgba(var(--primary-rgb, 99,102,241),.08)" : "var(--bg-surface)",
                  color: "var(--text-primary)", cursor: "pointer", fontWeight: selected ? 600 : 400,
                  transition: "border-color 0.15s",
                }}
              >
                {question.type === "mcq_multi" && (
                  <span style={{
                    display: "inline-block", width: 16, height: 16, border: "2px solid",
                    borderColor: selected ? "var(--primary)" : "var(--border)",
                    borderRadius: 3, marginRight: 10, flexShrink: 0, verticalAlign: "middle",
                    background: selected ? "var(--primary)" : "transparent",
                  }} />
                )}
                {opt.text}
              </button>
            );
          })
        )}
      </div>

      <button
        className="btn-primary"
        style={{ width: "100%", marginTop: 20 }}
        disabled={
          submitting ||
          (question.type === "true_false" ? selectedBool === null : selectedOptions.length === 0)
        }
        onClick={() => handleSubmit(false)}
      >
        {submitting ? "Submitting…" : questionNumber === totalQuestions ? "Submit Quiz" : "Next Question"}
      </button>
    </div>
  );
}
