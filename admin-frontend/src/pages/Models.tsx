import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminApi, type ModelInfo } from '../lib/api';
import { 
  Brain, 
  CheckCircle, 
  XCircle, 
  Clock,
  Rocket,
  RotateCcw,
  TrendingUp
} from 'lucide-react';

export function Models() {
  const queryClient = useQueryClient();
  const [selectedModel, setSelectedModel] = useState<ModelInfo | null>(null);
  const [showDeployDialog, setShowDeployDialog] = useState(false);

  const { data: models, isLoading } = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const response = await adminApi.getModels();
      return response.data;
    },
  });

  const deployMutation = useMutation({
    mutationFn: async (modelId: string) => {
      return adminApi.deployModel(modelId, {
        environment: 'production',
        replicas: 2,
        gpu_type: 'nvidia-l4',
        auto_scale: true,
        rollback_on_failure: true,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] });
      setShowDeployDialog(false);
      setSelectedModel(null);
    },
  });

  const getStatusIcon = (status: ModelInfo['status']) => {
    switch (status) {
      case 'deployed':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />;
      case 'training':
      case 'validating':
        return <Clock className="h-5 w-5 text-yellow-500" />;
      default:
        return <Brain className="h-5 w-5 text-gray-500" />;
    }
  };

  const getStatusColor = (status: ModelInfo['status']) => {
    switch (status) {
      case 'deployed':
        return 'bg-green-100 text-green-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'training':
      case 'validating':
        return 'bg-yellow-100 text-yellow-800';
      case 'ready':
        return 'bg-blue-100 text-blue-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  if (isLoading) {
    return <div>Loading models...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Models</h1>
      </div>

      <div className="bg-white shadow overflow-hidden sm:rounded-md">
        <ul className="divide-y divide-gray-200">
          {models?.map((model) => (
            <li key={model.id}>
              <div className="px-4 py-4 sm:px-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    {getStatusIcon(model.status)}
                    <div className="ml-4">
                      <div className="text-sm font-medium text-gray-900">
                        {model.name}
                      </div>
                      <div className="text-sm text-gray-500">
                        Version {model.version} • {model.base_model}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center space-x-4">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(model.status)}`}>
                      {model.status}
                    </span>
                    <div className="flex space-x-2">
                      {model.status === 'ready' && (
                        <button
                          onClick={() => {
                            setSelectedModel(model);
                            setShowDeployDialog(true);
                          }}
                          className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-white bg-primary-600 hover:bg-primary-700"
                        >
                          <Rocket className="h-3 w-3 mr-1" />
                          Deploy
                        </button>
                      )}
                      {model.status === 'deployed' && (
                        <button
                          onClick={() => {
                            if (confirm('Are you sure you want to rollback this model?')) {
                              adminApi.rollbackModel(model.id);
                              queryClient.invalidateQueries({ queryKey: ['models'] });
                            }
                          }}
                          className="inline-flex items-center px-3 py-1 border border-gray-300 text-xs font-medium rounded text-gray-700 bg-white hover:bg-gray-50"
                        >
                          <RotateCcw className="h-3 w-3 mr-1" />
                          Rollback
                        </button>
                      )}
                    </div>
                  </div>
                </div>
                
                <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">NAVLE Accuracy:</span>
                    <div className="flex items-center mt-1">
                      <span className="font-medium">{(model.performance_metrics.navle_accuracy * 100).toFixed(1)}%</span>
                      <TrendingUp className="h-3 w-3 ml-1 text-green-500" />
                    </div>
                  </div>
                  <div>
                    <span className="text-gray-500">VetQA F1:</span>
                    <div className="flex items-center mt-1">
                      <span className="font-medium">{(model.performance_metrics.vetqa_f1 * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                  <div>
                    <span className="text-gray-500">Training Data:</span>
                    <div className="flex items-center mt-1">
                      <span className="font-medium">{model.dataset_info.total_papers.toLocaleString()} papers</span>
                    </div>
                  </div>
                </div>

                {model.deployed_at && (
                  <div className="mt-2 text-xs text-gray-500">
                    Deployed {new Date(model.deployed_at).toLocaleDateString()} by {model.deployed_by}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* Deploy Dialog */}
      {showDeployDialog && selectedModel && (
        <div className="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg max-w-md w-full p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Deploy Model
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Are you sure you want to deploy {selectedModel.name} to production?
            </p>
            
            <div className="bg-gray-50 rounded p-4 mb-4">
              <h4 className="text-sm font-medium text-gray-900 mb-2">Deployment Configuration</h4>
              <ul className="text-sm text-gray-600 space-y-1">
                <li>• Environment: Production</li>
                <li>• Replicas: 2</li>
                <li>• GPU Type: NVIDIA L4</li>
                <li>• Auto-scaling: Enabled</li>
                <li>• Rollback on failure: Enabled</li>
              </ul>
            </div>

            <div className="flex justify-end space-x-3">
              <button
                onClick={() => {
                  setShowDeployDialog(false);
                  setSelectedModel(null);
                }}
                className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => deployMutation.mutate(selectedModel.id)}
                disabled={deployMutation.isPending}
                className="px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
              >
                {deployMutation.isPending ? 'Deploying...' : 'Deploy'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}