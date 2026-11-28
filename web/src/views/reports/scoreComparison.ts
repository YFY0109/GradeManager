import type { ExamSubject, Student } from '../../types'

export const TOTAL_RANK_ITEM = 'total'

export interface RankedStudent extends Student {
  ranks: Partial<Record<string, number>>
  tied?: Partial<Record<string, number>>
}

export interface RankField {
  key: 'grade_rank' | 'class_rank'
  label: string
}

interface SubjectPair {
  current: ExamSubject
  reference: ExamSubject
}

export interface ComparisonItem {
  id: string
  label: string
  currentSubjects: ExamSubject[]
  referenceSubjects: ExamSubject[]
  comparePoints: boolean
  rankItem?: string
}

function makeItem(id: string, label: string, subjects: SubjectPair[], rankItem?: string): ComparisonItem {
  return {
    id,
    label,
    currentSubjects: subjects.map((pair) => pair.current),
    referenceSubjects: subjects.map((pair) => pair.reference),
    comparePoints: subjects.every(({ current, reference }) => {
      const fullScore = Number(current.full_score)
      return Number.isFinite(fullScore) && fullScore > 0 && fullScore === Number(reference.full_score)
    }),
    rankItem,
  }
}

export function comparisonOptions(
  currentSubjects: ExamSubject[],
  referenceSubjects: ExamSubject[],
  visibleSubjects: ExamSubject[],
  canViewTotal: boolean,
) {
  const referenceById = new Map(referenceSubjects.map((subject) => [subject.public_id, subject]))
  const common: SubjectPair[] = []
  for (const current of currentSubjects) {
    const reference = referenceById.get(current.public_id)
    if (reference) common.push({ current, reference })
  }

  const sameSubjects = common.length > 0 &&
    common.length === currentSubjects.length && common.length === referenceSubjects.length
  const visibleIds = new Set(visibleSubjects.map((subject) => subject.public_id))
  const visibleCommon = common.filter(({ current }) => visibleIds.has(current.public_id))
  const items = visibleCommon.map((pair) =>
    makeItem(pair.current.public_id, pair.current.name, [pair], pair.current.public_id),
  )

  if (canViewTotal) {
    const total = sameSubjects ? makeItem(TOTAL_RANK_ITEM, '总分', common, TOTAL_RANK_ITEM) : null
    if (total?.comparePoints) {
      items.unshift(total)
    } else if (visibleCommon.length > 1) {
      items.unshift(makeItem('common', '共同科目合计', visibleCommon))
    }
  }

  return { items, sameSubjects }
}

export function comparisonScore(
  student: Student | undefined,
  subjects: ExamSubject[],
  equalWeight: boolean,
) {
  const marks = subjects.map((subject) => {
    const value = student?.scores[subject.name]
    return { score: value == null ? NaN : Number(value), fullScore: Number(subject.full_score) }
  })
  const fullScore = marks.every(({ fullScore }) => Number.isFinite(fullScore) && fullScore > 0)
    ? marks.reduce((sum, mark) => sum + mark.fullScore, 0)
    : null
  const total = marks.reduce((sum, mark) => sum + mark.score, 0)
  const score = marks.length > 0 && Number.isFinite(total) ? total : null
  let rate: number | null = null
  if (score != null && fullScore) {
    const ratio = equalWeight
      ? marks.reduce((sum, mark) => sum + mark.score / mark.fullScore, 0) / marks.length
      : score / fullScore
    rate = ratio * 100
  }
  return { score, fullScore, rate }
}
