# Firebase → React → Python Backend Authentication Setup

This guide explains how to set up the complete authentication flow for your finance chat application.

## Overview

The authentication flow works as follows:
1. **Frontend (React)**: Handles Firebase authentication (Google OAuth, email/password)
2. **Backend (Python FastAPI)**: Verifies Firebase tokens using Firebase Admin SDK
3. **Database**: Stores user information and session data

## Backend Setup

### 1. Install Dependencies

The backend dependencies are already configured in `pyproject.toml`. Install them:

```bash
cd /Users/debojyotichakraborty/codebase/finance-a2a-automation/host_agent
pip install -r requirements.txt  # or use your preferred method
```

### 2. Firebase Admin SDK Setup

#### Option A: Service Account (Recommended for Development)
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project (warm-rookery-461602-i8)
3. Go to Project Settings → Service Accounts
4. Generate new private key
5. Save the JSON file securely (DO NOT commit to git)
6. Set the path in your `.env` file:

```bash
FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/your/serviceAccountKey.json
```

#### Option B: Default Application Credentials (Production)
For production, use Application Default Credentials (ADC):
```bash
# Set this if not using service account file
# FIREBASE_SERVICE_ACCOUNT_PATH not needed
```

### 3. Environment Variables

Create `.env` file in the backend directory:

```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:password@localhost:5432/finance_a2a

# Firebase Configuration
FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/serviceAccountKey.json

# Google API Configuration
GOOGLE_API_KEY=your_google_api_key_here

# Host Agent Configuration
HOST_AGENT_PORT=10001
STOCK_ANALYSER_AGENT_URL=http://localhost:10002
STOCK_REPORT_ANALYSER_AGENT_URL=http://localhost:10003
```

### 4. Start Backend Server

```bash
cd /Users/debojyotichakraborty/codebase/finance-a2a-automation/host_agent
python -m uvicorn __main__:app --host localhost --port 10001 --reload
```

The backend will be available at `http://localhost:10001`

## Frontend Setup

### 1. Environment Variables

Create `.env` file in the frontend directory:

```bash
# API Configuration
REACT_APP_API_BASE_URL=http://localhost:10001/api

# Firebase Configuration (from your Firebase project)
REACT_APP_FIREBASE_API_KEY=AIzaSyB1uOVNJZHpmaUAIHqGeVwhRHsQZfc6vuA
REACT_APP_FIREBASE_AUTH_DOMAIN=warm-rookery-461602-i8.firebaseapp.com
REACT_APP_FIREBASE_PROJECT_ID=warm-rookery-461602-i8
REACT_APP_FIREBASE_STORAGE_BUCKET=warm-rookery-461602-i8.firebasestorage.app
REACT_APP_FIREBASE_MESSAGING_SENDER_ID=980823727426
REACT_APP_FIREBASE_APP_ID=1:980823727426:web:86c5fc0a404342393d3cdb
```

### 2. Start Frontend Server

```bash
cd /Users/debojyotichakraborty/codebase/finance-chat
npm start
```

The frontend will be available at `http://localhost:3000`

## Authentication Flow

### 1. User Login Process

1. **User clicks login** (Google OAuth or email/password)
2. **Firebase authenticates** and returns ID token
3. **Frontend calls `/api/login`** with ID token in request body
4. **Backend verifies token** with Firebase Admin SDK
5. **Backend creates/updates user** in database
6. **Backend returns user data** matching frontend interface
7. **Frontend stores user data** in AuthContext

### 2. Authenticated API Calls

All subsequent API calls automatically include the Firebase ID token:

```typescript
// Frontend automatically adds this header:
Authorization: Bearer <firebase-id-token>
```

Backend endpoints that require authentication use the `get_current_user` dependency.

### 3. Protected Endpoints

These endpoints require authentication:
- `POST /chats` - Send chat messages
- `POST /chats/stream` - Stream chat responses  
- `GET /users/{user_id}/profile` - Get user profile
- `PUT /users/{user_id}/profile` - Update user profile
- All other user-specific endpoints

### 4. Public Endpoints

These endpoints don't require authentication:
- `POST /api/login` - Firebase login
- `GET /health` - Health check
- `GET /agents/status` - Agent status

## Database Schema

The backend uses the following main tables:

### Users Table
```sql
CREATE TABLE users (
    id VARCHAR PRIMARY KEY,           -- Firebase UID
    email VARCHAR,                    -- User email
    paid_user BOOLEAN DEFAULT FALSE, -- Premium status
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Sessions & Messages
- `conversation_sessions` - Chat sessions
- `conversation_messages` - Individual messages
- `agent_states` - Agent conversation state

## API Endpoints

### Authentication
- `POST /api/login` - Login with Firebase token

### Chat
- `POST /chats` - Send message (requires auth)
- `POST /chats/stream` - Stream message (requires auth)

### User Management
- `GET /users/{user_id}/profile` - Get user profile
- `PUT /users/{user_id}/profile` - Update user profile  
- `GET /users/{user_id}/statistics` - Get user stats
- `POST /users/{user_id}/upgrade` - Upgrade to paid
- `DELETE /users/{user_id}` - Delete account

### System
- `GET /health` - Health check
- `GET /agents/status` - Connected agents status

## Security Features

1. **Token Verification**: All Firebase tokens verified with Admin SDK
2. **User Isolation**: Users can only access their own data
3. **Automatic Token Refresh**: Frontend handles expired tokens
4. **Rate Limiting**: Free users limited to 19 messages
5. **Input Validation**: All API inputs validated with Pydantic

## Troubleshooting

### Common Issues

1. **"Invalid Firebase token"**
   - Check Firebase project configuration
   - Verify service account key path
   - Ensure token isn't expired

2. **"CORS errors"**
   - Backend allows all origins for development
   - Configure appropriately for production

3. **"Database connection failed"**
   - Check PostgreSQL is running
   - Verify DATABASE_URL in backend .env

4. **"Agent not initialized"**
   - Check Google API key configuration
   - Verify other agents are running

### Logs

Backend logs are written to:
- Console (immediate feedback)
- `host_agent_api.log` (persistent logs)

## Production Considerations

1. **Security**:
   - Use environment variables for secrets
   - Configure CORS appropriately
   - Use HTTPS in production
   - Rotate Firebase service account keys

2. **Database**:
   - Use production PostgreSQL instance
   - Set up database migrations
   - Configure backups

3. **Monitoring**:
   - Set up log aggregation
   - Monitor authentication failures
   - Track API usage

4. **Scaling**:
   - Use load balancer for multiple backend instances
   - Configure Redis for session storage
   - Set up Firebase Auth quotas

This setup provides a robust, production-ready authentication system that scales with your application needs.