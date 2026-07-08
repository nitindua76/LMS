import { client } from "./client";

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ── Disciplines ────────────────────────────────────────────────────────────────
export interface Discipline {
  id: number;
  name: string;
  created_at: string;
}

export const disciplinesApi = {
  list: (page = 1, page_size = 50) =>
    client.get<Paginated<Discipline>>("/admin/disciplines", { params: { page, page_size } }).then((r) => r.data),
  create: (name: string) => client.post<Discipline>("/admin/disciplines", { name }).then((r) => r.data),
  update: (id: number, name: string) => client.put<Discipline>(`/admin/disciplines/${id}`, { name }).then((r) => r.data),
  delete: (id: number) => client.delete(`/admin/disciplines/${id}`),
};

// ── Levels ────────────────────────────────────────────────────────────────────
export interface Level {
  id: number;
  code: string;
  name: string;
  rank: number;
  created_at: string;
}

export const levelsApi = {
  list: (page = 1, page_size = 50) =>
    client.get<Paginated<Level>>("/admin/levels", { params: { page, page_size } }).then((r) => r.data),
  create: (data: { code: string; name: string; rank: number }) =>
    client.post<Level>("/admin/levels", data).then((r) => r.data),
  update: (id: number, data: Partial<{ code: string; name: string; rank: number }>) =>
    client.put<Level>(`/admin/levels/${id}`, data).then((r) => r.data),
  delete: (id: number) => client.delete(`/admin/levels/${id}`),
};

// ── Users ─────────────────────────────────────────────────────────────────────
export interface User {
  id: number;
  name: string;
  email: string;
  role: "admin" | "employee";
  active: boolean;
  force_password_change: boolean;
  discipline_id: number | null;
  level_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface UserListParams {
  page?: number;
  page_size?: number;
  search?: string;
  discipline_id?: number;
  level_id?: number;
  active?: boolean;
  role?: string;
}

export const usersApi = {
  list: (params: UserListParams = {}) =>
    client.get<Paginated<User>>("/admin/users", { params }).then((r) => r.data),
  get: (id: number) => client.get<User>(`/admin/users/${id}`).then((r) => r.data),
  create: (data: {
    name: string; email: string; password: string;
    role: string; discipline_id?: number; level_id?: number;
  }) => client.post<User>("/admin/users", data).then((r) => r.data),
  update: (id: number, data: Partial<User & { password: string }>) =>
    client.put<User>(`/admin/users/${id}`, data).then((r) => r.data),
  deactivate: (id: number) => client.post(`/admin/users/${id}/deactivate`),
  activate: (id: number) => client.post(`/admin/users/${id}/activate`),
  resetPassword: (id: number, new_password: string) =>
    client.post(`/admin/users/${id}/reset-password`, { new_password }),
  importCsv: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return client.post<CsvRowResult[]>("/admin/users/import/csv", fd).then((r) => r.data);
  },
};

export interface CsvRowResult {
  row: number;
  email: string;
  status: "imported" | "error";
  error: string | null;
}

// ── Courses ───────────────────────────────────────────────────────────────────
export interface CourseTarget { id: number; discipline_id: number; level_id: number; }
export interface Course {
  id: number;
  title: string;
  description: string | null;
  intro: string | null;
  duration_days: number | null;
  mandatory: boolean;
  passing_pct: number;
  max_attempts: number;
  start_date: string | null;
  enroll_close_date: string | null;
  status: "draft" | "published" | "archived";
  created_at: string;
  updated_at: string;
  targets: CourseTarget[];
}

