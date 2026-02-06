import { initializeApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';
import { getStorage } from 'firebase/storage';

const firebaseConfig = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY || "AIzaSyB1uOVNJZHpmaUAIHqGeVwhRHsQZfc6vuA",
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN || "warm-rookery-461602-i8.firebaseapp.com",
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID || "warm-rookery-461602-i8",
  storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET || "warm-rookery-461602-i8.firebasestorage.app",
  messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID || "980823727426",
  appId: process.env.REACT_APP_FIREBASE_APP_ID || "1:980823727426:web:86c5fc0a404342393d3cdb"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Firebase services
export const auth = getAuth(app);
export const db = getFirestore(app);
export const storage = getStorage(app);
export const googleProvider = new GoogleAuthProvider();

// Configure Google provider
googleProvider.addScope('profile');
googleProvider.addScope('email');
googleProvider.setCustomParameters({
  prompt: 'select_account'
});

export default app;
