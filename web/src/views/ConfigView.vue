<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">配置管理</h2>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="统计口径" name="stats">
        <el-card style="max-width: 860px">
          <el-form label-width="140px">
            <el-form-item label="优秀率阈值">
              <el-input-number
                v-model="stats.excellent"
                :min="0.01"
                :max="1"
                :step="0.01"
                :precision="2"
              />
              <span class="muted hint">0.85 = 85%</span>
            </el-form-item>
            <el-form-item label="良好率阈值">
              <el-input-number
                v-model="stats.good"
                :min="0.01"
                :max="1"
                :step="0.01"
                :precision="2"
              />
              <span class="muted hint">0.70 = 70%</span>
            </el-form-item>
            <el-form-item label="合格率阈值">
              <el-input-number
                v-model="stats.pass"
                :min="0.01"
                :max="1"
                :step="0.01"
                :precision="2"
              />
              <span class="muted hint">0.60 = 60%</span>
            </el-form-item>
            <el-form-item label="低分率阈值">
              <el-input-number
                v-model="stats.poor"
                :min="0.01"
                :max="1"
                :step="0.01"
                :precision="2"
              />
              <span class="muted hint">0.30 = 30%（≤ 该比例计为低分）</span>
            </el-form-item>

            <el-form-item label="等级模式">
              <el-radio-group v-model="stats.grade_mode">
                <el-radio value="ratio">按比例（分数）</el-radio>
                <el-radio value="rank">按排名</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="比例等级">
              <div
                v-for="level in stats.ratio_levels"
                :key="level.name"
                class="level-row"
              >
                <span class="level-name">{{ level.name }}</span>
                <el-input-number
                  v-model="level.threshold"
                  :min="0"
                  :max="1"
                  :step="0.01"
                  :precision="2"
                />
                <span class="muted">最低分比例</span>
              </div>
            </el-form-item>

            <el-form-item label="排名等级">
              <div
                v-for="level in stats.rank_levels"
                :key="level.name"
                class="level-row"
              >
                <span class="level-name">{{ level.name }}</span>
                <el-input-number
                  v-model="level.threshold"
                  :min="0"
                  :max="1"
                  :step="0.01"
                  :precision="2"
                />
                <span class="muted">累计名次比例上限</span>
              </div>
            </el-form-item>

            <el-form-item label="分段数">
              <el-input-number
                v-model="stats.segment_count"
                :min="2"
                :max="20"
              />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveStats">
                保存统计口径
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="学科管理" name="subjects">
        <SubjectManager />
      </el-tab-pane>

      <el-tab-pane label="导出模板" name="export">
        <el-card>
          <el-form label-width="110px">
            <el-form-item label="模板">
              <el-radio-group v-model="exportName" @change="loadExport">
                <el-radio-button value="full">完整成绩表</el-radio-button>
                <el-radio-button value="stats">统计表</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="JSON 配置">
              <el-input
                v-model="exportJson"
                type="textarea"
                :rows="22"
                spellcheck="false"
                class="json-editor"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveExport">
                保存模板
              </el-button>
              <el-button @click="loadExport">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { configApi } from '../api'
import SubjectManager from '../components/SubjectManager.vue'
import type { StatsConfig } from '../types'

const tab = ref('stats')
const saving = ref(false)
const exportName = ref<'full' | 'stats'>('full')
const exportJson = ref('')

const stats = ref<StatsConfig>({
  excellent: 0.85,
  good: 0.7,
  pass: 0.6,
  poor: 0.3,
  grade_mode: 'ratio',
  ratio_levels: [
    { name: 'A', threshold: 0.85 },
    { name: 'B', threshold: 0.7 },
    { name: 'C', threshold: 0.6 },
    { name: 'D', threshold: 0.4 },
    { name: 'E', threshold: 0 },
  ],
  rank_levels: [
    { name: 'A', threshold: 0.1 },
    { name: 'B', threshold: 0.3 },
    { name: 'C', threshold: 0.6 },
    { name: 'D', threshold: 0.85 },
    { name: 'E', threshold: 1 },
  ],
  segment_count: 10,
})

async function loadStats() {
  const { data } = await configApi.getStats()
  stats.value = data
}

async function saveStats() {
  saving.value = true
  try {
    const { data } = await configApi.saveStats(stats.value)
    stats.value = data
    ElMessage.success('统计口径已保存')
  } finally {
    saving.value = false
  }
}

async function loadExport() {
  const { data } = await configApi.getExport(exportName.value)
  exportJson.value = JSON.stringify(data, null, 2)
}

async function saveExport() {
  let body: Record<string, unknown>
  try {
    body = JSON.parse(exportJson.value)
  } catch {
    ElMessage.error('JSON 格式错误')
    return
  }
  saving.value = true
  try {
    const { data } = await configApi.saveExport(exportName.value, body)
    exportJson.value = JSON.stringify(data, null, 2)
    ElMessage.success('导出模板已保存')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadStats(), loadExport()])
})
</script>

<style scoped>
.hint {
  margin-left: 12px;
  font-size: 12px;
}

.level-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.level-name {
  width: 24px;
  font-weight: 600;
}

.json-editor :deep(textarea) {
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
}
</style>
