# Finance Chat Application Demo Guide

## Quick Start Demo

This guide will help you quickly test the Finance Chat application with Firebase.

### 1. Firebase Setup (Required)

Before running the application, you need to set up Firebase:

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or select an existing one
3. Enable Authentication:
   - Go to Authentication > Sign-in method
   - Enable Email/Password
   - Enable Google (add your domain to authorized domains)
4. Enable Firestore Database:
   - Go to Firestore Database > Create database
   - Start in test mode for development
5. Enable Storage:
   - Go to Storage > Get started
   - Start in test mode for development

### 2. Environment Configuration

Create a `.env.local` file in the root directory:

```bash
REACT_APP_FIREBASE_API_KEY=your-api-key
REACT_APP_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
REACT_APP_FIREBASE_PROJECT_ID=your-project-id
REACT_APP_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
REACT_APP_FIREBASE_MESSAGING_SENDER_ID=your-messaging-sender-id
REACT_APP_FIREBASE_APP_ID=your-app-id
```

### 3. Start the Application

```bash
npm start
```

The application will open at `http://localhost:3000`

### 4. Demo Flow

#### Step 1: Authentication
- Open the application in your browser
- You'll see the login/register form
- Try both email/password and Google OAuth

#### Step 2: Profile Setup (for new users)
- After authentication, new users will see the profile setup form
- Fill in your name, contact number, and select a country code
- Click "Complete Profile" to continue

#### Step 3: Chat Interface
- You'll be redirected to the chat page
- Send messages to test real-time functionality
- The file upload option will be disabled by default (upload_file: false)

### 5. Testing File Upload

To test file upload functionality, you need to set `upload_file: true` in your user profile:

1. **Option 1: Use the API endpoint**
   - Set up your backend API at `/users/{id}` 
   - Return `upload_file: true` in the user profile
   - The app will automatically fetch this and enable upload

2. **Option 2: Manual Firestore update**
   - Go to Firebase Console > Firestore Database
   - Find your user document in the `users` collection
   - Set `uploadFile: true`
   - Refresh the application

### 6. Testing Scenarios

#### New User Registration
1. Click "Don't have an account? Sign up"
2. Fill in all required fields
3. Complete profile setup
4. Verify chat access

#### Existing User Login
1. Use existing credentials
2. Verify profile data is loaded
3. Test chat functionality

#### File Upload (when enabled)
1. Ensure `upload_file: true` in user profile
2. Click "Select PDF" button
3. Choose a PDF file
4. Click "Upload"
5. Verify file appears in chat
6. Test download functionality

#### Real-time Chat
1. Open multiple browser tabs/windows
2. Log in with different accounts
3. Send messages from different users
4. Verify real-time updates across all tabs

### 7. Troubleshooting

#### Common Issues

**Firebase Authentication Error**
- Check if Google OAuth domain is authorized
- Verify API keys in environment variables
- Ensure Authentication is enabled in Firebase

**File Upload Not Working**
- Check if `upload_file` is true in user profile
- Verify Firebase Storage rules
- Check browser console for errors

**Chat Not Loading**
- Verify Firestore rules allow read/write
- Check if database is created and accessible
- Ensure proper authentication state

#### Debug Mode

Open browser console (F12) to see:
- Authentication state changes
- API calls and responses
- Firebase connection status
- Error messages

### 8. API Integration

The application expects these API endpoints:

```bash
GET /users/{id} - Returns user profile with upload_file permission
PUT /users/{id} - Updates user profile
```

Example user profile response:
```json
{
  "id": "user123",
  "email": "user@example.com",
  "name": "John Doe",
  "contact_number": "+1234567890",
  "country_code": "+1",
  "upload_file": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

### 9. Security Rules

For production, update Firebase security rules:

**Firestore Rules:**
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

**Storage Rules:**
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

### 10. Next Steps

After successful testing:
1. Customize the UI and branding
2. Implement additional security measures
3. Add user management features
4. Set up monitoring and analytics
5. Deploy to production environment

---

**Note:** This is a development setup. For production deployment, ensure proper security rules, environment variables, and monitoring are in place.
