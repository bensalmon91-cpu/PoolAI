import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import {
  DashboardScreen,
  DeviceScreen,
  LinkDeviceScreen,
  AccountScreen,
} from '../screens/main';
import { colors, typography } from '../theme';
import type { MainStackParamList } from './types';
import { View, Text, StyleSheet } from 'react-native';

const Stack = createNativeStackNavigator<MainStackParamList>();
const Tab = createBottomTabNavigator();

// Simple tab icons using text
const TabIcon: React.FC<{ name: string; focused: boolean }> = ({ name, focused }) => {
  const icons: Record<string, string> = {
    Devices: focused ? '[\u2713]' : '[ ]',
    Account: focused ? '(\u2713)' : '( )',
  };

  return (
    <Text style={[styles.icon, focused && styles.iconFocused]}>
      {icons[name] || name[0]}
    </Text>
  );
};

const DashboardTab: React.FC = () => {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
      }}
    >
      <Stack.Screen name="Dashboard" component={DashboardScreen} />
      <Stack.Screen name="Device" component={DeviceScreen} />
      <Stack.Screen name="LinkDevice" component={LinkDeviceScreen} />
    </Stack.Navigator>
  );
};

export const MainStack: React.FC = () => {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textTertiary,
        tabBarLabelStyle: {
          ...typography.caption,
          marginBottom: 4,
        },
        tabBarStyle: {
          borderTopWidth: 1,
          borderTopColor: colors.borderLight,
        },
      }}
    >
      <Tab.Screen
        name="DevicesTab"
        component={DashboardTab}
        options={{
          tabBarLabel: 'Devices',
          tabBarIcon: ({ focused }) => <TabIcon name="Devices" focused={focused} />,
        }}
      />
      <Tab.Screen
        name="AccountTab"
        component={AccountScreen}
        options={{
          tabBarLabel: 'Account',
          tabBarIcon: ({ focused }) => <TabIcon name="Account" focused={focused} />,
        }}
      />
    </Tab.Navigator>
  );
};

const styles = StyleSheet.create({
  icon: {
    fontSize: 20,
    color: colors.textTertiary,
  },
  iconFocused: {
    color: colors.primary,
  },
});
