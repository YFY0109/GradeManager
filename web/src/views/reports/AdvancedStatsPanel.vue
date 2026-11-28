<template>
  <div class="advanced">
    <el-card v-if="topBottom" class="block">
      <template #header>
        优秀生 / 学困生
        <span class="header-note">
          按总分取前 {{ topBottom.n }} 名 / 后 {{ topBottom.n }} 名
        </span>
      </template>
      <el-table :data="topBottom.classes" border size="small">
        <el-table-column prop="class" label="班级" width="100" fixed />
        <el-table-column prop="eligible" label="齐全人数" width="90" />
        <el-table-column label="优秀生人数" width="100">
          <template #default="{ row }">{{ row.top_count }}</template>
        </el-table-column>
        <el-table-column label="优秀生占比" width="100">
          <template #default="{ row }">{{ pct(row.top_ratio) }}</template>
        </el-table-column>
        <el-table-column label="学困生人数" width="100">
          <template #default="{ row }">{{ row.bottom_count }}</template>
        </el-table-column>
        <el-table-column label="学困生占比" width="100">
          <template #default="{ row }">{{ pct(row.bottom_ratio) }}</template>
        </el-table-column>
      </el-table>
      <p class="muted note">
        优秀生/学困生按年级总分名次划分，并列名次同时计入；占比以该班齐全人数为分母。
      </p>
    </el-card>

    <el-card v-if="rankBands" class="block">
      <template #header>名次段人数</template>
      <el-table :data="rankBands.classes" border size="small">
        <el-table-column prop="class" label="班级" width="100" fixed />
        <el-table-column prop="eligible" label="齐全人数" width="90" />
        <el-table-column
          v-for="band in rankBands.bands"
          :key="band"
          :label="`前 ${band} 名`"
          width="120"
        >
          <template #default="{ row }">
            {{ row.counts[String(band)] ?? 0 }}（{{ pct(row.ratios[String(band)]) }}）
          </template>
        </el-table-column>
      </el-table>
      <p class="muted note">
        按年级总分名次统计各班进入前 N 名的人数；占比以该班齐全人数为分母。
      </p>
    </el-card>

    <el-card
      v-if="classSegments && scopeType === 'grade'"
      class="block"
    >
      <template #header>分数段按班分布</template>
      <div ref="segmentRef" class="chart"></div>
      <el-table :data="classSegments.classes" border size="small" class="table-scroll">
        <el-table-column prop="class" label="班级" width="100" fixed />
        <el-table-column prop="eligible" label="齐全人数" width="90" />
        <el-table-column
          v-for="segment in classSegments.segments"
          :key="segment.label"
          :label="segment.label"
          width="110"
        >
          <template #default="{ row }">
            {{ row.counts[segment.label] ?? 0 }}（{{ pct(row.ratios[segment.label]) }}）
          </template>
        </el-table-column>
      </el-table>
      <p class="muted note">
        分数段按总分满分比例划分；占比以该班齐全人数为分母。
      </p>
    </el-card>

    <el-card v-if="balance" class="block">
      <template #header>学科均衡度</template>
      <template v-if="scopeType === 'class'">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12">
            <div class="metric-label">平均偏科指数（得分率标准差）</div>
            <div class="metric-value">{{ fixed(currentBalance?.avg_std, 3) }}</div>
            <div class="muted">越小表示各科越均衡</div>
          </el-col>
          <el-col :xs="24" :sm="12">
            <div class="metric-label">平均得分率极差</div>
            <div class="metric-value">{{ pct(currentBalance?.avg_range) }}</div>
            <div class="muted">最强科与最弱科的得分率之差</div>
          </el-col>
        </el-row>
        <p class="muted note">
          基于 {{ balance.subjects.join('、') }} 的得分率计算；仅统计总分齐全的学生。
        </p>
      </template>
      <template v-else>
        <el-table :data="balance.classes" border size="small">
          <el-table-column prop="class" label="班级" width="100" fixed />
          <el-table-column prop="eligible" label="齐全人数" width="90" />
          <el-table-column label="平均偏科指数" width="140">
            <template #default="{ row }">{{ fixed(row.avg_std, 3) }}</template>
          </el-table-column>
          <el-table-column label="平均得分率极差" width="150">
            <template #default="{ row }">{{ pct(row.avg_range) }}</template>
          </el-table-column>
        </el-table>
        <p class="muted note">
          偏科指数 = 学生各科得分率的总体标准差，按班取平均；越小表示学科发展越均衡。
        </p>
      </template>
    </el-card>

    <el-card v-if="dispersion" class="block">
      <template #header>班级离散度</template>
      <el-table
        v-if="scopeType === 'grade'"
        :data="dispersion.classes"
        border
        size="small"
        class="table-scroll"
      >
        <el-table-column prop="class" label="班级" width="100" fixed />
        <el-table-column
          v-for="subject in dispersion.subjects"
          :key="subject"
          :label="`${subject}变异系数`"
          width="120"
        >
          <template #default="{ row }">
            {{ pct(row.values[subject]?.cv) }}
          </template>
        </el-table-column>
      </el-table>
      <el-table v-else :data="currentDispersion" border size="small">
        <el-table-column prop="subject" label="科目" width="100" />
        <el-table-column prop="participants" label="有效人数" width="90" />
        <el-table-column label="标准差" width="100">
          <template #default="{ row }">{{ fixed(row.stddev, 2) }}</template>
        </el-table-column>
        <el-table-column label="变异系数" width="100">
          <template #default="{ row }">{{ pct(row.cv) }}</template>
        </el-table-column>
      </el-table>
      <p class="muted note">
        变异系数 = 标准差 ÷ 均分，越大表示该科成绩分化越明显。
      </p>
    </el-card>

    <el-card v-if="critical" class="block">
      <template #header>临界生对比</template>
      <el-alert
        v-if="!critical.configured"
        type="info"
        :closable="false"
        show-icon
        title="尚未配置分数线"
        description="请在「配置管理 → 统计口径 → 分数线」中添加后查看临界生。"
      />
      <template v-else>
        <div class="toolbar">
          <span class="muted">分数线</span>
          <el-select
            v-model="criticalLine"
            size="small"
            style="width: 160px"
            aria-label="临界生分数线"
          >
            <el-option
              v-for="line in critical.lines"
              :key="line.name"
              :label="line.name"
              :value="line.name"
            />
          </el-select>
          <span v-if="criticalSubjectOptions.length" class="muted">单科</span>
          <el-select
            v-if="criticalSubjectOptions.length"
            v-model="criticalSubject"
            size="small"
            style="width: 120px"
            aria-label="临界生科目"
          >
            <el-option
              v-for="name in criticalSubjectOptions"
              :key="name"
              :label="name"
              :value="name"
            />
          </el-select>
        </div>

        <template v-if="criticalTotal">
          <h4 class="sub-title">总分临界（{{ criticalTotal.total }} ± {{ criticalTotal.margin }}）</h4>
          <el-table :data="criticalTotal.classes" border size="small">
            <el-table-column prop="class" label="班级" width="100" fixed />
            <el-table-column prop="eligible" label="齐全人数" width="90" />
            <el-table-column prop="count" label="临界人数" width="90" />
            <el-table-column label="占比" width="90">
              <template #default="{ row }">{{ pct(row.ratio) }}</template>
            </el-table-column>
          </el-table>
          <el-table
            v-if="scopeType === 'class' && currentCriticalStudents.length"
            :data="currentCriticalStudents"
            border
            size="small"
            class="student-table"
          >
            <el-table-column prop="student_no" label="考号" width="130" />
            <el-table-column prop="name" label="姓名" width="110" />
            <el-table-column prop="class" label="班级" width="100" />
            <el-table-column label="总分" width="90">
              <template #default="{ row }">{{ fixed(row.value, 1) }}</template>
            </el-table-column>
          </el-table>
        </template>
        <el-empty
          v-else
          :image-size="60"
          description="该分数线未设置总分线"
        />

        <template v-if="criticalSubjectRows">
          <h4 class="sub-title">
            单科临界：{{ criticalSubjectRows.subject }}（得分率
            {{ pct(criticalSubjectRows.ratio) }} ± {{ pct(criticalSubjectRows.margin) }}）
          </h4>
          <el-table :data="criticalSubjectRows.classes" border size="small">
            <el-table-column prop="class" label="班级" width="100" fixed />
            <el-table-column prop="participants" label="有效人数" width="90" />
            <el-table-column prop="count" label="临界人数" width="90" />
            <el-table-column label="占比" width="90">
              <template #default="{ row }">{{ pct(row.ratio) }}</template>
            </el-table-column>
          </el-table>
          <el-table
            v-if="scopeType === 'class' && currentCriticalSubjectStudents.length"
            :data="currentCriticalSubjectStudents"
            border
            size="small"
            class="student-table"
          >
            <el-table-column prop="student_no" label="考号" width="130" />
            <el-table-column prop="name" label="姓名" width="110" />
            <el-table-column prop="class" label="班级" width="100" />
            <el-table-column :label="criticalSubjectRows.subject" width="90">
              <template #default="{ row }">{{ fixed(row.value, 1) }}</template>
            </el-table-column>
          </el-table>
        </template>
      </template>
    </el-card>

    <el-card v-if="cutoffs" class="block">
      <template #header>进线分析</template>
      <el-alert
        v-if="!cutoffs.configured"
        type="info"
        :closable="false"
        show-icon
        title="尚未配置分数线"
        description="请在「配置管理 → 统计口径 → 分数线」中添加后查看进线分析。"
      />
      <template v-else>
        <div class="toolbar">
          <span class="muted">分数线</span>
          <el-select
            v-model="cutoffLine"
            size="small"
            style="width: 160px"
            aria-label="进线分析分数线"
          >
            <el-option
              v-for="line in cutoffs.lines"
              :key="line.name"
              :label="line.name"
              :value="line.name"
            />
          </el-select>
          <el-radio-group v-model="cutoffView" size="small">
            <el-radio-button value="total">总分上线</el-radio-button>
            <el-radio-button value="subject">单科上线</el-radio-button>
            <el-radio-button value="double">双上线</el-radio-button>
          </el-radio-group>
          <el-select
            v-if="cutoffView !== 'total' && cutoffSubjectOptions.length"
            v-model="cutoffSubject"
            size="small"
            style="width: 120px"
            aria-label="进线分析科目"
          >
            <el-option
              v-for="name in cutoffSubjectOptions"
              :key="name"
              :label="name"
              :value="name"
            />
          </el-select>
        </div>

        <template v-if="cutoffView === 'total'">
          <el-table v-if="currentCutoff?.total != null" :data="currentCutoff.classes" border size="small">
            <el-table-column prop="class" label="班级" width="100" fixed />
            <el-table-column prop="eligible" label="齐全人数" width="90" />
            <el-table-column prop="total_online" label="上线人数" width="90" />
            <el-table-column label="上线率" width="90">
              <template #default="{ row }">{{ pct(row.total_rate) }}</template>
            </el-table-column>
            <el-table-column label="贡献率" width="90">
              <template #default="{ row }">{{ pct(row.contribution_rate) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else :image-size="60" description="该分数线未设置总分线" />
          <p class="muted note">
            上线率 = 本班上线人数 ÷ 本班齐全人数；贡献率 = 本班上线人数 ÷ 年级上线人数。
          </p>
        </template>

        <template v-else-if="cutoffView === 'subject'">
          <el-table
            v-if="cutoffSubject && currentCutoff && currentCutoff.subject_ratio != null"
            :data="currentCutoff.classes"
            border
            size="small"
          >
            <el-table-column prop="class" label="班级" width="100" fixed />
            <el-table-column label="有效人数" width="90">
              <template #default="{ row }">{{ row.subjects[cutoffSubject]?.participants ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="上线人数" width="90">
              <template #default="{ row }">{{ row.subjects[cutoffSubject]?.online ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="上线率" width="90">
              <template #default="{ row }">{{ pct(row.subjects[cutoffSubject]?.rate) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else :image-size="60" description="该分数线未设置单科线" />
          <p class="muted note">
            单科上线 = 该科成绩 ≥ 该科满分 × 单科得分率；上线率以该科有效人数为分母。
          </p>
        </template>

        <template v-else>
          <el-table
            v-if="cutoffSubject && currentCutoff && currentCutoff.subject_ratio != null && currentCutoff.total != null"
            :data="currentCutoff.classes"
            border
            size="small"
          >
            <el-table-column prop="class" label="班级" width="100" fixed />
            <el-table-column prop="eligible" label="齐全人数" width="90" />
            <el-table-column label="双上线人数" width="110">
              <template #default="{ row }">{{ row.double[cutoffSubject]?.online ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="占比" width="90">
              <template #default="{ row }">{{ pct(row.double[cutoffSubject]?.rate) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else :image-size="60" description="该分数线未同时设置总分线和单科线" />
          <p class="muted note">
            双上线 = 总分上线且所选科目单科上线；占比以该班齐全人数为分母。
          </p>
        </template>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { Overview } from '../../types'

