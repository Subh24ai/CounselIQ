import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";

import { authApi } from "@/lib/api";
import type { User } from "@/types";

// Cookie the Next.js middleware reads on the server (localStorage is not
// available there). Kept in sync with the persisted access token.
const ACCESS_COOKIE = "access_token";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 7; // 7 days

function setAccessCookie(token: string): void {
  if (typeof document === "undefined") return;
  document.cookie = `${ACCESS_COOKIE}=${token}; path=/; SameSite=Lax; max-age=${COOKIE_MAX_AGE}`;
}

function clearAccessCookie(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${ACCESS_COOKIE}=; path=/; SameSite=Lax; max-age=0`;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  setTokens: (access: string, refresh: string) => void;
  setUser: (user: User) => void;
  logout: () => void;
  initialize: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: true,

      setTokens: (access, refresh) => {
        setAccessCookie(access);
        set({
          accessToken: access,
          refreshToken: refresh,
          isAuthenticated: true,
        });
      },

      setUser: (user) => set({ user }),

      logout: () => {
        clearAccessCookie();
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          isLoading: false,
        });
        // Fire-and-forget server logout; local session is already cleared.
        void authApi.logout();
      },

      initialize: async () => {
        const token = get().accessToken;
        if (!token) {
          set({ isLoading: false, isAuthenticated: false });
          return;
        }
        // Ensure the middleware cookie matches the rehydrated token.
        setAccessCookie(token);
        try {
          const user = await authApi.getMe();
          set({ user, isAuthenticated: true, isLoading: false });
        } catch {
          clearAccessCookie();
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
            isLoading: false,
          });
        }
      },
    }),
    {
      name: "counseliq.auth",
      // Guard SSR: localStorage only exists in the browser.
      storage: createJSONStorage(() =>
        typeof window !== "undefined"
          ? window.localStorage
          : (undefined as unknown as StateStorage),
      ),
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
