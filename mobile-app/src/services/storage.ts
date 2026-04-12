import AsyncStorage from '@react-native-async-storage/async-storage';
import { STORAGE_KEYS } from '../utils/constants';

/**
 * Secure storage wrapper for persisting data
 */
class StorageService {
  async set(key: string, value: any): Promise<void> {
    try {
      const jsonValue = JSON.stringify(value);
      await AsyncStorage.setItem(key, jsonValue);
    } catch (e) {
      console.error('Storage set error:', e);
      throw e;
    }
  }

  async get<T>(key: string): Promise<T | null> {
    try {
      const jsonValue = await AsyncStorage.getItem(key);
      return jsonValue != null ? JSON.parse(jsonValue) : null;
    } catch (e) {
      console.error('Storage get error:', e);
      return null;
    }
  }

  async remove(key: string): Promise<void> {
    try {
      await AsyncStorage.removeItem(key);
    } catch (e) {
      console.error('Storage remove error:', e);
    }
  }

  async clear(): Promise<void> {
    try {
      await AsyncStorage.clear();
    } catch (e) {
      console.error('Storage clear error:', e);
    }
  }

  // Auth-specific helpers
  async getAccessToken(): Promise<string | null> {
    return this.get<string>(STORAGE_KEYS.ACCESS_TOKEN);
  }

  async setAccessToken(token: string): Promise<void> {
    return this.set(STORAGE_KEYS.ACCESS_TOKEN, token);
  }

  async getRefreshToken(): Promise<string | null> {
    return this.get<string>(STORAGE_KEYS.REFRESH_TOKEN);
  }

  async setRefreshToken(token: string): Promise<void> {
    return this.set(STORAGE_KEYS.REFRESH_TOKEN, token);
  }

  async clearAuth(): Promise<void> {
    await Promise.all([
      this.remove(STORAGE_KEYS.ACCESS_TOKEN),
      this.remove(STORAGE_KEYS.REFRESH_TOKEN),
      this.remove(STORAGE_KEYS.USER),
    ]);
  }
}

export const storage = new StorageService();
