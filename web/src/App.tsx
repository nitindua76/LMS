import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import Login from "./pages/Login";
import AdminLayout from "./components/AdminLayout";
import EmployeeLayout from "./components/EmployeeLayout";
import Disciplines from "./pages/admin/Disciplines";
import Levels from "./pages/admin/Levels";
import Employees from "./pages/admin/Employees";
import EmployeeDetail from "./pages/admin/EmployeeDetail";
import NewEmployee from "./pages/admin/NewEmployee";
import Courses from "./pages/admin/Courses";
import CourseForm from "./pages/admin/CourseForm";
import CourseDetail from "./pages/admin/CourseDetail";
import MyCourses from "./pages/employee/MyCourses";
import MyCourseDetail from "./pages/employee/MyCourseDetail";
import SectionPlayer from "./pages/employee/SectionPlayer";

function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <div className="center"><div className="spinner" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "admin" ? "/admin/courses" : "/my/courses"} replace />;
}

function RequireRole({ role, children }: { role: "admin" | "employee"; children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center"><div className="spinner" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return (
    <div className="center" style={{ color: "var(--danger)" }}>
      403 — Access denied
    </div>
  );
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<RootRedirect />} />

        <Route path="/admin" element={
          <RequireRole role="admin"><AdminLayout /></RequireRole>
        }>
          <Route index element={<Navigate to="courses" replace />} />
          <Route path="disciplines" element={<Disciplines />} />
          <Route path="levels" element={<Levels />} />
          <Route path="employees" element={<Employees />} />
          <Route path="employees/new" element={<NewEmployee />} />
          <Route path="employees/:id" element={<EmployeeDetail />} />
          <Route path="courses" element={<Courses />} />
          <Route path="courses/new" element={<CourseForm />} />
          <Route path="courses/:id" element={<CourseDetail />} />
          <Route path="courses/:id/edit" element={<CourseForm />} />
        </Route>

        <Route path="/my" element={
          <RequireRole role="employee"><EmployeeLayout /></RequireRole>
        }>
          <Route path="courses" element={<MyCourses />} />
          <Route path="courses/:courseId" element={<MyCourseDetail />} />
          <Route
            path="courses/:courseId/enrollments/:enrollmentId/sections/:sectionId"
            element={<SectionPlayer />}
          />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
