import { Link, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/panel";
import { LoadingState } from "@/components/ui/states";
import { AarPage } from "@/features/aar/AarPage";
import { AuditPage, SettingsPage, SystemPage, UsersPage } from "@/features/admin/AdminPages";
import { AccountPage } from "@/features/auth/AccountPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { ExercisePage } from "@/features/exercise/ExercisePage";
import { AssignmentCreatePage, AssignmentsPage } from "@/features/instructor/AssignmentPages";
import { AnalyticsPage, InstructorHome, SessionsPage } from "@/features/instructor/OverviewPages";
import { RubricDetailPage, RubricListPage } from "@/features/instructor/RubricPages";
import { ScenarioEditorPage } from "@/features/instructor/ScenarioEditor";
import { ScenarioDetailPage, ScenarioListPage } from "@/features/instructor/ScenarioPages";
import { HowToPlayPage } from "@/features/guide/HowToPlay";
import { HistoryPage } from "@/features/trainee/HistoryPage";
import {
  AssignmentBriefingPage,
  PracticeBriefingPage,
  PracticeLibraryPage,
  TraineeHome,
} from "@/features/trainee/TraineePages";
import { homeFor, useAuth } from "@/lib/auth";

function Home() {
  const { user, loading } = useAuth();
  if (loading) return <LoadingState label="Checking session" />;
  return <Navigate to={user ? homeFor(user.role) : "/login"} replace />;
}

function NotFound() {
  return (
    <>
      <PageHeader
        title="Page not found"
        description="The page you requested does not exist or you do not have access to it."
      />
      <Button asChild variant="secondary">
        <Link to="/">Go to your home page</Link>
      </Button>
    </>
  );
}

const TRAINEE = ["trainee"] as const;
const INSTRUCTOR = ["instructor"] as const;
const STAFF = ["instructor", "administrator"] as const;
const ADMIN = ["administrator"] as const;

function guard(el: JSX.Element, roles?: readonly ("trainee" | "instructor" | "administrator")[]) {
  return <RequireAuth roles={roles ? [...roles] : undefined}>{el}</RequireAuth>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Home />} />
      <Route element={guard(<AppShell />)}>
        <Route path="/account" element={<AccountPage />} />

        <Route path="/trainee" element={guard(<TraineeHome />, TRAINEE)} />
        <Route
          path="/trainee/assignments/:assignmentId"
          element={guard(<AssignmentBriefingPage />, TRAINEE)}
        />
        <Route path="/trainee/practice" element={guard(<PracticeLibraryPage />, TRAINEE)} />
        <Route path="/trainee/practice/:scenarioId" element={guard(<PracticeBriefingPage />, TRAINEE)} />
        <Route path="/trainee/history" element={guard(<HistoryPage />, TRAINEE)} />
        <Route path="/trainee/how-to-play" element={guard(<HowToPlayPage />, TRAINEE)} />
        <Route path="/exercise/:sessionId" element={guard(<ExercisePage />, TRAINEE)} />

        <Route path="/sessions/:sessionId/result" element={<AarPage />} />

        <Route path="/instructor" element={guard(<InstructorHome />, INSTRUCTOR)} />
        <Route path="/instructor/scenarios" element={guard(<ScenarioListPage />, INSTRUCTOR)} />
        <Route
          path="/instructor/scenarios/new"
          element={guard(<ScenarioEditorPage mode="new" />, INSTRUCTOR)}
        />
        <Route path="/instructor/scenarios/:scenarioId" element={guard(<ScenarioDetailPage />, INSTRUCTOR)} />
        <Route
          path="/instructor/scenarios/:scenarioId/edit"
          element={guard(<ScenarioEditorPage mode="version" />, INSTRUCTOR)}
        />
        <Route path="/instructor/rubrics" element={guard(<RubricListPage />, INSTRUCTOR)} />
        <Route path="/instructor/rubrics/:rubricId" element={guard(<RubricDetailPage />, INSTRUCTOR)} />
        <Route path="/instructor/assignments" element={guard(<AssignmentsPage />, INSTRUCTOR)} />
        <Route path="/instructor/assignments/new" element={guard(<AssignmentCreatePage />, INSTRUCTOR)} />
        <Route path="/instructor/sessions" element={guard(<SessionsPage />, STAFF)} />
        <Route path="/instructor/analytics" element={guard(<AnalyticsPage />, STAFF)} />

        <Route path="/admin/users" element={guard(<UsersPage />, ADMIN)} />
        <Route path="/admin/settings" element={guard(<SettingsPage />, ADMIN)} />
        <Route path="/admin/audit" element={guard(<AuditPage />, ADMIN)} />
        <Route path="/admin/system" element={guard(<SystemPage />, ADMIN)} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
