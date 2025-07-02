import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminApi, type PaperSource } from '../lib/api';
import { 
  FileText, 
  CheckCircle, 
  XCircle, 
  AlertCircle,
  RefreshCw,
  Clock,
  TrendingUp,
  Download
} from 'lucide-react';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts';

export function Papers() {
  const [selectedTab, setSelectedTab] = useState<'overview' | 'sources' | 'queue'>('overview');

  const { data: stats } = useQuery({
    queryKey: ['paper-stats'],
    queryFn: async () => {
      const response = await adminApi.getPaperStats();
      return response.data;
    },
    refetchInterval: 60000, // Refresh every minute
  });

  const { data: sources } = useQuery({
    queryKey: ['paper-sources'],
    queryFn: async () => {
      const response = await adminApi.getPaperSources();
      return response.data;
    },
    refetchInterval: 30000,
  });

  const { data: queue } = useQuery({
    queryKey: ['processing-queue'],
    queryFn: async () => {
      const response = await adminApi.getProcessingQueue(20);
      return response.data;
    },
    refetchInterval: 10000,
  });

  const getSourceStatusIcon = (source: PaperSource) => {
    switch (source.api_status) {
      case 'healthy':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'degraded':
        return <AlertCircle className="h-5 w-5 text-yellow-500" />;
      case 'down':
        return <XCircle className="h-5 w-5 text-red-500" />;
    }
  };

  const chartData = stats ? Object.entries(stats.papers_by_source).map(([name, count]) => ({
    name,
    count,
  })) : [];

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-8">Paper Acquisition</h1>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <FileText className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Total Papers
                  </dt>
                  <dd className="text-2xl font-semibold text-gray-900">
                    {stats?.total_papers.toLocaleString() || 0}
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
                <Clock className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Processing Queue
                  </dt>
                  <dd className="text-2xl font-semibold text-gray-900">
                    {stats?.processing_queue_size || 0}
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
                    Last 24h
                  </dt>
                  <dd className="text-2xl font-semibold text-gray-900">
                    +{stats?.last_24h_acquired || 0}
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
                <Download className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Storage Used
                  </dt>
                  <dd className="text-2xl font-semibold text-gray-900">
                    {stats?.storage_used_gb.toFixed(1) || 0} GB
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
              onClick={() => setSelectedTab('overview')}
              className={`py-2 px-4 border-b-2 font-medium text-sm ${
                selectedTab === 'overview'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Overview
            </button>
            <button
              onClick={() => setSelectedTab('sources')}
              className={`py-2 px-4 border-b-2 font-medium text-sm ${
                selectedTab === 'sources'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Sources
            </button>
            <button
              onClick={() => setSelectedTab('queue')}
              className={`py-2 px-4 border-b-2 font-medium text-sm ${
                selectedTab === 'queue'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Processing Queue
            </button>
          </nav>
        </div>

        <div className="p-6">
          {selectedTab === 'overview' && (
            <div>
              <h3 className="text-lg font-medium text-gray-900 mb-4">Papers by Source</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" fill="#0ea5e9" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {selectedTab === 'sources' && (
            <div className="space-y-4">
              {sources?.map((source) => (
                <div key={source.name} className="border rounded-lg p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center">
                      {getSourceStatusIcon(source)}
                      <div className="ml-3">
                        <h4 className="text-sm font-medium text-gray-900">{source.name}</h4>
                        <p className="text-sm text-gray-500">
                          {source.papers_acquired.toLocaleString()} papers acquired
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-4">
                      {source.rate_limit_remaining !== undefined && (
                        <span className="text-sm text-gray-500">
                          Rate limit: {source.rate_limit_remaining}
                        </span>
                      )}
                      <button
                        disabled={!source.enabled}
                        className="inline-flex items-center px-3 py-1 border border-gray-300 text-sm font-medium rounded text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                      >
                        <RefreshCw className="h-4 w-4 mr-1" />
                        Refresh
                      </button>
                    </div>
                  </div>
                  
                  {source.error_message && (
                    <div className="mt-2 bg-red-50 rounded p-2">
                      <p className="text-sm text-red-600">{source.error_message}</p>
                    </div>
                  )}
                  
                  <div className="mt-2 flex space-x-4 text-xs text-gray-500">
                    {source.last_crawl && (
                      <span>Last crawl: {new Date(source.last_crawl).toLocaleString()}</span>
                    )}
                    {source.error_count > 0 && (
                      <span className="text-red-600">{source.error_count} errors</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {selectedTab === 'queue' && (
            <div>
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-medium text-gray-900">
                  Processing Queue ({queue?.total || 0} items)
                </h3>
              </div>
              
              <div className="space-y-3">
                {queue?.papers.map((paper: any) => (
                  <div key={paper.id} className="border rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="text-sm font-medium text-gray-900">{paper.title}</h4>
                        <p className="text-sm text-gray-500">
                          Source: {paper.source} • Status: {paper.status}
                        </p>
                      </div>
                      {paper.status === 'failed' && (
                        <button
                          onClick={() => adminApi.retryPaper(paper.id)}
                          className="inline-flex items-center px-3 py-1 border border-gray-300 text-sm font-medium rounded text-gray-700 bg-white hover:bg-gray-50"
                        >
                          <RefreshCw className="h-4 w-4 mr-1" />
                          Retry
                        </button>
                      )}
                    </div>
                    {paper.error && (
                      <p className="mt-1 text-sm text-red-600">{paper.error}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}