import React, { useState, useEffect } from 'react';
import { User } from '../types';
import { apiService } from '../services/api';
import { User as UserIcon, Phone, Globe, Save } from 'lucide-react';

interface ProfileSetupProps {
  user: User;
  onComplete: (user: User) => void;
}

const ProfileSetup: React.FC<ProfileSetupProps> = ({ user, onComplete }) => {
  console.log('[ProfileSetup] Received user prop:', user);
  console.log('[ProfileSetup] user.name:', user.name);

  const [name, setName] = useState(user.name || '');
  const [contactNumber, setContactNumber] = useState(user.contactNumber || '');
  const [countryCode, setCountryCode] = useState(user.countryCode || '+1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Sync state with props when user prop changes
  useEffect(() => {
    console.log('[ProfileSetup] useEffect triggered - updating state from props');
    console.log('[ProfileSetup] Updating name to:', user.name);
    setName(user.name || '');
    setContactNumber(user.contactNumber || '');
    setCountryCode(user.countryCode || '+1');
  }, [user.name, user.contactNumber, user.countryCode]);

  console.log('[ProfileSetup] Initial state - name:', name, 'contactNumber:', contactNumber, 'countryCode:', countryCode);

  const countryCodes = [
    { code: '+1', name: 'USA/Canada', dialCode: '+1' },
    { code: '+44', name: 'UK', dialCode: '+44' },
    { code: '+91', name: 'India', dialCode: '+91' },
    { code: '+61', name: 'Australia', dialCode: '+61' },
    { code: '+86', name: 'China', dialCode: '+86' },
    { code: '+81', name: 'Japan', dialCode: '+81' },
    { code: '+49', name: 'Germany', dialCode: '+49' },
    { code: '+33', name: 'France', dialCode: '+33' },
    { code: '+39', name: 'Italy', dialCode: '+39' },
    { code: '+34', name: 'Spain', dialCode: '+34' },
    { code: '+65', name: 'Singapore', dialCode: '+65' },
    { code: '+60', name: 'Malaysia', dialCode: '+60' },
    { code: '+82', name: 'South Korea', dialCode: '+82' },
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      console.log('[ProfileSetup] Updating profile with:', { name, contactNumber, countryCode, email: user.email });

      // Call the backend API to update user profile
      const updatedUser = await apiService.updateUserProfile(user.id, {
        email: user.email,
        name,
        contactNumber,
        countryCode
      });

      console.log('[ProfileSetup] Profile update successful, received:', updatedUser);
      console.log('[ProfileSetup] Updated user fields - name:', updatedUser.name, 'contactNumber:', updatedUser.contactNumber, 'countryCode:', updatedUser.countryCode);

      onComplete(updatedUser);
    } catch (error: any) {
      console.error('Profile update error:', error);
      setError(error.message || 'Failed to update profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-8 sm:py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-6 sm:space-y-8">
        <div>
          <h2 className="mt-4 sm:mt-6 text-center text-2xl sm:text-3xl font-extrabold text-gray-900">
            Complete Your Profile
          </h2>
          <p className="mt-2 text-center text-sm sm:text-base text-gray-600">
            Please provide your information to continue
          </p>
        </div>

        <form className="mt-6 sm:mt-8 space-y-4 sm:space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div className="relative">
              <UserIcon className="absolute left-3 top-2.5 sm:top-3 h-5 w-5 text-gray-400" />
              <input
                type="text"
                required
                className="appearance-none relative block w-full px-10 py-2.5 sm:py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 text-base sm:text-sm"
                placeholder="Full Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="relative">
              <Globe className="absolute left-3 top-2.5 sm:top-3 h-5 w-5 text-gray-400" />
              <select
                required
                className="appearance-none relative block w-full px-10 py-2.5 sm:py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 text-base sm:text-sm"
                value={countryCode}
                onChange={(e) => setCountryCode(e.target.value)}
              >
                {countryCodes.map((country) => (
                  <option key={country.code} value={country.dialCode}>
                    {country.name} ({country.dialCode})
                  </option>
                ))}
              </select>
            </div>

            <div className="relative">
              <Phone className="absolute left-3 top-2.5 sm:top-3 h-5 w-5 text-gray-400" />
              <input
                type="tel"
                required
                className="appearance-none relative block w-full px-10 py-2.5 sm:py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 text-base sm:text-sm"
                placeholder="Contact Number"
                value={contactNumber}
                onChange={(e) => setContactNumber(e.target.value)}
              />
            </div>
          </div>

          {error && (
            <div className="text-red-600 text-sm text-center">{error}</div>
          )}

          <div>
            <button
              type="submit"
              disabled={loading || !name.trim() || !contactNumber.trim()}
              className="group relative w-full flex justify-center py-2.5 sm:py-2 px-4 border border-transparent text-base sm:text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              {loading ? (
                'Saving...'
              ) : (
                <>
                  <Save className="h-5 w-5 mr-2" />
                  Complete Profile
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ProfileSetup;
