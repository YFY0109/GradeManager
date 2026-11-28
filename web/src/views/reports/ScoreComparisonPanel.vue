<template>
  <div v-loading="loadingCurrent || loadingReference" class="comparison-panel">
    <el-alert v-if="loadError" type="error" :closable="false" title="对比考试的成绩加载失败。">
      <el-button link type="primary" @click="reload += 1">重试</el-button>
    </el-alert>
    <template v-else-if="item">
      <div class="toolbar">
        <el-select
          v-if="options.items.length > 1"
          v-model="itemId"
          aria-label="对比项目"
          placeholder="选择对比项目"
          style="width: 180px"
        >
          <el-option
            v-for="option in options.items"
            :key="option.id"
            :label="option.label"
            :value="option.id"
          />
        </el-select>
        <strong v-else>{{ item.label }}</strong>
        <span class="muted">本次：{{ currentName }} · 对比：{{ referenceExam.name }}</span>
      </div>
      <p v-if="!options.sameSubjects || !item.comparePoints" class="muted comparison-note">
        <template v-if="!options.sameSubjects">两场考试科目不同，仅对比共同科目。 </template>
        <template v-if="!item.comparePoints">
          科目满分不同，以得分率衡量变化。<template v-if="item.currentSubjects.length > 1">合计的得分率为各科得分率的平均值。</template>
        </template>
      </p>
      <p v-if="item.currentSubjects.length > 1" class="muted comparison-note">
        纳入科目：{{ item.currentSubjects.map((subject) => subject.name).join('、') }}
      </p>
      <p class="muted comparison-note">分差和得分率差按本次减对比计算，缺考时显示「—」。</p>
      <p v-if="rankError" class="muted comparison-note" role="status">
        对比名次加载失败。<el-button link type="primary" @click="reloadRanks += 1">重试</el-button>
      </p>

      <el-table
        :key="item.id"
        v-loading="loadingRanks"
        :data="pagedRows"
        row-key="public_id"
        border
        stripe
        height="calc(100vh - 370px)"
        :empty-text="searching ? '未找到匹配的学生' : '暂无学生数据'"
        @sort-change="changeSort"
      >
        <el-table-column prop="student_no" label="考号" width="110" fixed />
        <el-table-column prop="name" label="姓名" width="100" fixed />
        <el-table-column
          v-if="!classPid"
          prop="class"
          label="班级"
          width="80"
          fixed
        />
        <el-table-column label="对比成绩 / 满分" width="140">
          <template #default="{ row }">{{ formatScore(row.reference) }}</template>
        </el-table-column>
        <el-table-column label="本次成绩 / 满分" width="140">
          <template #default="{ row }">{{ formatScore(row.current) }}</template>
        </el-table-column>
        <el-table-column v-if="item.comparePoints" prop="pointsChange" label="分差" sortable="custom" width="95">
          <template #default="{ row }">
            <span :class="changeColor(row.pointsChange)">{{ formatChange(row.pointsChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="得分率（对比 → 本次）" width="175">
          <template #default="{ row }">{{ formatRate(row.reference.rate) }} → {{ formatRate(row.current.rate) }}</template>
        </el-table-column>
        <el-table-column prop="rateChange" label="得分率差（百分点）" sortable="custom" width="175">
          <template #default="{ row }">
            <span :class="changeColor(row.rateChange)">{{ formatChange(row.rateChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-for="rank in item.rankItem ? rankFields : []"
          :key="rank.key"
          :prop="rank.key"
          :label="`${rank.label}（对比 → 本次）`"
          sortable="custom"
          min-width="175"
        >
          <template #default="{ row }">{{ formatRank(row.ranks[rank.key]) }}</template>
        </el-table-column>
      </el-table>

      <TablePager
        :page="page"
        :page-size="pageSize"
        :total="rows.length"
        @update:page="page = $event"
        @update:page-size="pageSize = $event"
      />
    </template>
    <el-empty v-else-if="!loadingReference && !loadingCurrent" description="两场考试没有可对比的科目或总分" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { examApi } from '../../api'
import TablePager from '../../components/TablePager.vue'
import type { Exam, ExamSubject, RankRow, Student } from '../../types'
import { comparisonOptions, comparisonScore, TOTAL_RANK_ITEM } from './scoreComparison'
import type { RankedStudent, RankField } from './scoreComparison'

type Score = ReturnType<typeof comparisonScore>
interface RankComparison {
  reference: number | null
  current: number | null
  change: number | null
}
type RankKey = RankField['key']
type SortField = 'pointsChange' | 'rateChange' | RankKey
type SortOrder = 'ascending' | 'descending'

const props = defineProps<{
  currentName: string
  referenceExam: Exam
  classPid?: string
  currentSubjects: ExamSubject[]
  visibleSubjects: ExamSubject[]
  canViewTotal: boolean
  rankFields: RankField[]
  rows: RankedStudent[]
  loadingCurrent: boolean
  searching: boolean
}>()

const reference = shallowRef<{ subjects: ExamSubject[]; students: Map<string, Student> } | null>(null)
const referenceRanks = shallowRef(new Map<string, RankRow>())
const loadingReference = ref(false)
const loadingRanks = ref(false)
const loadError = ref(false)
const rankError = ref(false)
const reload = ref(0)
const reloadRanks = ref(0)
const itemId = ref('')
const sort = ref<{ prop: SortField; order: SortOrder } | null>(null)
const page = ref(1)
const pageSize = defineModel<number>('pageSize', { required: true })

const options = computed(() => comparisonOptions(
  props.currentSubjects,
  reference.value?.subjects ?? [],
  props.visibleSubjects,
  props.canViewTotal,
))
const item = computed(() => options.value.items.find((option) => option.id === itemId.value))
const rankItem = computed(() => props.rankFields.length ? item.value?.rankItem : undefined)
const rankClassPid = computed(() =>
  props.rankFields.some((rank) => rank.key === 'class_rank') ? props.classPid : undefined,
)

const pagedRows = computed(() => {
  const metric = item.value
  const other = reference.value
  if (!metric || !other) return []

  const equalWeight = !metric.comparePoints && metric.currentSubjects.length > 1
  const rows = props.rows.map((student) => {
    const current = comparisonScore(student, metric.currentSubjects, equalWeight)
    const referenceScore = comparisonScore(other.students.get(student.public_id), metric.referenceSubjects, equalWeight)
    const ranks: Partial<Record<RankKey, RankComparison>> = {}
    if (metric.rankItem) {
      const previousRanks = referenceRanks.value.get(student.public_id)
      for (const { key } of props.rankFields) {
        const currentRank = current.score == null ? null : student.ranks[`${metric.rankItem}:${key}`] ?? null
        const referenceRank = referenceScore.score == null ? null : previousRanks?.[key] ?? null
        ranks[key] = { reference: referenceRank, current: currentRank, change: difference(referenceRank, currentRank) }
      }
    }
    return {
      ...student,
      current,
      reference: referenceScore,
      pointsChange: metric.comparePoints ? difference(current.score, referenceScore.score) : null,
      rateChange: difference(current.rate, referenceScore.rate),
      ranks,
    }
  })

  const order = sort.value
  if (order) {
    const value = (row: (typeof rows)[number]) => order.prop === 'pointsChange' || order.prop === 'rateChange'
      ? row[order.prop]
      : row.ranks[order.prop]?.change ?? null
    rows.sort((a, b) => {
      const first = value(a)
      const second = value(b)
      if (first === second) return 0
      if (first == null) return 1
      if (second == null) return -1
      return order.order === 'ascending' ? first - second : second - first
    })
  }
  const start = (page.value - 1) * pageSize.value
  return pageSize.value === 0 ? rows : rows.slice(start, start + pageSize.value)
})

const numberFormat = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })

function difference(a: number | null, b: number | null) {
  return a == null || b == null ? null : Math.round((a - b) * 100) / 100
}

function formatScore({ score, fullScore }: Score) {
  if (score == null) return '—'
  const points = numberFormat.format(score)
  return fullScore == null ? points : `${points} / ${numberFormat.format(fullScore)}`
}

function formatRate(rate: number | null) {
  return rate == null ? '—' : `${rate.toFixed(2)}%`
}

function formatChange(change: number | null) {
  return change == null ? '—' : `${change > 0 ? '+' : ''}${numberFormat.format(change || 0)}`
}

function changeColor(change: number | null) {
  if (!change) return ''
  return change > 0 ? 'delta-up' : 'delta-down'
}

function formatRank(rank?: RankComparison) {
  if (!rank || (rank.reference == null && rank.current == null)) return '—'
  const position = `${rank.reference ?? '—'} → ${rank.current ?? '—'}`
  if (rank.change == null) return position
  if (rank.change === 0) return `${position}（持平）`
  return `${position}（${rank.change > 0 ? '升' : '降'} ${Math.abs(rank.change)} 名）`
}

function changeSort({ prop, order }: { prop: SortField; order: SortOrder | null }) {
  sort.value = order ? { prop, order } : null
  page.value = 1
}

watch(() => options.value.items, (items) => {
  if (!items.some((option) => option.id === itemId.value)) itemId.value = items[0]?.id ?? ''
})
watch(itemId, () => {
  sort.value = null
})
watch([() => props.rows, itemId], () => {
  page.value = 1
})

watch(
  [() => props.referenceExam.public_id, () => props.classPid, reload],
  async ([examPid, classPid], _, onCleanup) => {
    const controller = new AbortController()
    const { signal } = controller
    onCleanup(() => controller.abort())
    reference.value = null
    loadingReference.value = true
    loadError.value = false
    try {
      const [{ data: detail }, { data: students }] = await Promise.all([
        examApi.detail(examPid, signal),
        examApi.students(examPid, classPid, signal),
      ])
      if (signal.aborted) return
      reference.value = {
        subjects: detail.subjects,
        students: new Map(students.map((student) => [student.public_id, student])),
      }
    } catch {
      if (!signal.aborted) loadError.value = true
    } finally {
      if (!signal.aborted) loadingReference.value = false
    }
  },
  { immediate: true },
)

watch(
  [() => props.referenceExam.public_id, rankItem, rankClassPid, reloadRanks],
  async ([examPid, selected, classPid], _, onCleanup) => {
    referenceRanks.value = new Map()
    rankError.value = false
    loadingRanks.value = !!selected
    if (!selected) return

    const controller = new AbortController()
    const { signal } = controller
    onCleanup(() => controller.abort())
    try {
      const { data } = await examApi.rankings(examPid, {
        classPid,
        subjectPid: selected === TOTAL_RANK_ITEM ? undefined : selected,
        signal,
      })
      if (!signal.aborted) {
        referenceRanks.value = new Map(data.map((row) => [row.student_public_id, row]))
      }
    } catch {
      if (!signal.aborted) rankError.value = true
    } finally {
      if (!signal.aborted) loadingRanks.value = false
    }
  },
)
</script>

<style scoped>
.comparison-panel {
  min-height: 120px;
}

.comparison-note {
  margin: 0 0 8px;
}

.delta-up {
  color: #67c23a;
  font-weight: 600;
}

.delta-down {
  color: #f56c6c;
  font-weight: 600;
}
</style>
