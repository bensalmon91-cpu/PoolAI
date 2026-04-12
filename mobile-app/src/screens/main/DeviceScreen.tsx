import React, { useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RouteProp } from '@react-navigation/native';
import { HealthCard } from '../../components/device';
import { SuggestionCard, QuestionCard } from '../../components/ai';
import { Loading, StatusBadge, Card } from '../../components/common';
import { useDeviceStore } from '../../stores';
import { colors, spacing, typography } from '../../theme';

type Props = {
  navigation: NativeStackNavigationProp<any>;
  route: RouteProp<{ Device: { deviceId: number } }, 'Device'>;
};

export const DeviceScreen: React.FC<Props> = ({ navigation, route }) => {
  const { deviceId } = route.params;

  const {
    selectedDevice,
    isLoading,
    error,
    fetchDevice,
    clearSelectedDevice,
    markSuggestionRead,
    answerQuestion,
    unlinkDevice,
  } = useDeviceStore();

  useEffect(() => {
    fetchDevice(deviceId);
    return () => clearSelectedDevice();
  }, [deviceId]);

  const handleRefresh = useCallback(() => {
    fetchDevice(deviceId);
  }, [deviceId]);

  const handleSuggestionPress = async (suggestionId: number) => {
    await markSuggestionRead(deviceId, suggestionId);
  };

  const handleAnswerQuestion = async (queueId: number, answer: string) => {
    const result = await answerQuestion(deviceId, queueId, answer);
    if (!result.ok) {
      Alert.alert('Error', result.error || 'Failed to submit answer');
    }
  };

  const handleUnlink = () => {
    Alert.alert(
      'Unlink Device',
      'Are you sure you want to unlink this device? You will no longer receive notifications or see its data.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Unlink',
          style: 'destructive',
          onPress: async () => {
            const result = await unlinkDevice(deviceId);
            if (result.ok) {
              navigation.goBack();
            } else {
              Alert.alert('Error', result.error || 'Failed to unlink device');
            }
          },
        },
      ]
    );
  };

  if (isLoading && !selectedDevice) {
    return <Loading fullScreen message="Loading device..." />;
  }

  if (!selectedDevice) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.errorContainer}>
          <Text style={styles.errorTitle}>Device Not Found</Text>
          <Text style={styles.errorText}>{error || 'Unable to load device data'}</Text>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.backLink}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const displayName = selectedDevice.nickname || selectedDevice.alias || 'Device';
  const pendingQuestions = selectedDevice.pending_questions || [];
  const suggestions = selectedDevice.suggestions || [];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={isLoading}
            onRefresh={handleRefresh}
            colors={[colors.primary]}
            tintColor={colors.primary}
          />
        }
      >
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <TouchableOpacity onPress={() => navigation.goBack()}>
              <Text style={styles.backButton}>{'<'} Back</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity onPress={handleUnlink}>
            <Text style={styles.unlinkButton}>Unlink</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.titleSection}>
          <Text style={styles.title}>{displayName}</Text>
          <StatusBadge status={selectedDevice.status} />
        </View>

        {selectedDevice.health ? <HealthCard health={selectedDevice.health} /> : null}

        {pendingQuestions.length > 0 ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Questions</Text>
            {pendingQuestions.map((question) => (
              <QuestionCard
                key={question.queue_id}
                question={question}
                onAnswer={(answer) => handleAnswerQuestion(question.queue_id, answer)}
              />
            ))}
          </View>
        ) : null}

        {suggestions.length > 0 ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>AI Suggestions</Text>
            {suggestions.map((suggestion) => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                onPress={() => handleSuggestionPress(suggestion.id)}
              />
            ))}
          </View>
        ) : null}

        {pendingQuestions.length === 0 && suggestions.length === 0 ? (
          <Card style={styles.emptyCard}>
            <Text style={styles.emptyText}>
              No pending questions or suggestions. The AI assistant will provide insights as
              it learns more about your pool.
            </Text>
          </Card>
        ) : null}

        <View style={styles.infoSection}>
          <Text style={styles.infoLabel}>Device UUID</Text>
          <Text style={styles.infoValue}>{selectedDevice.device_uuid}</Text>

          {selectedDevice.health?.software_version ? (
            <>
              <Text style={styles.infoLabel}>Software Version</Text>
              <Text style={styles.infoValue}>{selectedDevice.health.software_version}</Text>
            </>
          ) : null}

          {selectedDevice.health?.ip_address ? (
            <>
              <Text style={styles.infoLabel}>IP Address</Text>
              <Text style={styles.infoValue}>{selectedDevice.health.ip_address}</Text>
            </>
          ) : null}

          <Text style={styles.infoLabel}>Last Seen</Text>
          <Text style={styles.infoValue}>
            {selectedDevice.last_seen
              ? new Date(selectedDevice.last_seen).toLocaleString()
              : 'Never'}
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.md,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  backButton: {
    ...typography.body,
    color: colors.primary,
  },
  unlinkButton: {
    ...typography.body,
    color: colors.error,
  },
  titleSection: {
    marginBottom: spacing.lg,
  },
  title: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  section: {
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    ...typography.h4,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  emptyCard: {
    alignItems: 'center',
    padding: spacing.xl,
  },
  emptyText: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  infoSection: {
    marginTop: spacing.lg,
    paddingTop: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  infoLabel: {
    ...typography.caption,
    color: colors.textTertiary,
    marginTop: spacing.sm,
  },
  infoValue: {
    ...typography.body,
    color: colors.textSecondary,
  },
  errorContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  errorTitle: {
    ...typography.h3,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  errorText: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.lg,
  },
  backLink: {
    ...typography.body,
    color: colors.primary,
    fontWeight: '600',
  },
});
