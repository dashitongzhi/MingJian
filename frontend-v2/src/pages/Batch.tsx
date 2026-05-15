import { Boxes, CheckCircle, Clock, Play, RefreshCw, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { LoadingSpinner } from '../components/ui/LoadingSpinner'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { batchApi } from '../api/endpoints'
import { useApi, useApiAction } from '../hooks/useApi'
import { ExpandableRecord, JsonBlock, MetricCard, asArray, asRecord, titleOf } from '../components/ui/DataSurface'

export default function Batch() {
  const { data: batches, loading, error, reload } = useApi(() => batchApi.list())
  const [selected, setSelected] = useState<string | null>(null)
  const { data: detail } = useApi(() => selected ? batchApi.get(selected) : Promise.resolve(null), [selected])
  const { data: tasks } = useApi(() => selected ? batchApi.tasks(selected) : Promise.resolve([]), [selected])
  const { execute: cancelBatch, loading: cancelling } = useApiAction((id: string) => batchApi.cancel(id))

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorBanner message={error} onRetry={reload} />

  const list = asArray(batches)
  const taskList = asArray(tasks)
  const completed = list.filter((item) => String(asRecord(item).status ?? '').toLowerCase().includes('completed'))
  const failed = list.filter((item) => String(asRecord(item).status ?? '').toLowerCase().includes('failed'))

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs text-blue-300">Batch</p>
          <h1 className="mt-1 text-3xl font-semibold text-slate-50">批处理任务</h1>
          <p className="mt-2 text-sm text-slate-500">展示批量辩论任务、子任务、状态计数和取消操作。</p>
        </div>
        <button onClick={reload} className="glass-button inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-slate-200"><RefreshCw className="h-4 w-4" />刷新</button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <MetricCard label="批任务" value={list.length} icon={<Boxes className="h-5 w-5" />} tone="blue" />
        <MetricCard label="已完成" value={completed.length} icon={<CheckCircle className="h-5 w-5" />} tone="emerald" />
        <MetricCard label="失败" value={failed.length} icon={<XCircle className="h-5 w-5" />} tone="red" />
        <MetricCard label="子任务" value={taskList.length} icon={<Clock className="h-5 w-5" />} tone="violet" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader title="批任务列表" />
          {list.length === 0 ? <CardBody><EmptyState icon="▣" title="暂无批任务" /></CardBody> : list.map((batch, index) => {
            const record = asRecord(batch)
            const id = String(record.id ?? '')
            return (
              <div key={id || index} className="border-b border-slate-800/50 px-5 py-4 last:border-b-0">
                <div className="flex items-start justify-between gap-4">
                  <button onClick={() => setSelected(id)} className="min-w-0 flex-1 text-left">
                    <p className="truncate text-sm font-medium text-slate-100">{titleOf(batch, `批任务 ${index + 1}`)}</p>
                    <p className="mt-1 truncate text-xs text-slate-600">{String(record.status ?? record.decision_point ?? '')}</p>
                  </button>
                  <button onClick={() => id && cancelBatch(id).then(reload)} disabled={!id || cancelling} className="rounded-md border border-red-400/20 bg-red-500/10 px-3 py-1.5 text-xs text-red-300 disabled:opacity-50">取消</button>
                </div>
              </div>
            )
          })}
        </Card>
        <Card>
          <CardHeader title={selected ? '批任务详情' : '子任务'} />
          {selected ? <CardBody><JsonBlock value={{ detail, tasks }} /></CardBody> : taskList.length === 0 ? <CardBody><EmptyState icon="▤" title="请选择一个批任务" /></CardBody> : taskList.map((task, index) => <ExpandableRecord key={index} item={task} eyebrow="task" />)}
        </Card>
      </div>

      <Card>
        <CardHeader title="提交批任务格式" action={<Play className="h-4 w-4 text-blue-300" />} />
        <CardBody><JsonBlock value={{ title: '方案对比', decision_point: '是否采用某战略方案', trigger_type: 'batch', proposals: [{ title: '方案 A', description: '...' }] }} /></CardBody>
      </Card>
    </div>
  )
}