export const coursesApi = {
  list: (params: { page?: number; page_size?: number; status?: string; mandatory?: boolean } = {}) =>
    client.get<Paginated<Course>>("/admin/courses", { params }).then((r) => r.data),
  get: (id: number) => client.get<Course>(`/admin/courses/${id}`).then((r) => r.data),
  create: (data: Partial<Course>) => client.post<Course>("/admin/courses", data).then((r) => r.data),
  update: (id: number, data: Partial<Course>) =>
    client.put<Course>(`/admin/courses/${id}`, data).then((r) => r.data),
  archive: (id: number) => client.delete(`/admin/courses/${id}`),
  purge: (id: number, confirmTitle: string) =>
    client
      .delete<{ course_id: number; title: string; enrollments_deleted: number; quiz_attempts_deleted: number }>(
        `/admin/courses/${id}/purge`,
        { data: { confirm_title: confirmTitle } }
      )
      .then((r) => r.data),
  addTarget: (courseId: number, data: { discipline_id: number; level_id: number }) =>
    client.post<CourseTarget>(`/admin/courses/${courseId}/targets`, data).then((r) => r.data),
  removeTarget: (courseId: number, targetId: number) =>
    client.delete(`/admin/courses/${courseId}/targets/${targetId}`),
  publishReadiness: (id: number) =>
    client.get<{ ready: boolean; issues: string[] }>(`/admin/courses/${id}/publish-readiness`).then((r) => r.data),
  publish: (id: number) => client.post<Course>(`/admin/courses/${id}/publish`, {}).then((r) => r.data),
  unpublish: (id: number) => client.post<Course>(`/admin/courses/${id}/unpublish`, {}).then((r) => r.data),
};

// ── Sections & Content ────────────────────────────────────────────────────────
export interface ContentItem {
  id: number; section_id: number; order_index: number;
  type: "video" | "pdf" | "scorm" | "cmi5"; url: string; video_duration_sec: number | null;
  storage_key: string | null;
}

export interface Section {
  id: number; course_id: number; order_index: number; title: string;
  content_items: ContentItem[];
}

export const sectionsApi = {
  list: (courseId: number) =>
    client.get<Section[]>(`/admin/courses/${courseId}/sections`).then((r) => r.data),
  create: (courseId: number, data: { order_index: number; title: string }) =>
    client.post<Section>(`/admin/courses/${courseId}/sections`, data).then((r) => r.data),
  update: (courseId: number, sectionId: number, data: Partial<Section>) =>
    client.put<Section>(`/admin/courses/${courseId}/sections/${sectionId}`, data).then((r) => r.data),
  delete: (courseId: number, sectionId: number) =>
    client.delete(`/admin/courses/${courseId}/sections/${sectionId}`),
  reorder: (courseId: number, section_ids: number[]) =>
    client.post(`/admin/courses/${courseId}/sections/reorder`, { section_ids }),
};

export const contentApi = {
  create: (courseId: number, sectionId: number, data: Partial<ContentItem>) =>
    client.post<ContentItem>(`/admin/courses/${courseId}/sections/${sectionId}/content`, data).then((r) => r.data),
  update: (courseId: number, sectionId: number, itemId: number, data: Partial<ContentItem>) =>
    client.put<ContentItem>(`/admin/courses/${courseId}/sections/${sectionId}/content/${itemId}`, data).then((r) => r.data),
  delete: (courseId: number, sectionId: number, itemId: number) =>
    client.delete(`/admin/courses/${courseId}/sections/${sectionId}/content/${itemId}`),
  uploadFile: (courseId: number, sectionId: number, itemId: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return client
      .post<ContentItem>(`/admin/courses/${courseId}/sections/${sectionId}/content/${itemId}/upload`, fd)
      .then((r) => r.data);
  },
};

// ── Quizzes ────────────────────────────────────────────────────────────────────
export interface Option { id: number; question_id: number; order_index: number; text: string; is_correct: boolean; }
export interface Question {
  id: number; quiz_id: number; order_index: number;
  type: "mcq_single" | "mcq_multi" | "true_false";
  text: string; marks: number; timer_sec: number;
  options: Option[];
}
export interface Quiz { id: number; section_id: number; passing_pct: number; max_attempts: number; questions: Question[]; }

