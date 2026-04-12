import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Card, StatusBadge } from '../common';
import { colors, spacing, typography } from '../../theme';
import type { Device } from '../../types/api';

interface DeviceCardProps {
  device: Device;
  onPress: () => void;
}

export const DeviceCard: React.FC<DeviceCardProps> = ({ device, onPress }) => {
  const displayName = device.nickname || device.alias || 'Unnamed Device';
  const hasAlarms = (device.alarms_total || 0) > 0;
  const hasCritical = (device.alarms_critical || 0) > 0;

  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.7}>
      <Card style={styles.card} variant="elevated">
        <View style={styles.header}>
          <View style={styles.titleContainer}>
            <Text style={styles.name} numberOfLines={1}>
              {displayName}
            </Text>
            <StatusBadge status={device.status} />
          </View>
          {device.pending_suggestions && device.pending_suggestions > 0 && (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{device.pending_suggestions}</Text>
            </View>
          )}
        </View>

        <View style={styles.info}>
          <View style={styles.infoRow}>
            <Text style={styles.label}>Controllers:</Text>
            <Text style={styles.value}>
              {device.controllers_online || 0} online
              {(device.controllers_offline || 0) > 0 ? (
                <Text style={styles.offlineText}>
                  {' '}/ {device.controllers_offline} offline
                </Text>
              ) : null}
            </Text>
          </View>

          {hasAlarms ? (
            <View style={styles.infoRow}>
              <Text style={styles.label}>Alarms:</Text>
              <Text
                style={[styles.value, hasCritical ? styles.criticalText : styles.warningText]}
              >
                {device.alarms_total || 0} active
                {hasCritical ? ` (${device.alarms_critical} critical)` : ''}
              </Text>
            </View>
          ) : null}

          {device.software_version ? (
            <View style={styles.infoRow}>
              <Text style={styles.label}>Version:</Text>
              <Text style={styles.value}>{device.software_version}</Text>
            </View>
          ) : null}
        </View>

        {device.has_issues ? (
          <View style={styles.issuesBanner}>
            <Text style={styles.issuesText}>Issues detected</Text>
          </View>
        ) : null}
      </Card>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  card: {
    marginBottom: spacing.md,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.md,
  },
  titleContainer: {
    flex: 1,
  },
  name: {
    ...typography.h4,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  badge: {
    backgroundColor: colors.primary,
    borderRadius: 12,
    minWidth: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.sm,
  },
  badgeText: {
    ...typography.caption,
    color: colors.textInverse,
    fontWeight: '600',
  },
  info: {
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
    paddingTop: spacing.md,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  label: {
    ...typography.bodySmall,
    color: colors.textSecondary,
  },
  value: {
    ...typography.bodySmall,
    color: colors.textPrimary,
    fontWeight: '500',
  },
  offlineText: {
    color: colors.error,
  },
  warningText: {
    color: colors.warning,
  },
  criticalText: {
    color: colors.error,
  },
  issuesBanner: {
    backgroundColor: colors.warning + '20',
    marginTop: spacing.md,
    marginHorizontal: -spacing.md,
    marginBottom: -spacing.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderBottomLeftRadius: 12,
    borderBottomRightRadius: 12,
  },
  issuesText: {
    ...typography.caption,
    color: colors.warning,
    fontWeight: '600',
    textAlign: 'center',
  },
});
