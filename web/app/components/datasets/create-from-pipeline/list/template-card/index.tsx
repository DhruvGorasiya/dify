import React, { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Modal from '@/app/components/base/modal'
import EditPipelineInfo from './edit-pipeline-info'
import type { PipelineTemplate } from '@/models/pipeline'
import Confirm from '@/app/components/base/confirm'
import {
  PipelineTemplateListQueryKeyPrefix,
  useDeleteTemplate,
  useExportTemplateDSL,
  usePipelineTemplateById,
} from '@/service/use-pipeline'
import { downloadFile } from '@/utils/format'
import Toast from '@/app/components/base/toast'
import { usePluginDependencies } from '@/app/components/workflow/plugin-dependency/hooks'
import { useRouter } from 'next/navigation'
import Details from './details'
import Content from './content'
import Actions from './actions'
import type { CreateDatasetReq } from '@/models/datasets'
import { useCreatePipelineDatasetFromCustomized } from '@/service/knowledge/use-create-dataset'
import CreateModal from './create-modal'
import { useInvalid } from '@/service/use-base'
import { useResetDatasetList } from '@/service/knowledge/use-dataset'

type TemplateCardProps = {
  pipeline: PipelineTemplate
  showMoreOperations?: boolean
  type: 'customized' | 'built-in'
}

const TemplateCard = ({
  pipeline,
  showMoreOperations = true,
  type,
}: TemplateCardProps) => {
  const { t } = useTranslation()
  const { push } = useRouter()
  const [showEditModal, setShowEditModal] = useState(false)
  const [showDeleteConfirm, setShowConfirmDelete] = useState(false)
  const [showDetailModal, setShowDetailModal] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)

  const { refetch: getPipelineTemplateInfo } = usePipelineTemplateById({
    template_id: pipeline.id,
    type,
  }, false)
  const { mutateAsync: createDataset } = useCreatePipelineDatasetFromCustomized()
  const { handleCheckPluginDependencies } = usePluginDependencies()
  const resetDatasetList = useResetDatasetList()

  const openCreateModal = useCallback(() => {
    setShowCreateModal(true)
  }, [])

  // todo: Directly create a pipeline dataset, no need to fill in the form
  const handleUseTemplate = useCallback(async (payload: Omit<CreateDatasetReq, 'yaml_content'>) => {
    const { data: pipelineTemplateInfo } = await getPipelineTemplateInfo()
    if (!pipelineTemplateInfo) {
      Toast.notify({
        type: 'error',
        message: t('datasetPipeline.creation.errorTip'),
      })
      return
    }
    const request = {
      ...payload,
      yaml_content: pipelineTemplateInfo.export_data,
    }
    await createDataset(request, {
      onSuccess: async (newDataset) => {
        Toast.notify({
          type: 'success',
          message: t('datasetPipeline.creation.successTip'),
        })
        resetDatasetList()
        if (newDataset.pipeline_id)
          await handleCheckPluginDependencies(newDataset.pipeline_id, true)
        setShowCreateModal(false)
        push(`/datasets/${newDataset.dataset_id}/pipeline`)
      },
      onError: () => {
        Toast.notify({
          type: 'error',
          message: t('datasetPipeline.creation.errorTip'),
        })
      },
    })
  }, [getPipelineTemplateInfo, createDataset, t, handleCheckPluginDependencies, push, resetDatasetList])

  const handleShowTemplateDetails = useCallback(() => {
    setShowDetailModal(true)
  }, [])

  const openEditModal = useCallback(() => {
    setShowEditModal(true)
  }, [])

  const closeEditModal = useCallback(() => {
    setShowEditModal(false)
  }, [])

  const closeDetailsModal = useCallback(() => {
    setShowDetailModal(false)
  }, [])

  const { mutateAsync: exportPipelineDSL, isPending: isExporting } = useExportTemplateDSL()

  const handleExportDSL = useCallback(async () => {
    if (isExporting) return
    await exportPipelineDSL(pipeline.id, {
      onSuccess: (res) => {
        const blob = new Blob([res.data], { type: 'application/yaml' })
        downloadFile({
          data: blob,
          fileName: `${pipeline.name}.yml`,
        })
        Toast.notify({
          type: 'success',
          message: t('datasetPipeline.exportDSL.successTip'),
        })
      },
      onError: () => {
        Toast.notify({
          type: 'error',
          message: t('datasetPipeline.exportDSL.errorTip'),
        })
      },
    })
  }, [t, isExporting, pipeline.id, pipeline.name, exportPipelineDSL])

  const handleDelete = useCallback(() => {
    setShowConfirmDelete(true)
  }, [])

  const onCancelDelete = useCallback(() => {
    setShowConfirmDelete(false)
  }, [])

  const { mutateAsync: deletePipeline } = useDeleteTemplate()
  const invalidCustomizedTemplateList = useInvalid([...PipelineTemplateListQueryKeyPrefix, 'customized'])

  const onConfirmDelete = useCallback(async () => {
    await deletePipeline(pipeline.id, {
      onSuccess: () => {
        invalidCustomizedTemplateList()
        setShowConfirmDelete(false)
      },
    })
  }, [pipeline.id, deletePipeline, invalidCustomizedTemplateList])

  return (
    <div className='group relative flex h-[132px] cursor-pointer flex-col rounded-xl border-[0.5px] border-components-panel-border bg-components-panel-on-panel-item-bg pb-3 shadow-xs shadow-shadow-shadow-3'>
      <Content
        name={pipeline.name}
        description={pipeline.description}
        iconInfo={pipeline.icon}
        chunkStructure={pipeline.chunk_structure}
      />
      <Actions
        onApplyTemplate={openCreateModal}
        handleShowTemplateDetails={handleShowTemplateDetails}
        showMoreOperations={showMoreOperations}
        openEditModal={openEditModal}
        handleExportDSL={handleExportDSL}
        handleDelete={handleDelete}
      />
      {showEditModal && (
        <Modal
          isShow={showEditModal}
          onClose={closeEditModal}
          className='max-w-[520px] p-0'
        >
          <EditPipelineInfo
            pipeline={pipeline}
            onClose={closeEditModal}
          />
        </Modal>
      )}
      {showDeleteConfirm && (
        <Confirm
          title={t('datasetPipeline.deletePipeline.title')}
          content={t('datasetPipeline.deletePipeline.content')}
          isShow={showDeleteConfirm}
          onConfirm={onConfirmDelete}
          onCancel={onCancelDelete}
        />
      )}
      {showDetailModal && (
        <Modal
          isShow={showDetailModal}
          onClose={closeDetailsModal}
          className='h-[calc(100vh-64px)] max-w-[1680px] rounded-3xl p-0'
        >
          <Details
            id={pipeline.id}
            type={type}
            onClose={closeDetailsModal}
            onApplyTemplate={openCreateModal}
          />
        </Modal>
      )}
      {showCreateModal && (
        <CreateModal
          show={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onCreate={handleUseTemplate}
        />
      )
      }
    </div>
  )
}

export default React.memo(TemplateCard)
