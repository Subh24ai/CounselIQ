"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { useAuthStore } from "@/store/auth";
import { useWebSocketStore } from "@/store/websocket";

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const user = useAuthStore((s) => s.user);
  const accessToken = useAuthStore((s) => s.accessToken);

  const connect = useWebSocketStore((s) => s.connect);
  const disconnect = useWebSocketStore((s) => s.disconnect);

  // Redirect unauthenticated users once the auth bootstrap has settled.
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  // Open the org-scoped WebSocket once we know the user and have a token.
  useEffect(() => {
    if (isAuthenticated && user?.organisation_id && accessToken) {
      connect(user.organisation_id, accessToken);
      return () => disconnect();
    }
  }, [isAuthenticated, user?.organisation_id, accessToken, connect, disconnect]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <LoadingSpinner size="lg" label="Loading your workspace…" />
      </div>
    );
  }

  if (!isAuthenticated) {
    // Redirect is in flight; render nothing to avoid a flash of content.
    return null;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto bg-muted/30 p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
