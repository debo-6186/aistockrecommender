import React, { useState } from 'react';
import { AlertCircle, X } from 'lucide-react';
import { apiService } from '../services/api';

interface MessageLimitBannerProps {
  onClose: () => void;
}

const MessageLimitBanner: React.FC<MessageLimitBannerProps> = ({ onClose }) => {
  const [isAddingCredits, setIsAddingCredits] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleAddCredits = async () => {
    setIsAddingCredits(true);
    setErrorMessage(null);

    try {
      const result = await apiService.addCredits();
      console.log('Credits added:', result);
      setShowSuccess(true);

      // Auto-close success message after 3 seconds
      setTimeout(() => {
        setShowSuccess(false);
        onClose();
        // Refresh the page to update credit balance
        window.location.reload();
      }, 3000);
    } catch (error: any) {
      console.error('Error adding credits:', error);
      setErrorMessage(error.message || 'Failed to add credits. Please try again.');
    } finally {
      setIsAddingCredits(false);
    }
  };

  if (showSuccess) {
    return (
      <div className="bg-green-50 border-l-4 border-green-400 p-4 mb-4">
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg className="h-5 w-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="ml-3 flex-1">
            <p className="text-sm text-green-700">
              <span className="font-medium">Credits added successfully!</span>
              {' '}30 message credits have been added to your account. Refreshing...
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-4">
      <div className="flex items-start">
        <div className="flex-shrink-0">
          <AlertCircle className="h-5 w-5 text-red-400" />
        </div>
        <div className="ml-3 flex-1">
          <p className="text-sm text-red-700">
            <span className="font-medium">Maximum message limit is reached for free tier.</span>
            {' '}Free users are limited to 30 messages. Add credits to continue.
          </p>
          {errorMessage && (
            <p className="text-sm text-red-600 mt-2">
              {errorMessage}
            </p>
          )}
          <div className="mt-3">
            <button
              onClick={handleAddCredits}
              disabled={isAddingCredits}
              className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isAddingCredits ? 'Adding Credits...' : 'Add Credit (Free for now)'}
            </button>
          </div>
        </div>
        <div className="flex-shrink-0 ml-4">
          <button
            type="button"
            className="inline-flex text-red-400 hover:text-red-600 focus:outline-none focus:text-red-600"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default MessageLimitBanner;