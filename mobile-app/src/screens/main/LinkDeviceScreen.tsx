import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Button, Input, Card } from '../../components/common';
import { useDeviceStore } from '../../stores';
import { colors, spacing, typography } from '../../theme';

type Props = {
  navigation: NativeStackNavigationProp<any>;
};

export const LinkDeviceScreen: React.FC<Props> = ({ navigation }) => {
  const [code, setCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const { linkDevice } = useDeviceStore();

  const formatCode = (input: string): string => {
    // Remove non-alphanumeric characters and convert to uppercase
    const cleaned = input.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
    // Limit to 6 characters
    return cleaned.slice(0, 6);
  };

  const handleCodeChange = (text: string) => {
    setCode(formatCode(text));
    setError('');
  };

  const handleSubmit = async () => {
    if (code.length !== 6) {
      setError('Please enter a 6-character link code');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const result = await linkDevice(code);

      if (result.ok) {
        Alert.alert('Success', 'Device linked successfully!', [
          {
            text: 'OK',
            onPress: () => navigation.goBack(),
          },
        ]);
      } else {
        setError(result.error || 'Failed to link device');
      }
    } catch (e: any) {
      setError(e.message || 'Failed to link device');
    } finally {
      setIsLoading(false);
    }
  };

  // Format display as XXX-XXX
  const displayCode = code.length > 3 ? `${code.slice(0, 3)}-${code.slice(3)}` : code;

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.backButton}>{'<'} Back</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.content}>
          <Text style={styles.title}>Link a Device</Text>
          <Text style={styles.subtitle}>
            Enter the 6-character code displayed on your PoolAIssistant device
          </Text>

          <Card style={styles.card}>
            <Text style={styles.label}>Link Code</Text>
            <View style={styles.codeInputContainer}>
              <Text style={styles.codeDisplay}>
                {displayCode || 'ABC-123'}
              </Text>
              <Input
                value={code}
                onChangeText={handleCodeChange}
                placeholder="Enter code"
                autoCapitalize="characters"
                autoCorrect={false}
                maxLength={6}
                containerStyle={styles.hiddenInput}
                style={styles.hiddenInputText}
              />
            </View>

            {error && (
              <Text style={styles.error}>{error}</Text>
            )}

            <Button
              title="Link Device"
              onPress={handleSubmit}
              loading={isLoading}
              disabled={code.length !== 6}
              style={styles.button}
            />
          </Card>

          <View style={styles.instructions}>
            <Text style={styles.instructionsTitle}>How to find your link code:</Text>
            <Text style={styles.instructionsText}>
              1. On your PoolAIssistant device, go to Settings
            </Text>
            <Text style={styles.instructionsText}>
              2. Select "Link to Mobile App"
            </Text>
            <Text style={styles.instructionsText}>
              3. A 6-character code will be displayed
            </Text>
            <Text style={styles.instructionsText}>
              4. Enter the code above within 15 minutes
            </Text>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  keyboardView: {
    flex: 1,
  },
  header: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  backButton: {
    ...typography.body,
    color: colors.primary,
  },
  content: {
    flex: 1,
    padding: spacing.lg,
  },
  title: {
    ...typography.h2,
    color: colors.textPrimary,
    textAlign: 'center',
    marginBottom: spacing.sm,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.xl,
  },
  card: {
    padding: spacing.lg,
    marginBottom: spacing.xl,
  },
  label: {
    ...typography.label,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
  codeInputContainer: {
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  codeDisplay: {
    ...typography.h1,
    color: colors.textPrimary,
    letterSpacing: 4,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  hiddenInput: {
    position: 'absolute',
    opacity: 0,
    width: '100%',
    height: '100%',
  },
  hiddenInputText: {
    width: '100%',
    height: '100%',
  },
  error: {
    ...typography.bodySmall,
    color: colors.error,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
  button: {
    marginTop: spacing.sm,
  },
  instructions: {
    padding: spacing.md,
  },
  instructionsTitle: {
    ...typography.label,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  instructionsText: {
    ...typography.bodySmall,
    color: colors.textTertiary,
    marginBottom: spacing.sm,
  },
});
