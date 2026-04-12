import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput } from 'react-native';
import { Card, Button } from '../common';
import { colors, spacing, typography, borderRadius } from '../../theme';
import type { Question } from '../../types/api';

interface QuestionCardProps {
  question: Question;
  onAnswer: (answer: string) => Promise<void>;
}

export const QuestionCard: React.FC<QuestionCardProps> = ({ question, onAnswer }) => {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [textAnswer, setTextAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    const answer = question.input_type === 'text' || question.input_type === 'number'
      ? textAnswer.trim()
      : selectedOption;

    if (!answer) return;

    setIsSubmitting(true);
    try {
      await onAnswer(answer);
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderInput = () => {
    switch (question.input_type) {
      case 'buttons':
        return (
          <View style={styles.optionsContainer}>
            {question.options?.map((option, index) => (
              <TouchableOpacity
                key={index}
                style={[
                  styles.optionButton,
                  selectedOption === option && styles.optionSelected,
                ]}
                onPress={() => setSelectedOption(option)}
              >
                <Text
                  style={[
                    styles.optionText,
                    selectedOption === option && styles.optionTextSelected,
                  ]}
                >
                  {option}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        );

      case 'dropdown':
        return (
          <View style={styles.optionsContainer}>
            {question.options?.map((option, index) => (
              <TouchableOpacity
                key={index}
                style={[
                  styles.dropdownOption,
                  selectedOption === option && styles.dropdownSelected,
                ]}
                onPress={() => setSelectedOption(option)}
              >
                <Text
                  style={[
                    styles.dropdownText,
                    selectedOption === option && styles.dropdownTextSelected,
                  ]}
                >
                  {option}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        );

      case 'text':
        return (
          <TextInput
            style={styles.textInput}
            placeholder="Type your answer..."
            placeholderTextColor={colors.textTertiary}
            value={textAnswer}
            onChangeText={setTextAnswer}
            multiline
          />
        );

      case 'number':
        return (
          <TextInput
            style={styles.textInput}
            placeholder="Enter a number..."
            placeholderTextColor={colors.textTertiary}
            value={textAnswer}
            onChangeText={setTextAnswer}
            keyboardType="numeric"
          />
        );

      default:
        return null;
    }
  };

  const canSubmit =
    (question.input_type === 'text' || question.input_type === 'number')
      ? textAnswer.trim().length > 0
      : selectedOption !== null;

  return (
    <Card style={styles.card} variant="elevated">
      <View style={styles.header}>
        <Text style={styles.category}>{question.category}</Text>
        <View style={[styles.priorityBadge, { opacity: 0.4 + question.priority * 0.15 }]}>
          <Text style={styles.priorityText}>P{question.priority}</Text>
        </View>
      </View>

      <Text style={styles.question}>{question.text}</Text>

      {renderInput()}

      <Button
        title="Submit Answer"
        onPress={handleSubmit}
        disabled={!canSubmit}
        loading={isSubmitting}
        style={styles.submitButton}
      />
    </Card>
  );
};

const styles = StyleSheet.create({
  card: {
    marginBottom: spacing.md,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  category: {
    ...typography.caption,
    color: colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  priorityBadge: {
    backgroundColor: colors.primary,
    paddingVertical: 2,
    paddingHorizontal: spacing.sm,
    borderRadius: borderRadius.sm,
  },
  priorityText: {
    ...typography.caption,
    color: colors.textInverse,
    fontWeight: '600',
  },
  question: {
    ...typography.h4,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  optionsContainer: {
    marginBottom: spacing.md,
  },
  optionButton: {
    backgroundColor: colors.surfaceVariant,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.md,
    marginBottom: spacing.sm,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  optionSelected: {
    backgroundColor: colors.primary + '10',
    borderColor: colors.primary,
  },
  optionText: {
    ...typography.body,
    color: colors.textPrimary,
    textAlign: 'center',
  },
  optionTextSelected: {
    color: colors.primary,
    fontWeight: '600',
  },
  dropdownOption: {
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  dropdownSelected: {
    backgroundColor: colors.primary + '10',
  },
  dropdownText: {
    ...typography.body,
    color: colors.textPrimary,
  },
  dropdownTextSelected: {
    color: colors.primary,
    fontWeight: '600',
  },
  textInput: {
    ...typography.body,
    color: colors.textPrimary,
    backgroundColor: colors.surfaceVariant,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    minHeight: 80,
    textAlignVertical: 'top',
    marginBottom: spacing.md,
  },
  submitButton: {
    marginTop: spacing.sm,
  },
});
