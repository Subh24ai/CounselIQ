"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Mail,
  ShieldCheck,
  User as UserIcon,
  UserPlus,
} from "lucide-react";

import { InviteDialog } from "@/components/settings/InviteDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { invitationsApi, usersApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";
import type { UserRole } from "@/types";

const ROLE_LABELS: Record<UserRole, string> = {
  org_admin: "Org Admin",
  legal_counsel: "Legal Counsel",
  compliance_officer: "Compliance Officer",
  viewer: "Viewer",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

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

function TeamSection() {
  const [inviteOpen, setInviteOpen] = useState(false);
  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: usersApi.listUsers,
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="text-base">Team</CardTitle>
          <CardDescription>Members of your organisation.</CardDescription>
        </div>
        <Button size="sm" onClick={() => setInviteOpen(true)}>
          <UserPlus className="mr-2 h-4 w-4" />
          Invite Member
        </Button>
      </CardHeader>
      <CardContent>
        {usersQuery.isLoading ? (
          <LoadingSpinner />
        ) : usersQuery.isError ? (
          <p className="text-sm text-destructive">
            {getApiErrorMessage(usersQuery.error, "Could not load team members.")}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Joined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(usersQuery.data ?? []).map((member) => (
                <TableRow key={member.id}>
                  <TableCell className="font-medium">
                    {member.full_name ?? "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {member.email}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{ROLE_LABELS[member.role]}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={member.is_active ? "success" : "secondary"}>
                      {member.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(member.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} />
    </Card>
  );
}

function PendingInvitationsSection() {
  const queryClient = useQueryClient();
  const addNotification = useUIStore((s) => s.addNotification);

  const invitationsQuery = useQuery({
    queryKey: ["invitations"],
    queryFn: () => invitationsApi.listInvitations(),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => invitationsApi.revokeInvitation(id),
    onSuccess: () => {
      addNotification({ type: "success", message: "Invitation revoked" });
      void queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
    onError: (error) => {
      addNotification({
        type: "error",
        message: getApiErrorMessage(error, "Could not revoke the invitation."),
      });
    },
  });

  const invitations = invitationsQuery.data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Pending Invitations</CardTitle>
        <CardDescription>
          Invitations that have been sent but not yet accepted.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {invitationsQuery.isLoading ? (
          <LoadingSpinner />
        ) : invitationsQuery.isError ? (
          <p className="text-sm text-destructive">
            {getApiErrorMessage(
              invitationsQuery.error,
              "Could not load invitations.",
            )}
          </p>
        ) : invitations.length === 0 ? (
          <EmptyState
            icon={Mail}
            title="No invitations"
            description="Invite a team member to get started."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Sent</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invitations.map((invitation) => (
                <TableRow key={invitation.id}>
                  <TableCell className="font-medium">
                    {invitation.email}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {ROLE_LABELS[invitation.role]}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(invitation.created_at)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(invitation.expires_at)}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={invitation.status} />
                  </TableCell>
                  <TableCell className="text-right">
                    {invitation.status === "pending" ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        disabled={revoke.isPending}
                        onClick={() => revoke.mutate(invitation.id)}
                      >
                        Revoke
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "org_admin";

  return (
    <div className="max-w-3xl space-y-6">
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
            {isAdmin
              ? "Manage your team and pending invitations below."
              : "Organisation-wide settings and member management are available to organisation administrators."}
          </p>
        </CardContent>
      </Card>

      {isAdmin && (
        <>
          <TeamSection />
          <PendingInvitationsSection />
        </>
      )}
    </div>
  );
}
