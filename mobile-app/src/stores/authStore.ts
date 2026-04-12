import { create } from 'zustand';
import { authService } from '../services/auth';
import type { User } from '../types/api';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  initialize: () => Promise<void>;
  login: (email: string, password: string) => Promise<boolean>;
  register: (
    email: string,
    password: string,
    name?: string,
    company?: string
  ) => Promise<{ ok: boolean; message?: string; error?: string }>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  updateProfile: (data: Partial<User>) => Promise<boolean>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<{ ok: boolean; error?: string }>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,

  initialize: async () => {
    set({ isLoading: true });
    try {
      const hasAuth = await authService.hasStoredAuth();
      if (hasAuth) {
        // Try to get stored user first
        const storedUser = await authService.getStoredUser();
        if (storedUser) {
          set({ user: storedUser, isAuthenticated: true });
        }

        // Then refresh from server
        try {
          const response = await authService.getAccount();
          if (response.ok && response.user) {
            set({ user: response.user, isAuthenticated: true });
          } else {
            // Token might be invalid, try refresh
            const refreshed = await authService.refresh();
            if (refreshed) {
              const retryResponse = await authService.getAccount();
              if (retryResponse.ok && retryResponse.user) {
                set({ user: retryResponse.user, isAuthenticated: true });
              } else {
                await authService.logout();
                set({ user: null, isAuthenticated: false });
              }
            } else {
              await authService.logout();
              set({ user: null, isAuthenticated: false });
            }
          }
        } catch (e) {
          // Network error - keep stored user if available
          if (!storedUser) {
            set({ user: null, isAuthenticated: false });
          }
        }
      } else {
        set({ user: null, isAuthenticated: false });
      }
    } catch (e) {
      set({ user: null, isAuthenticated: false });
    } finally {
      set({ isLoading: false });
    }
  },

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await authService.login(email, password);

      if (response.ok && response.user) {
        set({
          user: response.user,
          isAuthenticated: true,
          isLoading: false,
        });
        return true;
      } else {
        set({
          error: response.error || 'Login failed',
          isLoading: false,
        });
        return false;
      }
    } catch (e: any) {
      const message = e.response?.data?.error || e.message || 'Login failed';
      set({ error: message, isLoading: false });
      return false;
    }
  },

  register: async (email: string, password: string, name?: string, company?: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await authService.register(email, password, name, company);
      set({ isLoading: false });

      if (response.ok) {
        return { ok: true, message: response.message };
      } else {
        return { ok: false, error: response.error };
      }
    } catch (e: any) {
      const message = e.response?.data?.error || e.message || 'Registration failed';
      set({ error: message, isLoading: false });
      return { ok: false, error: message };
    }
  },

  logout: async () => {
    set({ isLoading: true });
    try {
      await authService.logout();
    } finally {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      });
    }
  },

  refreshUser: async () => {
    try {
      const response = await authService.getAccount();
      if (response.ok && response.user) {
        set({ user: response.user });
      }
    } catch (e) {
      console.log('Failed to refresh user:', e);
    }
  },

  updateProfile: async (data: Partial<User>) => {
    try {
      const response = await authService.updateProfile(data);
      if (response.ok && response.data) {
        set({ user: response.data });
        return true;
      }
      return false;
    } catch (e) {
      return false;
    }
  },

  changePassword: async (currentPassword: string, newPassword: string) => {
    try {
      const response = await authService.changePassword(currentPassword, newPassword);
      return { ok: response.ok, error: response.error };
    } catch (e: any) {
      return { ok: false, error: e.response?.data?.error || 'Failed to change password' };
    }
  },

  clearError: () => set({ error: null }),
}));
