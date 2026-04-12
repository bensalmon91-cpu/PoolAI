export const colors = {
  // Primary brand colors
  primary: '#0066CC',
  primaryLight: '#4D94DB',
  primaryDark: '#004C99',

  // Secondary colors
  secondary: '#00A3A3',
  secondaryLight: '#33CCCC',
  secondaryDark: '#007A7A',

  // Status colors
  success: '#28A745',
  warning: '#FFC107',
  error: '#DC3545',
  info: '#17A2B8',

  // Device status colors
  online: '#28A745',
  away: '#FFC107',
  offline: '#6C757D',

  // Alarm severity colors
  critical: '#DC3545',
  warningAlarm: '#FFC107',

  // Priority colors
  priority1: '#DC3545', // Highest
  priority2: '#FD7E14',
  priority3: '#FFC107',
  priority4: '#28A745',
  priority5: '#17A2B8', // Lowest

  // Background colors
  background: '#F8F9FA',
  surface: '#FFFFFF',
  surfaceVariant: '#F1F3F5',

  // Text colors
  textPrimary: '#212529',
  textSecondary: '#6C757D',
  textTertiary: '#ADB5BD',
  textInverse: '#FFFFFF',

  // Border colors
  border: '#DEE2E6',
  borderLight: '#E9ECEF',
  borderDark: '#CED4DA',

  // Overlay
  overlay: 'rgba(0, 0, 0, 0.5)',

  // Transparent
  transparent: 'transparent',
};

export type ColorName = keyof typeof colors;
