import React, { useEffect, useState, useCallback } from 'react';
import { BrowserRouter as Router, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Auth from './components/Auth';
import ProfileSetup from './components/ProfileSetup';
import Chat from './components/Chat';
import MainPage from './components/MainPage';
import AdminPanel from './components/AdminPanel';
import { User } from './types';
import { apiService } from './services/api';
import './App.css';

const AppContent: React.FC = () => {
  const { currentUser, userProfile, setUserProfile, loading, loginWithBackend, logout } = useAuth();
  const [apiLoading, setApiLoading] = useState(false);
  const [showMainPage, setShowMainPage] = useState(true);
  const [showChat, setShowChat] = useState(false);
  const location = useLocation();

  // Compute profile completeness from userProfile instead of maintaining separate state
  const isProfileComplete = userProfile?.name && userProfile?.contactNumber && userProfile?.countryCode;

  // Debug logging
  useEffect(() => {
    console.log('[App] userProfile:', userProfile);
    console.log('[App] isProfileComplete:', isProfileComplete);
    console.log('[App] name:', userProfile?.name);
    console.log('[App] contactNumber:', userProfile?.contactNumber);
    console.log('[App] countryCode:', userProfile?.countryCode);
  }, [userProfile, isProfileComplete]);

  const fetchUserProfile = useCallback(async () => {
    if (!currentUser || userProfile) return;

    setApiLoading(true);
    try {
      // Try to login with backend to get or create user
      const backendUser = await loginWithBackend(currentUser);
      setUserProfile(backendUser);
    } catch (error) {
      console.log('Backend login failed:', error);
      // If backend fails, user needs to complete profile with basic info
    } finally {
      setApiLoading(false);
    }
  }, [currentUser, userProfile, setUserProfile, loginWithBackend]);

  useEffect(() => {
    if (currentUser && !userProfile) {
      fetchUserProfile();
    }
  }, [currentUser, userProfile, fetchUserProfile]);

  const handleAuthSuccess = (user: User) => {
    setUserProfile(user);
    // Profile completeness is now automatically computed from userProfile
  };

  const handleProfileComplete = (user: User) => {
    setUserProfile(user);
    // Profile completeness is now automatically computed from userProfile
  };

  const handleStartChat = () => {
    setShowMainPage(false);
    setShowChat(true);
  };

  const handleNewChat = () => {
    setShowChat(false);
    setShowMainPage(true);
  };

  const handleLogoutFromMainPage = async () => {
    try {
      await logout();
      setShowMainPage(true);
      setShowChat(false);
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  const handleLogoutFromChat = async () => {
    try {
      await logout();
      setShowMainPage(true);
      setShowChat(false);
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  // Check if the current path is /admin
  if (location.pathname === '/admin') {
    return <AdminPanel />;
  }

  if (loading || apiLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return <Auth onAuthSuccess={handleAuthSuccess} />;
  }

  // Show loading while fetching user profile from backend
  // If we have currentUser but no userProfile, we're fetching from backend
  if (!userProfile) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading profile...</p>
        </div>
      </div>
    );
  }

  // If user profile exists but is incomplete, show ProfileSetup
  if (!isProfileComplete) {
    return <ProfileSetup user={userProfile} onComplete={handleProfileComplete} />;
  }

  // User is authenticated and has complete profile, show MainPage or Chat
  if (showChat) {
    return <Chat user={userProfile} onLogout={handleLogoutFromChat} onNewChat={handleNewChat} />;
  }
  
  return <MainPage user={userProfile} onStartChat={handleStartChat} onLogout={handleLogoutFromMainPage} />;
};

const App: React.FC = () => {
  return (
    <Router>
      <AuthProvider>
        <div className="App">
          <AppContent />
        </div>
      </AuthProvider>
    </Router>
  );
};

export default App;
