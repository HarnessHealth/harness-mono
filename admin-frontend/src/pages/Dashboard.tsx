import { useQuery } from '@tanstack/react-query';
import { adminApi } from '../lib/api';
import { 
  Brain, 
  FileText, 
  CheckCircle, 
  AlertCircle,
  Clock,
  TrendingUp
} from 'lucide-react';

export function Dashboard() {
  const { data: models } = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const response = await adminApi.getModels();
      return response.data;
    },
  });

  const { data: paperStats } = useQuery({
    queryKey: ['paper-stats'],
    queryFn: async () => {
      const response = await adminApi.getPaperStats();
      return response.data;
    },
  });

  const { data: health } = useQuery({
    queryKey: ['system-health'],
    queryFn: async () => {
      const response = await adminApi.getSystemHealth();
      return response.data;
    },
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const deployedModels = models?.filter(m => m.status === 'deployed').length || 0;
  const totalModels = models?.length || 0;

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-8">Dashboard</h1>
      
      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Brain className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Deployed Models
                  </dt>
                  <dd className="flex items-baseline">
                    <div className="text-2xl font-semibold text-gray-900">
                      {deployedModels}/{totalModels}
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
                <FileText className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Total Papers
                  </dt>
                  <dd className="flex items-baseline">
                    <div className="text-2xl font-semibold text-gray-900">
                      {paperStats?.total_papers.toLocaleString() || 0}
                    </div>
                    <div className="ml-2 flex items-baseline text-sm font-semibold text-green-600">
                      <TrendingUp className="h-4 w-4 mr-1" />
                      {paperStats?.last_24h_acquired || 0} today
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
                <Clock className="h-6 w-6 text-primary-600" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    Processing Queue
                  </dt>
                  <dd className="flex items-baseline">
                    <div className="text-2xl font-semibold text-gray-900">
                      {paperStats?.processing_queue_size || 0}
                    </div>
                    <div className="ml-2 flex items-baseline text-sm font-semibold text-red-600">
                      {paperStats?.failed_papers || 0} failed
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
                {health?.overall_status === 'healthy' ? (
                  <CheckCircle className="h-6 w-6 text-green-600" />
                ) : (
                  <AlertCircle className="h-6 w-6 text-red-600" />
                )}
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">
                    System Status
                  </dt>
                  <dd className="flex items-baseline">
                    <div className={`text-2xl font-semibold capitalize ${
                      health?.overall_status === 'healthy' ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {health?.overall_status || 'Unknown'}
                    </div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
            Papers by Source
          </h3>
          <div className="space-y-3">
            {paperStats && Object.entries(paperStats.papers_by_source).map(([source, count]) => (
              <div key={source} className="flex items-center justify-between">
                <div className="flex items-center">
                  <span className="text-sm font-medium text-gray-900">{source}</span>
                </div>
                <div className="flex items-center">
                  <span className="text-sm text-gray-500">{count.toLocaleString()} papers</span>
                  <div className="ml-4 w-32 bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-primary-600 h-2 rounded-full" 
                      style={{ 
                        width: `${(count / paperStats.total_papers) * 100}%` 
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}