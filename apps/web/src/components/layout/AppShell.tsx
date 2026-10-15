import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { label, ROLE_LABELS } from "@/lib/labels";
import type { Role } from "@/lib/types";

import { Wordmark } from "./Wordmark";

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

const NAV: Record<Role, { heading: string; items: NavItem[] }[]> = {
  trainee: [
    {
      heading: "Training",
      items: [
        { to: "/trainee", label: "My exercises", end: true },
        { to: "/trainee/practice", label: "Practice library" },
        { to: "/trainee/history", label: "My progress" },
        { to: "/trainee/how-to-play", label: "How to play" },
      ],
    },
  ],
  instructor: [
    {
      heading: "Instruction",
      items: [
        { to: "/instructor", label: "Overview", end: true },
        { to: "/instructor/assignments", label: "Assignments" },
        { to: "/instructor/sessions", label: "Sessions and reviews" },
        { to: "/instructor/analytics", label: "Analytics" },
      ],
    },
    {
      heading: "Content",
      items: [
        { to: "/instructor/scenarios", label: "Scenarios" },
        { to: "/instructor/rubrics", label: "Scoring rubrics" },
      ],
    },
  ],
  administrator: [
    {
      heading: "Administration",
      items: [
        { to: "/admin/users", label: "Users" },
        { to: "/admin/settings", label: "Settings" },
        { to: "/admin/audit", label: "Audit log" },
        { to: "/admin/system", label: "System health" },
      ],
    },
    {
      heading: "Records",
      items: [
        { to: "/instructor/sessions", label: "Sessions" },
        { to: "/instructor/analytics", label: "Analytics" },
      ],
    },
  ],
};

function NavSection({
  heading,
  items,
  onNavigate,
}: {
  heading: string;
  items: NavItem[];
  onNavigate: () => void;
}) {
  return (
    <div className="mb-5">
      <p className="mb-1 px-3 text-2xs font-medium uppercase tracking-wide text-ink-subtle">{heading}</p>
      <ul>
        {items.map((it) => (
          <li key={it.to}>
            <NavLink
              to={it.to}
              end={it.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "block rounded px-3 py-1.5 text-sm",
                  isActive
                    ? "bg-brand-soft font-medium text-brand"
                    : "text-ink-muted hover:bg-surface-muted hover:text-ink",
                )
              }
            >
              {it.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  if (!user) return null;
  const sections = NAV[user.role];

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to main content
      </a>
      <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-2 lg:hidden">
        <Wordmark />
        <Button
          variant="secondary"
          size="sm"
          aria-expanded={open}
          aria-controls="primary-nav"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Close menu" : "Menu"}
        </Button>
      </header>
      {/* The wrapper stretches to the full page height; the navigation inside stays in view. */}
      <div className={cn("border-r border-border bg-surface", open ? "block" : "hidden lg:block")}>
        <aside id="primary-nav" className="lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
          <div className="hidden px-4 pb-4 pt-5 lg:block">
            <Wordmark />
            <p className="mt-1 text-2xs text-ink-subtle">Training simulator</p>
          </div>
          <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2 pt-3 lg:pt-0">
            {sections.map((s) => (
              <NavSection
                key={s.heading}
                heading={s.heading}
                items={s.items}
                onNavigate={() => setOpen(false)}
              />
            ))}
            <NavSection
              heading="Account"
              items={[{ to: "/account", label: "Account and security" }]}
              onNavigate={() => setOpen(false)}
            />
          </nav>
          <div className="border-t border-border px-4 py-3">
            <p className="truncate text-sm font-medium" title={user.display_name}>
              {user.display_name}
            </p>
            <p className="text-xs text-ink-subtle">{label(ROLE_LABELS, user.role)}</p>
            <Button
              variant="link"
              size="sm"
              className="mt-1"
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
            >
              Sign out
            </Button>
          </div>
        </aside>
      </div>
      <main id="main" className="min-w-0 px-4 py-6 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1400px]">{children ?? <Outlet />}</div>
      </main>
    </div>
  );
}
