import React, { useEffect, useState } from 'react';
import { apiService } from '../services/api';
import { PortfolioPerformanceData } from '../types';
import { TrendingUp, TrendingDown, Clock, AlertCircle, RefreshCw } from 'lucide-react';

interface PortfolioPerformanceProps {
  userId: string;
}

const PortfolioPerformance: React.FC<PortfolioPerformanceProps> = ({ userId }) => {
  const [performanceData, setPerformanceData] = useState<PortfolioPerformanceData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPerformance = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiService.getUserPortfolioPerformance(userId);
      setPerformanceData(data);
    } catch (err: any) {
      console.error('Error fetching portfolio performance:', err);
      if (err.message?.includes('404') || err.message?.includes('No stock recommendations')) {
        setError('No portfolio recommendations found. Please get a recommendation first.');
      } else {
        setError(err.message || 'Failed to load portfolio performance');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (userId) {
      fetchPerformance();
    }
  }, [userId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 m-4">
        <div className="flex items-center gap-2 text-red-800">
          <AlertCircle className="w-5 h-5" />
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (!performanceData) {
    return null;
  }

  const { overall_performance, stocks, message, session_id } = performanceData;

  // Handle "no recommendations" state
  if (overall_performance.status === 'no_recommendations' || (stocks && stocks.length === 0)) {
    return (
      <div className="bg-white rounded-lg shadow-md p-4 sm:p-6 m-2 sm:m-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-0 mb-4">
          <div className="flex items-center gap-2 sm:gap-3 text-gray-600">
            <AlertCircle className="w-5 h-5 sm:w-6 sm:h-6" />
            <h2 className="text-lg sm:text-xl font-semibold">Portfolio Performance</h2>
          </div>
          <button
            onClick={fetchPerformance}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-blue-800 text-sm">
            {message || 'No portfolio recommendations found. Get a recommendation first to see performance tracking!'}
          </p>
        </div>
      </div>
    );
  }

  // Handle normal state with performance data
  const isProfit = overall_performance.status === 'profit';
  const OverallIcon = isProfit ? TrendingUp : TrendingDown;

  const overallColorClasses = {
    icon: isProfit ? 'text-green-600' : 'text-red-600',
    bg: isProfit ? 'bg-green-50' : 'bg-red-50',
    border: isProfit ? 'border-green-200' : 'border-red-200',
    text: isProfit ? 'text-green-700' : 'text-red-700',
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-4 sm:p-6 m-2 sm:m-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-0 mb-4 sm:mb-6">
        <div className="flex items-center gap-2 sm:gap-3">
          <OverallIcon className={`w-5 h-5 sm:w-6 sm:h-6 ${overallColorClasses.icon}`} />
          <h2 className="text-lg sm:text-xl font-semibold">Portfolio Performance</h2>
        </div>
        <button
          onClick={fetchPerformance}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Overall Performance Card */}
      <div className={`${overallColorClasses.bg} border-2 ${overallColorClasses.border} rounded-lg p-4 sm:p-6 mb-4 sm:mb-6`}>
        <h3 className="text-sm font-semibold text-gray-700 mb-3 sm:mb-4">Overall Performance</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
          <div>
            <p className="text-xs sm:text-sm text-gray-600 mb-1">Investment</p>
            <p className="text-lg sm:text-xl font-bold text-gray-900">
              ${overall_performance.total_investment.toLocaleString()}
            </p>
          </div>
          <div>
            <p className="text-xs sm:text-sm text-gray-600 mb-1">Current Value</p>
            <p className="text-lg sm:text-xl font-bold text-gray-900">
              ${(overall_performance.total_current_value || overall_performance.current_value || 0).toLocaleString()}
            </p>
          </div>
          <div>
            <p className={`text-xs sm:text-sm ${overallColorClasses.text} mb-1`}>
              {isProfit ? 'Profit' : 'Loss'}
            </p>
            <p className={`text-lg sm:text-xl font-bold ${overallColorClasses.text}`}>
              ${Math.abs(overall_performance.total_profit_loss || overall_performance.profit_loss || 0).toLocaleString()}
              <span className="text-sm sm:text-base ml-2">
                ({(overall_performance.total_profit_loss_percentage || overall_performance.profit_loss_percentage || 0).toFixed(2)}%)
              </span>
            </p>
          </div>
        </div>
      </div>

      {/* Individual Stocks */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Individual Stocks</h3>
        <div className="space-y-3">
          {stocks.map((stock) => {
            if (stock.status === 'error') {
              return (
                <div key={stock.ticker} className="bg-gray-50 rounded-lg p-4 border border-gray-300">
                  <div className="flex justify-between items-center">
                    <h4 className="font-semibold text-gray-900">{stock.ticker}</h4>
                    <span className="text-xs text-gray-500">{stock.error}</span>
                  </div>
                </div>
              );
            }

            const stockIsProfit = stock.status === 'profit';
            const stockIsLoss = stock.status === 'loss';
            const stockIsNeutral = stock.status === 'neutral';

            const StockIcon = stockIsProfit ? TrendingUp : stockIsLoss ? TrendingDown : Clock;

            const stockColorClasses = {
              border: stockIsProfit ? 'border-green-500' : stockIsLoss ? 'border-red-500' : 'border-gray-400',
              icon: stockIsProfit ? 'text-green-600' : stockIsLoss ? 'text-red-600' : 'text-gray-600',
              text: stockIsProfit ? 'text-green-700' : stockIsLoss ? 'text-red-700' : 'text-gray-700',
            };

            return (
              <div
                key={stock.ticker}
                className={`bg-white rounded-lg p-4 border-l-4 ${stockColorClasses.border} shadow-sm hover:shadow-md transition-shadow`}
              >
                <div className="flex justify-between items-start mb-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="font-semibold text-gray-900 text-lg">{stock.ticker}</h4>
                      {stock.recommendation && (
                        <span className={`inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded ${
                          stock.recommendation === 'BUY'
                            ? 'bg-green-100 text-green-800'
                            : 'bg-red-100 text-red-800'
                        }`}>
                          {stock.recommendation}
                        </span>
                      )}
                      {stock.conviction_level && stock.conviction_level !== 'N/A' && (
                        <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded ${
                          stock.conviction_level === 'HIGH'
                            ? 'bg-blue-100 text-blue-800'
                            : stock.conviction_level === 'MEDIUM'
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {stock.conviction_level}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-600">
                      ${stock.entry_price.toFixed(2)} → ${stock.current_price?.toFixed(2)}
                      {stock.price_change !== undefined && (
                        <span className={`ml-2 text-xs ${stock.price_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          ({stock.price_change >= 0 ? '+' : ''}{stock.price_change.toFixed(2)} / {stock.price_change_percentage?.toFixed(2)}%)
                        </span>
                      )}
                    </p>
                  </div>
                  <StockIcon className={`w-5 h-5 ${stockColorClasses.icon}`} />
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-2 gap-3 sm:gap-4 text-xs sm:text-sm">
                  <div>
                    <p className="text-gray-600">Shares</p>
                    <p className="font-medium text-gray-900">{(stock.number_of_shares || stock.shares || 0).toFixed(4)}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Investment</p>
                    <p className="font-medium text-gray-900">${stock.investment_amount.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Current Value</p>
                    <p className="font-medium text-gray-900">${stock.current_value?.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className={`${stockColorClasses.text} font-medium`}>
                      {stockIsProfit ? 'Gain' : stockIsLoss ? 'Loss' : 'Status'}
                    </p>
                    <p className={`font-medium ${stockColorClasses.text}`}>
                      {stockIsNeutral ? (
                        <span className="text-xs">{stock.recommendation || 'HOLD'} - No investment</span>
                      ) : (
                        <>
                          ${Math.abs(stock.profit_loss || 0).toFixed(2)}
                          <span className="text-xs ml-1">
                            ({stock.profit_loss_percentage?.toFixed(2)}%)
                          </span>
                        </>
                      )}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer Info */}
      <div className="mt-6 pt-4 border-t border-gray-200">
        <p className="text-xs text-gray-500 text-center">
          Latest recommendation{session_id && ` (Session: ${session_id.substring(0, 8)}...)`}
        </p>
        <p className="text-xs text-gray-400 text-center mt-1">
          Data refreshed from live market prices
        </p>
      </div>
    </div>
  );
};

export default PortfolioPerformance;