echarts.use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  data: Overview
  scopeType: 'grade' | 'class'
}>()

const analytics = computed(() => props.data.analytics)
const topBottom = computed(() => analytics.value.top_bottom)
const rankBands = computed(() => analytics.value.rank_bands)
const classSegments = computed(() => analytics.value.class_segments)
const balance = computed(() => analytics.value.balance)
const dispersion = computed(() => analytics.value.dispersion)
const critical = computed(() => analytics.value.critical)
const cutoffs = computed(() => analytics.value.cutoffs)

const currentBalance = computed(() => balance.value?.classes[0] ?? null)
const currentDispersion = computed(() => {
  const row = dispersion.value?.classes[0]
  if (!row) return []
  return (dispersion.value?.subjects ?? []).map((subject) => ({
    subject,
    ...row.values[subject],
  }))
})

const criticalLine = ref('')
const criticalSubject = ref('')
const criticalSubjectOptions = computed(() => {
  const names = new Set(
    (critical.value?.subjects ?? []).map((item) => item.subject),
  )
  return [...names]
})
const criticalTotal = computed(() =>
  (critical.value?.total ?? []).find((item) => item.line === criticalLine.value),
)
const criticalSubjectRows = computed(() =>
  (critical.value?.subjects ?? []).find(
    (item) =>
      item.line === criticalLine.value && item.subject === criticalSubject.value,
  ),
)
const currentCriticalStudents = computed(
  () => criticalTotal.value?.classes[0]?.students ?? [],
)
const currentCriticalSubjectStudents = computed(
  () => criticalSubjectRows.value?.classes[0]?.students ?? [],
)

