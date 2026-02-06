export interface User {
  id: string;
  email: string;
  name: string;
  contactNumber: string;
  countryCode: string;
  uploadFile: boolean;
  paid_user: boolean;
  createdAt: Date;
}

export interface Message {
  id: string;
  text: string;
  userId: string;
  userName: string;
  timestamp: Date;
  fileUrl?: string;
  fileName?: string;
}

export interface CountryCode {
  code: string;
  name: string;
  dialCode: string;
}

export interface ChatSession {
  session_id: string;
  user_id: string;
}

export interface StockPerformance {
  ticker: string;
  recommendation?: 'BUY' | 'SELL' | 'HOLD';
  conviction_level?: string;
  entry_price: number;
  current_price?: number;
  price_change?: number;
  price_change_percentage?: number;
  number_of_shares?: number;
  investment_amount: number;
  shares?: number; // Legacy field for backward compatibility
  current_value?: number;
  profit_loss?: number;
  profit_loss_percentage?: number;
  status: 'profit' | 'loss' | 'neutral' | 'too_recent' | 'error';
  error?: string;
}

export interface OverallPerformance {
  total_investment: number;
  current_value?: number;
  total_current_value?: number; // New field from latest endpoint
  total_profit_loss?: number; // New field from latest endpoint
  profit_loss?: number;
  profit_loss_percentage?: number;
  total_profit_loss_percentage?: number; // New field from latest endpoint
  status: 'profit' | 'loss' | 'too_recent' | 'no_recommendations';
  message?: string;
}

export interface PortfolioPerformanceData {
  user_id?: string; // New field from latest endpoint
  overall_performance: OverallPerformance;
  stocks: StockPerformance[];
  recommendation_date: string;
  session_id?: string;
  is_too_recent?: boolean;
  hours_since_recommendation?: number;
  days_since_recommendation?: number;
  message?: string;
}
