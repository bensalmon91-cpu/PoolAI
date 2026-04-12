import api from './api';
import { storage } from './storage';
import { STORAGE_KEYS } from '../utils/constants';
import { Platform } from 'react-native';
import type { LoginResponse, ApiResponse, User } from '../types/api';

const platform = Platform.OS === 'ios' ? 'ios' : 'android';

export const authService = {
  /**
   * Register a new user
   */
  async register(
    email: string,
    password: string,
    name?: string,
    company?: string
  ): Promise<ApiResponse> {
    const response = await api.post('/auth/register.php', {
      email,
      password,
      name,
      company,
    });
    return response.data;
  },

  /**
   * Login user and store tokens
   */
  async login(email: string, password: string): Promise<LoginResponse> {
    const deviceInfo = `${Platform.OS} ${Platform.Version}`;

    const response = await api.post<LoginResponse>('/auth/login.php', {
      email,
      password,
      platform,
      device_info: deviceInfo,
    });

    const data = response.data;

    if (data.ok && data.access_token && data.refresh_token) {
      await storage.setAccessToken(data.access_token);
      await storage.setRefreshToken(data.refresh_token);
      if (data.user) {
        await storage.set(STORAGE_KEYS.USER, data.user);
      }
    }

    return data;
  },

  /**
   * Logout user and clear tokens
   */
  async logout(): Promise<void> {
    try {
      const refreshToken = await storage.getRefreshToken();
      if (refreshToken) {
        await api.post('/auth/logout.php', {
          refresh_token: refreshToken,
        });
      }
    } catch (e) {
      // Ignore logout errors
      console.log('Logout API error:', e);
    } finally {
      await storage.clearAuth();
    }
  },

  /**
   * Refresh access token
   */
  async refresh(): Promise<boolean> {
    try {
      const refreshToken = await storage.getRefreshToken();
      if (!refreshToken) {
        return false;
      }

      const response = await api.post('/auth/refresh.php', {
        refresh_token: refreshToken,
      });

      if (response.data.ok && response.data.access_token) {
        await storage.setAccessToken(response.data.access_token);
        return true;
      }

      return false;
    } catch (e) {
      return false;
    }
  },

  /**
   * Request password reset
   */
  async forgotPassword(email: string): Promise<ApiResponse> {
    const response = await api.post('/auth/forgot-password.php', { email });
    return response.data;
  },

  /**
   * Reset password with token
   */
  async resetPassword(token: string, password: string): Promise<ApiResponse> {
    const response = await api.post('/auth/reset-password.php', {
      token,
      password,
    });
    return response.data;
  },

  /**
   * Get current user info
   */
  async getAccount(): Promise<{ ok: boolean; user?: User }> {
    const response = await api.get('/account.php');
    return response.data;
  },

  /**
   * Update user profile
   */
  async updateProfile(data: Partial<User>): Promise<ApiResponse<User>> {
    const response = await api.patch('/account.php', data);
    if (response.data.ok && response.data.user) {
      await storage.set(STORAGE_KEYS.USER, response.data.user);
    }
    return response.data;
  },

  /**
   * Change password
   */
  async changePassword(
    currentPassword: string,
    newPassword: string
  ): Promise<ApiResponse> {
    const response = await api.post('/account.php?action=password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },

  /**
   * Check if user has stored auth tokens
   */
  async hasStoredAuth(): Promise<boolean> {
    const token = await storage.getAccessToken();
    return !!token;
  },

  /**
   * Get stored user from storage
   */
  async getStoredUser(): Promise<User | null> {
    return storage.get<User>(STORAGE_KEYS.USER);
  },
};
