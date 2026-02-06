# Python Backend Authentication Example

This document shows how to implement the `/api/login` endpoint in your Python backend to work with the React frontend.

## Required Dependencies

```bash
pip install firebase-admin flask  # or fastapi, django, etc.
```

## Firebase Admin Setup

```python
import firebase_admin
from firebase_admin import credentials, auth
import json

# Initialize Firebase Admin
cred = credentials.Certificate("path/to/serviceAccountKey.json")
firebase_admin.initialize_app(cred)
```

## Flask Example

```python
from flask import Flask, request, jsonify
from firebase_admin import auth
import datetime

app = Flask(__name__)

@app.route('/api/login', methods=['POST'])
def login():
    try:
        # Extract Firebase ID token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401
        
        id_token = auth_header.split('Bearer ')[1]
        
        # Verify the Firebase ID token
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name', '')
        
        # Check if user exists in your database
        user = get_user_by_firebase_uid(uid)  # Your database function
        
        if not user:
            # Create new user in your database
            user_data = {
                'firebase_uid': uid,
                'email': email,
                'name': name,
                'contact_number': '',
                'country_code': '+1',
                'upload_file': False,
                'created_at': datetime.datetime.utcnow()
            }
            user_id = create_user(user_data)  # Your database function
            user = get_user_by_id(user_id)    # Your database function
        
        # Return user data
        return jsonify({
            'id': user['firebase_uid'],  # Use Firebase UID as the ID
            'email': user['email'],
            'name': user['name'],
            'contact_number': user['contact_number'],
            'country_code': user['country_code'],
            'upload_file': user['upload_file'],
            'created_at': user['created_at'].isoformat()
        })
        
    except auth.InvalidIdTokenError:
        return jsonify({'error': 'Invalid Firebase ID token'}), 401
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Internal server error'}), 500
```

## FastAPI Example

```python
from fastapi import FastAPI, Depends, HTTPException, Header
from firebase_admin import auth
from typing import Optional
import datetime

app = FastAPI()

def verify_firebase_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    id_token = authorization.split('Bearer ')[1]
    
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token")

@app.post("/api/login")
async def login(decoded_token: dict = Depends(verify_firebase_token)):
    try:
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name', '')
        
        # Check if user exists in your database
        user = await get_user_by_firebase_uid(uid)  # Your database function
        
        if not user:
            # Create new user in your database
            user_data = {
                'firebase_uid': uid,
                'email': email,
                'name': name,
                'contact_number': '',
                'country_code': '+1',
                'upload_file': False,
                'created_at': datetime.datetime.utcnow()
            }
            user_id = await create_user(user_data)  # Your database function
            user = await get_user_by_id(user_id)    # Your database function
        
        # Return user data
        return {
            'id': user['firebase_uid'],  # Use Firebase UID as the ID
            'email': user['email'],
            'name': user['name'],
            'contact_number': user['contact_number'],
            'country_code': user['country_code'],
            'upload_file': user['upload_file'],
            'created_at': user['created_at'].isoformat()
        }
        
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

## Protected Route Example

For any other protected routes, use the same token verification:

```python
@app.route('/api/users/<user_id>/profile', methods=['GET'])
def get_user_profile(user_id):
    try:
        # Verify token
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401
        
        id_token = auth_header.split('Bearer ')[1]
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        
        # Ensure user can only access their own data
        if uid != user_id:
            return jsonify({'error': 'Forbidden'}), 403
        
        # Your business logic here...
        user = get_user_by_firebase_uid(uid)
        return jsonify(user)
        
    except auth.InvalidIdTokenError:
        return jsonify({'error': 'Invalid Firebase ID token'}), 401
```

## Database Schema Example

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    firebase_uid VARCHAR(128) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    contact_number VARCHAR(20),
    country_code VARCHAR(5),
    upload_file BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

## Key Points

1. **Stateless Authentication**: No sessions are stored on the backend. Every request includes the Firebase ID token.

2. **Token Verification**: The backend verifies each Firebase ID token with Firebase Admin SDK.

3. **User Management**: Users are stored in both Firebase Auth and your backend database using Firebase UID as the primary key.

4. **Security**: Always verify the token on every protected request. Users can only access their own data.

5. **Error Handling**: Return proper HTTP status codes (401 for auth errors, 403 for forbidden, 500 for server errors).

The React frontend will automatically include the Firebase ID token in all requests, and your backend will verify it on each request.