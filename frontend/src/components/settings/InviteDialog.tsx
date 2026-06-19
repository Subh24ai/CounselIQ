"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Loader2, Mail } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { invitationsApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { useUIStore } from "@/store/ui";
import type { Invitation, InvitableRole } from "@/types";

interface RoleOption {
  value: InvitableRole;
  label: string;
  description: string;
}

const ROLE_OPTIONS: RoleOption[] = [
  {
    value: "legal_counsel",
    label: "Legal Counsel",
    description: "Reviews contracts and signs off on analyses.",
  },
  {
    value: "compliance_officer",
    label: "Compliance Officer",
    description: "Monitors regulatory impact and compliance status.",
  },
  {
    value: "viewer",
    label: "Viewer",
    description: "Read-only access to documents and reports.",
  },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface InviteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function InviteDialog({ open, onOpenChange }: InviteDialogProps) {
  const queryClient = useQueryClient();
  const addNotification = useUIStore((s) => s.addNotification);

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InvitableRole>("legal_counsel");
  const [created, setCreated] = useState<Invitation | null>(null);
  const [copied, setCopied] = useState(false);

  const mutation = useMutation({
    mutationFn: () => invitationsApi.createInvitation({ email, role }),
    onSuccess: (invitation) => {
      setCreated(invitation);
      addNotification({
        type: "success",
        message: `Invitation link generated for ${invitation.email}`,
      });
      void queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
  });

  function reset() {
    setEmail("");
    setRole("legal_counsel");
    setCreated(null);
    setCopied(false);
    mutation.reset();
  }

  function handleOpenChange(next: boolean) {
    if (!next) reset();
    onOpenChange(next);
  }

  async function copyLink() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.invite_link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard may be unavailable; the link is still selectable in the box */
    }
  }

  const emailValid = EMAIL_RE.test(email);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle>Invitation created</DialogTitle>
              <DialogDescription>
                Email delivery isn&apos;t enabled yet — share this link with{" "}
                <span className="font-medium text-foreground">
                  {created.email}
                </span>{" "}
                so they can join.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-2">
              <Label htmlFor="invite-link">Invitation link</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="invite-link"
                  readOnly
                  value={created.invite_link}
                  className="font-mono text-xs"
                  onFocus={(e) => e.currentTarget.select()}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={copyLink}
                  aria-label="Copy invitation link"
                >
                  {copied ? (
                    <Check className="h-4 w-4 text-emerald-500" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                This link expires in 48 hours.
              </p>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => reset()}>
                Invite another
              </Button>
              <Button onClick={() => handleOpenChange(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Invite a team member</DialogTitle>
              <DialogDescription>
                They&apos;ll join your organisation with the role you choose.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="invite-email">Email</Label>
                <Input
                  id="invite-email"
                  type="email"
                  autoComplete="off"
                  placeholder="colleague@enterprise.in"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="invite-role">Role</Label>
                <Select
                  value={role}
                  onValueChange={(value) => setRole(value as InvitableRole)}
                >
                  <SelectTrigger id="invite-role">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ROLE_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {ROLE_OPTIONS.find((o) => o.value === role)?.description}
                </p>
              </div>

              {mutation.isError && (
                <Alert variant="destructive">
                  <AlertDescription>
                    {getApiErrorMessage(
                      mutation.error,
                      "Could not create the invitation.",
                    )}
                  </AlertDescription>
                </Alert>
              )}
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => handleOpenChange(false)}
                disabled={mutation.isPending}
              >
                Cancel
              </Button>
              <Button
                onClick={() => mutation.mutate()}
                disabled={!emailValid || mutation.isPending}
              >
                {mutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Mail className="mr-2 h-4 w-4" />
                )}
                Send invitation
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
