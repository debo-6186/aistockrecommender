import React, { useState } from 'react';
import { MessageCircle, TrendingUp, BarChart3, Brain, LogOut, LayoutDashboard } from 'lucide-react';
import { User } from '../types';
import PortfolioDashboard from './PortfolioDashboard';

interface MainPageProps {
  user: User;
  onStartChat: () => void;
  onLogout: () => void;
}

const MainPage: React.FC<MainPageProps> = ({ user, onStartChat, onLogout }) => {
  const [activeTab, setActiveTab] = useState<'home' | 'portfolios'>('home');

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="relative flex items-center py-4 sm:py-6">
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Stock Recommender AI</h1>
              <p className="text-xs sm:text-sm text-gray-600">Welcome, {user.name}</p>
            </div>
            <div className="flex items-center gap-2 sm:gap-3 ml-auto relative z-10">
              <button
                onClick={onStartChat}
                className="flex items-center px-3 sm:px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors"
              >
                <MessageCircle className="h-4 w-4 sm:mr-2" />
                <span className="hidden sm:inline">New Chat</span>
              </button>
              <button
                onClick={onLogout}
                className="flex items-center px-3 sm:px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
              >
                <LogOut className="h-4 w-4 sm:mr-2" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex gap-2 sm:gap-4 border-t pt-3 sm:pt-4 pb-2 overflow-x-auto">
            <button
              onClick={() => setActiveTab('portfolios')}
              className={`flex items-center gap-2 px-3 sm:px-4 py-2 rounded-md font-medium transition-colors whitespace-nowrap ${
                activeTab === 'portfolios'
                  ? 'bg-indigo-100 text-indigo-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <LayoutDashboard className="h-4 w-4" />
              <span className="text-sm sm:text-base">My Portfolios</span>
            </button>
            <button
              onClick={() => setActiveTab('home')}
              className={`flex items-center gap-2 px-3 sm:px-4 py-2 rounded-md font-medium transition-colors whitespace-nowrap ${
                activeTab === 'home'
                  ? 'bg-indigo-100 text-indigo-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <TrendingUp className="h-4 w-4" />
              <span className="text-sm sm:text-base">About</span>
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'portfolios' ? (
          <PortfolioDashboard userId={user.id} />
        ) : (
          <>
            {/* Hero Section */}
        <div className="text-center px-4">
          <TrendingUp className="mx-auto h-12 sm:h-16 w-12 sm:w-16 text-indigo-600" />
          <h2 className="mt-4 sm:mt-6 text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900">
            Intelligent Stock Recommendations
          </h2>
          <p className="mt-3 sm:mt-4 text-base sm:text-lg lg:text-xl text-gray-600 max-w-3xl mx-auto">
            Get personalized stock recommendations powered by AI. Analyze market trends,
            upload financial documents, and make informed investment decisions. Track your previous
            portfolio recommendations and see exactly how much you would have gained or lost had you
            followed our AI's stock suggestions.
          </p>
        </div>

        {/* Features Grid */}
        <div className="mt-16 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          <div className="text-center p-6 bg-white rounded-lg shadow-sm">
            <MessageCircle className="mx-auto h-12 w-12 text-indigo-600 mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Start New Chat</h3>
            <p className="text-gray-600">
              Begin a conversation with our AI assistant anytime. Get instant stock recommendations, market analysis, and personalized investment advice.
            </p>
          </div>

          <div className="text-center p-6 bg-white rounded-lg shadow-sm">
            <Brain className="mx-auto h-12 w-12 text-indigo-600 mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">AI-Powered Analysis</h3>
            <p className="text-gray-600">
              Our advanced AI analyzes market data, news, and trends to provide intelligent stock recommendations tailored to your investment goals.
            </p>
          </div>

          <div className="text-center p-6 bg-white rounded-lg shadow-sm">
            <BarChart3 className="mx-auto h-12 w-12 text-indigo-600 mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Portfolio Performance</h3>
            <p className="text-gray-600">
              Track your previous portfolio recommendations and see exactly how much you would have gained or lost by following our AI's stock suggestions.
            </p>
          </div>
        </div>

        {/* CTA Section */}
        <div className="mt-12 sm:mt-16 text-center">
          <div className="bg-indigo-600 rounded-lg px-6 sm:px-8 py-8 sm:py-12">
            <h3 className="text-xl sm:text-2xl font-bold text-white mb-3 sm:mb-4">
              Ready to Start Your Investment Journey?
            </h3>
            <p className="text-sm sm:text-base text-indigo-100 mb-6 sm:mb-8 max-w-2xl mx-auto">
              Begin chatting with our AI-powered stock recommendation assistant.
              Get personalized insights, upload financial documents, and discover investment opportunities.
            </p>
            <button
              onClick={onStartChat}
              className="inline-flex items-center px-6 sm:px-8 py-2.5 sm:py-3 bg-white text-indigo-600 font-semibold rounded-md hover:bg-gray-100 transition-colors text-base sm:text-lg"
            >
              <MessageCircle className="h-5 w-5 sm:h-6 sm:w-6 mr-2 sm:mr-3" />
              Start Chat
            </button>
          </div>
        </div>

        {/* Additional Info */}
        <div className="mt-16 grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="bg-white p-6 rounded-lg shadow-sm">
            <h4 className="text-lg font-semibold text-gray-900 mb-3">How It Works</h4>
            <ul className="space-y-2 text-gray-600">
              <li className="flex items-start">
                <span className="text-indigo-600 font-bold mr-2">1.</span>
                Start a conversation with our AI assistant
              </li>
              <li className="flex items-start">
                <span className="text-indigo-600 font-bold mr-2">2.</span>
                Share your investment goals and preferences
              </li>
              <li className="flex items-start">
                <span className="text-indigo-600 font-bold mr-2">3.</span>
                Upload financial documents for detailed analysis
              </li>
              <li className="flex items-start">
                <span className="text-indigo-600 font-bold mr-2">4.</span>
                Receive personalized stock recommendations
              </li>
            </ul>
          </div>
          
          <div className="bg-white p-6 rounded-lg shadow-sm">
            <h4 className="text-lg font-semibold text-gray-900 mb-3">Features</h4>
            <ul className="space-y-2 text-gray-600">
              <li>✓ Real-time market analysis</li>
              <li>✓ Document upload and analysis</li>
              <li>✓ Personalized recommendations</li>
              <li>✓ Previous portfolio performance tracking</li>
              <li>✓ Gain/loss analysis on past recommendations</li>
              <li>✓ Risk assessment tools</li>
              <li>✓ Portfolio optimization suggestions</li>
              <li>✓ Market trend insights</li>
            </ul>
          </div>
        </div>
          </>
        )}
      </div>
    </div>
  );
};

export default MainPage;