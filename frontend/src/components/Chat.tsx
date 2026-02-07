import React, { useState, useEffect, useRef } from 'react';
import { Message, User } from '../types';
import { apiService } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { Send, Upload, LogOut, FileText, Plus } from 'lucide-react';
import MessageLimitBanner from './MessageLimitBanner';
import EmailConfirmationModal from './EmailConfirmationModal';
import AuthorizationErrorModal from './AuthorizationErrorModal';

interface ChatProps {
  user: User;
  onLogout: () => void;
  onNewChat: () => void;
}

// Helper function to clean message text (remove asterisks)
const cleanMessageText = (text: string): string => {
  return text.replace(/\*/g, '');
};

// Helper function to split message into sentences
const splitIntoSentences = (text: string): string[] => {
  // Split by full stops, keeping the period with each sentence
  // Handle edge cases like "Dr.", "Mr.", numbers like "3.5", etc.
  const sentences = text.split(/(?<=[.!?])\s+/).filter(s => s.trim());
  return sentences.length > 0 ? sentences : [text];
};

const Chat: React.FC<ChatProps> = ({ user, onLogout, onNewChat }) => {
  const { logout } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [isFileUploaded, setIsFileUploaded] = useState<boolean>(false);
  const [showMessageLimitBanner, setShowMessageLimitBanner] = useState(false);
  const [endSession, setEndSession] = useState<boolean>(false);
  const [showEmailConfirmationModal, setShowEmailConfirmationModal] = useState(false);
  const [showAuthErrorModal, setShowAuthErrorModal] = useState(false);
  const [authErrorMessage, setAuthErrorMessage] = useState('');
  const [isReportLimitError, setIsReportLimitError] = useState(false);
  const [isChatDisabled, setIsChatDisabled] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const justInitializedRef = useRef<boolean>(false);

  // Function to add assistant message with chunked delivery (2-3 sec delays)
  // Each sentence appears as a separate message bubble
  const addAssistantMessageChunked = async (
    messageId: string,
    fullText: string,
    userName: string = 'Finance Assistant'
  ) => {
    const cleanedText = cleanMessageText(fullText);
    const sentences = splitIntoSentences(cleanedText);

    for (let i = 0; i < sentences.length; i++) {
      const isLastChunk = i === sentences.length - 1;

      // Add each sentence as a separate message bubble
      const chunkMessage: Message = {
        id: `${messageId}-${i}`,
        text: sentences[i],
        userId: 'assistant',
        userName: userName,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, chunkMessage]);

      // Wait 2-3 seconds before next chunk (except for the last one)
      if (!isLastChunk) {
        await new Promise(resolve => setTimeout(resolve, 2500));
      }
    }
  };

  useEffect(() => {
    // Validate user profile on mount and redirect if invalid
    if (!user || !user.id) {
      console.error('Invalid user prop passed to Chat component, redirecting to login');
      logout();
      return;
    }

    // Initialize chat session and get greeting message
    const initializeChat = async () => {
      try {
        console.log('[CHAT] Initializing chat session...');
        const response = await apiService.initChat(user.id);

        console.log('[CHAT] Init response:', response);

        // Set the session ID
        setSessionId(response.session_id);

        // If there's a greeting, add it to messages with chunked delivery
        if (response.greeting) {
          justInitializedRef.current = true; // Mark that we just initialized
          console.log('[CHAT] Starting chunked greeting message delivery');
          // Use chunked delivery for greeting
          addAssistantMessageChunked(
            `${response.session_id}-greeting`,
            response.greeting,
            'Finance Assistant'
          );
        } else if (response.has_messages) {
          // Session already has messages, they will be fetched by the sessionId useEffect
          justInitializedRef.current = false; // Let the fetch happen
          console.log('[CHAT] Session has existing messages, will fetch them');
        } else {
          // No greeting and no messages - start fresh
          setMessages([]);
          justInitializedRef.current = true;
        }
      } catch (error: any) {
        console.error('[CHAT] Error initializing chat:', error);

        // Display error message in chat window
        const errorMessage: Message = {
          id: 'init-error',
          text: error.message || 'Failed to initialize chat. Please try again or contact support.',
          userId: 'assistant',
          userName: 'System',
          timestamp: new Date()
        };
        setMessages([errorMessage]);
        justInitializedRef.current = true;

        // Check if this is an authorization error and disable chat
        if (error.code === 'ACCOUNT_NOT_AUTHORIZED' || error.code === 'REPORT_LIMIT_REACHED') {
          setAuthErrorMessage(error.message);
          setIsReportLimitError(error.code === 'REPORT_LIMIT_REACHED');
          setShowAuthErrorModal(true);
          setIsChatDisabled(true);
        }
      }
    };

    initializeChat();
  }, [user, logout]);

  useEffect(() => {
    // Scroll to bottom when new messages arrive
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    // Fetch existing messages when sessionId is set
    const fetchSessionMessages = async () => {
      if (!sessionId) return;

      // Skip fetching if we just initialized with a greeting
      if (justInitializedRef.current) {
        console.log('[CHAT] Skipping message fetch - just initialized');
        justInitializedRef.current = false; // Reset the flag
        return;
      }

      try {
        console.log('[CHAT] Fetching session messages...');
        const response = await apiService.getSessionMessages(sessionId);
        if (response && response.messages) {
          // Transform backend messages to frontend Message format
          // Clean asterisks from assistant messages (but don't animate history)
          const fetchedMessages: Message[] = response.messages.map((msg: any) => ({
            id: msg.id,
            text: msg.message_type === 'user' ? msg.content : cleanMessageText(msg.content),
            userId: msg.message_type === 'user' ? user.id : 'assistant',
            userName: msg.message_type === 'user' ? user.name : 'Finance Assistant',
            timestamp: new Date(msg.timestamp)
          }));

          // Replace messages with fetched messages to show greeting and all history
          setMessages(fetchedMessages);
          console.log('[CHAT] Messages fetched and displayed');
        }
      } catch (error) {
        console.error('Error fetching session messages:', error);
        // Continue with current messages if fetch fails
      }
    };

    fetchSessionMessages();
  }, [sessionId, user.id, user.name]);

  useEffect(() => {
    // Show email confirmation modal when session ends
    if (endSession) {
      setShowEmailConfirmationModal(true);
    }
  }, [endSession]);

  const handleCloseEmailConfirmationModal = () => {
    setShowEmailConfirmationModal(false);
    setMessages([]); // Clear chat history
    onNewChat(); // Redirect to home page
  };

  const handleCloseAuthErrorModal = () => {
    setShowAuthErrorModal(false);
    // Keep chat disabled, user needs to contact support
  };

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Check if user is valid (should `already be validated at mount)
    if (!user || !user.id) {
      console.error('User is invalid, redirecting to login');
      logout();
      return;
    }
    
    // Allow sending if there's a message or a file
    if ((!newMessage.trim() && !selectedFile) || sendingMessage) return;

    setSendingMessage(true);
    const messageText = newMessage.trim() || (selectedFile ? `Uploaded: ${selectedFile.name}` : '');
    const fileToSend = selectedFile;

    setNewMessage('');
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }

    // Add user message to chat immediately (optimistic UI update)
    const userMessage: Message = {
      id: Date.now().toString() + '-user',
      text: messageText,
      userId: user.id,
      userName: user.name,
      timestamp: new Date(),
      ...(fileToSend && {
        fileName: fileToSend.name,
        fileUrl: undefined
      })
    };

    setMessages(prev => [...prev, userMessage]);

    try {
      if (fileToSend) {
        // FILE UPLOAD: Use async flow to avoid gateway timeouts during portfolio analysis
        const asyncResponse = await apiService.sendChatMessageAsync(
          messageText,
          user.id,
          user.paid_user,
          sessionId,
          fileToSend
        );

        // Update session ID
        if (asyncResponse.session_id && asyncResponse.session_id !== sessionId) {
          setSessionId(asyncResponse.session_id);
        }

        // Show processing indicator
        const processingMessage: Message = {
          id: `processing-${asyncResponse.task_id}`,
          text: 'Analyzing your portfolio document... This may take a moment.',
          userId: 'assistant',
          userName: 'Finance Assistant',
          timestamp: new Date()
        };
        setMessages(prev => [...prev, processingMessage]);

        // Poll for result
        const pollInterval = 5000; // 5 seconds
        const maxPolls = 120; // 10 minutes max
        let polls = 0;

        const pollForResult = async () => {
          while (polls < maxPolls) {
            polls++;
            await new Promise(resolve => setTimeout(resolve, pollInterval));

            try {
              const taskStatus = await apiService.pollTaskStatus(asyncResponse.task_id);

              if (taskStatus.status === 'completed') {
                // Remove processing message and add real response
                setMessages(prev => prev.filter(m => m.id !== `processing-${asyncResponse.task_id}`));

                if (typeof taskStatus.is_file_uploaded === 'boolean') {
                  setIsFileUploaded(taskStatus.is_file_uploaded);
                }
                if (typeof taskStatus.end_session === 'boolean') {
                  setEndSession(taskStatus.end_session);
                }

                if (taskStatus.response) {
                  // Use chunked delivery for assistant response
                  await addAssistantMessageChunked(
                    Date.now().toString() + '-assistant',
                    taskStatus.response,
                    'Finance Assistant'
                  );
                }
                return;
              } else if (taskStatus.status === 'failed') {
                // Remove processing message and show error
                setMessages(prev => prev.filter(m => m.id !== `processing-${asyncResponse.task_id}`));
                const errorMessage: Message = {
                  id: `error-${Date.now()}`,
                  text: taskStatus.error || 'An error occurred while analyzing your portfolio. Please try again.',
                  userId: 'system',
                  userName: 'System',
                  timestamp: new Date()
                };
                setMessages(prev => [...prev, errorMessage]);
                return;
              }
              // status is 'pending' or 'processing' - continue polling
            } catch (pollError) {
              console.error('Error polling task status:', pollError);
              // Continue polling on transient errors
            }
          }

          // Timeout - max polls reached
          setMessages(prev => prev.filter(m => m.id !== `processing-${asyncResponse.task_id}`));
          const timeoutMessage: Message = {
            id: `timeout-${Date.now()}`,
            text: 'Portfolio analysis is taking longer than expected. Please check back later.',
            userId: 'system',
            userName: 'System',
            timestamp: new Date()
          };
          setMessages(prev => [...prev, timeoutMessage]);
        };

        await pollForResult();

      } else {
        // NO FILE: Use sync flow as before
        const response = await apiService.sendChatMessage(
          messageText,
          user.id,
          user.paid_user,
          sessionId
        );

        // Update session ID if returned from API
        if (response.session_id && response.session_id !== sessionId) {
          setSessionId(response.session_id);
        }

        // Update file upload status from API response
        if (typeof response.is_file_uploaded === 'boolean') {
          setIsFileUploaded(response.is_file_uploaded);
        }

        // Update end_session status from API response
        if (typeof response.end_session === 'boolean') {
          setEndSession(response.end_session);
        }

        // Add assistant response if exists (with chunked delivery)
        if (response.response) {
          await addAssistantMessageChunked(
            Date.now().toString() + '-assistant',
            response.response,
            'Finance Assistant'
          );
        }
      }
    } catch (error: any) {
      console.error('Error sending message:', error);

      // Check if this is an authorization error or report limit error
      if (error.code === 'ACCOUNT_NOT_AUTHORIZED' || error.code === 'REPORT_LIMIT_REACHED') {
        setAuthErrorMessage(error.message);
        setIsReportLimitError(error.code === 'REPORT_LIMIT_REACHED');
        setShowAuthErrorModal(true);
        setIsChatDisabled(true);
        return; // Don't restore message, stop the chat
      }

      // Check if this is a message limit error
      if (error.code === 'MESSAGE_LIMIT_REACHED') {
        setShowMessageLimitBanner(true);
      }

      // Check if this is a rate limit error - show temporary message in chat
      if (error.code === 'RATE_LIMIT_EXCEEDED') {
        const rateLimitMessage: Message = {
          id: `rate-limit-${Date.now()}`,
          text: error.message || 'Server is busy. Please wait a moment and try again.',
          userId: 'system',
          userName: 'System',
          timestamp: new Date()
        };
        setMessages(prev => [...prev, rateLimitMessage]);
      }

      // Restore the message and file if there was an error with the API call
      setNewMessage(messageText);
      if (fileToSend) {
        setSelectedFile(fileToSend);
      }
    } finally {
      setSendingMessage(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];

    if (!file) return;

    console.log('File selected:', file.name, 'Type:', file.type);

    const allowedTypes = [
      'application/pdf',
      'image/jpeg',
      'image/jpg',
      'image/png',
      'image/gif',
      'image/bmp',
      'image/tiff',
      'image/webp'
    ];

    // Check file extension as fallback
    const allowedExtensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'];
    const fileName = file.name.toLowerCase();
    const hasValidExtension = allowedExtensions.some(ext => fileName.endsWith(ext));

    if (allowedTypes.includes(file.type) || hasValidExtension) {
      console.log('File accepted:', file.name);
      setSelectedFile(file);
    } else {
      console.error('File rejected. Type:', file.type, 'Name:', file.name);
      alert('Please select a PDF or image file (JPG, PNG, GIF, BMP, TIFF, WEBP).');
    }
  };


  const downloadFile = (fileUrl: string, fileName: string) => {
    const link = document.createElement('a');
    link.href = fileUrl;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const formatTime = (timestamp: Date) => {
    return timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      {/* Header */}
      <div className="bg-white shadow-sm border-b px-4 sm:px-6 py-4 flex justify-between items-center">
        <div className="min-w-0 flex-1">
          <h1 className="text-lg sm:text-xl font-semibold text-gray-900 truncate">Finance Chat</h1>
          <p className="text-xs sm:text-sm text-gray-600 truncate">Welcome, {user.name}</p>
        </div>
        <div className="flex items-center space-x-2 sm:space-x-3 flex-shrink-0">
          <button
            onClick={onNewChat}
            className="flex items-center px-2 sm:px-3 py-2 text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-md transition-colors"
          >
            <Plus className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">New Chat</span>
          </button>
          <button
            onClick={onLogout}
            className="flex items-center px-2 sm:px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
          >
            <LogOut className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      </div>

      {/* Message Limit Banner */}
      {showMessageLimitBanner && (
        <div className="px-6 pt-4">
          <MessageLimitBanner onClose={() => setShowMessageLimitBanner(false)} onNavigateHome={onNewChat} />
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.userId === user.id ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] sm:max-w-md lg:max-w-lg px-4 py-2 rounded-lg ${
                message.userId === user.id
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-gray-900 border'
              }`}
            >
              <div className="flex items-center mb-1">
                <span className="text-xs font-medium opacity-75">
                  {message.userName}
                </span>
                <span className="text-xs opacity-75 ml-2">
                  {formatTime(message.timestamp)}
                </span>
              </div>
              
              <div className="text-sm">
                {message.text}
                {message.fileUrl && (
                  <div className="mt-2 flex items-center space-x-2">
                    <FileText className="h-4 w-4" />
                    <span className="text-xs">{message.fileName}</span>
                    <button
                      onClick={() => downloadFile(message.fileUrl!, message.fileName!)}
                      className="text-xs underline hover:no-underline"
                    >
                      Download
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Message Input */}
      <div className="bg-white border-t px-4 sm:px-6 py-3 sm:py-4">
        <form onSubmit={sendMessage} className="flex space-x-2 sm:space-x-4">
          <div className="flex-1 flex space-x-2">
            <input
              type="text"
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder="Type your message..."
              disabled={isChatDisabled}
              className="flex-1 px-3 sm:px-4 py-2 text-sm sm:text-base border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.webp"
              onChange={handleFileSelect}
              className="hidden"
            />
            {!isFileUploaded && (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isChatDisabled}
                className="px-2 sm:px-3 py-2 text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
                title="Upload file"
              >
                <Upload className="h-4 w-4 sm:h-5 sm:w-5" />
              </button>
            )}
          </div>
          <button
            type="submit"
            disabled={(!newMessage.trim() && !selectedFile) || sendingMessage || endSession || isChatDisabled}
            className={`px-4 sm:px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 transition-colors flex-shrink-0 ${(endSession || isChatDisabled) ? 'blur-sm' : ''}`}
          >
            {sendingMessage ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <Send className="h-4 w-4 sm:h-5 sm:w-5" />
            )}
          </button>
        </form>
        
        {/* File Preview */}
        {selectedFile && (
          <div className="mt-3 p-3 bg-gray-50 rounded-md flex items-center justify-between gap-2">
            <div className="flex items-center space-x-2 min-w-0 flex-1">
              <FileText className="h-4 w-4 text-gray-500 flex-shrink-0" />
              <span className="text-sm text-gray-700 truncate">{selectedFile.name}</span>
              <span className="text-xs text-gray-500 hidden sm:inline flex-shrink-0">• Ready to send</span>
            </div>
            <button
              onClick={() => {
                setSelectedFile(null);
                if (fileInputRef.current) fileInputRef.current.value = '';
              }}
              className="px-3 py-1 text-xs font-medium text-gray-600 bg-gray-200 hover:bg-gray-300 rounded transition-colors flex-shrink-0"
            >
              Remove
            </button>
          </div>
        )}
      </div>

      {/* Email Confirmation Modal */}
      <EmailConfirmationModal
        isOpen={showEmailConfirmationModal}
        onClose={handleCloseEmailConfirmationModal}
      />

      {/* Authorization Error Modal */}
      <AuthorizationErrorModal
        isOpen={showAuthErrorModal}
        onClose={handleCloseAuthErrorModal}
        onNavigateHome={onNewChat}
        errorMessage={authErrorMessage}
        showAddCredits={isReportLimitError}
      />
    </div>
  );
};

export default Chat;
