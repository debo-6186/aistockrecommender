import React, { useEffect, useState } from 'react';
import { apiService } from '../services/api';
import PortfolioPerformance from './PortfolioPerformance';
import { TrendingUp, AlertCircle, Calendar, DollarSign, List, BarChart3, X, Eye } from 'lucide-react';

interface PortfolioDashboardProps {
  userId: string;
}

interface Recommendation {
  session_id: string;
  created_at: string;
  total_investment: number;
  stock_count: number;
  stocks: string[];
  has_entry_prices: boolean;
  recommendation_date: string;
}

type TabType = 'recommendations' | 'performance';

const PortfolioDashboard: React.FC<PortfolioDashboardProps> = ({ userId }) => {
  const [activeTab, setActiveTab] = useState<TabType>('performance');
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedRecommendation, setSelectedRecommendation] = useState<any | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRecommendations = async () => {
      try {
        setLoading(true);
        setError(null);

        // Debug log
        console.log('[PortfolioDashboard] Fetching recommendations for userId:', userId);

        const data = await apiService.getUserRecommendations(userId);

        console.log('[PortfolioDashboard] Received data:', data);

        setRecommendations(data.recommendations || []);
      } catch (err: any) {
        console.error('[PortfolioDashboard] Error fetching recommendations:', err);
        setError(err.message || 'Failed to load recommendations');
      } finally {
        setLoading(false);
      }
    };

    if (userId) {
      fetchRecommendations();
    } else {
      console.error('[PortfolioDashboard] No userId provided!');
    }
  }, [userId]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const viewRecommendationDetails = async (sessionId: string) => {
    try {
      const headers = {
        'Authorization': `Bearer ${await (await import('../firebase')).auth.currentUser?.getIdToken()}`,
        'Content-Type': 'application/json'
      };

      const response = await fetch(`${process.env.REACT_APP_API_BASE_URL || 'http://localhost:10001/api'}/debug/user-recommendations/${userId}`, {
        headers
      });

      if (!response.ok) throw new Error('Failed to fetch recommendation details');

      const data = await response.json();
      setSelectedRecommendation(data.recommendation_data);
    } catch (err) {
      console.error('Error fetching recommendation details:', err);
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-8">
        <div className="flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
          <span className="ml-3 text-gray-600">Loading your portfolios...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <div className="flex items-center gap-2 text-red-800 mb-2">
          <AlertCircle className="w-5 h-5" />
          <p className="font-semibold">Error Loading Portfolios</p>
        </div>
        <p className="text-red-700 text-sm">{error}</p>
        <p className="text-red-600 text-xs mt-2">Your user ID: {userId}</p>
      </div>
    );
  }

  if (recommendations.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-md p-8 text-center">
        <TrendingUp className="mx-auto h-16 w-16 text-gray-400 mb-4" />
        <h3 className="text-xl font-semibold text-gray-900 mb-2">No Recommendations Yet</h3>
        <p className="text-gray-600 mb-4">
          Start a chat to get your first personalized stock recommendation!
        </p>
        <p className="text-xs text-gray-500">User ID: {userId}</p>
      </div>
    );
  }

  const tabs = [
    { id: 'performance' as TabType, label: 'Performance Tracker', icon: BarChart3 },
    { id: 'recommendations' as TabType, label: 'All Recommendations', icon: List },
  ];

  return (
    <div className="space-y-6">
      {/* Tab Navigation */}
      <div className="bg-white rounded-lg shadow-md">
        <div className="border-b border-gray-200 overflow-x-auto">
          <nav className="flex -mb-px min-w-full">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 sm:px-6 py-3 sm:py-4 text-xs sm:text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                    isActive
                      ? 'border-indigo-600 text-indigo-600'
                      : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
                  }`}
                >
                  <Icon className="w-4 h-4 sm:w-5 sm:h-5" />
                  <span className="hidden sm:inline">{tab.label}</span>
                  <span className="sm:hidden">{tab.id === 'performance' ? 'Performance' : 'All'}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Tab Content */}
        <div className="p-6">
          {/* Performance Tab */}
          {activeTab === 'performance' && (
            <div>
              <PortfolioPerformance userId={userId} />
            </div>
          )}

          {/* Recommendations List Tab */}
          {activeTab === 'recommendations' && (
            <div>
              <h2 className="text-2xl font-bold text-gray-900 mb-4">Your Portfolio Recommendations</h2>
              <p className="text-gray-600 mb-6">
                View all your historical stock recommendations
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {[...recommendations].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).map((rec) => (
                  <div
                    key={rec.session_id}
                    onClick={() => viewRecommendationDetails(rec.session_id)}
                    className="p-4 rounded-lg border-2 border-gray-200 bg-white hover:border-indigo-300 hover:shadow-md transition-all cursor-pointer group"
                  >
                    <div className="flex items-center gap-2 text-sm text-gray-600 mb-3">
                      <Calendar className="w-4 h-4" />
                      <span>{formatDate(rec.created_at)}</span>
                    </div>

                    <div className="flex items-center gap-2 mb-2">
                      <DollarSign className="w-5 h-5 text-green-600" />
                      <span className="text-lg font-bold text-gray-900">
                        ${rec.total_investment.toLocaleString()}
                      </span>
                    </div>

                    <div className="text-sm text-gray-600 mb-3">
                      {rec.stock_count} {rec.stock_count === 1 ? 'stock' : 'stocks'}
                    </div>

                    <div className="flex flex-wrap gap-1">
                      {rec.stocks.slice(0, 4).map((stock) => (
                        <span
                          key={stock}
                          className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded"
                        >
                          {stock}
                        </span>
                      ))}
                      {rec.stocks.length > 4 && (
                        <span className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">
                          +{rec.stocks.length - 4}
                        </span>
                      )}
                    </div>

                    {!rec.has_entry_prices && (
                      <div className="mt-3">
                        <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded">
                          ⚠️ No performance tracking
                        </span>
                      </div>
                    )}

                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <button className="flex items-center gap-1 text-sm text-indigo-600 group-hover:text-indigo-700 font-medium">
                        <Eye className="w-4 h-4" />
                        View Details
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommendation Details Modal */}
          {selectedRecommendation && (
            <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-0 sm:p-4 z-50">
              <div className="bg-white rounded-none sm:rounded-lg shadow-xl w-full sm:max-w-4xl h-full sm:h-auto sm:max-h-[90vh] overflow-y-auto">
                {/* Modal Header */}
                <div className="sticky top-0 bg-white border-b border-gray-200 p-4 sm:p-6 flex items-center justify-between">
                  <h2 className="text-lg sm:text-2xl font-bold text-gray-900">Portfolio Recommendation Details</h2>
                  <button
                    onClick={() => setSelectedRecommendation(null)}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors flex-shrink-0"
                  >
                    <X className="w-5 h-5 sm:w-6 sm:h-6 text-gray-600" />
                  </button>
                </div>

                {/* Modal Content */}
                <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
                  {/* Allocation Breakdown */}
                  {selectedRecommendation.allocation_breakdown && (
                    <section>
                      <h3 className="text-base sm:text-lg font-semibold text-gray-900 mb-3 sm:mb-4">Portfolio Allocation</h3>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {selectedRecommendation.allocation_breakdown.map((stock: any) => (
                          <div key={stock.ticker} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                            <div className="flex justify-between items-start mb-2">
                              <span className="font-semibold text-gray-900">{stock.ticker}</span>
                              <span className="text-sm bg-indigo-100 text-indigo-800 px-2 py-1 rounded">
                                {stock.percentage}
                              </span>
                            </div>
                            <div className="text-lg font-bold text-green-600">{stock.investment_amount}</div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Individual Stock Recommendations */}
                  {selectedRecommendation.individual_stock_recommendations && (
                    <section>
                      <h3 className="text-base sm:text-lg font-semibold text-gray-900 mb-3 sm:mb-4">Individual Stock Analysis</h3>
                      <div className="space-y-3">
                        {selectedRecommendation.individual_stock_recommendations.map((stock: any) => (
                          <div key={stock.ticker} className="bg-white border-2 border-gray-200 rounded-lg p-4">
                            <div className="flex items-start justify-between mb-3">
                              <div className="flex items-center gap-3">
                                <h4 className="text-lg font-semibold text-gray-900">{stock.ticker}</h4>
                                <span className={`inline-flex items-center px-3 py-1 text-sm font-semibold rounded ${
                                  stock.recommendation === 'BUY'
                                    ? 'bg-green-100 text-green-800'
                                    : stock.recommendation === 'SELL'
                                    ? 'bg-red-100 text-red-800'
                                    : 'bg-gray-100 text-gray-800'
                                }`}>
                                  {stock.recommendation}
                                </span>
                                {stock.conviction_level && stock.conviction_level !== 'N/A' && (
                                  <span className="text-sm bg-blue-100 text-blue-800 px-2 py-1 rounded">
                                    {stock.conviction_level} Conviction
                                  </span>
                                )}
                              </div>
                              <div className="text-right">
                                <div className="text-sm text-gray-600">Investment</div>
                                <div className="text-lg font-bold text-gray-900">{stock.investment_amount}</div>
                              </div>
                            </div>

                            {stock.entry_price && (
                              <div className="mb-3 text-sm">
                                <span className="text-gray-600">Entry Price: </span>
                                <span className="font-semibold text-gray-900">{stock.entry_price}</span>
                              </div>
                            )}

                            {stock.key_metrics && (
                              <div className="mb-3 p-3 bg-gray-50 rounded-lg">
                                <div className="text-xs text-gray-600 mb-1">Key Metrics</div>
                                <div className="text-sm text-gray-800">{stock.key_metrics}</div>
                              </div>
                            )}

                            {stock.reasoning && (
                              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                                <div className="text-xs text-blue-900 font-semibold mb-1">Analysis</div>
                                <div className="text-sm text-blue-800">{stock.reasoning}</div>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Risk Warnings */}
                  {selectedRecommendation.risk_warnings && selectedRecommendation.risk_warnings.length > 0 && (
                    <section>
                      <h3 className="text-base sm:text-lg font-semibold text-red-900 mb-3 sm:mb-4">⚠️ Risk Warnings</h3>
                      <div className="space-y-2">
                        {selectedRecommendation.risk_warnings.map((warning: string, index: number) => (
                          <div key={index} className="bg-red-50 border border-red-200 rounded-lg p-4">
                            <p className="text-sm text-red-800">{warning}</p>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Entry Prices */}
                  {selectedRecommendation.entry_prices && Object.keys(selectedRecommendation.entry_prices).length > 0 && (
                    <section>
                      <h3 className="text-base sm:text-lg font-semibold text-gray-900 mb-3 sm:mb-4">Entry Prices at Recommendation</h3>
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 sm:gap-3">
                        {Object.entries(selectedRecommendation.entry_prices).map(([ticker, price]) => (
                          <div key={ticker} className="bg-gray-50 rounded-lg p-3 text-center border border-gray-200">
                            <div className="text-sm text-gray-600 mb-1">{ticker}</div>
                            <div className="text-lg font-bold text-gray-900">${(price as number).toFixed(2)}</div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}
                </div>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
};

export default PortfolioDashboard;
