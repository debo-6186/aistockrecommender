# Finance Chat Application

A React-based chat application with Firebase authentication, real-time messaging, and PDF file upload capabilities.

## Features

- **Authentication**: Email/password and Google OAuth login/register
- **User Profile**: Collects name, contact number, and country code
- **Real-time Chat**: Live message updates with chat history
- **PDF File Upload**: Permission-based file upload (only if `upload_file` is true)
- **Secure Storage**: User-specific file access with download capability
- **Responsive Design**: Modern UI with Tailwind CSS

## User Flow

1. **Landing Page** → Authentication (Login/Register)
2. **After Signup** → Profile setup to collect user information
3. **After Login** → Chat page with full functionality
4. **File Upload** → Enabled/disabled based on user's `upload_file` permission

## Prerequisites

- Node.js (v14 or higher)
- npm or yarn
- Firebase project
- API endpoint for user profile management

## Setup Instructions

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd finance-chat
npm install
```

### 2. Firebase Configuration

1. Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
2. Enable Authentication (Email/Password and Google)
3. Enable Firestore Database
4. Enable Storage
5. Update `src/firebase.ts` with your Firebase configuration:

```typescript
const firebaseConfig = {
  apiKey: "your-api-key",
  authDomain: "your-project.firebaseapp.com",
  projectId: "your-project-id",
  storageBucket: "your-project.appspot.com",
  messagingSenderId: "your-messaging-sender-id",
  appId: "your-app-id"
};
```

### 3. API Configuration

Create environment files for different environments:

**For Local Development** (`.env` or `.env.local`):
```bash
REACT_APP_API_BASE_URL=http://localhost:10001/api
```

**For Production** (`.env.production`):
```bash
REACT_APP_API_BASE_URL=https://dtwugznkn4ata.cloudfront.net/api
```

The application expects the following API endpoints:

- `POST /api/login` - Firebase authentication and user login
- `GET /api/users/{id}/profile` - Fetch user profile
- `PUT /api/users/{id}/profile` - Update user profile
- `POST /api/chats` - Send chat messages

### 4. Start Development Server

```bash
npm start
```

The application will open at `http://localhost:3000`

## Project Structure

```
src/
├── components/
│   ├── Auth.tsx           # Authentication component
│   ├── ProfileSetup.tsx   # User profile setup
│   └── Chat.tsx          # Chat interface
├── contexts/
│   └── AuthContext.tsx   # Authentication context
├── services/
│   └── api.ts            # API service layer
├── types/
│   └── index.ts          # TypeScript type definitions
├── firebase.ts           # Firebase configuration
└── App.tsx              # Main application component
```

## Key Components

### Authentication (`Auth.tsx`)
- Email/password login and registration
- Google OAuth integration
- Form validation and error handling

### Profile Setup (`ProfileSetup.tsx`)
- Collects user information (name, contact, country code)
- Country code dropdown with common options
- Updates Firestore and local state

### Chat (`Chat.tsx`)
- Real-time messaging using Firestore
- PDF file upload (permission-based)
- File download functionality
- Responsive message layout

## Firebase Collections

### Users Collection
```typescript
{
  id: string;
  email: string;
  name: string;
  contactNumber: string;
  countryCode: string;
  uploadFile: boolean;
  createdAt: Date;
}
```

### Messages Collection
```typescript
{
  id: string;
  text: string;
  userId: string;
  userName: string;
  timestamp: Date;
  fileUrl?: string;
  fileName?: string;
}
```

## Environment Variables

### Local Development (`.env` or `.env.local`)

Create a `.env.local` file in the root directory for local development:

```bash
REACT_APP_API_BASE_URL=http://localhost:10001/api
REACT_APP_FIREBASE_API_KEY=your-firebase-api-key
REACT_APP_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
REACT_APP_FIREBASE_PROJECT_ID=your-project-id
REACT_APP_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
REACT_APP_FIREBASE_MESSAGING_SENDER_ID=your-messaging-sender-id
REACT_APP_FIREBASE_APP_ID=your-app-id
```

### Production (`.env.production`)

Create a `.env.production` file for production builds:

```bash
REACT_APP_API_BASE_URL=https://dtwugznkn4ata.cloudfront.net/api
# Firebase config (same as above)
```

**Note**: React automatically uses `.env.production` when running `npm run build`

## Security Rules

### Firestore Rules
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
    match /messages/{messageId} {
      allow read, write: if request.auth != null;
    }
  }
}
```

### Storage Rules
```javascript
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /files/{userId}/{allPaths=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

## Build and Deployment

### Local Development

For local development, the app uses `.env` or `.env.local`:

```bash
# Start development server (uses .env or .env.local)
npm start
```

### Production Build

**Important**: Create React App uses `.env.production` for production builds.

Create a `.env.production` file:
```bash
REACT_APP_API_BASE_URL=https://dtwugznkn4ata.cloudfront.net/api
```

Then build:
```bash
# Build for production (automatically uses .env.production)
npm run build
```

Or explicitly set the API URL during build:
```bash
# Alternative: Set environment variable inline
REACT_APP_API_BASE_URL=https://dtwugznkn4ata.cloudfront.net/api npm run build
```

### Deploy to Firebase

After building, deploy to Firebase Hosting:

```bash
# Deploy hosting only
firebase deploy --only hosting

# Or deploy everything
firebase deploy
```

**Note**: Always rebuild before deploying to ensure environment variables are updated!

## Troubleshooting

### Common Issues

1. **Firebase Authentication Error**: Ensure Google OAuth is properly configured
2. **File Upload Fails**: Check Firebase Storage rules and user permissions
3. **API Connection Error**: Verify API endpoint and network connectivity
4. **Tailwind CSS Not Working**: Ensure PostCSS and Tailwind are properly configured

### Development Tips

- Use Firebase Emulator Suite for local development
- Check browser console for detailed error messages
- Verify Firebase project settings and API keys
- Test file upload permissions with different user accounts

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.