const cutoffLine = ref('')
const cutoffView = ref<'total' | 'subject' | 'double'>('total')
const cutoffSubject = ref('')
const currentCutoff = computed(() =>
  (cutoffs.value?.lines ?? []).find((item) => item.name === cutoffLine.value),
)
const cutoffSubjectOptions = computed(() => {
  const first = currentCutoff.value?.classes[0]
  if (!first) return []
  return Object.keys(first.subjects)
})

const segmentRef = ref<HTMLDivElement>()
const segmentChart = shallowRef<ReturnType<typeof echarts.init> | null>(null)

function pct(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function fixed(value: number | null | undefined, digits = 2) {
  return value == null ? '—' : Number(value).toFixed(digits)
}

function renderSegmentChart() {
  const block = classSegments.value
  if (!block || !segmentRef.value) return
  const segments = [...block.segments].reverse()
  segmentChart.value?.dispose()
  segmentChart.value = echarts.init(segmentRef.value)
  segmentChart.value.setOption({
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', top: 0 },
    grid: { left: 48, right: 24, top: 44, bottom: 60 },
    xAxis: {
      type: 'category',
      data: block.classes.map((row) => row.class),
      axisLabel: { rotate: 35, fontSize: 10 },
    },
    yAxis: { type: 'value', name: '人数' },
    series: segments.map((segment) => ({
      name: segment.label,
      type: 'bar',
      stack: 'total',
      barMaxWidth: 42,
      data: block.classes.map((row) => row.counts[segment.label] ?? 0),
    })),
  })
}

function handleResize() {
  segmentChart.value?.resize()
}

function resetSelections() {
  const lines = critical.value?.lines ?? []
  if (!lines.some((line) => line.name === criticalLine.value)) {
    criticalLine.value = lines[0]?.name ?? ''
  }
  const subjectNames = criticalSubjectOptions.value
  if (!subjectNames.includes(criticalSubject.value)) {
    criticalSubject.value = subjectNames[0] ?? ''
  }
  const cutoffLines = cutoffs.value?.lines ?? []
  if (!cutoffLines.some((line) => line.name === cutoffLine.value)) {
    cutoffLine.value = cutoffLines[0]?.name ?? ''
  }
  const cutoffNames = cutoffSubjectOptions.value
  if (!cutoffNames.includes(cutoffSubject.value)) {
    cutoffSubject.value = cutoffNames[0] ?? ''
  }
}

watch(
  () => props.data,
  async () => {
    resetSelections()
    await nextTick()
    renderSegmentChart()
  },
)
watch([criticalSubjectOptions, cutoffSubjectOptions], resetSelections)

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  resetSelections()
  await nextTick()
  renderSegmentChart()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  segmentChart.value?.dispose()
})
</script>

<style scoped>
.block {
  margin-bottom: 16px;
}

.header-note {
  margin-left: 10px;
  font-size: 12px;
  font-weight: normal;
  color: #909399;
}

.note {
  margin: 8px 0 0;
  font-size: 12px;
}

.chart {
  width: 100%;
  height: 360px;
  margin-bottom: 12px;
}

.table-scroll {
  width: 100%;
}

.sub-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.student-table {
  margin-top: 8px;
}

.metric-label {
  color: #909399;
  font-size: 13px;
  margin-bottom: 6px;
}

.metric-value {
  font-size: 26px;
  font-weight: 600;
  margin-bottom: 4px;
}
</style>
