import { User, ChatSession, PortfolioPerformanceData } from '../types';
import { auth } from '../firebase';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:10001/api';

// Helper function to get Firebase ID token
const getAuthToken = async (): Promise<string | null> => {
  const user = auth.currentUser;
  if (!user) return null;
  return await user.getIdToken();
};

// Helper function to create authenticated headers
const getAuthHeaders = async (): Promise<HeadersInit> => {
  const token = await getAuthToken();
  return {
    'Content-Type': 'application/json',
    ...(token && { 'Authorization': `Bearer ${token}` })
  };
};

// Helper function to retry fetch on 504 Gateway Timeout (1 retry)
const fetchWithRetry = async (url: string, options: RequestInit): Promise<Response> => {
  const response = await fetch(url, options);
  if (response.status === 504) {
    console.log('[API] Got 504 Gateway Timeout, retrying once...');
    return await fetch(url, options);
  }
  return response;
};

// Helper function to handle API responses with auth errors
const handleResponse = async (response: Response) => {
  if (response.status === 401) {
    // Token expired or invalid, force refresh
    const user = auth.currentUser;
    if (user) {
      try {
        await user.getIdToken(true); // Force refresh
        throw new Error('Authentication expired. Please try again.');
      } catch (error) {
        throw new Error('Please log in again.');
      }
    } else {
      throw new Error('Please log in again.');
    }
  }

  if (response.status === 409) {
    // Duplicate email or conflict error
    const error = await response.json().catch(() => ({}));
    console.log('[API] 409 Error detected:', error);
    const errorMessage = error.detail || error.message || 'This email is already registered with another account.';
    console.log('[API] Throwing error message:', errorMessage);
    throw new Error(errorMessage);
  }

  if (response.status === 429) {
    const error = await response.json().catch(() => ({}));
    const errorMessage = error.detail || error.message || error.error || '';

    // Check if this is a rate limit error (from slowapi)
    if (errorMessage.toLowerCase().includes('rate limit')) {
      const rateLimitError = new Error('Server is busy. Please wait a moment and try again.');
      (rateLimitError as any).code = 'RATE_LIMIT_EXCEEDED';
      throw rateLimitError;
    }

    // Otherwise, it's a message limit error
    const limitError = new Error(errorMessage || 'Maximum message limit is reached for free tier. Free users are limited to 30 messages. Add credits to continue.');
    (limitError as any).code = 'MESSAGE_LIMIT_REACHED';
    throw limitError;
  }

  if (response.status === 403) {
    // Report limit reached or account blocked
    const error = await response.json().catch(() => ({}));
    const errorMessage = error.detail || error.message || 'You have reached your report limit. Please upgrade your account.';

    // Check if this is an authorization error (account not authorized or disabled)
    if (typeof errorMessage === 'string' &&
        (errorMessage.includes('not authorized') || errorMessage.includes('has been disabled'))) {
      const authError = new Error(errorMessage);
      (authError as any).code = 'ACCOUNT_NOT_AUTHORIZED';
      throw authError;
    }

    // Otherwise, it's a report limit error - show Add Credits option
    const reportLimitError = new Error(errorMessage);
    (reportLimitError as any).code = 'REPORT_LIMIT_REACHED';
    throw reportLimitError;
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));

    // Check for authorization error
    if (error.detail && typeof error.detail === 'string' &&
        error.detail.includes('Your account is not authorized')) {
      const authError: any = new Error(error.detail);
      authError.code = 'ACCOUNT_NOT_AUTHORIZED';
      throw authError;
    }

    // Handle structured error responses from backend
    if (error.detail && typeof error.detail === 'object') {
      const errorDetail = error.detail;
      const errorMessage = errorDetail.message || errorDetail.error || `HTTP error! status: ${response.status}`;
      const customError: any = new Error(errorMessage);
      customError.statusCode = response.status;
      customError.errorType = errorDetail.error;
      throw customError;
    }

    throw new Error(error.detail || error.message || `HTTP error! status: ${response.status}`);
  }

  return response.json();
};

