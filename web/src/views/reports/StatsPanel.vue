<template>
  <div>
    <div class="toolbar">
      <span class="muted" v-if="data">
        参考 {{ data.total?.participants ?? data.students }} 人
      </span>
    </div>

    <template v-if="data">
      <el-row v-if="data.total" :gutter="16" class="block stat-cards">
        <el-col :xs="12" :sm="6">
          <el-card>
            <div class="stat-label">参考人数</div>
            <div class="stat-value">{{ data.total.participants }}</div>
            <div class="stat-sub">缺考 {{ data.total.absent }}</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card>
            <div class="stat-label">总分平均</div>
            <div class="stat-value">{{ fixed(data.total.avg, 2) }}</div>
            <div class="stat-sub">满分 {{ data.full_total }}</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card>
            <div class="stat-label">最高分</div>
            <div class="stat-value">{{ fixed(data.total.max, 1) }}</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="6">
          <el-card>
            <div class="stat-label">最低分</div>
            <div class="stat-value">{{ fixed(data.total.min, 1) }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-card class="block">
        <template #header>学科成绩对比</template>
        <el-table :data="data.subjects" border size="small">
          <el-table-column prop="name" label="学科" width="80" fixed />
          <el-table-column prop="participants" label="实考" width="70" />
          <el-table-column prop="absent" label="缺考" width="70" />
          <el-table-column prop="full_score" label="满分" width="70" />
          <el-table-column label="最高" width="70">
            <template #default="{ row }">{{ fixed(row.max, 1) }}</template>
          </el-table-column>
          <el-table-column label="最低" width="70">
            <template #default="{ row }">{{ fixed(row.min, 1) }}</template>
          </el-table-column>
          <el-table-column label="均分" width="80">
            <template #default="{ row }">{{ fixed(row.avg, 2) }}</template>
          </el-table-column>
          <el-table-column v-if="scopeType === 'class' && canRankGrade" label="排名" width="70">
            <template #default="{ row }">{{ row.rank ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="优秀率" width="80">
            <template #default="{ row }">{{ pct(row.excellent_rate) }}</template>
          </el-table-column>
          <el-table-column label="良好率" width="80">
            <template #default="{ row }">{{ pct(row.good_rate) }}</template>
          </el-table-column>
          <el-table-column label="合格率" width="80">
            <template #default="{ row }">{{ pct(row.pass_rate) }}</template>
          </el-table-column>
          <el-table-column label="低分率" width="80">
            <template #default="{ row }">{{ pct(row.poor_rate) }}</template>
          </el-table-column>
          <el-table-column v-if="scopeType === 'class'" label="超均率" width="85">
            <template #default="{ row }">{{ pct(row.above_avg_rate) }}</template>
          </el-table-column>
          <el-table-column label="标准差" width="80">
            <template #default="{ row }">{{ fixed(row.stddev, 1) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-row v-if="data.total" :gutter="16" class="block">
        <el-col :xs="24" :md="12">
          <el-card>
            <template #header>学业等级分布</template>
            <div ref="levelRef" class="chart"></div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card>
            <template #header>成绩分段对比</template>
            <div ref="segmentRef" class="chart"></div>
          </el-card>
        </el-col>
      </el-row>

      <el-alert
        v-if="comment"
        :title="comment"
        type="info"
        :closable="false"
        show-icon
        class="block"
      />

      <el-card
        v-if="scopeType === 'class' && data.advantages.z_scores"
        class="block"
      >
        <template #header>优劣势学科对比</template>
        <el-row :gutter="16">
          <el-col :xs="24" :md="12">
            <div ref="radarRef" class="chart chart-radar"></div>
          </el-col>
          <el-col :xs="24" :md="12">
            <p>
              <strong>优势学科：</strong>
              {{ data.advantages.strong.join('、') || '无' }}
            </p>
            <p>
              <strong>劣势学科：</strong>
              {{ data.advantages.weak.join('、') || '无' }}
            </p>
            <p class="muted">
              z 分数 =（班级均分 − 年级均分）/ 年级标准差；正值越大学科优势越明显。
            </p>
          </el-col>
        </el-row>
      </el-card>

      <el-card v-if="scopeType === 'grade'" class="block">
        <template #header>班级成绩对比</template>
        <el-table :data="data.classes" border size="small">
          <el-table-column prop="class" label="班级" width="90" fixed />
          <el-table-column prop="students" label="人数" width="80" />
          <el-table-column prop="complete" label="齐全" width="80" />
          <el-table-column v-if="canViewTotal" label="总分均" width="90">
            <template #default="{ row }">{{ fixed(row.total_avg, 2) }}</template>
          </el-table-column>
          <el-table-column
            v-for="name in subjectNames"
            :key="name"
            :label="`${name}均`"
            width="90"
          >
            <template #default="{ row }">
              {{ fixed(row.subject_avg[name], 2) }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <el-empty v-else-if="!loading" description="暂无统计数据" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, RadarChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  RadarComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { overviewApi } from '../../api'
import { useAuthStore } from '../../stores/auth'
import type { Overview } from '../../types'

echarts.use([
  BarChart,
  LineChart,
  RadarChart,
  GridComponent,
  LegendComponent,
  RadarComponent,
  TooltipComponent,
  CanvasRenderer,
])

const props = defineProps<{
  examPid: string
  scopeType: 'grade' | 'class'
  classPid: string
}>()
const auth = useAuthStore()

const data = ref<Overview | null>(null)
const loading = ref(false)

const levelRef = ref<HTMLDivElement>()
const segmentRef = ref<HTMLDivElement>()
const radarRef = ref<HTMLDivElement>()
let levelChart: ReturnType<typeof echarts.init> | null = null
let segmentChart: ReturnType<typeof echarts.init> | null = null
let radarChart: ReturnType<typeof echarts.init> | null = null

const subjectNames = computed(() =>
  (data.value?.subjects || []).map((item) => item.name),
)
const canRankGrade = computed(() => auth.can('can_rank_grade'))
const canViewTotal = computed(() => auth.can('view_total'))

const comment = computed(() => {
  const total = data.value?.total?.participants || 0
  if (!total || !data.value?.segments?.length) return ''
  const segments = data.value.segments
  const n = segments.length
  const highEnd = Math.max(1, Math.round(n * 0.3))
  const lowStart = Math.max(highEnd, Math.floor(n * 0.8))
  const high = segments.slice(0, highEnd).reduce((sum, item) => sum + item.count, 0)
  const mid = segments
    .slice(highEnd, lowStart)
    .reduce((sum, item) => sum + item.count, 0)
  const low = segments.slice(lowStart).reduce((sum, item) => sum + item.count, 0)
  if (mid / total >= 0.6) {
    return '本次考试成绩较集中，中等水平学生居多；后续教学可在中等生群体上多花功夫。'
  }
  if (high / total >= 0.4) {
    return '本次考试高分段占比较高，整体成绩较好。'
  }
  if (low / total >= 0.2) {
    return '本次考试低分段占比偏高，建议关注后进生辅导。'
  }
  return '成绩分布较为均衡。'
})

function fixed(value: number | null | undefined, digits: number) {
  return value == null ? '—' : Number(value).toFixed(digits)
}

function pct(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

async function load() {
  if (!props.examPid) return
  if (props.scopeType === 'class' && !props.classPid) {
    data.value = null
    return
  }
  loading.value = true
  try {
    const { data: res } = await overviewApi.get(
      props.examPid,
      props.scopeType === 'class' ? props.classPid : undefined,
    )
    data.value = res
    await nextTick()
    renderCharts()
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  const current = data.value
  if (!current) return

  if (levelRef.value && current.grade_levels.length) {
    levelChart?.dispose()
    levelChart = echarts.init(levelRef.value)
    levelChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 24, top: 30, bottom: 40 },
      xAxis: {
        type: 'category',
        data: current.grade_levels.map((item) => item.name),
      },
      yAxis: { type: 'value', name: '人数' },
      series: [
        {
          name: '人数',
          type: 'bar',
          data: current.grade_levels.map((item) => item.count),
          barMaxWidth: 48,
          itemStyle: { color: '#409eff' },
          label: { show: true, position: 'top' },
        },
      ],
    })
  }

  if (segmentRef.value && current.segments.length) {
    segmentChart?.dispose()
    segmentChart = echarts.init(segmentRef.value)
    segmentChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 24, top: 30, bottom: 50 },
      xAxis: {
        type: 'category',
        data: current.segments.map((item) => item.label),
        axisLabel: { rotate: 35, fontSize: 10 },
      },
      yAxis: { type: 'value', name: '人数' },
      series: [
        {
          name: '人数',
          type: 'line',
          smooth: true,
          data: current.segments.map((item) => item.count),
          areaStyle: { opacity: 0.15 },
          itemStyle: { color: '#67c23a' },
        },
      ],
    })
  }

  if (radarRef.value && current.advantages.z_scores) {
    const names = Object.keys(current.advantages.z_scores)
    if (names.length) {
      radarChart?.dispose()
      radarChart = echarts.init(radarRef.value)
      radarChart.setOption({
        tooltip: {},
        radar: {
          indicator: names.map((name) => ({ name, min: -2, max: 2 })),
          radius: '65%',
        },
        series: [
          {
            type: 'radar',
            data: [
              {
                value: names.map((name) => current.advantages.z_scores[name]),
                name: 'z 分数',
                areaStyle: { opacity: 0.25 },
              },
            ],
          },
        ],
      })
    }
  }
}

function handleResize() {
  levelChart?.resize()
  segmentChart?.resize()
  radarChart?.resize()
}

watch(
  () => [props.examPid, props.scopeType, props.classPid],
  () => load(),
)

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  await load()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  levelChart?.dispose()
  segmentChart?.dispose()
  radarChart?.dispose()
})
</script>

<style scoped>
.stat-label {
  color: #909399;
  font-size: 13px;
  margin-bottom: 6px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
}

.stat-sub {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}

.block {
  margin-bottom: 16px;
}

.stat-cards {
  align-items: stretch;
}

.stat-cards :deep(.el-col) {
  display: flex;
}

.stat-cards :deep(.el-card) {
  width: 100%;
  height: 100%;
  min-height: 116px;
}

.stat-cards :deep(.el-card__body) {
  height: 100%;
}

.chart {
  width: 100%;
  height: 320px;
}

.chart-radar {
  height: 360px;
}
</style>
