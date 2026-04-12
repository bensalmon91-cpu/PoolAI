import api from './api';
import { storage } from './storage';
import { STORAGE_KEYS } from '../utils/constants';
import type { ApiResponse, PushNotification, NotificationPrefs } from '../types/api';

export const pushService = {
  /**
   * Register FCM token with server
   */
  async registerToken(
    fcmToken: string,
    platform: 'ios' | 'android',
    deviceInfo?: string
  ): Promise<ApiResponse> {
    const response = await api.post('/push.php', {
      fcm_token: fcmToken,
      platform,
      device_info: deviceInfo,
    });

    if (response.data.ok) {
      await storage.set(STORAGE_KEYS.PUSH_TOKEN, fcmToken);
    }

    return response.data;
  },

  /**
   * Unregister FCM token
   */
  async unregisterToken(fcmToken: string): Promise<ApiResponse> {
    const response = await api.delete('/push.php', {
      data: { fcm_token: fcmToken },
    });

    await storage.remove(STORAGE_KEYS.PUSH_TOKEN);

    return response.data;
  },

  /**
   * Get notification history
   */
  async getHistory(
    limit: number = 50
  ): Promise<{ ok: boolean; notifications: PushNotification[] }> {
    const response = await api.get(`/push.php?history=1&limit=${limit}`);
    return response.data;
  },

  /**
   * Mark notification as read
   */
  async markAsRead(notificationId: number): Promise<ApiResponse> {
    const response = await api.post(`/push.php?action=read&id=${notificationId}`);
    return response.data;
  },

  /**
   * Get notification preferences
   */
  async getPreferences(
    deviceId?: number
  ): Promise<{ ok: boolean; preferences: NotificationPrefs[] }> {
    let url = '/notifications.php';
    if (deviceId) {
      url += `?device_id=${deviceId}`;
    }
    const response = await api.get(url);
    return response.data;
  },

  /**
   * Update notification preferences
   */
  async updatePreferences(
    prefs: Partial<NotificationPrefs>,
    deviceId?: number
  ): Promise<ApiResponse> {
    let url = '/notifications.php';
    if (deviceId) {
      url += `?device_id=${deviceId}`;
    }
    const response = await api.patch(url, prefs);
    return response.data;
  },

  /**
   * Get stored FCM token
   */
  async getStoredToken(): Promise<string | null> {
    return storage.get<string>(STORAGE_KEYS.PUSH_TOKEN);
  },
};
