// API Configuration
export const API_BASE_URL = __DEV__
  ? 'https://poolaissistant.modprojects.co.uk/api/mobile'
  : 'https://poolaissistant.modprojects.co.uk/api/mobile';

// Storage Keys
export const STORAGE_KEYS = {
  ACCESS_TOKEN: '@poolai_access_token',
  REFRESH_TOKEN: '@poolai_refresh_token',
  USER: '@poolai_user',
  PUSH_TOKEN: '@poolai_push_token',
  ONBOARDING_COMPLETE: '@poolai_onboarding_complete',
} as const;

// Device Status
export const DEVICE_STATUS = {
  ONLINE: 'online',
  AWAY: 'away',
  OFFLINE: 'offline',
} as const;

// Suggestion Status
export const SUGGESTION_STATUS = {
  PENDING: 'pending',
  DELIVERED: 'delivered',
  READ: 'read',
  ACTED_UPON: 'acted_upon',
  DISMISSED: 'dismissed',
} as const;

// Notification Types
export const NOTIFICATION_TYPES = {
  ALARM: 'alarm',
  SUGGESTION: 'suggestion',
  DEVICE_OFFLINE: 'device_offline',
  MAINTENANCE: 'maintenance',
} as const;

// Refresh Intervals (ms)
export const REFRESH_INTERVALS = {
  DEVICE_LIST: 60000, // 1 minute
  DEVICE_DETAIL: 30000, // 30 seconds
  HEALTH_DATA: 30000,
  SUGGESTIONS: 120000, // 2 minutes
} as const;
