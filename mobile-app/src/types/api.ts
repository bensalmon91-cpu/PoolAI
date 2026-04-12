// API Response Types

export interface ApiResponse<T = any> {
  ok: boolean;
  error?: string;
  message?: string;
  data?: T;
}

export interface User {
  id: number;
  email: string;
  name: string;
  company?: string;
  phone?: string;
  created_at?: string;
  last_login_at?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export interface LoginResponse extends ApiResponse {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  user?: User;
  unverified?: boolean;
}

export interface Device {
  device_id: number;
  device_uuid: string;
  alias: string;
  nickname?: string;
  role: 'owner' | 'operator' | 'viewer';
  status: 'online' | 'away' | 'offline';
  last_seen: string;
  linked_at: string;
  link_id: number;
  ip_address?: string;
  software_version?: string;
  controllers_online?: number;
  controllers_offline?: number;
  alarms_total?: number;
  alarms_critical?: number;
  has_issues?: boolean;
  pending_suggestions?: number;
}

export interface DeviceDetail extends Device {
  health?: DeviceHealth;
  suggestions?: Suggestion[];
  pending_questions?: Question[];
}

export interface DeviceHealth {
  ts: string;
  uptime_seconds?: number;
  uptime_display?: string;
  disk_used_pct?: number;
  memory_used_pct?: number;
  cpu_temp?: number;
  software_version?: string;
  ip_address?: string;
  controllers_online?: number;
  controllers_offline?: number;
  controllers?: Controller[];
  alarms_total?: number;
  alarms_critical?: number;
  alarms_warning?: number;
  issues?: Issue[];
  has_issues?: boolean;
}

export interface Controller {
  name: string;
  status: 'online' | 'offline';
  ip?: string;
  last_reading?: string;
  readings?: {
    ph?: number;
    chlorine?: number;
    orp?: number;
    temperature?: number;
  };
}

export interface Issue {
  type: string;
  message: string;
  severity: 'critical' | 'warning' | 'info';
}

export interface HealthHistory {
  ts: string;
  cpu_temp?: number;
  memory_used_pct?: number;
  disk_used_pct?: number;
  controllers_online?: number;
  controllers_offline?: number;
  alarms_total?: number;
}

export interface Suggestion {
  id: number;
  pool: string;
  suggestion_type: string;
  title: string;
  body: string;
  priority: number;
  confidence?: number;
  status: 'pending' | 'delivered' | 'read' | 'acted_upon' | 'dismissed';
  created_at: string;
  delivered_at?: string;
  read_at?: string;
}

export interface Question {
  queue_id: number;
  question_id: number;
  pool: string;
  text: string;
  input_type: 'buttons' | 'dropdown' | 'text' | 'number' | 'date';
  options?: string[];
  priority: number;
  category: string;
  triggered_by?: string;
  created_at: string;
}

export interface NotificationPrefs {
  notify_alarms: boolean;
  notify_suggestions: boolean;
  notify_device_offline: boolean;
  notify_maintenance_due: boolean;
  quiet_hours_start?: string;
  quiet_hours_end?: string;
}

export interface PushNotification {
  id: number;
  device_id?: number;
  type: string;
  title: string;
  body?: string;
  sent_at: string;
  read_at?: string;
}
