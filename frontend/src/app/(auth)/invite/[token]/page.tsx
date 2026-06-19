"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { isAxiosError } from "axios";
import { Eye, EyeOff, Loader2, MailX, ShieldX, Clock } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { invitationsApi } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";
import type { InvitationValidateResponse, UserRole } from "@/types";

const ROLE_LABELS: Record<UserRole, string> = {
  org_admin: "Org Admin",
  legal_counsel: "Legal Counsel",
  compliance_officer: "Compliance Officer",
  viewer: "Viewer",
};

// "valid" shows the form; the others are terminal error states.
type ValidationState = "loading" | "valid" | "not_found" | "expired" | "used" | "error";

const acceptSchema = z
  .object({
    full_name: z.string().min(2, "Please enter your full name."),
    password: z.string().min(8, "Password must be at least 8 characters."),
    confirm_password: z.string().min(1, "Please confirm your password."),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match.",
    path: ["confirm_password"],
  });

type AcceptForm = z.infer<typeof acceptSchema>;

function passwordStrength(password: string) {
  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1;
  const labels = ["Very weak", "Weak", "Fair", "Good", "Strong"];
  const colors = [
    "bg-destructive",
    "bg-destructive",
    "bg-amber-500",
    "bg-blue-500",
    "bg-emerald-500",
  ];
  return { score, label: labels[score], color: colors[score] };
}

function ErrorCard({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof MailX;
  title: string;
  description: string;
}) {
  return (
    <Card className="border-border/60 shadow-xl shadow-primary/[0.03]">
      <CardHeader className="items-center text-center">
        <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
          <Icon className="h-6 w-6 text-muted-foreground" />
        </div>
        <CardTitle className="text-xl">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild variant="outline" className="w-full">
          <Link href="/login">Go to sign in</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

export default function AcceptInvitePage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const router = useRouter();
  const setTokens = useAuthStore((s) => s.setTokens);
  const setUser = useAuthStore((s) => s.setUser);
  const addNotification = useUIStore((s) => s.addNotification);

  const [state, setState] = useState<ValidationState>("loading");
  const [info, setInfo] = useState<InvitationValidateResponse | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<AcceptForm>({
    resolver: zodResolver(acceptSchema),
    defaultValues: { full_name: "", password: "", confirm_password: "" },
  });

  useEffect(() => {
    let active = true;
    invitationsApi
      .validateToken(token)
      .then((data) => {
        if (!active) return;
        setInfo(data);
        setState("valid");
      })
      .catch((error: unknown) => {
        if (!active) return;
        const code = isAxiosError(error) ? error.response?.status : undefined;
        if (code === 404) setState("not_found");
        else if (code === 410) setState("expired");
        else if (code === 409) setState("used");
        else setState("error");
      });
    return () => {
      active = false;
    };
  }, [token]);

  async function onSubmit(values: AcceptForm) {
    setServerError(null);
    try {
      const result = await invitationsApi.acceptInvitation({
        token,
        full_name: values.full_name,
        password: values.password,
        confirm_password: values.confirm_password,
      });
      setTokens(result.access_token, result.refresh_token);
      setUser(result.user);
      addNotification({
        type: "success",
        message: `Welcome to ${result.organisation.name}!`,
      });
      router.replace("/dashboard");
    } catch (error) {
      setServerError(getApiErrorMessage(error, "Unable to accept the invitation."));
    }
  }

  const passwordValue = watch("password");
  const strength = passwordStrength(passwordValue);

  if (state === "loading") {
    return (
      <Card className="border-border/60 shadow-xl shadow-primary/[0.03]">
        <CardContent className="flex flex-col items-center gap-3 py-12">
          <LoadingSpinner />
          <p className="text-sm text-muted-foreground">
            Checking your invitation…
          </p>
        </CardContent>
      </Card>
    );
  }

  if (state === "not_found") {
    return (
      <ErrorCard
        icon={ShieldX}
        title="Invalid invitation link"
        description="This invitation link is not valid. Please double-check the link or ask your administrator to send a new one."
      />
    );
  }

  if (state === "expired") {
    return (
      <ErrorCard
        icon={Clock}
        title="This invitation has expired"
        description="Ask your administrator to send you a new invitation."
      />
    );
  }

  if (state === "used") {
    return (
      <ErrorCard
        icon={MailX}
        title="This invitation has already been used"
        description="If you already have an account, sign in instead."
      />
    );
  }

  if (state === "error" || !info) {
    return (
      <ErrorCard
        icon={ShieldX}
        title="Something went wrong"
        description="We couldn't load this invitation. Please try again later."
      />
    );
  }

  return (
    <Card className="border-border/60 shadow-xl shadow-primary/[0.03]">
      <CardHeader className="space-y-1.5 pb-4">
        <CardTitle className="text-2xl">
          Join {info.organisation_name}
        </CardTitle>
        <CardDescription>
          You&apos;ve been invited as{" "}
          <Badge variant="secondary" className="align-middle">
            {ROLE_LABELS[info.role]}
          </Badge>
          . Set up your account to continue.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={info.email}
              readOnly
              disabled
              className="h-11 bg-muted/50"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="full_name">Full name</Label>
            <Input
              id="full_name"
              autoComplete="name"
              placeholder="Priya Sharma"
              className="h-11"
              aria-invalid={!!errors.full_name}
              {...register("full_name")}
            />
            {errors.full_name && (
              <p className="text-sm text-destructive">
                {errors.full_name.message}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                placeholder="At least 8 characters"
                className="h-11 pr-10"
                aria-invalid={!!errors.password}
                {...register("password")}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
            {passwordValue.length > 0 && (
              <div className="space-y-1">
                <div className="flex h-1.5 gap-1">
                  {[0, 1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className={cn(
                        "h-full flex-1 rounded-full transition-colors",
                        i < strength.score ? strength.color : "bg-muted",
                      )}
                    />
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  Password strength: {strength.label}
                </p>
              </div>
            )}
            {errors.password && (
              <p className="text-sm text-destructive">
                {errors.password.message}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirm_password">Confirm password</Label>
            <Input
              id="confirm_password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              placeholder="Re-enter your password"
              className="h-11"
              aria-invalid={!!errors.confirm_password}
              {...register("confirm_password")}
            />
            {errors.confirm_password && (
              <p className="text-sm text-destructive">
                {errors.confirm_password.message}
              </p>
            )}
          </div>

          {serverError && (
            <Alert variant="destructive">
              <AlertDescription>{serverError}</AlertDescription>
            </Alert>
          )}

          <Button
            type="submit"
            className="h-11 w-full text-[15px]"
            disabled={isSubmitting}
          >
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isSubmitting ? "Joining…" : `Join ${info.organisation_name}`}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-medium text-primary hover:underline"
          >
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
