import api from './api';
import type {
  Device,
  DeviceDetail,
  DeviceHealth,
  HealthHistory,
  Suggestion,
  Question,
  ApiResponse,
} from '../types/api';

export const deviceService = {
  /**
   * Get all user's devices
   */
  async getDevices(): Promise<{ ok: boolean; devices: Device[] }> {
    const response = await api.get('/devices.php');
    return response.data;
  },

  /**
   * Get single device with details
   */
  async getDevice(deviceId: number): Promise<{ ok: boolean; device?: DeviceDetail }> {
    const response = await api.get(`/device.php?id=${deviceId}`);
    return response.data;
  },

  /**
   * Link device using code
   */
  async linkDevice(code: string): Promise<ApiResponse<{ device: Device }>> {
    const response = await api.post('/link.php', { code });
    return response.data;
  },

  /**
   * Unlink device
   */
  async unlinkDevice(deviceId: number): Promise<ApiResponse> {
    const response = await api.delete(`/device.php?id=${deviceId}`);
    return response.data;
  },

  /**
   * Update device nickname
   */
  async updateNickname(deviceId: number, nickname: string): Promise<ApiResponse> {
    const response = await api.patch(`/device.php?id=${deviceId}`, { nickname });
    return response.data;
  },

  /**
   * Get device health data
   */
  async getHealth(deviceId: number): Promise<{ ok: boolean; health?: DeviceHealth }> {
    const response = await api.get(`/health.php?device_id=${deviceId}`);
    return response.data;
  },

  /**
   * Get health history for charts
   */
  async getHealthHistory(
    deviceId: number,
    hours: number = 24
  ): Promise<{ ok: boolean; history: HealthHistory[] }> {
    const response = await api.get(`/health.php?device_id=${deviceId}&hours=${hours}`);
    return response.data;
  },

  /**
   * Get AI suggestions for device
   */
  async getSuggestions(
    deviceId: number,
    limit: number = 10,
    status?: string
  ): Promise<{ ok: boolean; suggestions: Suggestion[] }> {
    let url = `/suggestions.php?device_id=${deviceId}&limit=${limit}`;
    if (status) {
      url += `&status=${status}`;
    }
    const response = await api.get(url);
    return response.data;
  },

  /**
   * Submit feedback on suggestion
   */
  async suggestionFeedback(
    deviceId: number,
    suggestionId: number,
    action: 'read' | 'acted_upon' | 'dismissed',
    feedback?: string
  ): Promise<ApiResponse> {
    const response = await api.post(
      `/suggestions.php?device_id=${deviceId}&id=${suggestionId}`,
      { action, feedback }
    );
    return response.data;
  },

  /**
   * Get pending AI questions
   */
  async getQuestions(deviceId: number): Promise<{ ok: boolean; questions: Question[] }> {
    const response = await api.get(`/questions.php?device_id=${deviceId}`);
    return response.data;
  },

  /**
   * Answer AI question
   */
  async answerQuestion(
    deviceId: number,
    queueId: number,
    answer: string,
    answerJson?: any
  ): Promise<ApiResponse> {
    const response = await api.post(`/questions.php?device_id=${deviceId}&id=${queueId}`, {
      answer,
      answer_json: answerJson,
    });
    return response.data;
  },
};
