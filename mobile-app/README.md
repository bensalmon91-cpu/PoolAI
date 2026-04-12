# PoolAIssistant Mobile App

React Native mobile app for iOS and Android that provides pool operators with real-time monitoring, AI suggestions, and push notifications.

## Features

- **Device Dashboard**: View all linked pool monitoring devices with live status
- **Health Monitoring**: Real-time system health, controller status, and alarms
- **AI Suggestions**: Receive AI-generated recommendations for water quality, maintenance, and equipment
- **AI Questions**: Answer contextual questions to help the AI learn about your pools
- **Push Notifications**: Get alerts for alarms, device offline, and new suggestions
- **Device Linking**: Link new devices using a 6-character code

## Tech Stack

- **React Native** 0.73
- **TypeScript**
- **React Navigation** 6.x
- **Zustand** for state management
- **Axios** for API calls
- **Firebase Cloud Messaging** for push notifications

## Project Structure

```
mobile-app/
├── src/
│   ├── navigation/       # Navigation setup (AuthStack, MainStack)
│   ├── screens/
│   │   ├── auth/         # Login, Register, ForgotPassword
│   │   └── main/         # Dashboard, Device, LinkDevice, Account
│   ├── components/
│   │   ├── common/       # Button, Input, Card, Loading, StatusBadge
│   │   ├── device/       # DeviceCard, HealthCard
│   │   └── ai/           # SuggestionCard, QuestionCard
│   ├── services/         # API, auth, devices, push, storage
│   ├── stores/           # Zustand stores (auth, device)
│   ├── theme/            # Colors, typography, spacing
│   ├── types/            # TypeScript type definitions
│   └── utils/            # Constants, formatters
├── package.json
├── tsconfig.json
└── app.json
```

## Getting Started

### Prerequisites

- Node.js 18+
- Xcode (for iOS)
- Android Studio (for Android)
- CocoaPods (for iOS dependencies)

### Installation

```bash
# Install dependencies
npm install

# Install iOS pods
cd ios && pod install && cd ..
```

### Running the App

```bash
# Start Metro bundler
npm start

# Run on iOS
npm run ios

# Run on Android
npm run android
```

## API Endpoints

The mobile app connects to the PoolAIssistant backend API:

**Base URL**: `https://poolaissistant.modprojects.co.uk/api/mobile`

### Authentication
- `POST /auth/register.php` - Register new user
- `POST /auth/login.php` - Login (returns JWT tokens)
- `POST /auth/refresh.php` - Refresh access token
- `POST /auth/logout.php` - Logout (revoke token)
- `POST /auth/forgot-password.php` - Request password reset
- `POST /auth/reset-password.php` - Reset password with token

### Devices
- `GET /devices.php` - List user's devices
- `GET /device.php?id=X` - Get device details
- `POST /link.php` - Link device with code
- `DELETE /device.php?id=X` - Unlink device
- `PATCH /device.php?id=X` - Update device nickname

### Health & AI
- `GET /health.php?device_id=X` - Get device health
- `GET /health.php?device_id=X&hours=24` - Get health history
- `GET /suggestions.php?device_id=X` - Get AI suggestions
- `POST /suggestions.php?device_id=X&id=Y` - Submit suggestion feedback
- `GET /questions.php?device_id=X` - Get pending AI questions
- `POST /questions.php?device_id=X&id=Y` - Submit answer

### Push & Account
- `POST /push.php` - Register FCM token
- `DELETE /push.php` - Unregister FCM token
- `GET /notifications.php` - Get notification preferences
- `PATCH /notifications.php` - Update notification preferences
- `GET /account.php` - Get user account
- `PATCH /account.php` - Update profile
- `POST /account.php?action=password` - Change password

## Environment Setup

The app uses environment-based configuration. The API base URL is set in `src/utils/constants.ts`.

For production, you may want to:
1. Set up proper app icons and splash screens
2. Configure Firebase project for push notifications
3. Set up code signing for iOS (certificates, provisioning profiles)
4. Set up signing config for Android (keystore)

## Backend Configuration

The backend requires these environment variables in `.env`:

```
JWT_SECRET=<your-jwt-secret>
FCM_SERVER_KEY=<your-firebase-server-key>
```

## License

Proprietary - ModProjects Software
