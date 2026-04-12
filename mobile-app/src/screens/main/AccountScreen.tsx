import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Input, Card } from '../../components/common';
import { useAuthStore } from '../../stores';
import { colors, spacing, typography } from '../../theme';

export const AccountScreen: React.FC = () => {
  const { user, logout, updateProfile, changePassword, isLoading } = useAuthStore();

  const [name, setName] = useState(user?.name || '');
  const [company, setCompany] = useState(user?.company || '');
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  const handleSaveProfile = async () => {
    setIsSaving(true);
    const success = await updateProfile({ name, company });
    setIsSaving(false);

    if (success) {
      setIsEditing(false);
      Alert.alert('Success', 'Profile updated successfully');
    } else {
      Alert.alert('Error', 'Failed to update profile');
    }
  };

  const handleChangePassword = async () => {
    if (newPassword.length < 8) {
      Alert.alert('Error', 'Password must be at least 8 characters');
      return;
    }

    if (newPassword !== confirmPassword) {
      Alert.alert('Error', 'Passwords do not match');
      return;
    }

    setIsChangingPassword(true);
    const result = await changePassword(currentPassword, newPassword);
    setIsChangingPassword(false);

    if (result.ok) {
      setShowPasswordForm(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      Alert.alert('Success', 'Password changed successfully');
    } else {
      Alert.alert('Error', result.error || 'Failed to change password');
    }
  };

  const handleLogout = () => {
    Alert.alert(
      'Log Out',
      'Are you sure you want to log out?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Log Out', style: 'destructive', onPress: logout },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Account</Text>

        <Card style={styles.card}>
          <Text style={styles.sectionTitle}>Profile</Text>

          <View style={styles.field}>
            <Text style={styles.label}>Email</Text>
            <Text style={styles.value}>{user?.email}</Text>
          </View>

          {isEditing ? (
            <>
              <Input
                label="Name"
                value={name}
                onChangeText={setName}
                placeholder="Enter your name"
              />
              <Input
                label="Company"
                value={company}
                onChangeText={setCompany}
                placeholder="Enter your company"
              />
              <View style={styles.buttonRow}>
                <Button
                  title="Cancel"
                  onPress={() => {
                    setIsEditing(false);
                    setName(user?.name || '');
                    setCompany(user?.company || '');
                  }}
                  variant="outline"
                  style={styles.buttonHalf}
                />
                <Button
                  title="Save"
                  onPress={handleSaveProfile}
                  loading={isSaving}
                  style={styles.buttonHalf}
                />
              </View>
            </>
          ) : (
            <>
              <View style={styles.field}>
                <Text style={styles.label}>Name</Text>
                <Text style={styles.value}>{user?.name || 'Not set'}</Text>
              </View>
              <View style={styles.field}>
                <Text style={styles.label}>Company</Text>
                <Text style={styles.value}>{user?.company || 'Not set'}</Text>
              </View>
              <Button
                title="Edit Profile"
                onPress={() => setIsEditing(true)}
                variant="outline"
              />
            </>
          )}
        </Card>

        <Card style={styles.card}>
          <Text style={styles.sectionTitle}>Security</Text>

          {showPasswordForm ? (
            <>
              <Input
                label="Current Password"
                value={currentPassword}
                onChangeText={setCurrentPassword}
                secureTextEntry
                placeholder="Enter current password"
              />
              <Input
                label="New Password"
                value={newPassword}
                onChangeText={setNewPassword}
                secureTextEntry
                placeholder="Enter new password"
              />
              <Input
                label="Confirm New Password"
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                secureTextEntry
                placeholder="Confirm new password"
              />
              <View style={styles.buttonRow}>
                <Button
                  title="Cancel"
                  onPress={() => {
                    setShowPasswordForm(false);
                    setCurrentPassword('');
                    setNewPassword('');
                    setConfirmPassword('');
                  }}
                  variant="outline"
                  style={styles.buttonHalf}
                />
                <Button
                  title="Change"
                  onPress={handleChangePassword}
                  loading={isChangingPassword}
                  style={styles.buttonHalf}
                />
              </View>
            </>
          ) : (
            <Button
              title="Change Password"
              onPress={() => setShowPasswordForm(true)}
              variant="outline"
            />
          )}
        </Card>

        <Card style={styles.card}>
          <Text style={styles.sectionTitle}>App Info</Text>
          <View style={styles.field}>
            <Text style={styles.label}>Version</Text>
            <Text style={styles.value}>1.0.0</Text>
          </View>
        </Card>

        <Button
          title="Log Out"
          onPress={handleLogout}
          variant="danger"
          style={styles.logoutButton}
        />
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
    padding: spacing.lg,
  },
  title: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: spacing.lg,
  },
  card: {
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    ...typography.h4,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  field: {
    marginBottom: spacing.md,
  },
  label: {
    ...typography.caption,
    color: colors.textTertiary,
    marginBottom: 2,
  },
  value: {
    ...typography.body,
    color: colors.textPrimary,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  buttonHalf: {
    flex: 1,
  },
  logoutButton: {
    marginTop: spacing.lg,
  },
});
