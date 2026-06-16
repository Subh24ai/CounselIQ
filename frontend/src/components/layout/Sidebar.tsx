"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Brain,
  CheckSquare,
  ChevronLeft,
  FileText,
  LayoutDashboard,
  LogOut,
  Scale,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";
import type { UserRole } from "@/types";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  roles?: UserRole[]; // when set, only these roles see the item
}

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/analysis", label: "Analysis", icon: Brain },
  { href: "/reviews", label: "Reviews", icon: CheckSquare },
  {
    href: "/regulatory",
    label: "Regulatory",
    icon: Scale,
    roles: ["org_admin", "compliance_officer"],
  },
  { href: "/settings", label: "Settings", icon: Settings, roles: ["org_admin"] },
];

const ROLE_LABELS: Record<UserRole, string> = {
  org_admin: "Org Admin",
  legal_counsel: "Legal Counsel",
  compliance_officer: "Compliance Officer",
  viewer: "Viewer",
};

function initials(name: string | undefined, email: string | undefined): string {
  if (name) {
    const parts = name.trim().split(/\s+/);
    return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? ""))
      .toUpperCase()
      .slice(0, 2);
  }
  return (email?.[0] ?? "?").toUpperCase();
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.roles || (user && item.roles.includes(user.role)),
  );

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <aside
      className={cn(
        "flex h-screen flex-col border-r bg-card transition-[width] duration-200",
        collapsed ? "w-[68px]" : "w-64",
      )}
    >
      <div className="flex h-16 items-center gap-2 px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/20">
          <ShieldCheck className="h-5 w-5 text-primary" aria-hidden />
        </div>
        {!collapsed && (
          <span className="text-lg font-semibold tracking-tight">
            CounselIQ
          </span>
        )}
      </div>

      <Separator />

      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {visibleItems.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              title={collapsed ? label : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                collapsed && "justify-center px-0",
              )}
            >
              <Icon className="h-5 w-5 shrink-0" aria-hidden />
              {!collapsed && <span>{label}</span>}
            </Link>
          );
        })}
      </nav>

      <Separator />

      <div className="p-2">
        <div
          className={cn(
            "flex items-center gap-3 rounded-md px-2 py-2",
            collapsed && "justify-center px-0",
          )}
        >
          <Avatar className="h-8 w-8">
            <AvatarFallback className="text-xs">
              {initials(user?.full_name, user?.email)}
            </AvatarFallback>
          </Avatar>
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {user?.full_name ?? user?.email ?? "—"}
              </p>
              {user && (
                <Badge variant="secondary" className="mt-0.5 text-[10px]">
                  {ROLE_LABELS[user.role]}
                </Badge>
              )}
            </div>
          )}
        </div>

        <div className={cn("mt-1 flex gap-1", collapsed && "flex-col")}>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleSidebar}
            className="flex-1"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <ChevronLeft
              className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")}
            />
            {!collapsed && <span className="ml-1">Collapse</span>}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLogout}
            className={cn("flex-1 text-muted-foreground", collapsed && "w-full")}
            title="Log out"
            aria-label="Log out"
          >
            <LogOut className="h-4 w-4" />
            {!collapsed && <span className="ml-1">Logout</span>}
          </Button>
        </div>
      </div>
    </aside>
  );
}
