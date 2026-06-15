import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import { TOKEN_STORAGE_KEY } from "@/lib/api";
import type { User } from "@/types";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  setSession: (user: User, accessToken: string) => void;
  setUser: (user: User | null) => void;
  logout: () => void;
}

/**
 * Auth store. The access token is also mirrored into a plain localStorage key
 * (TOKEN_STORAGE_KEY) so the axios interceptor in lib/api.ts can read it
 * synchronously without importing the store.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      isAuthenticated: false,

      setSession: (user, accessToken) => {
        if (typeof window !== "undefined") {
          window.localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
        }
        set({ user, accessToken, isAuthenticated: true });
      },

      setUser: (user) => set({ user }),

      logout: () => {
        if (typeof window !== "undefined") {
          window.localStorage.removeItem(TOKEN_STORAGE_KEY);
        }
        set({ user: null, accessToken: null, isAuthenticated: false });
      },
    }),
    {
      name: "counseliq.auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