export const apiService = {
  // Login endpoint to verify Firebase token and create/get user
  async login(firebaseToken: string): Promise<User> {
    try {
      const response = await fetch(`${API_BASE_URL}/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          id_token: firebaseToken
        })
      });

      const userData = await handleResponse(response);
      
      // The backend already returns data in the correct format
      return {
        id: userData.id,
        email: userData.email,
        name: userData.name,
        contactNumber: userData.contactNumber || '',
        countryCode: userData.countryCode || '+1',
        uploadFile: userData.uploadFile || false,
        paid_user: userData.paid_user || false,
        createdAt: new Date(userData.createdAt)
      };
    } catch (error) {
      console.error('Error during backend login:', error);
      throw error;
    }
  },
  async getUserProfile(userId: string): Promise<User> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/users/${userId}/profile`, {
        method: 'GET',
        headers,
      });

      const userData = await handleResponse(response);
      
      // Transform the API response to match our User interface
      return {
        id: userData.id,
        email: userData.email,
        name: userData.name,
        contactNumber: userData.contact_number || userData.contactNumber,
        countryCode: userData.country_code || userData.countryCode,
        uploadFile: userData.upload_file || userData.uploadFile,
        paid_user: userData.paid_user,
        createdAt: new Date(userData.created_at || userData.createdAt)
      };
    } catch (error) {
      console.error('Error fetching user profile:', error);
      throw error;
    }
  },

  async updateUserProfile(userId: string, userData: Partial<User>): Promise<User> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/users/${userId}/profile`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({
          email: userData.email,
          name: userData.name,
          contact_number: userData.contactNumber,
          country_code: userData.countryCode,
        }),
      });

      const userProfile = await handleResponse(response);
      
      // Transform UserProfile response to User interface
      return {
        id: userProfile.user_id,
        email: userProfile.email || '',
        name: userProfile.name || '',
        contactNumber: userProfile.contact_number || '',
        countryCode: userProfile.country_code || '+1',
        uploadFile: userProfile.paid_user || false,  // Map paid_user to uploadFile
        paid_user: userProfile.paid_user || false,
        createdAt: new Date(userProfile.created_at)
      };
    } catch (error) {
      console.error('Error updating user profile:', error);
      throw error;
    }
  },

  async initChat(userId: string, sessionId?: string): Promise<{session_id: string, greeting: string | null, has_messages: boolean}> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/chats/init`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          user_id: userId,
          session_id: sessionId
        })
      });

      return await handleResponse(response);
    } catch (error) {
      console.error('Error initializing chat:', error);
      throw error;
    }
  },

  async sendChatMessage(message: string, user_id: string, paid_user: boolean, session_id?: string, file?: File): Promise<{response: string, session_id?: string, is_file_uploaded?: boolean, is_complete?: boolean, end_session?: boolean}> {
    try {
      console.log('=== sendChatMessage called ===');
      
      let body: any;
      let headers: HeadersInit;
      
      if (file) {
        // If file is provided, use FormData
        const formData = new FormData();
        formData.append('message', message);
        formData.append('user_id', user_id);
        formData.append('paid_user', paid_user.toString());
        if (session_id) {
          formData.append('session_id', session_id);
        }
        formData.append('file', file);
        
        body = formData;
        
        // Get auth headers without Content-Type (FormData sets it automatically)
        const token = await getAuthToken();
        headers = {
          ...(token && { 'Authorization': `Bearer ${token}` })
        };
      } else {
        // If no file, use JSON
        const requestBody: any = {
          message: message,
          user_id: user_id,
          paid_user: paid_user
        };

        if (session_id) {
          requestBody.session_id = session_id;
        }

        body = JSON.stringify(requestBody);
        headers = await getAuthHeaders();
      }

      console.log('Request body:', body);
      console.error('Sending chat request');
      console.error('Auth headers obtained:', headers);

      const response = await fetchWithRetry(`${API_BASE_URL}/chats`, {
        method: 'POST',
        headers,
        body
      });

      console.log('API response status:', response.status);
      console.log('API response ok:', response.ok);
      
      const result = await handleResponse(response);
      console.log('Parsed API result:', result);
      return result;
    } catch (error) {
      console.error('Error sending chat message:', error);
      throw error;
    }
  },

  async sendChatMessageAsync(message: string, user_id: string, paid_user: boolean, session_id?: string, file?: File): Promise<{task_id: string, session_id: string, status: string, message: string}> {
    try {
      console.log('=== sendChatMessageAsync called ===');

      let body: any;
      let headers: HeadersInit;

      if (file) {
        const formData = new FormData();
        formData.append('message', message);
        formData.append('user_id', user_id);
        formData.append('paid_user', paid_user.toString());
        if (session_id) {
          formData.append('session_id', session_id);
        }
        formData.append('file', file);

        body = formData;
        const token = await getAuthToken();
        headers = {
          ...(token && { 'Authorization': `Bearer ${token}` })
        };
      } else {
        const requestBody: any = {
          message: message,
          user_id: user_id,
          paid_user: paid_user
        };
        if (session_id) {
          requestBody.session_id = session_id;
        }
        body = JSON.stringify(requestBody);
        headers = await getAuthHeaders();
      }

      const response = await fetch(`${API_BASE_URL}/chats/async`, {
        method: 'POST',
        headers,
        body
      });

      const result = await handleResponse(response);
      console.log('Async task created:', result);
      return result;
    } catch (error) {
      console.error('Error sending async chat message:', error);
      throw error;
    }
  },

  async pollTaskStatus(taskId: string): Promise<{task_id: string, session_id: string, status: string, response?: string, is_complete: boolean, is_file_uploaded: boolean, end_session: boolean, error?: string, progress?: string}> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/chats/tasks/${taskId}`, {
        method: 'GET',
        headers,
      });

      return await handleResponse(response);
    } catch (error) {
      console.error('Error polling task status:', error);
      throw error;
    }
  },

  async getPortfolioPerformance(sessionId: string): Promise<PortfolioPerformanceData> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/portfolio-performance/${sessionId}`, {
        method: 'GET',
        headers,
      });

      const performanceData = await handleResponse(response);
      return performanceData;
    } catch (error) {
      console.error('Error fetching portfolio performance:', error);
      throw error;
    }
  },

  async getUserRecommendations(userId: string): Promise<any> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/user-recommendations/${userId}`, {
        method: 'GET',
        headers,
      });

      const recommendationsData = await handleResponse(response);
      return recommendationsData;
    } catch (error) {
      console.error('Error fetching user recommendations:', error);
      throw error;
    }
  },

  async getUserPortfolioPerformance(userId: string): Promise<PortfolioPerformanceData> {
    try {
      const headers = await getAuthHeaders();
      // Using the new latest-portfolio-performance endpoint that automatically gets the latest recommendation
      const response = await fetch(`${API_BASE_URL}/latest-portfolio-performance/${userId}`, {
        method: 'GET',
        headers,
      });

      const performanceData = await handleResponse(response);
      return performanceData;
    } catch (error) {
      console.error('Error fetching user portfolio performance:', error);
      throw error;
    }
  },

  // Admin API functions
  async adminManageUser(data: {
    email: string;
    credits?: number;
    max_reports?: number;
    whitelist?: boolean;
  }): Promise<any> {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/credits`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });

      return await handleResponse(response);
    } catch (error) {
      console.error('Error managing user:', error);
      throw error;
    }
  },

  async adminGetUserInfo(email: string): Promise<any> {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/credits/${encodeURIComponent(email)}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      return await handleResponse(response);
    } catch (error) {
      console.error('Error fetching user info:', error);
      throw error;
    }
  },

  async getSessionMessages(sessionId: string, limit: number = 50): Promise<any> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/messages?limit=${limit}`, {
        method: 'GET',
        headers,
      });

      return await handleResponse(response);
    } catch (error) {
      console.error('Error fetching session messages:', error);
      throw error;
    }
  },

  async addCredits(): Promise<any> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/users/add-credits`, {
        method: 'POST',
        headers,
      });

      return await handleResponse(response);
    } catch (error) {
      console.error('Error adding credits:', error);
      throw error;
    }
  },

  async getPayPalInfo(): Promise<any> {
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/payment/paypal-info`, {
        method: 'GET',
        headers,
      });

      return await handleResponse(response);
    } catch (error) {
      console.error('Error fetching PayPal info:', error);
      throw error;
    }
  }
};
