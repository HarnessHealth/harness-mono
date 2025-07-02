import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '../lib/api';
import { 
  Database, 
  HardDrive,
  Cpu,
  CheckCircle,
  XCircle,
  AlertCircle,
  GitBranch,
  Calendar
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

export function System() {
  const [metricsRange, setMetricsRange] = useState('1h');

  const { data: health } = useQuery({
    queryKey: ['system-health'],
    queryFn: async () => {
      const response = await adminApi.getSystemHealth();
      return response.data;
    },
    refetchInterval: 30000,
  });

  const { data: metrics } = useQuery({
    queryKey: ['system-metrics', metricsRange],
    queryFn: async () => {
      const response = await adminApi.getSystemMetrics(metricsRange);
      return response.data;
    },
    refetchInterval: 60000,
  });

  const { data: dags } = useQuery({
    queryKey: ['airflow-dags'],
    queryFn: async () => {
      const response = await adminApi.getAirflowDags();
      return response.data;
    },
  });

  const getStatusIcon = (status: boolean | string) => {
    if (status === true || status === 'healthy') {
      return <CheckCircle className="h-5 w-5 text-green-500" />;
    } else if (status === 'degraded') {
      return <AlertCircle className="h-5 w-5 text-yellow-500" />;
    } else {
      return <XCircle className="h-5 w-5 text-red-500" />;
    }
  };

  const getOverallStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-100 text-green-800';
      case 'degraded':
        return 'bg-yellow-100 text-yellow-800';
      case 'critical':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-8">System Health</h1>

      {/* Overall Status */}
      <div className="bg-white shadow rounded-lg p-6 mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-medium text-gray-900">Overall System Status</h2>
            <p className="text-sm text-gray-500 mt-1">
              Last updated: {health ? new Date(health.timestamp).toLocaleString() : 'Loading...'}
            </p>
          </div>
          <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium capitalize ${
            health ? getOverallStatusColor(health.overall_status) : 'bg-gray-100 text-gray-800'
          }`}>
            {health?.overall_status || 'Unknown'}
          </span>
        </div>
      </div>

      {/* Services Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6 mb-8">
        {/* Databases */}
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center mb-4">
            <Database className="h-6 w-6 text-primary-600 mr-2" />
            <h3 className="text-lg font-medium text-gray-900">Databases</h3>
          </div>
          <div className="space-y-3">
            {health?.database_status && Object.entries(health.database_status).map(([name, status]) => (
              <div key={name} className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700 capitalize">{name}</span>
                {getStatusIcon(status)}
              </div>
            ))}
          </div>
        </div>

        {/* Storage */}
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center mb-4">
            <HardDrive className="h-6 w-6 text-primary-600 mr-2" />
            <h3 className="text-lg font-medium text-gray-900">Storage</h3>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">S3 Connection</span>
              {getStatusIcon(health?.storage_status?.s3_connected || false)}
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-700">Storage Usage</span>
                <span className="text-gray-900 font-medium">
                  {health?.storage_status?.used_gb || 0} GB / {(health?.storage_status?.used_gb || 0) + (health?.storage_status?.available_gb || 0)} GB
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-primary-600 h-2 rounded-full"
                  style={{
                    width: `${((health?.storage_status?.used_gb || 0) / ((health?.storage_status?.used_gb || 0) + (health?.storage_status?.available_gb || 1))) * 100}%`
                  }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* GPU Status */}
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center mb-4">
            <Cpu className="h-6 w-6 text-primary-600 mr-2" />
            <h3 className="text-lg font-medium text-gray-900">GPU Status</h3>
          </div>
          {health?.gpu_status?.[0] && (
            <div className="space-y-3">
              <div className="text-sm">
                <div className="font-medium text-gray-900">{health.gpu_status[0].name}</div>
                <div className="text-gray-500">ID: {health.gpu_status[0].id}</div>
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-700">Memory</span>
                  <span className="text-gray-900 font-medium">
                    {health.gpu_status[0].memory_used_gb} / {health.gpu_status[0].memory_total_gb} GB
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-primary-600 h-2 rounded-full"
                    style={{
                      width: `${(health.gpu_status[0].memory_used_gb / health.gpu_status[0].memory_total_gb) * 100}%`
                    }}
                  />
                </div>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-700">Utilization</span>
                <span className="text-gray-900 font-medium">{health.gpu_status[0].utilization}%</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-700">Temperature</span>
                <span className="text-gray-900 font-medium">{health.gpu_status[0].temperature}°C</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Performance Metrics */}
      <div className="bg-white shadow rounded-lg p-6 mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">Performance Metrics</h3>
          <select
            value={metricsRange}
            onChange={(e) => setMetricsRange(e.target.value)}
            className="px-3 py-1 border border-gray-300 rounded-md text-sm"
          >
            <option value="1h">Last Hour</option>
            <option value="6h">Last 6 Hours</option>
            <option value="24h">Last 24 Hours</option>
            <option value="7d">Last 7 Days</option>
          </select>
        </div>
        
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-2">CPU Usage</h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={metrics?.resources?.cpu_usage || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" display="none" />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke="#0ea5e9" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-2">Memory Usage</h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={metrics?.resources?.memory_usage || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" display="none" />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke="#10b981" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-2">GPU Usage</h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={metrics?.resources?.gpu_usage || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" display="none" />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke="#f59e0b" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* Airflow DAGs */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex items-center mb-4">
          <GitBranch className="h-6 w-6 text-primary-600 mr-2" />
          <h3 className="text-lg font-medium text-gray-900">Airflow DAGs</h3>
        </div>
        
        <div className="space-y-4">
          {dags?.map((dag: any) => (
            <div key={dag.dag_id} className="border rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-medium text-gray-900">{dag.dag_id}</h4>
                  <p className="text-sm text-gray-500">{dag.description}</p>
                </div>
                <div className="flex items-center space-x-4">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    dag.last_run_state === 'success' ? 'bg-green-100 text-green-800' :
                    dag.last_run_state === 'running' ? 'bg-blue-100 text-blue-800' :
                    dag.last_run_state === 'failed' ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {dag.last_run_state || 'No runs'}
                  </span>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    dag.is_paused ? 'bg-gray-100 text-gray-800' : 'bg-green-100 text-green-800'
                  }`}>
                    {dag.is_paused ? 'Paused' : 'Active'}
                  </span>
                </div>
              </div>
              
              <div className="mt-2 flex space-x-4 text-xs text-gray-500">
                {dag.schedule_interval && (
                  <span className="flex items-center">
                    <Calendar className="h-3 w-3 mr-1" />
                    Schedule: {dag.schedule_interval}
                  </span>
                )}
                {dag.next_run && (
                  <span>Next run: {new Date(dag.next_run).toLocaleString()}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}