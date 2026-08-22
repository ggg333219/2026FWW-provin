import { describe, expect, it } from 'vitest'
import { buildIntentRevisionMessage } from './intentStore'

describe('buildIntentRevisionMessage', () => {
  it('builds an explicit correction message understood by the S1 rule engine', () => {
    expect(buildIntentRevisionMessage({
      topic: '快速排序',
      duration_minutes: '50',
      target_student: '大二软件工程学生',
      style: '沉稳专业',
      knowledge_points: '分治思想、枢轴选择，分区过程',
      with_interactive: true
    })).toBe(
      '请更新教学意图：课程主题：快速排序；授课时长：50分钟；授课对象：大二软件工程学生；教学风格：沉稳专业；知识点：分治思想、枢轴选择、分区过程；互动设计：需要。'
    )
  })

  it('can explicitly turn interaction off without sending empty optional fields', () => {
    expect(buildIntentRevisionMessage({
      topic: '快速排序',
      duration_minutes: 45,
      with_interactive: false
    })).toBe('请更新教学意图：课程主题：快速排序；授课时长：45分钟；互动设计：不需要。')
  })
})
