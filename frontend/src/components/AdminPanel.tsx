import React, { useState } from 'react';
import { apiService } from '../services/api';

interface ErrorPopupProps {
  message: string;
  onClose: () => void;
}

const ErrorPopup: React.FC<ErrorPopupProps> = ({ message, onClose }) => {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 max-w-md w-full mx-4">
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className="ml-3 flex-1">
            <h3 className="text-lg font-medium text-gray-900">Error</h3>
            <div className="mt-2 text-sm text-gray-700">
              {message}
            </div>
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

interface SuccessPopupProps {
  message: string;
  onClose: () => void;
}

const SuccessPopup: React.FC<SuccessPopupProps> = ({ message, onClose }) => {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 max-w-md w-full mx-4">
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="ml-3 flex-1">
            <h3 className="text-lg font-medium text-gray-900">Success</h3>
            <div className="mt-2 text-sm text-gray-700">
              {message}
            </div>
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

const AdminPanel: React.FC = () => {
  const [email, setEmail] = useState('');
  const [credits, setCredits] = useState<number | ''>('');
  const [maxReports, setMaxReports] = useState<number | ''>('');
  const [whitelist, setWhitelist] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [userInfo, setUserInfo] = useState<any>(null);

  const handleGetUserInfo = async () => {
    if (!email) {
      setErrorMessage('Please enter an email address');
      return;
    }

    setLoading(true);
    try {
      const data = await apiService.adminGetUserInfo(email);
      setUserInfo(data);
      setSuccessMessage('User information retrieved successfully');
    } catch (error: any) {
      setErrorMessage(error.message || 'Failed to fetch user information');
      setUserInfo(null);
    } finally {
      setLoading(false);
    }
  };

  const handleManageUser = async () => {
    if (!email) {
      setErrorMessage('Please enter an email address');
      return;
    }

    // Check if at least one field is provided
    if (credits === '' && maxReports === '' && whitelist === null) {
      setErrorMessage('Please provide at least one field to update (credits, max reports, or whitelist status)');
      return;
    }

    setLoading(true);
    try {
      const requestData: any = { email };
      if (credits !== '') requestData.credits = Number(credits);
      if (maxReports !== '') requestData.max_reports = Number(maxReports);
      if (whitelist !== null) requestData.whitelist = whitelist;

      const data = await apiService.adminManageUser(requestData);
      setSuccessMessage(data.message || 'User updated successfully');

      // Refresh user info
      handleGetUserInfo();

      // Clear form
      setCredits('');
      setMaxReports('');
      setWhitelist(null);
    } catch (error: any) {
      setErrorMessage(error.message || 'Failed to update user');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-900 mb-8">Admin Panel</h1>

        {/* User Email Search */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">User Management</h2>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              User Email
            </label>
            <div className="flex gap-2">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={handleGetUserInfo}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {loading ? 'Loading...' : 'Get Info'}
              </button>
            </div>
          </div>

          {/* User Info Display */}
          {userInfo && (
            <div className="mt-4 p-4 bg-gray-50 rounded-md">
              <h3 className="font-semibold mb-2">Current User Information</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="font-medium">Email:</span> {userInfo.email}</div>
                <div><span className="font-medium">Whitelisted:</span> {userInfo.whitelisted ? 'Yes' : 'No'}</div>
                <div><span className="font-medium">Max Reports:</span> {userInfo.max_reports}</div>
                <div><span className="font-medium">Current Reports:</span> {userInfo.current_report_count}</div>
                <div className="col-span-2"><span className="font-medium">Remaining:</span> {userInfo.remaining_reports}</div>
              </div>
            </div>
          )}
        </div>

        {/* Update User Form */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Update User Settings</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Add Credits
              </label>
              <input
                type="number"
                value={credits}
                onChange={(e) => setCredits(e.target.value === '' ? '' : Number(e.target.value))}
                placeholder="5"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Set Max Reports
              </label>
              <input
                type="number"
                value={maxReports}
                onChange={(e) => setMaxReports(e.target.value === '' ? '' : Number(e.target.value))}
                placeholder="10"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Whitelist Status
              </label>
              <div className="flex gap-4">
                <label className="flex items-center">
                  <input
                    type="radio"
                    name="whitelist"
                    checked={whitelist === true}
                    onChange={() => setWhitelist(true)}
                    className="mr-2"
                  />
                  Whitelist
                </label>
                <label className="flex items-center">
                  <input
                    type="radio"
                    name="whitelist"
                    checked={whitelist === false}
                    onChange={() => setWhitelist(false)}
                    className="mr-2"
                  />
                  Blacklist
                </label>
                <label className="flex items-center">
                  <input
                    type="radio"
                    name="whitelist"
                    checked={whitelist === null}
                    onChange={() => setWhitelist(null)}
                    className="mr-2"
                  />
                  No Change
                </label>
              </div>
            </div>

            <button
              onClick={handleManageUser}
              disabled={loading}
              className="w-full px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {loading ? 'Updating...' : 'Update User'}
            </button>
          </div>
        </div>
      </div>

      {/* Error Popup */}
      {errorMessage && (
        <ErrorPopup
          message={errorMessage}
          onClose={() => setErrorMessage(null)}
        />
      )}

      {/* Success Popup */}
      {successMessage && (
        <SuccessPopup
          message={successMessage}
          onClose={() => setSuccessMessage(null)}
        />
      )}
    </div>
  );
};

export default AdminPanel;
