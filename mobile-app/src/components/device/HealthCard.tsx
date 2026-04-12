import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Card } from '../common';
import { colors, spacing, typography } from '../../theme';
import type { DeviceHealth } from '../../types/api';

interface HealthCardProps {
  health: DeviceHealth;
}

interface MetricRowProps {
  label: string;
  value: string | number;
  unit?: string;
  status?: 'normal' | 'warning' | 'critical';
}

const MetricRow: React.FC<MetricRowProps> = ({ label, value, unit, status = 'normal' }) => {
  const statusColors = {
    normal: colors.textPrimary,
    warning: colors.warning,
    critical: colors.error,
  };

  return (
    <View style={styles.metricRow}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color: statusColors[status] }]}>
        {value}
        {unit && <Text style={styles.metricUnit}> {unit}</Text>}
      </Text>
    </View>
  );
};

export const HealthCard: React.FC<HealthCardProps> = ({ health }) => {
  const getPercentageStatus = (value: number | undefined): 'normal' | 'warning' | 'critical' => {
    if (!value) return 'normal';
    if (value >= 90) return 'critical';
    if (value >= 75) return 'warning';
    return 'normal';
  };

  const getTempStatus = (temp: number | undefined): 'normal' | 'warning' | 'critical' => {
    if (!temp) return 'normal';
    if (temp >= 80) return 'critical';
    if (temp >= 70) return 'warning';
    return 'normal';
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>System Health</Text>

      <View style={styles.grid}>
        <View style={styles.column}>
          <MetricRow
            label="Uptime"
            value={health.uptime_display || 'N/A'}
          />
          <MetricRow
            label="CPU Temp"
            value={health.cpu_temp?.toFixed(1) || 'N/A'}
            unit={health.cpu_temp ? '°C' : undefined}
            status={getTempStatus(health.cpu_temp)}
          />
        </View>

        <View style={styles.column}>
          <MetricRow
            label="Memory"
            value={health.memory_used_pct?.toFixed(0) || 'N/A'}
            unit={health.memory_used_pct ? '%' : undefined}
            status={getPercentageStatus(health.memory_used_pct)}
          />
          <MetricRow
            label="Disk"
            value={health.disk_used_pct?.toFixed(0) || 'N/A'}
            unit={health.disk_used_pct ? '%' : undefined}
            status={getPercentageStatus(health.disk_used_pct)}
          />
        </View>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>
          {health.controllers_online || 0} controllers online
          {(health.controllers_offline || 0) > 0 ? (
            <Text style={styles.offlineText}> / {health.controllers_offline} offline</Text>
          ) : null}
        </Text>
        {(health.alarms_total || 0) > 0 ? (
          <Text style={styles.alarmsText}>
            {health.alarms_total} active alarm{health.alarms_total !== 1 ? 's' : ''}
          </Text>
        ) : null}
      </View>
    </Card>
  );
};

const styles = StyleSheet.create({
  card: {
    marginBottom: spacing.md,
  },
  title: {
    ...typography.h4,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  grid: {
    flexDirection: 'row',
    marginBottom: spacing.md,
  },
  column: {
    flex: 1,
  },
  metricRow: {
    marginBottom: spacing.sm,
  },
  metricLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: 2,
  },
  metricValue: {
    ...typography.h4,
    color: colors.textPrimary,
  },
  metricUnit: {
    ...typography.body,
    fontWeight: '400',
  },
  footer: {
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    paddingTop: spacing.md,
  },
  footerText: {
    ...typography.bodySmall,
    color: colors.textSecondary,
  },
  offlineText: {
    color: colors.error,
  },
  alarmsText: {
    ...typography.bodySmall,
    color: colors.warning,
    marginTop: spacing.xs,
  },
});
