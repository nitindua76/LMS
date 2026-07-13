import { client } from "./client";

export interface CourseState {
  course_id: number;
  title: string;
  mandatory: boolean;
  duration_days: number | null;
  state: "locked" | "available" | "not_started" | "in_progress" | "completed" | "failed" | "expired";
  lock_reason: string | null;
  enrollment_id: number | null;
  deadline_at: string | null;
}

export interface ContentItem {
  id: number;
  order_index: number;
  type: "video" | "pdf" | "scorm" | "cmi5" | "meeting";
  title?: string;
  url?: string;
  video_duration_sec?: number | null;
  resume_seconds?: number;
}

export interface SessionEligibility {
  eligible: boolean;
  reason: string | null;
  seconds_until_join_opens: number | null;
  session: {
    id: number;
    mode: "meeting" | "webinar";
    status: "scheduled" | "live" | "ended" | "cancelled";
    start_at: string;
    end_at: string;
    timezone: string;
    join_before_start_min: number;
    waiting_room_enabled: boolean;
  } | null;
}

export interface SessionJoinResponse {
  livekit_url: string;
  token: string;
  room_name: string;
  identity: string;
  role: "host" | "attendee";
}

export interface SectionDetail {
  id: number;
  order_index: number;
  title: string;
  locked: boolean;
  content_done: boolean;
  quiz_passed: boolean | null;
  completed_at: string | null;
  has_quiz: boolean;
  content_items: ContentItem[];
}

export interface CourseDetail {
  id: number;
  title: string;
  description: string | null;
  intro: string | null;
  duration_days: number | null;
  mandatory: boolean;
  state: string;
  lock_reason: string | null;
  deadline_at: string | null;
  enrollment_id: number | null;
  sections: SectionDetail[];
}

export interface QuizQuestion {
  id: number;
  order_index: number;
  type: "mcq_single" | "mcq_multi" | "true_false";
  text: string;
  timer_sec: number;
  options: Array<{ id: number; order_index: number; text: string }>;
}

export interface AttemptResponse {
  attempt_id?: number;
  attempt_no?: number;
  total_questions?: number;
  question?: QuizQuestion;
  complete?: boolean;
  passed?: boolean;
  score_pct?: number;
  section_complete?: boolean;
  attempts_used?: number;
  max_attempts?: number;
  question_number?: number;
  seconds_remaining?: number;
  timed_out?: boolean;
}

export interface TeamMember {
  id: number;
  name: string;
  email: string;
  discipline: { id: number; name: string } | null;
  level: { id: number; code: string; name: string; rank: number } | null;
}

export interface TeamMemberSectionScore {
  section_id: number;
  title: string;
  order_index: number;
  content_done: boolean;
  quiz_passed: boolean | null;
  completed_at: string | null;
  has_quiz: boolean;
  best_score_pct: number | null;
  attempts_used: number;
  content_pct: number | null;
}

export interface TeamMemberCourseDetail {
  id: number;
  title: string;
  mandatory: boolean;
  state: string;
  lock_reason: string | null;
  deadline_at: string | null;
  enrollment_id: number | null;
  started_at: string | null;
  sections: TeamMemberSectionScore[];
}

