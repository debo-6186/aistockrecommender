import React, { useState } from 'react';
import { AlertCircle, X } from 'lucide-react';
import { apiService } from '../services/api';

interface AuthorizationErrorModalProps {
  isOpen: boolean;
  onClose: () => void;
  errorMessage: string;
  showAddCredits?: boolean;
}

const AuthorizationErrorModal: React.FC<AuthorizationErrorModalProps> = ({ isOpen, onClose, errorMessage, showAddCredits = false }) => {
  const [isAddingCredits, setIsAddingCredits] = useState(false);
  const [addCreditsError, setAddCreditsError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleAddCredits = async () => {
    setIsAddingCredits(true);
    setAddCreditsError(null);

    try {
      await apiService.addCredits();
      // Refresh the page to update credit balance and re-initialize
      window.location.reload();
    } catch (error: any) {
      console.error('Error adding credits:', error);
      setAddCreditsError(error.message || 'Failed to add credits. Please try again.');
    } finally {
      setIsAddingCredits(false);
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
          {/* Error Icon */}
          <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-red-100 mb-4">
            <AlertCircle className="h-10 w-10 text-red-600" />
          </div>

          {/* Message */}
          <h3 className="text-xl font-semibold text-gray-900 mb-2">
            {showAddCredits ? 'Report Credits Exhausted' : 'Authorization Error'}
          </h3>
          <p className="text-gray-600 mb-4">
            {errorMessage}
          </p>

          {addCreditsError && (
            <p className="text-sm text-red-600 mb-4">
              {addCreditsError}
            </p>
          )}

          {/* Buttons */}
          <div className="space-y-3">
            {showAddCredits && (
              <button
                onClick={handleAddCredits}
                disabled={isAddingCredits}
                className="w-full px-6 py-3 bg-green-600 text-white font-medium rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isAddingCredits ? 'Adding Credits...' : 'Add Credits (Free for now)'}
              </button>
            )}
            <button
              onClick={onClose}
              className="w-full px-6 py-3 bg-indigo-600 text-white font-medium rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
            >
              {showAddCredits ? 'Close' : 'OK'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuthorizationErrorModal;
