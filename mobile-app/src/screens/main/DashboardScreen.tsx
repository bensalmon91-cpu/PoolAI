import React, { useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { DeviceCard } from '../../components/device';
import { Loading } from '../../components/common';
import { useDeviceStore } from '../../stores';
import { colors, spacing, typography } from '../../theme';
import type { Device } from '../../types/api';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

export const DashboardScreen: React.FC<Props> = ({ navigation }) => {
  const { devices, isLoading, isRefreshing, error, fetchDevices, clearError } =
    useDeviceStore();

  useEffect(() => {
    fetchDevices();
  }, []);

  const handleRefresh = useCallback(() => {
    fetchDevices();
  }, [fetchDevices]);

  const handleDevicePress = (device: Device) => {
    navigation.navigate('Device', { deviceId: device.device_id });
  };

  const renderDevice = ({ item }: { item: Device }) => (
    <DeviceCard device={item} onPress={() => handleDevicePress(item)} />
  );

  const renderEmpty = () => {
    if (isLoading) return null;

    return (
      <View style={styles.emptyContainer}>
        <Text style={styles.emptyTitle}>No Devices</Text>
        <Text style={styles.emptyText}>
          Link a device to get started. Tap the + button to add your first device.
        </Text>
        <TouchableOpacity
          style={styles.linkButton}
          onPress={() => navigation.navigate('LinkDevice')}
        >
          <Text style={styles.linkButtonText}>Link Device</Text>
        </TouchableOpacity>
      </View>
    );
  };

  if (isLoading && devices.length === 0) {
    return <Loading fullScreen message="Loading devices..." />;
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>My Devices</Text>
        <TouchableOpacity
          style={styles.addButton}
          onPress={() => navigation.navigate('LinkDevice')}
        >
          <Text style={styles.addButtonText}>+</Text>
        </TouchableOpacity>
      </View>

      {error ? (
        <TouchableOpacity style={styles.errorBanner} onPress={clearError}>
          <Text style={styles.errorText}>{error}</Text>
          <Text style={styles.dismissText}>Tap to dismiss</Text>
        </TouchableOpacity>
      ) : null}

      <FlatList
        data={devices}
        renderItem={renderDevice}
        keyExtractor={(item) => item.device_id.toString()}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={handleRefresh}
            colors={[colors.primary]}
            tintColor={colors.primary}
          />
        }
        ListEmptyComponent={renderEmpty}
      />
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  title: {
    ...typography.h2,
    color: colors.textPrimary,
  },
  addButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addButtonText: {
    fontSize: 24,
    color: colors.textInverse,
    fontWeight: '300',
    marginTop: -2,
  },
  list: {
    padding: spacing.md,
    flexGrow: 1,
  },
  errorBanner: {
    backgroundColor: colors.error + '10',
    padding: spacing.md,
    marginHorizontal: spacing.md,
    borderRadius: 8,
    marginBottom: spacing.sm,
  },
  errorText: {
    ...typography.bodySmall,
    color: colors.error,
  },
  dismissText: {
    ...typography.caption,
    color: colors.error,
    marginTop: spacing.xs,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  emptyTitle: {
    ...typography.h3,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  emptyText: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.lg,
  },
  linkButton: {
    backgroundColor: colors.primary,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderRadius: 8,
  },
  linkButtonText: {
    ...typography.button,
    color: colors.textInverse,
  },
});
