'use client'

import { useState } from 'react'
import type { ReactElement } from 'react'
import {
  RiCloseCircleFill,
  RiFilter3Line,
  RiPriceTag3Line,
} from '@remixicon/react'
import {
  PortalToFollowElem,
  PortalToFollowElemContent,
  PortalToFollowElemTrigger,
} from '@/app/components/base/portal-to-follow-elem'
import Checkbox from '@/app/components/base/checkbox'
import cn from '@/utils/classnames'
import Input from '@/app/components/base/input'
import { useTags } from '@/app/components/plugins/hooks'
import { useMixedTranslation } from '@/app/components/plugins/marketplace/hooks'

type TagsFilterProps = {
  tags: string[]
  onTagsChange: (tags: string[]) => void
  size: 'small' | 'large'
  locale?: string
  emptyTrigger?: ReactElement
  className?: string
  triggerClassName?: string
}
const TagsFilter = ({
  tags,
  onTagsChange,
  size,
  locale,
  emptyTrigger,
  className,
  triggerClassName,
}: TagsFilterProps) => {
  const { t } = useMixedTranslation(locale)
  const [open, setOpen] = useState(false)
  const [searchText, setSearchText] = useState('')
  const { tags: options, tagsMap } = useTags(t)
  const filteredOptions = options.filter(option => option.label.toLowerCase().includes(searchText.toLowerCase()))
  const handleCheck = (id: string) => {
    if (tags.includes(id))
      onTagsChange(tags.filter((tag: string) => tag !== id))
    else
      onTagsChange([...tags, id])
  }
  const selectedTagsLength = tags.length

  return (
    <PortalToFollowElem
      placement='bottom-start'
      offset={{
        mainAxis: 4,
        crossAxis: -6,
      }}
      open={open}
      onOpenChange={setOpen}
    >
      <PortalToFollowElemTrigger
        className='shrink-0'
        onClick={() => setOpen(v => !v)}
      >
        <div className={cn(
          'ml-0.5 mr-1.5 flex  select-none items-center text-text-tertiary',
          size === 'large' && 'h-8 py-1',
          size === 'small' && 'h-7 py-0.5 ',
          className,
        )}>
          {
            !emptyTrigger && (
              <div className='p-0.5'>
                <RiFilter3Line className='h-4 w-4' />
              </div>
            )
          }
          <div className={cn(
            'system-sm-medium flex items-center p-1',
            size === 'large' && 'p-1',
            size === 'small' && 'px-0.5 py-1',
            triggerClassName,
          )}>
            {
              !selectedTagsLength && (emptyTrigger || t('pluginTags.allTags'))
            }
            {
              !!selectedTagsLength && tags.map(tag => tagsMap[tag].label).slice(0, 2).join(',')
            }
            {
              selectedTagsLength > 2 && (
                <div className='system-xs-medium ml-1 text-text-tertiary'>
                  +{selectedTagsLength - 2}
                </div>
              )
            }
          </div>
          {
            !!selectedTagsLength && (
              <RiCloseCircleFill
                className='h-4 w-4 cursor-pointer text-text-quaternary'
                onClick={() => onTagsChange([])}
              />
            )
          }
          {
            !selectedTagsLength && !emptyTrigger && (
              <div className='cursor-pointer rounded-md p-0.5 hover:bg-state-base-hover'>
                <RiPriceTag3Line className='h-4 w-4 text-text-tertiary' />
              </div>
            )
          }
        </div>
      </PortalToFollowElemTrigger>
      <PortalToFollowElemContent className='z-[1000]'>
        <div className='w-[240px] rounded-xl border-[0.5px] border-components-panel-border bg-components-panel-bg-blur shadow-lg backdrop-blur-sm'>
          <div className='p-2 pb-1'>
            <Input
              showLeftIcon
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              placeholder={t('pluginTags.searchTags') || ''}
            />
          </div>
          <div className='max-h-[448px] overflow-y-auto p-1'>
            {
              filteredOptions.map(option => (
                <div
                  key={option.name}
                  className='flex h-7 cursor-pointer select-none items-center rounded-lg px-2 py-1.5 hover:bg-state-base-hover'
                  onClick={() => handleCheck(option.name)}
                >
                  <Checkbox
                    className='mr-1'
                    checked={tags.includes(option.name)}
                  />
                  <div className='system-sm-medium px-1 text-text-secondary'>
                    {option.label}
                  </div>
                </div>
              ))
            }
          </div>
        </div>
      </PortalToFollowElemContent>
    </PortalToFollowElem>
  )
}

export default TagsFilter
