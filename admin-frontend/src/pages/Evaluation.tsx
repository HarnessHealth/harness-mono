import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { adminApi } from '../lib/api';
import { 
  FlaskConical, 
  Play, 
  CheckCircle, 
  TrendingUp
} from 'lucide-react';

export function Evaluation() {
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [selectedBenchmarks, setSelectedBenchmarks] = useState<string[]>([]);
  const [activeRun, setActiveRun] = useState<string | null>(null);
  const [runProgress, setRunProgress] = useState<Record<string, number>>({});

  const { data: models } = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const response = await adminApi.getModels();
      return response.data;
    },
  });

  const { data: benchmarks } = useQuery({
    queryKey: ['benchmarks'],
    queryFn: async () => {
      const response = await adminApi.getBenchmarks();
      return response.data;
    },
  });

  const runEvaluation = useMutation({
    mutationFn: async () => {
      const response = await adminApi.runEvaluation({
        model_id: selectedModel,
        benchmarks: selectedBenchmarks,
        batch_size: 8,
        temperature: 0.1,
      });
      return response.data;
    },
    onSuccess: (data) => {
      setActiveRun(data.id);
      // Start streaming progress
      const eventSource = adminApi.streamEvaluationProgress(data.id);
      
      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'progress') {
          setRunProgress(data.data.progress);
        } else if (data.type === 'complete') {
          eventSource.close();
          setActiveRun(null);
          // Refresh evaluation runs
        }
      };
      
      eventSource.onerror = () => {
        eventSource.close();
        setActiveRun(null);
      };
    },
  });

  const toggleBenchmark = (benchmarkId: string) => {
    setSelectedBenchmarks(prev => 
      prev.includes(benchmarkId)
        ? prev.filter(id => id !== benchmarkId)
        : [...prev, benchmarkId]
    );
  };

  const canRunEvaluation = selectedModel && selectedBenchmarks.length > 0 && !activeRun;

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-8">Model Evaluation</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Configuration */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Configure Evaluation</h2>
          
          {/* Model Selection */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select Model
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Choose a model...</option>
              {models?.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name} (v{model.version})
                </option>
              ))}
            </select>
          </div>

          {/* Benchmark Selection */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select Benchmarks
            </label>
            <div className="space-y-2">
              {benchmarks?.map((benchmark: any) => (
                <label
                  key={benchmark.id}
                  className="flex items-start p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
                >
                  <input
                    type="checkbox"
                    checked={selectedBenchmarks.includes(benchmark.id)}
                    onChange={() => toggleBenchmark(benchmark.id)}
                    className="mt-0.5 h-4 w-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                  />
                  <div className="ml-3">
                    <div className="text-sm font-medium text-gray-900">
                      {benchmark.name}
                    </div>
                    <div className="text-sm text-gray-500">
                      {benchmark.description} • {benchmark.question_count} questions
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Run Button */}
          <button
            onClick={() => runEvaluation.mutate()}
            disabled={!canRunEvaluation}
            className="w-full inline-flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play className="h-4 w-4 mr-2" />
            {activeRun ? 'Evaluation Running...' : 'Run Evaluation'}
          </button>
        </div>

        {/* Progress/Results */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">
            {activeRun ? 'Evaluation Progress' : 'Recent Results'}
          </h2>
          
          {activeRun ? (
            <div className="space-y-4">
              {Object.entries(runProgress).map(([benchmark, progress]) => (
                <div key={benchmark}>
                  <div className="flex justify-between text-sm text-gray-700 mb-1">
                    <span>{benchmark}</span>
                    <span>{Math.round(progress)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-primary-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <FlaskConical className="h-12 w-12 mx-auto mb-3 text-gray-400" />
              <p>No active evaluation</p>
              <p className="text-sm mt-1">Configure and run an evaluation to see progress</p>
            </div>
          )}
        </div>
      </div>

      {/* Results History */}
      <div className="mt-8 bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
            Evaluation History
          </h3>
          
          <div className="overflow-hidden shadow ring-1 ring-black ring-opacity-5 md:rounded-lg">
            <table className="min-w-full divide-y divide-gray-300">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Benchmarks
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    NAVLE Score
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    MedGemma Veterinary v2
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    NAVLE, VetQA-1000, Clinical Cases
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <span className="text-sm font-medium text-gray-900">89%</span>
                      <TrendingUp className="h-4 w-4 ml-1 text-green-500" />
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      <CheckCircle className="h-3 w-3 mr-1" />
                      Completed
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    2 hours ago
                  </td>
                </tr>
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    MedGemma Veterinary v1
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    NAVLE, Safety
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <span className="text-sm font-medium text-gray-900">87%</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      <CheckCircle className="h-3 w-3 mr-1" />
                      Completed
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    Yesterday
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}