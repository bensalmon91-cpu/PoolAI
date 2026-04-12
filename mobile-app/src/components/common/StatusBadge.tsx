import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, borderRadius, typography } from '../../theme';

type StatusType = 'online' | 'away' | 'offline' | 'success' | 'warning' | 'error' | 'info';

interface StatusBadgeProps {
  status: StatusType;
  label?: string;
  size?: 'small' | 'medium';
}

const statusColors: Record<StatusType, string> = {
  online: colors.online,
  away: colors.away,
  offline: colors.offline,
  success: colors.success,
  warning: colors.warning,
  error: colors.error,
  info: colors.info,
};

const defaultLabels: Record<StatusType, string> = {
  online: 'Online',
  away: 'Away',
  offline: 'Offline',
  success: 'Success',
  warning: 'Warning',
  error: 'Error',
  info: 'Info',
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  label,
  size = 'medium',
}) => {
  const color = statusColors[status];
  const displayLabel = label || defaultLabels[status];

  return (
    <View style={[styles.container, styles[`container_${size}`]]}>
      <View style={[styles.dot, styles[`dot_${size}`], { backgroundColor: color }]} />
      <Text style={[styles.label, styles[`label_${size}`]]}>{displayLabel}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  container_small: {
    paddingVertical: 2,
    paddingHorizontal: spacing.sm,
  },
  container_medium: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
  },
  dot: {
    borderRadius: borderRadius.full,
  },
  dot_small: {
    width: 6,
    height: 6,
    marginRight: spacing.xs,
  },
  dot_medium: {
    width: 8,
    height: 8,
    marginRight: spacing.sm,
  },
  label: {
    ...typography.caption,
    color: colors.textSecondary,
    textTransform: 'capitalize',
  },
  label_small: {
    fontSize: 10,
  },
  label_medium: {
    fontSize: 12,
  },
});
