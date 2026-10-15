import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { LoadingState } from "@/components/ui/states";
import { homeFor, useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

/**
 * Client-side route guard for navigation convenience only.
 * Authorisation is enforced by the backend on every request.
 */
export function RequireAuth({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingState label="Checking session" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if ((user.must_change_password || user.mfa_enrollment_required) && location.pathname !== "/account")
    return <Navigate to="/account" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}
