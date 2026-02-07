import React, { useState, useEffect } from 'react';
import {
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  signOut,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  sendEmailVerification,
  sendPasswordResetEmail,
  updateProfile
} from 'firebase/auth';
import { auth, googleProvider } from '../firebase';
import { User } from '../types';
import { useAuth } from '../contexts/AuthContext';

interface AuthProps {
  onAuthSuccess: (user: User) => void;
}

const Auth: React.FC<AuthProps> = ({ onAuthSuccess }) => {
  const { loginWithBackend } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [authMode, setAuthMode] = useState<'google' | 'email'>('google');
  const [emailAuthMode, setEmailAuthMode] = useState<'login' | 'signup' | 'reset'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [name, setName] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Check for persisted error on mount
  useEffect(() => {
    const persistedError = sessionStorage.getItem('authError');
    if (persistedError) {
      console.log('[Auth] Found persisted error:', persistedError);
      setError(persistedError);
      sessionStorage.removeItem('authError');
    }
  }, []);

  // Debug: Log error state changes
  useEffect(() => {
    console.log('[Auth] Error state changed to:', error);
  }, [error]);

  // Handle redirect result on component mount
  useEffect(() => {
    const handleRedirectResult = async () => {
      try {
        const result = await getRedirectResult(auth);
        if (result) {
          const user = result.user;

          if (user.email) {
            // Call backend to login/register user
            try {
              const backendUser = await loginWithBackend(user);
              onAuthSuccess(backendUser);
            } catch (backendError: any) {
              // Backend login failed - persist error, then sign out from Firebase
              const errorMsg = backendError.message || 'Failed to complete login. Please try again.';
              sessionStorage.setItem('authError', errorMsg);
              setError(errorMsg);
              await signOut(auth);
              return; // Don't throw, we've already handled the error
            }
          }
        }
      } catch (error: any) {
        console.error('Redirect result error:', error);
        setError(error.message || 'Authentication failed. Please try again.');
      }
    };

    handleRedirectResult();
  }, [onAuthSuccess, loginWithBackend]);

  const handleGoogleAuth = async () => {
    setLoading(true);
    setError('');
    setSuccessMessage('');

    try {
      const result = await signInWithPopup(auth, googleProvider);
      const user = result.user;

      if (!user.email) {
        throw new Error('No email found in Google account');
      }

      // Call backend to login/register user
      try {
        const backendUser = await loginWithBackend(user);
        onAuthSuccess(backendUser);
      } catch (backendError: any) {
        // Backend login failed - persist error, then sign out from Firebase
        console.log('[Auth Google] Backend login failed, error:', backendError);
        const errorMsg = backendError.message || backendError.toString() || 'Failed to complete login. Please try again.';
        console.log('[Auth Google] Error message extracted:', errorMsg);

        // Persist error to sessionStorage so it survives component remount
        sessionStorage.setItem('authError', errorMsg);
        console.log('[Auth Google] Error persisted to sessionStorage');

        setError(errorMsg);
        console.log('[Auth Google] Error state set, now signing out');
        setLoading(false);

        try {
          await signOut(auth);
          console.log('[Auth Google] Sign out completed');
        } catch (signOutError) {
          console.error('[Auth Google] Sign out failed:', signOutError);
        }
        return; // Don't throw, we've already handled the error
      }
    } catch (error: any) {
      console.error('[Auth] Google Auth Error:', error);
      console.log('[Auth] Error code:', error.code);
      console.log('[Auth] Error message:', error.message);

      // Handle Firebase auth errors only
      if (error.code && error.code.startsWith('auth/')) {
        // Handle specific Firebase auth errors
        if (error.code === 'auth/popup-closed-by-user') {
          setError('Sign-in was cancelled. Please try again.');
        } else if (error.code === 'auth/popup-blocked') {
          // Try redirect as fallback
          try {
            await signInWithRedirect(auth, googleProvider);
            return;
          } catch (redirectError) {
            setError('Popup was blocked and redirect failed. Please allow popups and try again.');
          }
        } else if (error.code === 'auth/cancelled-popup-request') {
          setError('Another sign-in popup is already open.');
        } else if (error.code === 'auth/network-request-failed') {
          setError('Network error. Please check your connection and try again.');
        } else {
          setError(error.message || 'Failed to sign in with Google. Please try again.');
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const handleEmailPasswordAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccessMessage('');

    try {
      // Validation
      if (!email || !password) {
        setError('Please enter both email and password.');
        setLoading(false);
        return;
      }

      if (emailAuthMode === 'signup') {
        if (!name.trim()) {
          setError('Please enter your name.');
          setLoading(false);
          return;
        }
        if (password.length < 6) {
          setError('Password must be at least 6 characters long.');
          setLoading(false);
          return;
        }
        if (password !== confirmPassword) {
          setError('Passwords do not match.');
          setLoading(false);
          return;
        }
      }

      let userCredential;

      if (emailAuthMode === 'signup') {
        // Create new account
        userCredential = await createUserWithEmailAndPassword(auth, email, password);

        // Update user profile with display name
        await updateProfile(userCredential.user, {
          displayName: name.trim()
        });

        // Reload user to get updated profile data
        await userCredential.user.reload();

        // Send verification email
        await sendEmailVerification(userCredential.user);
        setSuccessMessage('Account created! Please check your email to verify your account.');
      } else {
        // Sign in with existing account
        userCredential = await signInWithEmailAndPassword(auth, email, password);
      }

      // Get the current user from auth to ensure we have the latest data
      const user = emailAuthMode === 'signup' ? auth.currentUser || userCredential.user : userCredential.user;

      if (!user.email) {
        throw new Error('No email found in account');
      }

      // Call backend to login/register user
      try {
        // For signup, force refresh the token to include the updated displayName
        if (emailAuthMode === 'signup') {
          await user.getIdToken(true); // true forces token refresh
        }

        const backendUser = await loginWithBackend(user);
        onAuthSuccess(backendUser);
      } catch (backendError: any) {
        // Backend login failed - persist error, then sign out from Firebase
        console.log('[Auth Email] Backend login failed, error:', backendError);
        const errorMsg = backendError.message || backendError.toString() || 'Failed to complete login. Please try again.';
        console.log('[Auth Email] Error message extracted:', errorMsg);

        sessionStorage.setItem('authError', errorMsg);
        setError(errorMsg);
        setLoading(false);

        try {
          await signOut(auth);
        } catch (signOutError) {
          console.error('[Auth Email] Sign out failed:', signOutError);
        }
        return;
      }
    } catch (error: any) {
      console.error('[Auth] Email/Password Auth Error:', error);

      // Handle Firebase auth errors
      if (error.code === 'auth/email-already-in-use') {
        setError('This email is already registered. Please sign in instead.');
      } else if (error.code === 'auth/invalid-email') {
        setError('Invalid email address.');
      } else if (error.code === 'auth/weak-password') {
        setError('Password is too weak. Please use a stronger password.');
      } else if (error.code === 'auth/user-not-found') {
        setError('No account found with this email. Please sign up first.');
      } else if (error.code === 'auth/wrong-password') {
        setError('Incorrect password. Please try again.');
      } else if (error.code === 'auth/invalid-credential') {
        setError('Invalid email or password. Please try again.');
      } else if (error.code === 'auth/too-many-requests') {
        setError('Too many failed attempts. Please try again later.');
      } else if (error.code === 'auth/network-request-failed') {
        setError('Network error. Please check your connection and try again.');
      } else {
        setError(error.message || 'Authentication failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handlePasswordReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccessMessage('');

    try {
      if (!email) {
        setError('Please enter your email address.');
        setLoading(false);
        return;
      }

      await sendPasswordResetEmail(auth, email);
      setSuccessMessage('Password reset email sent! Please check your inbox.');

      // Switch back to login mode after 3 seconds
      setTimeout(() => {
        setEmailAuthMode('login');
        setSuccessMessage('');
      }, 3000);
    } catch (error: any) {
      console.error('[Auth] Password Reset Error:', error);

      if (error.code === 'auth/user-not-found') {
        setError('No account found with this email address.');
      } else if (error.code === 'auth/invalid-email') {
        setError('Invalid email address.');
      } else if (error.code === 'auth/too-many-requests') {
        setError('Too many requests. Please try again later.');
      } else {
        setError(error.message || 'Failed to send password reset email. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h2 className="text-4xl sm:text-5xl font-extrabold text-gray-900 mb-2">
            AI Stock Recommender
          </h2>
          <p className="text-lg text-gray-600">
            Sign in to continue
          </p>
        </div>

        <div className="mt-8">
          {error && (
            <div className="mb-6 text-red-600 text-sm text-center bg-red-50 border border-red-200 p-4 rounded-lg shadow-sm">
              <strong>Error:</strong> {error}
            </div>
          )}

          {successMessage && (
            <div className="mb-6 text-green-600 text-sm text-center bg-green-50 border border-green-200 p-4 rounded-lg shadow-sm">
              <strong>Success:</strong> {successMessage}
            </div>
          )}

          <div className="bg-white py-8 px-6 shadow-xl rounded-2xl border border-gray-100">
            {/* Auth Mode Tabs */}
            <div className="flex mb-6 bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => {
                  setAuthMode('google');
                  setError('');
                  setSuccessMessage('');
                }}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-all duration-200 ${
                  authMode === 'google'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Google
              </button>
              <button
                onClick={() => {
                  setAuthMode('email');
                  setError('');
                  setSuccessMessage('');
                }}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-all duration-200 ${
                  authMode === 'email'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Email
              </button>
            </div>

            {/* Google Auth */}
            {authMode === 'google' && (
              <button
                onClick={handleGoogleAuth}
                disabled={loading}
                className="w-full inline-flex items-center justify-center py-4 px-6 border-2 border-gray-300 rounded-xl shadow-sm bg-white text-base font-semibold text-gray-700 hover:bg-gray-50 hover:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
              >
                {loading ? (
                  <span className="text-gray-500">Signing in...</span>
                ) : (
                  <>
                    <svg className="w-6 h-6 mr-3" viewBox="0 0 24 24">
                      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                    </svg>
                    <span>Continue with Google</span>
                  </>
                )}
              </button>
            )}

            {/* Email/Password Auth */}
            {authMode === 'email' && (
              <div>
                {emailAuthMode !== 'reset' && (
                  <div className="flex mb-4 bg-gray-50 rounded-lg p-1">
                    <button
                      onClick={() => {
                        setEmailAuthMode('login');
                        setError('');
                        setSuccessMessage('');
                      }}
                      className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-all duration-200 ${
                        emailAuthMode === 'login'
                          ? 'bg-white text-indigo-600 shadow-sm'
                          : 'text-gray-600 hover:text-gray-900'
                      }`}
                    >
                      Sign In
                    </button>
                    <button
                      onClick={() => {
                        setEmailAuthMode('signup');
                        setError('');
                        setSuccessMessage('');
                      }}
                      className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-all duration-200 ${
                        emailAuthMode === 'signup'
                          ? 'bg-white text-indigo-600 shadow-sm'
                          : 'text-gray-600 hover:text-gray-900'
                      }`}
                    >
                      Sign Up
                    </button>
                  </div>
                )}

                <form onSubmit={emailAuthMode === 'reset' ? handlePasswordReset : handleEmailPasswordAuth}>
                  <div className="space-y-4">
                    {emailAuthMode === 'signup' && (
                      <div>
                        <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
                          Full Name
                        </label>
                        <input
                          id="name"
                          type="text"
                          value={name}
                          onChange={(e) => setName(e.target.value)}
                          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                          placeholder="John Doe"
                          required
                        />
                      </div>
                    )}

                    <div>
                      <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                        Email Address
                      </label>
                      <input
                        id="email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                        placeholder="you@example.com"
                        required
                      />
                    </div>

                    {emailAuthMode !== 'reset' && (
                      <div>
                        <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                          Password
                        </label>
                        <input
                          id="password"
                          type="password"
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                          placeholder="••••••••"
                          required
                        />
                      </div>
                    )}

                    {emailAuthMode === 'signup' && (
                      <div>
                        <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-1">
                          Confirm Password
                        </label>
                        <input
                          id="confirmPassword"
                          type="password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                          placeholder="••••••••"
                          required
                        />
                      </div>
                    )}

                    <button
                      type="submit"
                      disabled={loading}
                      className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg shadow-md focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
                    >
                      {loading ? (
                        <span>Processing...</span>
                      ) : emailAuthMode === 'reset' ? (
                        'Send Reset Link'
                      ) : emailAuthMode === 'signup' ? (
                        'Create Account'
                      ) : (
                        'Sign In'
                      )}
                    </button>

                    {emailAuthMode === 'login' && (
                      <div className="text-center mt-3">
                        <button
                          type="button"
                          onClick={() => {
                            setEmailAuthMode('reset');
                            setError('');
                            setSuccessMessage('');
                          }}
                          className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
                        >
                          Forgot Password?
                        </button>
                      </div>
                    )}

                    {emailAuthMode === 'reset' && (
                      <div className="text-center mt-3">
                        <button
                          type="button"
                          onClick={() => {
                            setEmailAuthMode('login');
                            setError('');
                            setSuccessMessage('');
                          }}
                          className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
                        >
                          Back to Sign In
                        </button>
                      </div>
                    )}

                    {emailAuthMode === 'signup' && (
                      <p className="text-xs text-gray-500 text-center mt-2">
                        Password must be at least 6 characters long
                      </p>
                    )}
                  </div>
                </form>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Auth;
