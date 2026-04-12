import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Card } from '../common';
import { colors, spacing, typography, borderRadius } from '../../theme';
import type { Suggestion } from '../../types/api';

interface SuggestionCardProps {
  suggestion: Suggestion;
  onPress: () => void;
  onAction?: (action: 'acted_upon' | 'dismissed') => void;
}

const priorityColors: Record<number, string> = {
  1: colors.priority1,
  2: colors.priority2,
  3: colors.priority3,
  4: colors.priority4,
  5: colors.priority5,
};

export const SuggestionCard: React.FC<SuggestionCardProps> = ({
  suggestion,
  onPress,
  onAction,
}) => {
  const priorityColor = priorityColors[suggestion.priority] || colors.priority3;
  const isUnread = suggestion.status === 'pending' || suggestion.status === 'delivered';

  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.7}>
      <Card style={[styles.card, isUnread && styles.unread]} variant="outlined">
        <View style={[styles.priorityBar, { backgroundColor: priorityColor }]} />

        <View style={styles.content}>
          <View style={styles.header}>
            <Text style={styles.type}>{suggestion.suggestion_type}</Text>
            {suggestion.confidence != null && suggestion.confidence > 0 ? (
              <Text style={styles.confidence}>
                {Math.round(suggestion.confidence * 100)}% confidence
              </Text>
            ) : null}
          </View>

          <Text style={styles.title} numberOfLines={2}>
            {suggestion.title}
          </Text>

          <Text style={styles.body} numberOfLines={3}>
            {suggestion.body}
          </Text>

          {onAction && suggestion.status === 'read' ? (
            <View style={styles.actions}>
              <TouchableOpacity
                style={[styles.actionButton, styles.actionDone]}
                onPress={() => onAction('acted_upon')}
              >
                <Text style={styles.actionButtonText}>Done</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, styles.actionDismiss]}
                onPress={() => onAction('dismissed')}
              >
                <Text style={[styles.actionButtonText, styles.dismissText]}>Dismiss</Text>
              </TouchableOpacity>
            </View>
          ) : null}

          <Text style={styles.timestamp}>
            {new Date(suggestion.created_at).toLocaleDateString()}
          </Text>
        </View>
      </Card>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  card: {
    marginBottom: spacing.md,
    flexDirection: 'row',
    padding: 0,
    overflow: 'hidden',
  },
  unread: {
    backgroundColor: colors.primary + '05',
  },
  priorityBar: {
    width: 4,
  },
  content: {
    flex: 1,
    padding: spacing.md,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  type: {
    ...typography.caption,
    color: colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  confidence: {
    ...typography.caption,
    color: colors.textTertiary,
  },
  title: {
    ...typography.h4,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  body: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  actions: {
    flexDirection: 'row',
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
  },
  actionButton: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.md,
    marginRight: spacing.sm,
  },
  actionDone: {
    backgroundColor: colors.success,
  },
  actionDismiss: {
    backgroundColor: colors.surfaceVariant,
  },
  actionButtonText: {
    ...typography.bodySmall,
    color: colors.textInverse,
    fontWeight: '600',
  },
  dismissText: {
    color: colors.textSecondary,
  },
  timestamp: {
    ...typography.caption,
    color: colors.textTertiary,
  },
});
