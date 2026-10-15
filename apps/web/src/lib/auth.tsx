import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, ApiError, onAuthFailure } from "./api";
import type { Me, Role } from "./types";

/** Result of the password step: signed in, or a second factor is needed. */
export type LoginResult =
  | { kind: "signed_in"; user: Me }
  | { kind: "mfa_required"; mfaToken: string; expiresAt: string };

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<LoginResult>;
  verifyMfa: (mfaToken: string, code: string) => Promise<Me>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  can: (permission: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await api.get<Me>("/auth/me"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setUser(null);
      else throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh().catch(() => setLoading(false));
    return onAuthFailure((status) => {
      if (status === 401) setUser(null);
      else refresh().catch(() => undefined);
    });
  }, [refresh]);

  const login = useCallback(async (username: string, password: string): Promise<LoginResult> => {
    const res = await api.post<
      { mfa_required: false; user: Me } | { mfa_required: true; mfa_token: string; expires_at: string }
    >("/auth/login", { username, password });
    if (res.mfa_required) return { kind: "mfa_required", mfaToken: res.mfa_token, expiresAt: res.expires_at };
    setUser(res.user);
    return { kind: "signed_in", user: res.user };
  }, []);

  const verifyMfa = useCallback(async (mfaToken: string, code: string) => {
    const res = await api.post<{ user: Me }>("/auth/mfa/verify", { mfa_token: mfaToken, code });
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login,
      verifyMfa,
      logout,
      refresh,
      can: (p: string) => Boolean(user?.permissions.includes(p)),
    }),
    [user, loading, login, verifyMfa, logout, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export function homeFor(role: Role): string {
  return role === "trainee" ? "/trainee" : role === "instructor" ? "/instructor" : "/admin/users";
}
