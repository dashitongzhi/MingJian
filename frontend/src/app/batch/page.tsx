'use client';

import { useState } from 'react';
import { useTranslation } from '@/contexts/LanguageContext';

interface BatchTask {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  decision_id?: string;
}

interface BatchResponse {
  batch_id: string;
  tasks: BatchTask[];
  status: string;
}

export default function BatchPage() {
  const { t } = useTranslation();
  const [title, setTitle] = useState('');
  const [decisionPoint, setDecisionPoint] = useState('');
  const [proposals, setProposals] = useState([{ title: '', description: '' }]);
  const [result, setResult] = useState<BatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const addProposal = () => {
    setProposals([...proposals, { title: '', description: '' }]);
  };

  const removeProposal = (index: number) => {
    setProposals(proposals.filter((_, i) => i !== index));
  };

  const updateProposal = (index: number, field: 'title' | 'description', value: string) => {
    const updated = [...proposals];
    updated[index][field] = value;
    setProposals(updated);
  };

  const handleSubmit = async () => {
    if (!title.trim()) {
      setError(t('batch.titleRequired'));
      return;
    }
    if (!decisionPoint.trim()) {
      setError(t('batch.decisionPointRequired'));
      return;
    }
    const valid = proposals.filter(p => p.title.trim() && p.description.trim());
    if (valid.length < 1) {
      setError(t('batch.atLeastOneProposal'));
      return;
    }

    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${apiUrl}/batch/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          decision_point: decisionPoint,
          proposals: valid,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          {t('batch.title')}
        </h1>
        <p className="mt-1 text-gray-500 dark:text-gray-400">
          {t('batch.subtitle')}
        </p>
      </div>

      {/* 任务标题 */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
          {t('batch.batchTitle')}
        </label>
        <input
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder={t('batch.batchTitlePlaceholder')}
          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
        />
      </div>

      {/* 决策点 */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
          {t('batch.decisionPoint')}
        </label>
        <textarea
          value={decisionPoint}
          onChange={e => setDecisionPoint(e.target.value)}
          placeholder={t('batch.decisionPointPlaceholder')}
          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
          rows={3}
        />
      </div>

      {/* 方案列表 */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {t('batch.proposals')} ({proposals.length})
          </h2>
          <button
            onClick={addProposal}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
          >
            + {t('batch.addProposal')}
          </button>
        </div>
        <div className="space-y-4">
          {proposals.map((p, index) => (
            <div
              key={index}
              className="rounded-lg border border-gray-200 p-4 dark:border-gray-600"
            >
              <div className="mb-2 flex items-center justify-between">
                <input
                  value={p.title}
                  onChange={e => updateProposal(index, 'title', e.target.value)}
                  placeholder={t('batch.proposalTitlePlaceholder')}
                  className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
                {proposals.length > 1 && (
                  <button
                    onClick={() => removeProposal(index)}
                    className="ml-2 rounded-md px-2 py-1 text-sm text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                  >
                    {t('batch.removeProposal')}
                  </button>
                )}
              </div>
              <textarea
                value={p.description}
                onChange={e => updateProposal(index, 'description', e.target.value)}
                placeholder={t('batch.proposalDescriptionPlaceholder')}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                rows={3}
              />
            </div>
          ))}
        </div>
      </div>

      {/* 提交按钮 */}
      <div className="flex justify-end">
        <button
          onClick={handleSubmit}
          disabled={loading}
          className="rounded-lg bg-green-600 px-6 py-3 font-medium text-white shadow-sm hover:bg-green-700 disabled:opacity-50"
        >
          {loading ? t('batch.submitting') : t('batch.submit')}
        </button>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* 批量任务结果 */}
      {result && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-6 shadow-sm dark:border-green-800 dark:bg-green-900/20">
          <h2 className="mb-4 text-lg font-semibold text-green-800 dark:text-green-300">
            {t('batch.submitSuccess')}
          </h2>
          <div className="mb-3 text-sm text-green-700 dark:text-green-400">
            Batch ID: <span className="font-mono">{result.batch_id}</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {result.tasks.map(task => (
              <div
                key={task.id}
                className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-600 dark:bg-gray-800"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-gray-900 dark:text-white">{task.name}</span>
                  <StatusBadge status={task.status} />
                </div>
                {task.decision_id && (
                  <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    ID: {task.decision_id}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
    completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] || styles.pending}`}>
      {status}
    </span>
  );
}
