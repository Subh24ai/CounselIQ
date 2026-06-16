"use client";

import { Building2, Mail, ShieldCheck, User as UserIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useAuthStore } from "@/store/auth";
import type { UserRole } from "@/types";

const ROLE_LABELS: Record<UserRole, string> = {
  org_admin: "Org Admin",
  legal_counsel: "Legal Counsel",
  compliance_officer: "Compliance Officer",
  viewer: "Viewer",
};

function Row({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof UserIcon;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 py-3">
      <Icon className="h-4 w-4 text-muted-foreground" />
      <span className="w-32 text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile</CardTitle>
          <CardDescription>Your account details.</CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          <Row
            icon={UserIcon}
            label="Full name"
            value={user?.full_name ?? "—"}
          />
          <Row icon={Mail} label="Email" value={user?.email ?? "—"} />
          <Row
            icon={ShieldCheck}
            label="Role"
            value={
              user ? (
                <Badge variant="secondary">{ROLE_LABELS[user.role]}</Badge>
              ) : (
                "—"
              )
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Organisation</CardTitle>
          <CardDescription>
            Workspace your account belongs to.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Row
            icon={Building2}
            label="Organisation ID"
            value={
              <span className="font-mono text-xs">
                {user?.organisation_id ?? "—"}
              </span>
            }
          />
          <Separator />
          <p className="pt-4 text-sm text-muted-foreground">
            Organisation-wide settings and member management are available to
            organisation administrators.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
