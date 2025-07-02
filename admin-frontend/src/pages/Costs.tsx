import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '../lib/api';
import { 
  DollarSign, 
  TrendingUp, 
  TrendingDown,
  Calendar,
  Server,
  Database,
  HardDrive,
  Cpu,
  Cloud,
  AlertCircle
} from 'lucide-react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';

const COLORS = ['#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

export function Costs() {
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | '90d'>('30d');
  const [view, setView] = useState<'overview' | 'services' | 'trends'>('overview');

  const { data: costData, isLoading } = useQuery({
    queryKey: ['costs', timeRange],
    queryFn: async () => {
      const response = await adminApi.getCosts(timeRange);
      return response.data;
    },
    refetchInterval: 300000, // Refresh every 5 minutes
  });

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const getChangeIcon = (change: number) => {
    if (change > 0) {
      return <TrendingUp className="h-4 w-4 text-red-500" />;
    } else if (change < 0) {
      return <TrendingDown className="h-4 w-4 text-green-500" />;
    }
    return null;
  };

  const getServiceIcon = (service: string) => {
    const icons: Record<string, React.ReactElement> = {
      'EC2': <Server className="h-5 w-5" />,
      'RDS': <Database className="h-5 w-5" />,
      'S3': <HardDrive className="h-5 w-5" />,
      'SageMaker': <Cpu className="h-5 w-5" />,
      'CloudFront': <Cloud className="h-5 w-5" />,
    };
    return icons[service] || <Server className="h-5 w-5" />;
  };

  if (isLoading) {
    return <div>Loading cost data...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold text-gray-900">AWS Costs</h1>
        <div className="flex items-center space-x-4">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value as '7d' | '30d' | '90d')}
            className="px-3 py-1 border border-gray-300 rounded-md text-sm"
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>
        </div>
      </div>

      {/* Cost Summary Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <DollarSign className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Current Month
                  </dt>
                  <dd className="flex items-baseline">
                    <div className="text-2xl font-semibold text-gray-900">
                      {formatCurrency(costData?.currentMonth?.total || 0)}
                    </div>
                    {costData?.currentMonth?.change && (
                      <div className="ml-2 flex items-baseline text-sm">
                        {getChangeIcon(costData.currentMonth.change)}
                        <span className={costData.currentMonth.change > 0 ? 'text-red-600' : 'text-green-600'}>
                          {Math.abs(costData.currentMonth.change).toFixed(1)}%
                        </span>
                      </div>
                    )}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Calendar className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Today's Cost
                  </dt>
                  <dd className="flex items-baseline">
                    <div className="text-2xl font-semibold text-gray-900">
                      {formatCurrency(costData?.today?.total || 0)}
                    </div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <TrendingUp className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Projected Month
                  </dt>
                  <dd className="flex items-baseline">
                    <div className="text-2xl font-semibold text-gray-900">
                      {formatCurrency(costData?.projected?.total || 0)}
                    </div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <AlertCircle className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Budget Status
                  </dt>
                  <dd className="flex items-baseline">
                    <div className="text-sm">
                      <span className="text-2xl font-semibold text-gray-900">
                        {costData?.budgetUtilization || 0}%
                      </span>
                      <span className="text-gray-500 ml-2">
                        of ${costData?.monthlyBudget || 5000}
                      </span>
                    </div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white shadow rounded-lg">
        <div className="border-b border-gray-200">
          <nav className="-mb-px flex">
            <button
              onClick={() => setView('overview')}
              className={`py-2 px-4 border-b-2 font-medium text-sm ${
                view === 'overview'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Overview
            </button>
            <button
              onClick={() => setView('services')}
              className={`py-2 px-4 border-b-2 font-medium text-sm ${
                view === 'services'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              By Service
            </button>
            <button
              onClick={() => setView('trends')}
              className={`py-2 px-4 border-b-2 font-medium text-sm ${
                view === 'trends'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Trends
            </button>
          </nav>
        </div>

        <div className="p-6">
          {view === 'overview' && (
            <div>
              <h3 className="text-lg font-medium text-gray-900 mb-4">Daily Costs</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={costData?.dailyCosts || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis tickFormatter={(value) => `$${value}`} />
                    <Tooltip formatter={(value: number) => formatCurrency(value)} />
                    <Line 
                      type="monotone" 
                      dataKey="total" 
                      stroke="#0ea5e9" 
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {view === 'services' && (
            <div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div>
                  <h3 className="text-lg font-medium text-gray-900 mb-4">Cost by Service</h3>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={costData?.serviceBreakdown || []}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                          outerRadius={80}
                          fill="#8884d8"
                          dataKey="cost"
                        >
                          {(costData?.serviceBreakdown || []).map((_, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-medium text-gray-900 mb-4">Service Details</h3>
                  <div className="space-y-3">
                    {costData?.serviceBreakdown?.map((service) => (
                      <div key={service.name} className="flex items-center justify-between p-3 border rounded-lg">
                        <div className="flex items-center">
                          {getServiceIcon(service.name)}
                          <div className="ml-3">
                            <div className="text-sm font-medium text-gray-900">{service.name}</div>
                            <div className="text-sm text-gray-500">{service.description}</div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-medium text-gray-900">
                            {formatCurrency(service.cost)}
                          </div>
                          <div className="text-xs text-gray-500">
                            {service.change > 0 ? '+' : ''}{service.change.toFixed(1)}% vs last period
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {view === 'trends' && (
            <div>
              <h3 className="text-lg font-medium text-gray-900 mb-4">Monthly Trends</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={costData?.monthlyTrends || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="month" />
                    <YAxis tickFormatter={(value) => `$${value}`} />
                    <Tooltip formatter={(value: number) => formatCurrency(value)} />
                    <Legend />
                    <Bar dataKey="compute" stackId="a" fill="#0ea5e9" name="Compute (EC2, ECS)" />
                    <Bar dataKey="storage" stackId="a" fill="#10b981" name="Storage (S3, EBS)" />
                    <Bar dataKey="database" stackId="a" fill="#f59e0b" name="Database (RDS, DynamoDB)" />
                    <Bar dataKey="ml" stackId="a" fill="#8b5cf6" name="ML (SageMaker)" />
                    <Bar dataKey="other" stackId="a" fill="#6b7280" name="Other" />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {costData?.anomalies && costData.anomalies.length > 0 && (
                <div className="mt-6">
                  <h4 className="text-md font-medium text-gray-900 mb-3">Cost Anomalies</h4>
                  <div className="space-y-2">
                    {costData.anomalies.map((anomaly, index) => (
                      <div key={index} className="flex items-center p-3 bg-red-50 border border-red-200 rounded-lg">
                        <AlertCircle className="h-5 w-5 text-red-600 mr-3" />
                        <div>
                          <div className="text-sm font-medium text-red-900">{anomaly.service}</div>
                          <div className="text-sm text-red-700">
                            {anomaly.description} - {formatCurrency(anomaly.amount)} on {anomaly.date}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}