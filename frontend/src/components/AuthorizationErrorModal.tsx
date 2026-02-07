import React, { useState } from 'react';
import { AlertCircle, X } from 'lucide-react';
import { apiService } from '../services/api';

interface AuthorizationErrorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigateHome: () => void;
  errorMessage: string;
  showAddCredits?: boolean;
}

const AuthorizationErrorModal: React.FC<AuthorizationErrorModalProps> = ({ isOpen, onClose, onNavigateHome, errorMessage, showAddCredits = false }) => {
  const [isRequesting, setIsRequesting] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  if (!isOpen) return null;

  const handleRequestCredits = async () => {
    setIsRequesting(true);
    setRequestError(null);

    try {
      await apiService.requestCredits();
      setShowSuccess(true);

      // Navigate to About page after 3 seconds
      setTimeout(() => {
        onNavigateHome();
      }, 3000);
    } catch (error: any) {
      console.error('Error requesting credits:', error);
      setRequestError(error.message || 'Failed to request credits. Please try again.');
    } finally {
      setIsRequesting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 relative">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors"
          aria-label="Close"
        >
          <X className="h-6 w-6" />
        </button>

        {/* Content */}
        <div className="text-center">
          {/* Icon */}
          <div className={`mx-auto flex items-center justify-center h-16 w-16 rounded-full ${showSuccess ? 'bg-green-100' : 'bg-red-100'} mb-4`}>
            {showSuccess ? (
              <svg className="h-10 w-10 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            ) : (
              <AlertCircle className="h-10 w-10 text-red-600" />
            )}
          </div>

          {/* Message */}
          <h3 className="text-xl font-semibold text-gray-900 mb-2">
            {showSuccess ? 'Request Submitted' : showAddCredits ? 'Report Credits Exhausted' : 'Authorization Error'}
          </h3>
          <p className="text-gray-600 mb-4">
            {showSuccess
              ? 'Your credit request has been notified. Once we update the credits, we will send you an email to your registered email ID. Redirecting...'
              : errorMessage}
          </p>

          {requestError && (
            <p className="text-sm text-red-600 mb-4">
              {requestError}
            </p>
          )}

          {/* Buttons */}
          <div className="space-y-3">
            {showAddCredits && !showSuccess && (
              <button
                onClick={handleRequestCredits}
                disabled={isRequesting}
                className="w-full px-6 py-3 bg-green-600 text-white font-medium rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isRequesting ? 'Requesting Credits...' : 'Request Credits'}
              </button>
            )}
            {!showSuccess && (
              <button
                onClick={onClose}
                className="w-full px-6 py-3 bg-indigo-600 text-white font-medium rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
              >
                {showAddCredits ? 'Close' : 'OK'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuthorizationErrorModal;
