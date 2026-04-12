import { create } from 'zustand';
import { deviceService } from '../services/devices';
import type { Device, DeviceDetail, Suggestion, Question } from '../types/api';

interface DeviceState {
  devices: Device[];
  selectedDevice: DeviceDetail | null;
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;

  // Actions
  fetchDevices: () => Promise<void>;
  fetchDevice: (deviceId: number) => Promise<void>;
  linkDevice: (code: string) => Promise<{ ok: boolean; error?: string }>;
  unlinkDevice: (deviceId: number) => Promise<{ ok: boolean; error?: string }>;
  updateNickname: (deviceId: number, nickname: string) => Promise<boolean>;
  markSuggestionRead: (deviceId: number, suggestionId: number) => Promise<void>;
  answerQuestion: (
    deviceId: number,
    queueId: number,
    answer: string
  ) => Promise<{ ok: boolean; error?: string }>;
  clearSelectedDevice: () => void;
  clearError: () => void;
}

export const useDeviceStore = create<DeviceState>((set, get) => ({
  devices: [],
  selectedDevice: null,
  isLoading: false,
  isRefreshing: false,
  error: null,

  fetchDevices: async () => {
    const state = get();
    const isInitial = state.devices.length === 0;
    set({ isLoading: isInitial, isRefreshing: !isInitial, error: null });

    try {
      const response = await deviceService.getDevices();
      if (response.ok) {
        set({ devices: response.devices });
      } else {
        set({ error: 'Failed to load devices' });
      }
    } catch (e: any) {
      set({ error: e.message || 'Failed to load devices' });
    } finally {
      set({ isLoading: false, isRefreshing: false });
    }
  },

  fetchDevice: async (deviceId: number) => {
    set({ isLoading: true, error: null });

    try {
      const response = await deviceService.getDevice(deviceId);
      if (response.ok && response.device) {
        set({ selectedDevice: response.device });
      } else {
        set({ error: 'Device not found' });
      }
    } catch (e: any) {
      set({ error: e.message || 'Failed to load device' });
    } finally {
      set({ isLoading: false });
    }
  },

  linkDevice: async (code: string) => {
    try {
      const response = await deviceService.linkDevice(code);
      if (response.ok) {
        // Refresh device list
        await get().fetchDevices();
        return { ok: true };
      }
      return { ok: false, error: response.error };
    } catch (e: any) {
      return { ok: false, error: e.response?.data?.error || 'Failed to link device' };
    }
  },

  unlinkDevice: async (deviceId: number) => {
    try {
      const response = await deviceService.unlinkDevice(deviceId);
      if (response.ok) {
        // Remove from local state
        set((state) => ({
          devices: state.devices.filter((d) => d.device_id !== deviceId),
          selectedDevice:
            state.selectedDevice?.device_id === deviceId ? null : state.selectedDevice,
        }));
        return { ok: true };
      }
      return { ok: false, error: response.error };
    } catch (e: any) {
      return { ok: false, error: e.response?.data?.error || 'Failed to unlink device' };
    }
  },

  updateNickname: async (deviceId: number, nickname: string) => {
    try {
      const response = await deviceService.updateNickname(deviceId, nickname);
      if (response.ok) {
        // Update local state
        set((state) => ({
          devices: state.devices.map((d) =>
            d.device_id === deviceId ? { ...d, nickname } : d
          ),
          selectedDevice:
            state.selectedDevice?.device_id === deviceId
              ? { ...state.selectedDevice, nickname }
              : state.selectedDevice,
        }));
        return true;
      }
      return false;
    } catch (e) {
      return false;
    }
  },

  markSuggestionRead: async (deviceId: number, suggestionId: number) => {
    try {
      await deviceService.suggestionFeedback(deviceId, suggestionId, 'read');

      // Update local state
      set((state) => {
        if (!state.selectedDevice) return state;

        const updatedSuggestions = state.selectedDevice.suggestions?.map((s) =>
          s.id === suggestionId ? { ...s, status: 'read' as const } : s
        );

        return {
          selectedDevice: {
            ...state.selectedDevice,
            suggestions: updatedSuggestions,
          },
        };
      });
    } catch (e) {
      console.log('Failed to mark suggestion as read:', e);
    }
  },

  answerQuestion: async (deviceId: number, queueId: number, answer: string) => {
    try {
      const response = await deviceService.answerQuestion(deviceId, queueId, answer);
      if (response.ok) {
        // Remove answered question from local state
        set((state) => {
          if (!state.selectedDevice) return state;

          const updatedQuestions = state.selectedDevice.pending_questions?.filter(
            (q) => q.queue_id !== queueId
          );

          return {
            selectedDevice: {
              ...state.selectedDevice,
              pending_questions: updatedQuestions,
            },
          };
        });
        return { ok: true };
      }
      return { ok: false, error: response.error };
    } catch (e: any) {
      return { ok: false, error: e.response?.data?.error || 'Failed to submit answer' };
    }
  },

  clearSelectedDevice: () => set({ selectedDevice: null }),

  clearError: () => set({ error: null }),
}));