export const employeeApi = {
  myCourses: () =>
    client.get<CourseState[]>("/my/courses").then((r) => r.data),

  myTeam: () =>
    client.get<TeamMember[]>("/my/team").then((r) => r.data),

  teamMemberCourses: (memberId: number) =>
    client.get<CourseState[]>(`/my/team/${memberId}/courses`).then((r) => r.data),

  teamMemberCourseDetail: (memberId: number, courseId: number) =>
    client
      .get<TeamMemberCourseDetail>(`/my/team/${memberId}/courses/${courseId}`)
      .then((r) => r.data),

  courseDetail: (id: number) =>
    client.get<CourseDetail>(`/my/courses/${id}`).then((r) => r.data),

  startCourse: (courseId: number) =>
    client.post(`/my/courses/${courseId}/start`, {}).then((r) => r.data),

  // Video progress heartbeat
  videoProgress: (enrollmentId: number, sectionId: number, itemId: number, watchedSeconds: number) =>
    client
      .post(`/my/enrollments/${enrollmentId}/sections/${sectionId}/content/${itemId}/progress`, {
        watched_seconds: watchedSeconds,
      })
      .then((r) => r.data),

  // PDF mark-read
  markPdfRead: (enrollmentId: number, sectionId: number, itemId: number, dwellSeconds: number) =>
    client
      .post(`/my/enrollments/${enrollmentId}/sections/${sectionId}/content/${itemId}/mark-read`, {
        dwell_seconds: dwellSeconds,
      })
      .then((r) => r.data),

  // Embedded/external video (e.g. YouTube) — dwell-based completion
  markVideoWatched: (enrollmentId: number, sectionId: number, itemId: number, dwellSeconds: number) =>
    client
      .post(`/my/enrollments/${enrollmentId}/sections/${sectionId}/content/${itemId}/mark-watched`, {
        dwell_seconds: dwellSeconds,
      })
      .then((r) => r.data),

  // Quiz
  startQuizAttempt: (enrollmentId: number, sectionId: number) =>
    client
      .post<AttemptResponse>(`/my/enrollments/${enrollmentId}/sections/${sectionId}/quiz/attempts`, {})
      .then((r) => r.data),

  answerQuestion: (
    enrollmentId: number,
    sectionId: number,
    attemptId: number,
    body: { option_ids?: number[]; value?: boolean }
  ) =>
    client
      .post<AttemptResponse>(
        `/my/enrollments/${enrollmentId}/sections/${sectionId}/quiz/attempts/${attemptId}/answer`,
        body
      )
      .then((r) => r.data),

  currentQuestion: (enrollmentId: number, sectionId: number, attemptId: number) =>
    client
      .get<AttemptResponse>(
        `/my/enrollments/${enrollmentId}/sections/${sectionId}/quiz/attempts/${attemptId}/current`
      )
      .then((r) => r.data),

  // cmi5
  cmi5Launch: (enrollmentId: number, sectionId: number) =>
    client
      .post<{ launch_url: string; session_id: string; registration: string }>(
        `/my/enrollments/${enrollmentId}/sections/${sectionId}/cmi5/launch`
      )
      .then((r) => r.data),

  // SCORM
  scormProgress: (enrollmentId: number, packageId: number) =>
    client
      .get<Record<string, {
        completion_status: string;
        success_status: string;
        score_scaled: number | null;
        score_raw: number | null;
      }>>(`/my/enrollments/${enrollmentId}/packages/${packageId}/progress`)
      .then((r) => r.data),

  resetScoProgress: (enrollmentId: number, packageId: number, scoIdentifier: string) =>
    client
      .post<{ ok: boolean }>(`/my/enrollments/${enrollmentId}/packages/${packageId}/sco/reset`, {
        sco_identifier: scoIdentifier,
      })
      .then((r) => r.data),

  // Live session (meeting content items)
  sessionEligibility: (enrollmentId: number, sectionId: number, itemId: number) =>
    client
      .get<SessionEligibility>(`/my/enrollments/${enrollmentId}/sections/${sectionId}/content/${itemId}/session`)
      .then((r) => r.data),

  joinSession: (enrollmentId: number, sectionId: number, itemId: number) =>
    client
      .post<SessionJoinResponse>(`/my/enrollments/${enrollmentId}/sections/${sectionId}/content/${itemId}/session/join`, {})
      .then((r) => r.data),

  leaveSession: (enrollmentId: number, sectionId: number, itemId: number) =>
    client
      .post(`/my/enrollments/${enrollmentId}/sections/${sectionId}/content/${itemId}/session/leave`, {})
      .then((r) => r.data),
};