export const quizzesApi = {
  get: (courseId: number, sectionId: number) =>
    client.get<Quiz>(`/admin/courses/${courseId}/sections/${sectionId}/quiz`).then((r) => r.data),
  create: (courseId: number, sectionId: number, data: { passing_pct: number; max_attempts: number }) =>
    client.post<Quiz>(`/admin/courses/${courseId}/sections/${sectionId}/quiz`, data).then((r) => r.data),
  update: (courseId: number, sectionId: number, data: Partial<Quiz>) =>
    client.put<Quiz>(`/admin/courses/${courseId}/sections/${sectionId}/quiz`, data).then((r) => r.data),
  delete: (courseId: number, sectionId: number) =>
    client.delete(`/admin/courses/${courseId}/sections/${sectionId}/quiz`),
  createQuestion: (courseId: number, sectionId: number, data: Partial<Question & { options: Partial<Option>[] }>) =>
    client.post<Question>(`/admin/courses/${courseId}/sections/${sectionId}/quiz/questions`, data).then((r) => r.data),
  updateQuestion: (courseId: number, sectionId: number, qId: number, data: Partial<Question>) =>
    client.put<Question>(`/admin/courses/${courseId}/sections/${sectionId}/quiz/questions/${qId}`, data).then((r) => r.data),
  deleteQuestion: (courseId: number, sectionId: number, qId: number) =>
    client.delete(`/admin/courses/${courseId}/sections/${sectionId}/quiz/questions/${qId}`),
};

export const packagesApi = {
  import: (itemId: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return client.post(`/admin/content-items/${itemId}/package`, fd).then((r) => r.data);
  },
};

// ── Analytics ──────────────────────────────────────────────────────────────────
export interface AnalyticsOverview {
  enrolled_courses_count: number;
  total_targeted_instances: number;
  active_courses_count: number;
  closed_courses_count: number;
  total_time_spent_hours: number;
}

export interface CourseStudentProgress {
  user_id: number;
  name: string;
  email: string;
  progress: number;
  quiz_score: number | null;
  started_at: string | null;
  completed_at?: string | null;
  status?: "completed" | "in_progress" | "not_enrolled";
}

export interface CourseAnalyticsDetail extends CourseAnalyticsSummary {
  students: CourseStudentProgress[];
}

export interface CourseScormStat {
  sco_identifier: string;
  title: string;
  avg_time_sec: number;
  completed_count: number;
  in_progress_count: number;
  not_attempted_count: number;
  is_quiz: boolean;
  passed_count: number;
  failed_count: number;
  avg_score: number;
}

export interface CourseAnalyticsSummary {
  id: number;
  title: string;
  status: string;
  target_audience_count: number;
  completed_count: number;
  started_count: number;
  not_enrolled_count: number;
  students_completed: CourseStudentProgress[];
  students_started: CourseStudentProgress[];
  students_not_enrolled: CourseStudentProgress[];
  scorm_stats: CourseScormStat[];
}

export interface EmployeeTargetedCourse {
  course_id: number;
  title: string;
  status: "Completed" | "Enrolled" | "Not Enrolled";
  is_active: boolean;
  progress: number;
  quiz_score: number | null;
}

export interface EmployeeActivityEvent {
  date: string;
  event: string;
  type: "completion" | "quiz";
}

export interface EmployeeCourseProgress {
  course_id: number;
  title: string;
  status: "completed" | "in_progress" | "not_enrolled";
  progress: number;
  quiz_score: number | null;
  time_spent_hours: number;
}

export interface EmployeeAnalyticsSummary {
  id: number;
  name: string;
  email: string;
  discipline: string;
  level: string;
  completed_targeted_count: number;
  enrolled_targeted_count: number;
  not_enrolled_targeted_count: number;
  targeted_courses: EmployeeTargetedCourse[];
  timeline: EmployeeActivityEvent[];
}

export interface EmployeeAnalyticsDetail extends EmployeeAnalyticsSummary {
  active: boolean;
  courses: EmployeeCourseProgress[];
}

export const analyticsApi = {
  overview: () => client.get<AnalyticsOverview>("/admin/analytics/overview").then((r) => r.data),
  courses: () => client.get<CourseAnalyticsSummary[]>("/admin/analytics/courses").then((r) => r.data),
  courseDetail: (id: number) => client.get<CourseAnalyticsDetail>(`/admin/analytics/courses/${id}`).then((r) => r.data),
  employees: () => client.get<EmployeeAnalyticsSummary[]>("/admin/analytics/employees").then((r) => r.data),
  employeeDetail: (id: number) => client.get<EmployeeAnalyticsDetail>(`/admin/analytics/employees/${id}`).then((r) => r.data),
};

