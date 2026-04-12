export type AuthStackParamList = {
  Login: undefined;
  Register: undefined;
  ForgotPassword: undefined;
};

export type MainStackParamList = {
  Dashboard: undefined;
  Device: { deviceId: number };
  LinkDevice: undefined;
  Account: undefined;
};

export type RootStackParamList = {
  Auth: undefined;
  Main: undefined;
};
