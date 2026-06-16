"use client";

import { useEffect } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  useUIStore,
  type Notification,
  type NotificationType,
} from "@/store/ui";

const DEFAULT_DURATION = 5_000;

const ICONS: Record<NotificationType, typeof Info> = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const ACCENTS: Record<NotificationType, string> = {
  success: "border-l-emerald-500",
  error: "border-l-destructive",
  warning: "border-l-amber-500",
  info: "border-l-blue-500",
};

const ICON_COLORS: Record<NotificationType, string> = {
  success: "text-emerald-500",
  error: "text-destructive",
  warning: "text-amber-500",
  info: "text-blue-500",
};

function NotificationToast({ notification }: { notification: Notification }) {
  const remove = useUIStore((s) => s.removeNotification);
  const Icon = ICONS[notification.type];

  useEffect(() => {
    const duration = notification.duration ?? DEFAULT_DURATION;
    const timer = setTimeout(() => remove(notification.id), duration);
    return () => clearTimeout(timer);
  }, [notification.id, notification.duration, remove]);

  return (
    <div
      role="status"
      className={cn(
        "pointer-events-auto flex w-full items-start gap-3 rounded-md border border-l-4 bg-card p-4 text-card-foreground shadow-lg animate-in slide-in-from-right-5 fade-in-0",
        ACCENTS[notification.type],
      )}
    >
      <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", ICON_COLORS[notification.type])} />
      <p className="flex-1 text-sm leading-relaxed">{notification.message}</p>
      <button
        type="button"
        onClick={() => remove(notification.id)}
        className="shrink-0 rounded-sm text-muted-foreground transition-colors hover:text-foreground"
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export function NotificationPanel() {
  const notifications = useUIStore((s) => s.notifications);

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-full max-w-sm flex-col gap-2">
      {notifications.map((notification) => (
        <NotificationToast key={notification.id} notification={notification} />
      ))}
    </div>
  );
}
