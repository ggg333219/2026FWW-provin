<template>
  <div class="pc-shell">
    <section class="pc-fixed-region">
    <header class="pc-top">
      <div class="pc-identity">
        <div class="avatar" :title="studentId">{{ avatarText }}</div>
        <div class="id-meta">
          <div class="title-row">
            <div class="title-main">
              <h2>个人中心</h2>
              <span class="pill" v-if="currentCourseName">正在学习：{{ currentCourseName }}</span>
            </div>
            <button type="button" class="stats-toggle-btn" @click="toggleStatsPanel">
              {{ statsPanelVisible ? '收起数据统计' : '数据统计' }}
            </button>
          </div>
          <p class="subtitle">把「学习 → 记录 → 练习 → 复习 → 任务 → 反馈」收拢到一个闭环里。</p>
        </div>
      </div>

      <div class="pc-learning-viz">
        <div class="mastery-row">
          <div class="mastery-head">
            <span class="mastery-title">综合掌握率</span>
            <span class="mastery-pct">{{ masteryRateClamped }}%</span>
          </div>
          <div class="mastery-track" aria-hidden="true">
            <div class="mastery-fill" :style="{ width: `${masteryRateClamped}%` }"></div>
          </div>
          <p class="mastery-hint">数据来自当前课件的学情统计，可与下方薄弱点联动复习。</p>
        </div>
        <div class="weak-row">
          <div class="weak-head">
            <span class="weak-title">薄弱点快捷入口</span>
            <button type="button" class="btn ghost btn-compact" @click="jumpToAnalytics">查看学情分析</button>
          </div>
          <div v-if="!weakPointTagsSafe.length" class="weak-empty">暂无薄弱点标签，完成练习或测验后会在此汇总。</div>
          <div v-else class="weak-chips">
            <button
              v-for="wp in weakPointTagsSafe.slice(0, 8)"
              :key="wp.id || wp.name"
              type="button"
              class="weak-chip"
              :title="`去「学习分析」查看：${wp.name}`"
              @click="jumpToAnalytics"
            >
              {{ wp.name }}
            </button>
            <span v-if="weakPointTagsSafe.length > 8" class="weak-more">+{{ weakPointTagsSafe.length - 8 }}</span>
          </div>
        </div>
      </div>

      <transition name="stats-pop">
        <div v-if="statsPanelVisible" class="pc-stats-popover">
          <div class="metric">
            <div class="metric-label">学习专注</div>
            <div class="metric-value">{{ learningStatsSafe.focusScore }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">掌握率</div>
            <div class="metric-value">{{ masteryRateClamped }}%</div>
          </div>
          <div class="metric">
            <div class="metric-label">薄弱点</div>
            <div class="metric-value">{{ weakPointTagsSafe.length }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">未读通知</div>
            <div class="metric-value">{{ unreadNotificationCount }}</div>
          </div>
        </div>
      </transition>
    </header>

    <div v-if="dueReminders.length" class="pc-banner">
      <div v-for="item in dueReminders" :key="item.key" class="banner-item">
        <div class="banner-text">{{ item.message }}</div>
        <button class="btn primary" @click="openReminder(item)">立即处理</button>
      </div>
    </div>

    <div class="pc-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        <span class="tab-label">{{ tab.label }}</span>
        <span class="tab-count" v-if="tabCount(tab.key) !== null">{{ tabCount(tab.key) }}</span>
      </button>
    </div>
    </section>

    <main class="pc-body" ref="bodyEl" @dragover.prevent>
      <transition name="pc-fade-slide" mode="out-in">
        <section v-if="activeTab === 'notes'" key="notes" class="panel">
          <div class="panel-head">
            <div class="head-left">
              <h3>笔记</h3>
              <p>从课堂学习同步过来，可拖拽到收藏看板进行归类。</p>
            </div>
            <div class="head-right">
              <input v-model="noteQuery" class="input" placeholder="搜索：关键词 / 课程" />
              <select v-model="noteSort" class="input select">
                <option value="time_desc">按时间（新→旧）</option>
                <option value="time_asc">按时间（旧→新）</option>
              </select>
              <button class="btn primary" @click="startNoteEdit()">添加笔记</button>
            </div>
          </div>

          <div v-if="showNoteForm" class="editor">
            <div class="grid">
              <select v-model="noteForm.courseId" class="input select">
                <option disabled value="">选择课程</option>
                <option v-for="course in courses" :key="course.id" :value="course.id">{{ course.title }}</option>
              </select>
              <input v-model.number="noteForm.pageNum" class="input" type="number" min="1" placeholder="页码" />
            </div>
            <textarea v-model="noteForm.content" class="input textarea" rows="4" placeholder="输入笔记内容（建议包含：结论/易错点/例题）"></textarea>
            <div class="row actions">
              <button class="btn" @click="cancelNoteEdit">取消</button>
              <button class="btn primary" @click="saveNote">保存</button>
            </div>
          </div>

          <div v-if="!filteredNotes.length" class="empty-card">
            <div class="empty-title">还没有笔记</div>
            <div class="empty-desc">去课堂学习页添加笔记，回来这里会自动同步。</div>
            <div class="empty-actions">
              <button class="btn primary" @click="startNoteEdit()">添加第一条笔记</button>
              <button class="btn ghost" @click="jumpToClassroom">去课堂学习</button>
            </div>
          </div>

          <div v-else class="note-list">
            <div
              v-for="note in filteredNotes"
              :key="note.id"
              class="card note-card"
              draggable="true"
              @dragstart="onDragStart($event, { kind: 'note', id: note.id })"
              @click="openNoteDrawer(note)"
              title="拖拽到收藏列：待学习/薄弱点/重点难点/已掌握"
            >
              <div class="card-top">
                <div class="card-title">{{ resolveNoteTitle(note) }}</div>
                <div class="card-actions" @click.stop>
                  <button class="icon-btn" @click="startNoteEdit(note)">编辑</button>
                  <button class="icon-btn danger" @click="deleteNote(note.id)">删除</button>
                </div>
              </div>
              <div class="card-body">{{ note.note }}</div>
              <div class="card-foot">
                <span class="chip">{{ getCourseName(note.courseId) }}</span>
                <span class="muted">第 {{ note.pageNum }} 页</span>
                <span class="muted">{{ formatDate(note.createdAt) }}</span>
              </div>
            </div>
          </div>
        </section>

        <section v-else-if="activeTab === 'favorites'" key="favorites" class="panel">
          <div class="panel-head">
            <div class="head-left">
              <h3>收藏看板</h3>
              <p>拖拽卡片跨列移动，状态会被记住；可把笔记拖进来快速归类。</p>
            </div>
            <div class="head-right">
              <input v-model="favoriteQuery" class="input" placeholder="搜索：标题 / 课程 / 标签" />
              <button class="btn ghost" @click="resetFavoriteBoard">重置看板</button>
            </div>
          </div>

          <div class="board">
            <div
              v-for="col in favoriteColumns"
              :key="col.key"
              class="board-col"
              :class="{ dragging: dragOverCol === col.key }"
              @dragenter.prevent="dragOverCol = col.key"
              @dragleave.prevent="dragOverCol = ''"
              @drop.prevent="onDropToFavoriteCol(col.key)"
            >
              <div class="col-head">
                <div class="col-title">
                  <span class="col-icon">{{ col.icon }}</span>
                  <span>{{ col.label }}</span>
                </div>
                <span class="col-count">{{ favoritesByCol(col.key).length }}</span>
              </div>

              <div v-if="favoritesByCol(col.key).length === 0" class="col-empty">
                <div class="empty-title">暂无内容</div>
                <div class="empty-desc">你可以从「笔记」拖拽进来，或在课堂学习页点击收藏。</div>
              </div>

              <div v-else class="col-list">
                <div
                  v-for="fav in favoritesByCol(col.key)"
                  :key="fav.id"
                  class="card fav-card"
                  draggable="true"
                  @dragstart="onDragStart($event, { kind: 'favorite', id: fav.id })"
                >
                  <div class="card-top">
                    <div class="card-title">{{ fav.title || '未命名收藏' }}</div>
                    <div class="card-actions">
                      <button class="icon-btn" @click="quickAddFavoriteToPlan(fav)">加入复习计划</button>
                      <button class="icon-btn" @click="startFavoriteEdit(fav)">标签</button>
                      <button class="icon-btn danger" @click="deleteFavorite(fav.id)">删除</button>
                    </div>
                  </div>

                  <div class="progress">
                    <div class="progress-bar">
                      <div class="progress-fill" :style="{ width: `${getMasteryForFavorite(fav)}%` }"></div>
                    </div>
                    <div class="progress-meta">{{ getMasteryForFavorite(fav) }}%</div>
                  </div>

                  <div class="tag-row">
                    <span v-for="tag in (fav.tags || []).slice(0, 3)" :key="tag" class="chip">{{ tag }}</span>
                    <span v-if="!(fav.tags || []).length" class="chip muted">未设置标签</span>
                  </div>

                  <div class="card-foot">
                    <span class="muted">{{ getCourseName(fav.courseId) }}</span>
                    <span class="muted">节点 {{ fav.nodeId || '-' }}</span>
                  </div>

                  <div v-if="editingFavorite && editingFavorite.id === fav.id" class="editor slim">
                    <input v-model="newTag" class="input" placeholder="输入标签后点添加" />
                    <button class="btn" @click="addTag">添加</button>
                    <div class="tag-row">
                      <span v-for="tag in editingFavorite.tags" :key="tag" class="chip removable" @click="removeTag(tag)">{{ tag }} ×</span>
                    </div>
                    <div class="row actions">
                      <button class="btn" @click="cancelFavoriteEdit">取消</button>
                      <button class="btn primary" @click="saveTags">保存标签</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section v-else-if="activeTab === 'plans'" key="plans" class="panel">
          <div class="panel-head">
            <div class="head-left">
              <h3>复习计划</h3>
              <p>把笔记/收藏转成可执行复习清单，形成学习闭环。</p>
            </div>
            <div class="head-right">
              <button class="btn primary" @click="startPlanEdit()">创建计划</button>
            </div>
          </div>

          <div v-if="showPlanForm" class="editor">
            <div class="grid">
              <input v-model="planForm.name" class="input" placeholder="计划名称（例如：本周薄弱点复习）" />
              <select v-model="planForm.frequency" class="input select">
                <option value="daily">每日</option>
                <option value="weekly">每周</option>
                <option value="monthly">每月</option>
              </select>
            </div>
            <textarea v-model="planForm.description" class="input textarea" rows="3" placeholder="计划说明（可选）"></textarea>
            <div class="row actions">
              <button class="btn" @click="showPlanForm = false; editingPlan = null">取消</button>
              <button class="btn primary" @click="savePlan">保存计划</button>
            </div>
          </div>

          <div v-if="!reviewPlans.length" class="empty-card">
            <div class="empty-title">暂无复习计划</div>
            <div class="empty-desc">你可以从收藏看板一键加入计划，或先新建一个空计划。</div>
            <div class="empty-actions">
              <button class="btn primary" @click="startPlanEdit()">创建第一个计划</button>
            </div>
          </div>

          <template v-else>
            <div class="grid-2">
              <div v-for="plan in reviewPlans" :key="plan.id" class="card compact">
                <div class="card-top">
                  <div class="card-title">{{ plan.name || '未命名计划' }}</div>
                  <span class="badge">{{ formatPlanStatus(plan.status) }}</span>
                </div>
                <div class="card-body">{{ plan.description || '暂无计划说明' }}</div>
                <div class="card-foot">
                  <span class="muted">频率：{{ formatFrequency(plan.frequency) }}</span>
                  <span class="muted">下次：{{ formatDate(plan.nextReviewDate) || '-' }}</span>
                </div>
                <div class="row actions">
                  <button class="btn" @click="viewPlanItems(plan)">查看复习项</button>
                  <button class="btn" @click="startPlanEdit(plan)">编辑</button>
                  <button class="btn danger" @click="deletePlan(plan.id)">删除</button>
                </div>
              </div>
            </div>

            <div v-if="currentPlan" class="subpanel">
              <div class="section-head">
                <h4>计划详情：{{ currentPlan.name }}</h4>
                <button class="btn ghost" @click="viewPlanItems(currentPlan)">刷新复习项</button>
              </div>

              <div class="editor slim">
                <div class="grid">
                  <select v-model="addItemForm.type" class="input select">
                    <option value="note">笔记</option>
                    <option value="favorite">收藏</option>
                  </select>
                  <select v-model="addItemForm.itemId" class="input select">
                    <option disabled value="">选择要加入的内容</option>
                    <option v-for="item in availablePlanItems" :key="item.id" :value="item.id">
                      {{ addItemForm.type === 'favorite' ? getFavoriteTitle(item.id) : (item.title || `第${item.pageNum}页笔记`) }}
                    </option>
                  </select>
                </div>
                <div class="row actions">
                  <button class="btn primary" @click="addPlanItem">加入复习项</button>
                </div>
              </div>

              <div v-if="!planItems.length" class="empty">当前计划还没有复习项。</div>
              <div v-else class="note-list">
                <div v-for="item in planItems" :key="item.id" class="card compact">
                  <div class="card-top">
                    <div class="card-title">
                      {{ item.itemType === 'favorite' ? getFavoriteTitle(item.itemId) : getNoteContent(item.itemId) }}
                    </div>
                    <span class="pill">{{ item.itemType === 'favorite' ? '收藏' : '笔记' }}</span>
                  </div>
                  <div class="card-foot">
                    <span class="muted">优先级：{{ item.priority || '-' }}</span>
                    <span class="muted">复习次数：{{ item.reviewCount || 0 }}</span>
                    <span class="muted">最近复习：{{ formatDate(item.lastReviewedAt) || '-' }}</span>
                  </div>
                  <div class="row actions">
                    <button class="btn primary" @click="markReviewed(item)">标记已复习</button>
                    <button class="btn danger" @click="removePlanItem(item.id)">移除</button>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </section>

        <section v-else-if="activeTab === 'practice'" key="practice" class="panel">
          <div class="panel-head">
            <div class="head-left">
              <h3>练习记录</h3>
              <p>展示最近练习历史与错题，支持一键重做。</p>
            </div>
            <div class="head-right">
              <button class="btn ghost" @click="loadPracticeData">刷新</button>
            </div>
          </div>

          <div v-if="!practiceHistory.length && !wrongQuestions.length" class="empty-card">
            <div class="empty-title">暂无练习记录</div>
            <div class="empty-desc">先去「随堂练习」做题，结果会自动同步到这里。</div>
            <div class="empty-actions">
              <button class="btn primary" @click="jumpToClassroom">去课堂学习</button>
            </div>
          </div>

          <template v-else>
            <div class="subpanel">
              <div class="section-head">
                <h4>最近练习</h4>
                <span class="muted">共 {{ practiceHistory.length }} 条</span>
              </div>
              <div v-if="!practiceHistory.length" class="empty">暂无已提交练习。</div>
              <div v-else class="grid-2">
                <div v-for="item in practiceHistory" :key="item.taskId" class="card compact">
                  <div class="card-top">
                    <div class="card-title">任务 {{ item.taskId }}</div>
                    <span class="badge">{{ item.status === 'completed' ? '已完成' : '待完成' }}</span>
                  </div>
                  <div class="card-foot">
                    <span class="muted">页码：{{ item.pageNum || '-' }}</span>
                    <span class="muted">难度：{{ item.difficulty || '-' }}</span>
                    <span class="muted">提交：{{ formatDate(item.attempt?.submittedAt || item.createdAt) || '-' }}</span>
                  </div>
                  <div class="card-foot">
                    <span class="muted">正确：{{ item.attempt?.correctCount || 0 }}/{{ item.attempt?.totalCount || item.questionCount || item.questionCnt || 0 }}</span>
                    <span class="muted">得分：{{ item.attempt?.score || 0 }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="subpanel">
              <div class="section-head">
                <h4>错题列表</h4>
                <span class="muted">共 {{ wrongQuestions.length }} 题</span>
              </div>
              <div v-if="!wrongQuestions.length" class="empty">当前没有错题，继续保持。</div>
              <div v-else class="note-list">
                <div v-for="item in wrongQuestions" :key="item.recordId || item.questionId" class="card">
                  <div class="card-top">
                    <div class="card-title">{{ item.content || '未提供题干' }}</div>
                    <span class="pill">{{ item.questionType || '题目' }}</span>
                  </div>
                  <div class="card-body">
                    <div>你的答案：{{ item.userAnswer || '未作答' }}</div>
                    <div>正确答案：{{ item.correctAnswer || item.referenceAnswer || '主观题请查看解析' }}</div>
                    <div>解析：{{ item.explanation || item.aiComment || '暂无解析' }}</div>
                  </div>
                  <div class="row actions">
                    <button class="btn primary" @click="retryWrongQuestion(item.questionId)">重做本题</button>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </section>

        <section v-else-if="activeTab === 'tasks'" key="tasks" class="panel">
          <div class="panel-head">
            <div class="head-left">
              <h3>任务</h3>
              <p>个人任务 + 教师/系统下发任务统一收口，完成后会沉淀为你的学习记录。</p>
            </div>
            <div class="head-right">
              <select v-model="taskFilter" class="input select">
                <option value="all">全部</option>
                <option value="personal">个人</option>
                <option value="teacher">教师/系统</option>
                <option value="done">已完成</option>
              </select>
              <button class="btn primary" @click="openTaskEditor()">创建任务</button>
            </div>
          </div>

          <div v-if="showTaskEditor" class="editor">
            <div class="grid">
              <input v-model="taskForm.title" class="input" placeholder="任务名称（例如：复习 薄弱点-二次函数）" />
              <input v-model="taskForm.dueAt" class="input" type="datetime-local" />
            </div>
            <textarea v-model="taskForm.detail" class="input textarea" rows="3" placeholder="补充说明（可选）"></textarea>
            <div class="row actions">
              <button class="btn" @click="closeTaskEditor">取消</button>
              <button class="btn primary" @click="savePersonalTask">保存</button>
            </div>
          </div>

          <div v-if="!filteredTaskCards.length" class="empty-card">
            <div class="empty-title">暂无任务</div>
            <div class="empty-desc">你可以把复习计划拆成可执行任务，也可以等待教师发布练习/作业。</div>
            <div class="empty-actions">
              <button class="btn primary" @click="openTaskEditor()">创建一个任务</button>
            </div>
          </div>

          <div v-else class="task-list">
            <div
              v-for="task in filteredTaskCards"
              :key="task.id"
              class="card task-card"
              :class="{ overdue: isOverdue(task), done: task.status === 'done' }"
              draggable="true"
              @dragstart="onDragStart($event, { kind: 'personal_task', id: task.id })"
            >
              <div class="card-top">
                <div class="card-title">
                  <input type="checkbox" :checked="task.status === 'done'" @change="toggleTaskDone(task)" />
                  <span>{{ task.title }}</span>
                </div>
                <div class="card-actions">
                  <span class="pill" v-if="task.source === 'teacher'">教师/系统</span>
                  <span class="pill" v-else>个人</span>
                  <button class="icon-btn" v-if="task.source === 'personal'" @click="openTaskEditor(task)">编辑</button>
                  <button class="icon-btn danger" v-if="task.source === 'personal'" @click="deletePersonalTask(task)">删除</button>
                </div>
              </div>
              <div class="card-body" v-if="task.detail">{{ task.detail }}</div>
              <div class="card-foot">
                <span class="muted" v-if="task.dueAt">截止：{{ formatDate(task.dueAt) }}</span>
                <span class="muted" v-else>无截止时间</span>
              </div>
            </div>
          </div>

          <div class="subpanel">
            <div class="section-head">
              <h4>系统调度（后台任务）</h4>
              <button class="btn ghost" @click="loadTaskData">刷新</button>
            </div>
            <div v-if="!scheduledTasks.length" class="empty">暂无系统调度任务。</div>
            <div v-else class="grid-2">
              <div v-for="task in scheduledTasks" :key="task.id" class="card compact">
                <div class="card-top">
                  <div class="card-title">{{ formatTaskType(task.taskType) }}</div>
                  <span class="badge" :class="task.status">{{ task.status }}</span>
                </div>
                <div class="card-foot">
                  <span class="muted">计划：{{ formatDate(task.scheduledAt || task.nextAttempt) || '-' }}</span>
                </div>
                <div class="row actions">
                  <button class="btn" @click="executeTask(task.id)">立即执行</button>
                  <button class="btn danger" @click="deleteTask(task.id)">删除</button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section v-else key="placeholder" class="panel">
          <div class="panel-head">
            <div class="head-left">
              <h3>{{ tabs.find(t => t.key === activeTab)?.label }}</h3>
              <p>这一块我会按你给的设计逐步补齐（P1/P2）。现在先把 P0 的闭环做扎实。</p>
            </div>
          </div>
          <div class="empty-card">
            <div class="empty-title">即将上线</div>
            <div class="empty-desc">优先完成：笔记 / 收藏 / 任务 的联动与统一交互。</div>
          </div>
        </section>
      </transition>
    </main>

    <transition name="drawer-fade">
      <div v-if="noteDrawer.open" class="drawer-backdrop" @click.self="noteDrawer.open = false">
        <div class="drawer">
          <div class="drawer-head">
            <div>
              <div class="drawer-kicker">笔记详情</div>
              <div class="drawer-title">{{ resolveNoteTitle(noteDrawer.note) }}</div>
              <div class="drawer-meta">
                <span class="chip">{{ getCourseName(noteDrawer.note?.courseId) }}</span>
                <span class="muted">第 {{ noteDrawer.note?.pageNum || 1 }} 页</span>
                <span class="muted">{{ formatDate(noteDrawer.note?.createdAt) }}</span>
              </div>
            </div>
            <button class="icon-btn" @click="noteDrawer.open = false">关闭</button>
          </div>
          <textarea v-model="noteDrawer.content" class="input textarea" rows="10"></textarea>
          <div class="row actions">
            <button class="btn ghost" @click="noteDrawer.open = false">取消</button>
            <button class="btn primary" @click="saveNoteFromDrawer">保存修改</button>
          </div>
          <div class="drawer-tip">
            提示：你可以把这条笔记拖到「收藏看板」的任意列，快速归类到学习闭环里。
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script>
import { ElMessage } from 'element-plus'
import { studentCoursewareApi } from '@/services/v1/coursewareApi'
import { studentNotificationApi } from '@/services/v1/notificationApi'
import { studentTaskApi } from '@/services/v1/taskApi'

const emptyNoteForm = () => ({ courseId: '', pageNum: 1, content: '' })
const emptyPlanForm = () => ({ name: '', description: '', frequency: 'daily' })
const emptyAddItemForm = () => ({ type: 'note', itemId: '', priority: 3 })

export default {
  name: 'StudentPersonalCenter',
  props: {
    studentId: { type: String, required: true },
    courseId: { type: String, default: '' },
    currentCourseName: { type: String, default: '' },
    learningStats: { type: Object, default: null },
    weakPointTags: { type: Array, default: () => [] },
    initialTab: { type: String, default: 'notes' }
  },
  data() {
    return {
      activeTab: 'notes',
      tabs: [{ key: 'notes', label: '笔记' }, { key: 'favorites', label: '收藏' }, { key: 'plans', label: '复习计划' }, { key: 'practice', label: '练习记录' }, { key: 'notifications', label: '通知' }, { key: 'tasks', label: '任务' }],
      courses: [], notes: [], favorites: [], reviewPlans: [], planItems: [], practiceHistory: [], wrongQuestions: [], notifications: [], scheduledTasks: [], taskStatuses: [],
      unreadNotificationCount: 0, selectedTag: '', currentPlan: null, showNoteForm: false, showPlanForm: false, editingNote: null, editingPlan: null, editingFavorite: null, newTag: '',
      noteForm: emptyNoteForm(), planForm: emptyPlanForm(), addItemForm: emptyAddItemForm(),
      noteQuery: '',
      noteSort: 'time_desc',
      favoriteQuery: '',
      dragPayload: null,
      dragOverCol: '',
      noteDrawer: { open: false, note: null, content: '' },
      taskFilter: 'all',
      personalTasks: [],
      showTaskEditor: false,
      editingTaskId: '',
      taskForm: { title: '', detail: '', dueAt: '' },
      noteTitleMap: {},
      statsPanelVisible: false,
    }
  },
  computed: {
    avatarText() {
      const s = String(this.studentId || '学').trim()
      return (s.slice(0, 1) || '学').toUpperCase()
    },
    learningStatsSafe() {
      const base = this.learningStats && typeof this.learningStats === 'object' ? this.learningStats : {}
      return {
        focusScore: Number(base.focusScore || 0),
        masteryRate: Number(base.masteryRate || 0),
        totalQuestions: Number(base.totalQuestions || 0),
        weakPointCount: Number(base.weakPointCount || 0)
      }
    },
    weakPointTagsSafe() {
      return Array.isArray(this.weakPointTags) ? this.weakPointTags : []
    },
    masteryRateClamped() {
      const n = Number(this.learningStatsSafe.masteryRate)
      if (!Number.isFinite(n)) return 0
      return Math.min(100, Math.max(0, Math.round(n)))
    },
    availableTags() { return [...new Set(this.favorites.flatMap(item => item.tags || []))] },
    filteredFavorites() { return this.selectedTag ? this.favorites.filter(item => (item.tags || []).includes(this.selectedTag)) : this.favorites },
    availablePlanItems() { return this.addItemForm.type === 'favorite' ? this.favorites : this.notes },
    filteredNotes() {
      const q = String(this.noteQuery || '').trim().toLowerCase()
      const list = (this.notes || []).filter((n) => {
        if (!q) return true
        const courseName = this.getCourseName(n.courseId)
        const hay = `${this.resolveNoteTitle(n)} ${n.note || ''} ${courseName}`.toLowerCase()
        return hay.includes(q)
      })
      const sorted = [...list].sort((a, b) => {
        const at = new Date(a.createdAt || 0).getTime()
        const bt = new Date(b.createdAt || 0).getTime()
        return this.noteSort === 'time_asc' ? (at - bt) : (bt - at)
      })
      return sorted
    },
    favoriteColumns() {
      return [
        { key: 'to_learn', label: '待学习', icon: '📚' },
        { key: 'mastered', label: '已掌握', icon: '✅' },
        { key: 'weak', label: '薄弱点', icon: '⚠️' },
        { key: 'key', label: '重点难点', icon: '🎯' }
      ]
    },
    filteredTaskCards() {
      const cards = this.mergeTasks()
      if (this.taskFilter === 'personal') return cards.filter(t => t.source === 'personal' && t.status !== 'done')
      if (this.taskFilter === 'teacher') return cards.filter(t => t.source !== 'personal' && t.status !== 'done')
      if (this.taskFilter === 'done') return cards.filter(t => t.status === 'done')
      return cards
    },
    dueReminders() {
      const now = Date.now()
      const planReminders = this.reviewPlans.filter(item => item.status === 'active' && item.nextReviewDate && new Date(item.nextReviewDate).getTime() <= now).map(item => ({ key: `plan-${item.id}`, kind: 'plan', message: `复习计划“${item.name}”已到期`, plan: item }))
      const notificationReminders = this.notifications.filter(item => item.status !== 'read' && String(item.type || '').includes('review')).map(item => ({ key: `notification-${item.id}`, kind: 'notification', message: item.title, notification: item }))
      return [...planReminders, ...notificationReminders].slice(0, 5)
    }
  },
  async created() {
    this.applyInitialTab(this.initialTab)
    this.loadLocalNoteTitleMap()
    await this.loadData()
  },
  watch: {
    initialTab(next) {
      this.applyInitialTab(next)
    }
  },
  methods: {
    applyInitialTab(tab) {
      const safe = String(tab || '').trim()
      if (!safe) return
      const exists = this.tabs.some((item) => item.key === safe)
      if (!exists) return
      if (this.activeTab === safe) return
      this.activeTab = safe
    },
    switchTab(key) {
      if (this.activeTab === key) return
      this.activeTab = key
      this.dragOverCol = ''
      this.editingFavorite = null
      this.statsPanelVisible = false
      this.$nextTick(() => {
        const el = this.$refs.bodyEl
        if (!el) return
        el.scrollTop = 0
      })
    },
    toggleStatsPanel() {
      this.statsPanelVisible = !this.statsPanelVisible
    },
    tabCount(key) {
      if (key === 'notes') return (this.notes || []).length
      if (key === 'favorites') return (this.favorites || []).length
      if (key === 'plans') return (this.reviewPlans || []).length
      if (key === 'practice') return (this.practiceHistory || []).length
      if (key === 'notifications') return this.unreadNotificationCount
      if (key === 'tasks') return (this.mergeTasks() || []).filter(t => t.status !== 'done').length
      return null
    },
    async loadData() { await this.loadCollections(); await this.loadPracticeData(); await this.loadNotificationData(); await this.loadTaskData() },
    async loadCollections() {
      try {
        this.loadLocalNoteTitleMap()
        const [courseRes, notesRes, favRes, plansRes] = await Promise.all([studentCoursewareApi.list(), studentCoursewareApi.listNotes({ studentId: this.studentId, pageSize: 100 }), studentCoursewareApi.listFavorites({ studentId: this.studentId, pageSize: 100 }), studentCoursewareApi.listReviewPlans(this.studentId)])
        this.courses = courseRes.data || []
        this.notes = (notesRes.data && notesRes.data.items) || []
        this.favorites = (((favRes.data && favRes.data.items) || [])).map(item => ({ ...item, tags: this.parseFavoriteTags(item.tags) }))
        this.reviewPlans = plansRes.data || []
        this.loadFavoriteBoardState()
      } catch (error) { ElMessage.error(`加载个人资料失败：${error.message}`) }
    },
    async loadPracticeData() {
      try {
        const [historyRes, wrongRes] = await Promise.all([studentCoursewareApi.getPracticeHistory({ studentId: this.studentId, pageSize: 20 }), studentCoursewareApi.getWrongQuestions({ studentId: this.studentId, pageSize: 20 })])
        this.practiceHistory = historyRes.data.items || []
        this.wrongQuestions = wrongRes.data.items || []
      } catch (error) { ElMessage.error(`加载练习数据失败：${error.message}`) }
    },
    async loadNotificationData() {
      try {
        const [listRes, countRes] = await Promise.all([studentNotificationApi.list({ studentId: this.studentId, pageSize: 20 }), studentNotificationApi.getUnreadCount(this.studentId)])
        this.notifications = listRes.data.list || []
        this.unreadNotificationCount = (countRes.data && countRes.data.unreadCount) || 0
      } catch (error) { ElMessage.error(`加载通知失败：${error.message}`) }
    },
    async loadTaskData() {
      try {
        const [taskRes, statusRes] = await Promise.all([studentTaskApi.listScheduled({ studentId: this.studentId, pageSize: 20 }), studentTaskApi.listStatuses({ studentId: this.studentId, pageSize: 20 })])
        this.scheduledTasks = taskRes.data.list || []
        this.taskStatuses = statusRes.data.list || []
        this.loadPersonalTasks()
      } catch (error) { ElMessage.error(`加载任务失败：${error.message}`) }
    },
    startNoteEdit(note = null) { this.editingNote = note; this.noteForm = note ? { courseId: note.courseId, pageNum: note.pageNum, content: note.note } : emptyNoteForm(); this.showNoteForm = true },
    cancelNoteEdit() { this.showNoteForm = false; this.editingNote = null; this.noteForm = emptyNoteForm() },
    async saveNote() {
      if (!this.noteForm.courseId || !this.noteForm.content) return ElMessage.warning('请先填写课程和笔记内容')
      try {
        if (this.editingNote) await studentCoursewareApi.deleteNote(this.editingNote.id, this.studentId)
        await studentCoursewareApi.saveNote({ studentId: this.studentId, courseId: this.noteForm.courseId, pageNum: this.noteForm.pageNum, content: this.noteForm.content })
        this.cancelNoteEdit()
        await this.loadCollections()
        ElMessage.success('笔记已保存')
      } catch (error) { ElMessage.error(`保存笔记失败：${error.message}`) }
    },
    async deleteNote(id) { if (!window.confirm('确认删除这条笔记吗？')) return; try { await studentCoursewareApi.deleteNote(id, this.studentId); await this.loadCollections(); ElMessage.success('笔记已删除') } catch (error) { ElMessage.error(`删除笔记失败：${error.message}`) } },
    startFavoriteEdit(favorite) { this.editingFavorite = { ...favorite, tags: [...(favorite.tags || [])] }; this.newTag = '' },
    cancelFavoriteEdit() { this.editingFavorite = null; this.newTag = '' },
    addTag() { const tag = this.newTag.trim(); if (tag && !this.editingFavorite.tags.includes(tag)) this.editingFavorite.tags.push(tag); this.newTag = '' },
    removeTag(tag) { this.editingFavorite.tags = this.editingFavorite.tags.filter(item => item !== tag) },
    async saveTags() {
      try {
        await studentCoursewareApi.addFavorite({ studentId: this.studentId, courseId: this.editingFavorite.courseId, nodeId: this.editingFavorite.nodeId, pageNum: this.editingFavorite.pageNum, title: this.editingFavorite.title, tags: this.editingFavorite.tags })
        this.cancelFavoriteEdit(); await this.loadCollections(); ElMessage.success('标签已更新')
      } catch (error) { ElMessage.error(`保存标签失败：${error.message}`) }
    },
    async deleteFavorite(id) { if (!window.confirm('确认删除这条收藏吗？')) return; try { await studentCoursewareApi.deleteFavorite(id); await this.loadCollections(); ElMessage.success('收藏已删除') } catch (error) { ElMessage.error(`删除收藏失败：${error.message}`) } },
    startPlanEdit(plan = null) { this.editingPlan = plan; this.planForm = plan ? { name: plan.name, description: plan.description, frequency: plan.frequency } : emptyPlanForm(); this.showPlanForm = true },
    async savePlan() {
      if (!this.planForm.name) return ElMessage.warning('请先填写计划名称')
      try {
        if (this.editingPlan) await studentCoursewareApi.updateReviewPlan(this.editingPlan.id, this.planForm)
        else await studentCoursewareApi.createReviewPlan({ studentId: this.studentId, ...this.planForm })
        this.showPlanForm = false; this.editingPlan = null; this.planForm = emptyPlanForm(); await this.loadCollections(); ElMessage.success('复习计划已保存')
      } catch (error) { ElMessage.error(`保存计划失败：${error.message}`) }
    },
    async deletePlan(id) { if (!window.confirm('确认删除这条复习计划吗？')) return; try { await studentCoursewareApi.deleteReviewPlan(id); if (this.currentPlan && this.currentPlan.id === id) this.currentPlan = null; await this.loadCollections(); ElMessage.success('计划已删除') } catch (error) { ElMessage.error(`删除计划失败：${error.message}`) } },
    async viewPlanItems(plan) { try { const res = await studentCoursewareApi.listReviewPlanItems(plan.id); this.currentPlan = plan; this.planItems = res.data || [] } catch (error) { ElMessage.error(`加载复习项失败：${error.message}`) } },
    async addPlanItem() {
      if (!this.currentPlan || !this.addItemForm.itemId) return ElMessage.warning('请先选择要加入的内容')
      try {
        await studentCoursewareApi.addReviewPlanItem({ reviewPlanId: this.currentPlan.id, itemType: this.addItemForm.type, itemId: this.addItemForm.itemId, priority: this.addItemForm.priority })
        this.addItemForm = emptyAddItemForm(); await this.viewPlanItems(this.currentPlan); ElMessage.success('复习项已添加')
      } catch (error) { ElMessage.error(`添加复习项失败：${error.message}`) }
    },
    async markReviewed(item) { try { await studentCoursewareApi.updateReviewPlanItem(item.id, { lastReviewedAt: new Date().toISOString(), reviewCount: (item.reviewCount || 0) + 1 }); await this.viewPlanItems(this.currentPlan); await this.loadCollections(); ElMessage.success('已标记复习') } catch (error) { ElMessage.error(`标记复习失败：${error.message}`) } },
    async removePlanItem(id) { try { await studentCoursewareApi.deleteReviewPlanItem(id); await this.viewPlanItems(this.currentPlan); ElMessage.success('复习项已移除') } catch (error) { ElMessage.error(`移除复习项失败：${error.message}`) } },
    async retryWrongQuestion(questionId) { try { const res = await studentCoursewareApi.retryWrongQuestion({ questionId, studentId: this.studentId }); ElMessage.success(`已生成重做任务 ${res.data.taskId}`); await this.loadPracticeData() } catch (error) { ElMessage.error(`生成重做任务失败：${error.message}`) } },
    async markNotificationRead(item) { if (item.status === 'read') return; try { await studentNotificationApi.markAsRead(item.id); await this.loadNotificationData(); ElMessage.success('通知已标记为已读') } catch (error) { ElMessage.error(`处理通知失败：${error.message}`) } },
    async markAllNotificationsRead() { try { await studentNotificationApi.markAllAsRead(this.studentId); await this.loadNotificationData(); ElMessage.success('全部通知已读') } catch (error) { ElMessage.error(`批量已读失败：${error.message}`) } },
    async deleteNotification(id) { if (!window.confirm('确认删除这条通知吗？')) return; try { await studentNotificationApi.remove(id); await this.loadNotificationData(); await this.loadTaskData(); ElMessage.success('通知已删除') } catch (error) { ElMessage.error(`删除通知失败：${error.message}`) } },
    async executeTask(id) { try { await studentTaskApi.executeNow(id); await this.loadTaskData(); await this.loadNotificationData(); ElMessage.success('任务已提交执行') } catch (error) { ElMessage.error(`执行任务失败：${error.message}`) } },
    async deleteTask(id) { if (!window.confirm('确认删除这条任务吗？')) return; try { await studentTaskApi.remove(id); await this.loadTaskData(); ElMessage.success('任务已删除') } catch (error) { ElMessage.error(`删除任务失败：${error.message}`) } },
    async openReminder(item) { if (item.kind === 'plan') return this.viewPlanItems(item.plan); await this.markNotificationRead(item.notification) },
    parseFavoriteTags(raw) { if (Array.isArray(raw)) return raw; if (!raw) return []; try { const parsed = JSON.parse(raw); return Array.isArray(parsed) ? parsed : [] } catch (error) { return [] } },
    noteTitleMapKey() { return `fuww_student_note_title_map:${String(this.studentId || '').trim().toLowerCase()}` },
    loadLocalNoteTitleMap() {
      this.noteTitleMap = {}
      if (typeof window === 'undefined') return
      try {
        const parsed = JSON.parse(window.localStorage.getItem(this.noteTitleMapKey()) || '{}')
        if (parsed && typeof parsed === 'object') this.noteTitleMap = parsed
      } catch (error) {
        this.noteTitleMap = {}
      }
    },
    resolveNoteTitle(note) {
      if (!note) return '课堂笔记'
      if (note.title) return note.title
      const key = `${note.courseId || ''}::${note.pageNum || ''}`
      const mapped = this.noteTitleMap?.[key]
      if (mapped) return mapped
      return `第${note.pageNum || 1}页笔记`
    },
    getCourseName(id) { const target = this.courses.find(item => item.id === id); return (target && target.title) || id || '未关联课程' },
    getNoteContent(id) { const target = this.notes.find(item => item.id === id); return (target && target.note) || '未找到笔记' },
    getFavoriteTitle(id) { const target = this.favorites.find(item => item.id === id); return (target && target.title) || '未找到收藏' },
    formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN') : '' },
    formatFrequency(value) { return { daily: '每日', weekly: '每周', monthly: '每月' }[value] || value || '-' },
    formatPlanStatus(value) { return { active: '进行中', paused: '暂停', completed: '已完成' }[value] || value || '-' },
    formatNotificationType(value) { return { system: '系统通知', review_reminder: '复习提醒', practice: '练习通知' }[value] || value || '普通通知' },
    formatNotificationStatus(value) { return { unread: '未读', read: '已读', scheduled: '待发送', sent: '已发送' }[value] || value || '-' },
    formatTaskType(value) { return { review_reminder: '复习提醒', practice_generation: '练习生成', notification: '通知发送' }[value] || value || '通用任务' },

    jumpToClassroom() { this.$emit && this.$emit('jump-classroom') },
    jumpToAnalytics() { this.$emit && this.$emit('jump-analytics') },

    openNoteDrawer(note) {
      if (!note) return
      this.noteDrawer.note = note
      this.noteDrawer.content = note.note || ''
      this.noteDrawer.open = true
    },
    async saveNoteFromDrawer() {
      const note = this.noteDrawer.note
      if (!note) return
      const content = String(this.noteDrawer.content || '').trim()
      if (!content) return ElMessage.warning('笔记内容不能为空')
      try {
        await studentCoursewareApi.deleteNote(note.id, this.studentId)
        await studentCoursewareApi.saveNote({ studentId: this.studentId, courseId: note.courseId, pageNum: note.pageNum, content })
        this.noteDrawer.open = false
        await this.loadCollections()
        ElMessage.success('笔记已更新')
      } catch (error) {
        ElMessage.error(`更新笔记失败：${error.message}`)
      }
    },

    onDragStart(event, payload) {
      this.dragPayload = payload
      try {
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData('application/json', JSON.stringify(payload))
      } catch (e) {
        // ignore
      }
    },
    readDragPayload() {
      if (this.dragPayload) return this.dragPayload
      try {
        // eslint-disable-next-line no-undef
        const raw = event?.dataTransfer?.getData?.('application/json') || ''
        return raw ? JSON.parse(raw) : null
      } catch (e) {
        return null
      }
    },

    favoritesByCol(colKey) {
      const q = String(this.favoriteQuery || '').trim().toLowerCase()
      const list = (this.favorites || []).filter((fav) => this.getFavoriteCol(fav.id) === colKey)
      if (!q) return list
      return list.filter((fav) => {
        const course = this.getCourseName(fav.courseId)
        const tags = (fav.tags || []).join(' ')
        const hay = `${fav.title || ''} ${course} ${tags}`.toLowerCase()
        return hay.includes(q)
      })
    },
    boardStateKey() { return `fuww_student_favorite_board:${String(this.studentId || '')}` },
    getFavoriteCol(favId) {
      const map = this._favoriteBoardMap || {}
      return map[favId] || 'to_learn'
    },
    setFavoriteCol(favId, colKey) {
      if (!this._favoriteBoardMap) this._favoriteBoardMap = {}
      this._favoriteBoardMap[favId] = colKey
      try {
        window.localStorage.setItem(this.boardStateKey(), JSON.stringify(this._favoriteBoardMap))
      } catch (e) {
        // ignore
      }
    },
    loadFavoriteBoardState() {
      this._favoriteBoardMap = {}
      if (typeof window === 'undefined') return
      try {
        const parsed = JSON.parse(window.localStorage.getItem(this.boardStateKey()) || '{}')
        if (parsed && typeof parsed === 'object') this._favoriteBoardMap = parsed
      } catch (e) {
        this._favoriteBoardMap = {}
      }
    },
    resetFavoriteBoard() {
      if (!window.confirm('确认重置收藏看板状态吗？')) return
      this._favoriteBoardMap = {}
      try {
        window.localStorage.removeItem(this.boardStateKey())
      } catch (e) {
        console.error('Failed to reset favorite board:', e)
      }
      ElMessage.success('看板已重置')
    },
    async onDropToFavoriteCol(colKey) {
      const payload = this.dragPayload
      this.dragPayload = null
      this.dragOverCol = ''
      if (!payload) return
      if (payload.kind === 'favorite') {
        this.setFavoriteCol(payload.id, colKey)
        return
      }
      if (payload.kind === 'note') {
        await this.createFavoriteFromNote(payload.id, colKey)
        return
      }
    },
    favoriteMatchesWeakPoint(fav) {
      const names = (this.weakPointTagsSafe || []).map(w => String(w.name || '').trim()).filter(Boolean)
      if (!names.length || !fav) return false
      const hay = [
        fav.title,
        ...(Array.isArray(fav.tags) ? fav.tags : []),
        this.getCourseName(fav.courseId)
      ]
        .map(s => String(s || '').toLowerCase())
        .join(' ')
      return names.some((n) => {
        const t = n.toLowerCase()
        if (t.length < 2) return false
        return hay.includes(t) || hay.includes(t.slice(0, Math.min(t.length, 6)))
      })
    },
    getMasteryForFavorite(fav) {
      const col = this.getFavoriteCol(fav.id)
      const globalM = this.masteryRateClamped
      let base = 55
      if (col === 'mastered') base = 86
      else if (col === 'weak') base = 40
      else if (col === 'key') base = 64
      else if (col === 'to_learn') base = 52
      if (this.favoriteMatchesWeakPoint(fav)) base -= 16
      const blended = Math.round(base * 0.65 + globalM * 0.35)
      return Math.min(98, Math.max(8, blended))
    },

    personalTaskKey() { return `fuww_student_personal_tasks:${String(this.studentId || '')}` },
    loadPersonalTasks() {
      this.personalTasks = []
      if (typeof window === 'undefined') return
      try {
        const parsed = JSON.parse(window.localStorage.getItem(this.personalTaskKey()) || '[]')
        this.personalTasks = Array.isArray(parsed) ? parsed : []
      } catch (e) {
        this.personalTasks = []
      }
    },
    persistPersonalTasks() {
      if (typeof window === 'undefined') return
      try {
        window.localStorage.setItem(this.personalTaskKey(), JSON.stringify(this.personalTasks))
      } catch (e) {
        console.error('Failed to persist personal tasks:', e)
      }
    },
    mergeTasks() {
      const personal = (this.personalTasks || []).map(t => ({ ...t, source: 'personal' }))
      const teacher = (this.notifications || [])
        .filter(n => String(n.type || '').includes('practice') || String(n.type || '').includes('task'))
        .map(n => ({
          id: `teacher:${n.id}`,
          title: n.title || '教师任务',
          detail: n.content || '',
          dueAt: n.scheduledAt || n.createdAt || '',
          status: n.status === 'read' ? 'done' : 'todo',
          source: 'teacher'
        }))
      const all = [...personal, ...teacher]
      return all.sort((a, b) => {
        const ad = a.status === 'done' ? 1 : 0
        const bd = b.status === 'done' ? 1 : 0
        if (ad !== bd) return ad - bd
        const at = new Date(a.dueAt || 0).getTime()
        const bt = new Date(b.dueAt || 0).getTime()
        return bt - at
      })
    },
    openTaskEditor(task = null) {
      this.showTaskEditor = true
      this.editingTaskId = task && task.source === 'personal' ? task.id : ''
      this.taskForm = {
        title: task?.title || '',
        detail: task?.detail || '',
        dueAt: task?.dueAt ? this.toDatetimeLocal(task.dueAt) : ''
      }
    },
    closeTaskEditor() {
      this.showTaskEditor = false
      this.editingTaskId = ''
      this.taskForm = { title: '', detail: '', dueAt: '' }
    },
    toDatetimeLocal(value) {
      if (!value) return ''
      const d = new Date(value)
      if (Number.isNaN(d.getTime())) return ''
      const pad = (n) => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
    },
    savePersonalTask() {
      const title = String(this.taskForm.title || '').trim()
      if (!title) return ElMessage.warning('请填写任务名称')
      const now = new Date().toISOString()
      const dueAt = this.taskForm.dueAt ? new Date(this.taskForm.dueAt).toISOString() : ''
      if (this.editingTaskId) {
        this.personalTasks = this.personalTasks.map(t => t.id === this.editingTaskId ? { ...t, title, detail: this.taskForm.detail || '', dueAt } : t)
      } else {
        const id = `p-${Date.now()}-${Math.random().toString(16).slice(2)}`
        this.personalTasks.unshift({ id, title, detail: this.taskForm.detail || '', dueAt, status: 'todo', createdAt: now })
      }
      this.persistPersonalTasks()
      this.closeTaskEditor()
      ElMessage.success('任务已保存')
    },
    deletePersonalTask(task) {
      if (!window.confirm('确认删除该任务吗？')) return
      this.personalTasks = this.personalTasks.filter(t => t.id !== task.id)
      this.persistPersonalTasks()
      ElMessage.success('任务已删除')
    },
    toggleTaskDone(task) {
      if (task.source !== 'personal') return
      const next = task.status === 'done' ? 'todo' : 'done'
      this.personalTasks = this.personalTasks.map(t => t.id === task.id ? { ...t, status: next } : t)
      this.persistPersonalTasks()
    },
    isOverdue(task) {
      if (!task?.dueAt || task.status === 'done') return false
      const t = new Date(task.dueAt).getTime()
      return Number.isFinite(t) && t < Date.now()
    },
    createQuickTaskFromNote(noteId, colKey) {
      const note = (this.notes || []).find(n => n.id === noteId)
      const title = note ? `归类笔记：${this.getCourseName(note.courseId)} 第${note.pageNum}页` : '处理拖拽笔记'
      const detail = note ? String(note.note || '').slice(0, 120) : ''
      const id = `p-${Date.now()}-${Math.random().toString(16).slice(2)}`
      this.personalTasks.unshift({
        id,
        title,
        detail: `${detail}\n\n（来自笔记拖拽 → 收藏列：${colKey}）`.trim(),
        dueAt: '',
        status: 'todo',
        createdAt: new Date().toISOString()
      })
      this.persistPersonalTasks()
    },
    colKeyToStatusTag(colKey) {
      return {
        to_learn: '待学习',
        mastered: '已掌握',
        weak: '薄弱点',
        key: '重点难点'
      }[colKey] || colKey
    },
    async createFavoriteFromNote(noteId, colKey) {
      const note = (this.notes || []).find(n => n.id === noteId)
      if (!note) return ElMessage.warning('未找到该笔记，无法创建收藏')
      const statusTag = this.colKeyToStatusTag(colKey)
      const title = note.title || `笔记：第${note.pageNum}页`
      try {
        await studentCoursewareApi.addFavorite({
          studentId: this.studentId,
          courseId: note.courseId,
          nodeId: note.nodeId || null,
          pageNum: note.pageNum || 1,
          title,
          tags: [statusTag, '来自笔记']
        })
        await this.loadCollections()
        const matched = (this.favorites || [])
          .filter(f => f.courseId === note.courseId && Number(f.pageNum || 0) === Number(note.pageNum || 0))
          .sort((a, b) => new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime())[0]
        if (matched?.id) this.setFavoriteCol(matched.id, colKey)
        ElMessage.success(`已将笔记同步为收藏，并归类到「${statusTag}」`)
      } catch (error) {
        this.createQuickTaskFromNote(noteId, colKey)
        ElMessage.warning(`收藏同步失败，已先生成待办任务兜底：${error.message}`)
      }
    },
    async ensureDefaultReviewPlan() {
      if (Array.isArray(this.reviewPlans) && this.reviewPlans.length) return this.reviewPlans[0]
      await studentCoursewareApi.createReviewPlan({
        studentId: this.studentId,
        name: '智能复习清单',
        description: '从收藏/笔记一键加入，形成计划→任务→执行→复盘闭环。',
        frequency: 'daily'
      })
      await this.loadCollections()
      return (this.reviewPlans || [])[0] || null
    },
    async quickAddFavoriteToPlan(fav) {
      if (!fav?.id) return
      try {
        const plan = await this.ensureDefaultReviewPlan()
        if (!plan?.id) return ElMessage.warning('暂无可用复习计划，请稍后重试')
        await studentCoursewareApi.addReviewPlanItem({
          reviewPlanId: plan.id,
          itemType: 'favorite',
          itemId: fav.id,
          priority: 3
        })
        ElMessage.success(`已加入复习计划「${plan.name || '智能复习清单'}」`)
      } catch (error) {
        ElMessage.error(`加入复习计划失败：${error.message}`)
      }
    }
  }
}
</script>

<style scoped>
.pc-shell { display: grid; gap: 14px; padding: 16px; color: #1E293B; background: #F5F7FA; }
.pc-fixed-region {
  position: sticky;
  top: 8px;
  z-index: 12;
  display: grid;
  gap: 10px;
  background: #F5F7FA;
  backface-visibility: hidden;
  transform: translateZ(0);
}
.pc-top { min-height: 176px; background: #FFFFFF; border: 1px solid rgba(226,232,240,0.95); border-radius: 16px; padding: 14px 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); display: grid; gap: 12px; overflow: visible; }
.pc-identity { display: flex; gap: 12px; align-items: center; }
.avatar { width: 52px; height: 52px; border-radius: 16px; background: linear-gradient(135deg, #2f605a 0%, #4d8a80 100%); color: #fff; display: grid; place-items: center; font-size: 20px; font-weight: 800; box-shadow: 0 8px 30px rgba(47, 96, 90, 0.18); }
.id-meta { min-width: 0; }
.title-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.title-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.title-row h2 { margin: 0; font-size: 20px; }
.subtitle { margin: 6px 0 0; color: #64748B; font-size: 13px; }
.stats-toggle-btn {
  border: 1px solid rgba(226,232,240,0.95);
  background: #FFFFFF;
  color: #334155;
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.18s ease-out, border-color 0.2s ease-out, box-shadow 0.2s ease-out;
}
.stats-toggle-btn:hover { transform: translateY(-1px); border-color: rgba(47, 96, 90, 0.35); box-shadow: 0 6px 18px rgba(47, 96, 90, 0.08); }
.stats-toggle-btn:active { transform: scale(0.97); }
.pc-stats-popover {
  position: absolute;
  top: 64px;
  right: 16px;
  width: min(420px, calc(100% - 32px));
  border: 1px solid rgba(226,232,240,0.95);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(8px);
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.metric { border: 1px solid rgba(226,232,240,0.9); background: #F8FAFC; border-radius: 12px; padding: 10px 12px; }
.metric-label { font-size: 12px; color: #64748B; font-weight: 600; letter-spacing: 0.02em; }
.metric-value { margin-top: 4px; font-size: 18px; font-weight: 800; color: #1E293B; }

.stats-pop-enter-active,
.stats-pop-leave-active { transition: all 0.2s ease-out; }
.stats-pop-enter-from,
.stats-pop-leave-to { opacity: 0; transform: translateY(-6px); }

.pc-learning-viz {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.mastery-row {
  border: 1px solid rgba(226,232,240,0.95);
  background: #F8FAFC;
  border-radius: 12px;
  padding: 12px 14px;
  display: grid;
  gap: 8px;
}
.mastery-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.mastery-title { font-size: 13px; font-weight: 600; color: #64748B; }
.mastery-pct { font-size: 16px; font-weight: 800; color: #1E293B; }
.mastery-track {
  height: 10px;
  border-radius: 999px;
  background: rgba(226,232,240,0.95);
  overflow: hidden;
}
.mastery-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #2f605a 0%, #4d8a80 100%);
  transition: width 0.35s ease-out;
}
.mastery-hint { margin: 0; font-size: 12px; color: #64748B; line-height: 1.5; }

.weak-row {
  border: 1px solid rgba(226,232,240,0.95);
  background: #FFFFFF;
  border-radius: 12px;
  padding: 12px 14px;
  display: grid;
  gap: 10px;
}
.weak-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.weak-title { font-size: 13px; font-weight: 600; color: #334155; }
.btn-compact { padding: 7px 10px; font-size: 12px; border-radius: 8px; }
.weak-empty { margin: 0; font-size: 12px; color: #64748B; }
.weak-chips { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.weak-chip {
  border: 1px solid rgba(226,232,240,0.95);
  background: #F8FAFC;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 10px;
  border-radius: 999px;
  cursor: pointer;
  transition: transform 0.15s ease-out, border-color 0.2s ease-out, box-shadow 0.2s ease-out;
}
.weak-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(47, 96, 90, 0.3);
  box-shadow: 0 4px 14px rgba(47, 96, 90, 0.08);
}
.weak-chip:active { transform: scale(0.97); }
.weak-more { font-size: 12px; color: #64748B; font-weight: 600; }

@media (max-width: 900px) {
  .pc-learning-viz { grid-template-columns: 1fr; }
}

.pc-banner { border-radius: 16px; border: 1px solid rgba(226,232,240,0.95); background: #FFFFFF; padding: 12px; display: grid; gap: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); }
.banner-item { display: flex; justify-content: space-between; gap: 10px; align-items: center; }
.banner-text { color: #334155; font-weight: 600; }

.pc-tabs { display: flex; flex-wrap: wrap; gap: 6px; padding: 4px 0 2px; }
.tab { width: 96px; height: 32px; border: 1px solid rgba(226,232,240,0.95); background: #FFFFFF; border-radius: 11px; padding: 0 8px; cursor: pointer; display: inline-flex; justify-content: center; gap: 5px; align-items: center; font-size: 11px; font-weight: 600; transition: transform 0.16s ease-out, box-shadow 0.18s ease-out, border-color 0.18s ease-out, background 0.18s ease-out; }
.tab:hover { transform: translateY(-1px); border-color: rgba(47, 96, 90, 0.32); box-shadow: 0 4px 12px rgba(47, 96, 90, 0.08); }
.tab:active { transform: translateY(0) scale(0.97); }
.tab.active { background: #2f605a; color: #fff; border-color: #2f605a; box-shadow: 0 4px 12px rgba(47, 96, 90, 0.14); }
.tab-label { line-height: 1; }
.tab-count { background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.22); padding: 1px 5px; border-radius: 999px; font-size: 10px; font-weight: 800; }
.tab:not(.active) .tab-count { background: #F8FAFC; border-color: rgba(226,232,240,0.95); color: #334155; }

.pc-body { min-height: 240px; max-height: calc(100vh - 280px); overflow: auto; scroll-behavior: auto; padding-bottom: 2px; }
.panel { background: #FFFFFF; border: 1px solid rgba(226,232,240,0.95); border-radius: 16px; padding: 14px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); display: grid; gap: 12px; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.head-left h3 { margin: 0; font-size: 16px; color: #1E293B; }
.head-left p { margin: 6px 0 0; color: #64748B; font-size: 13px; }
.head-right { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }

.input { border: 1px solid rgba(226,232,240,0.95); background: #FFFFFF; border-radius: 12px; padding: 10px 12px; font: inherit; color: #334155; }
.input.select { padding-right: 34px; }
.input.textarea { resize: vertical; }
.btn { border: 1px solid rgba(226,232,240,0.95); background: #FFFFFF; border-radius: 12px; padding: 9px 12px; cursor: pointer; font: inherit; transition: transform 0.2s ease-out, box-shadow 0.2s ease-out, border-color 0.2s ease-out, background 0.2s ease-out; }
.btn:hover { transform: translateY(-2px) scale(1.01); border-color: rgba(47, 96, 90, 0.35); box-shadow: 0 8px 30px rgba(47, 96, 90, 0.08); }
.btn:active { transform: translateY(0) scale(0.97); }
.btn.primary { background: #2f605a; color: #fff; border-color: #2f605a; }
.btn.ghost { background: transparent; }
.btn.danger, .icon-btn.danger { border-color: rgba(239, 68, 68, 0.35); color: #b91c1c; }

.editor { padding: 12px; border-radius: 16px; background: #F8FAFC; border: 1px solid rgba(226,232,240,0.95); display: grid; gap: 10px; }
.editor .grid { display: grid; grid-template-columns: 1fr 140px; gap: 10px; }
.row.actions { display: flex; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }

.card { border: 1px solid rgba(226,232,240,0.95); background: #FFFFFF; border-radius: 16px; padding: 12px; display: grid; gap: 10px; transition: transform 0.2s ease-out, box-shadow 0.2s ease-out, border-color 0.2s ease-out; }
.card:hover { transform: translateY(-4px) scale(1.01); border-color: rgba(47, 96, 90, 0.22); box-shadow: 0 8px 30px rgba(47, 96, 90, 0.08); }
.card-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.card-title { font-weight: 800; color: #1E293B; display: flex; align-items: center; gap: 10px; min-width: 0; }
.card-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.icon-btn { border: 1px solid rgba(226,232,240,0.95); background: #FFFFFF; border-radius: 999px; padding: 6px 10px; cursor: pointer; font-size: 12px; color: #334155; transition: transform 0.15s ease-out, background 0.2s ease-out, border-color 0.2s ease-out; }
.icon-btn:hover { transform: scale(1.03); border-color: rgba(47, 96, 90, 0.25); }
.icon-btn:active { transform: scale(0.97); }
.card-body { color: #334155; font-size: 13px; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.card-foot { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; color: #64748B; font-size: 12px; }
.muted { color: #64748B; }
.pill { display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 999px; border: 1px solid rgba(226,232,240,0.95); background: #F8FAFC; color: #334155; font-size: 12px; font-weight: 700; }
.chip { display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 999px; background: #F8FAFC; border: 1px solid rgba(226,232,240,0.95); color: #334155; font-size: 12px; font-weight: 600; }
.chip.muted { color: #64748B; }
.chip.removable { cursor: pointer; }

.empty-card { border: 1px dashed rgba(226,232,240,0.95); border-radius: 16px; padding: 18px; background: #FFFFFF; text-align: center; display: grid; gap: 10px; }
.empty-title { font-weight: 800; color: #1E293B; }
.empty-desc { color: #64748B; font-size: 13px; }
.empty-actions { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }

.note-list { display: grid; gap: 10px; }

.board { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; align-items: start; }
.board-col { border: 1px solid rgba(226,232,240,0.95); background: #FFFFFF; border-radius: 16px; padding: 10px; min-height: 280px; display: grid; gap: 10px; }
.board-col.dragging { box-shadow: 0 0 0 3px rgba(47, 96, 90, 0.18); border-color: #2f605a; }
.col-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.col-title { display: inline-flex; gap: 8px; align-items: center; font-weight: 800; color: #1E293B; }
.col-count { font-weight: 800; color: #334155; background: #F8FAFC; border: 1px solid rgba(226,232,240,0.95); border-radius: 999px; padding: 2px 10px; }
.col-empty { border: 1px dashed rgba(226,232,240,0.95); border-radius: 16px; padding: 12px; color: #64748B; background: #F8FAFC; }
.col-list { display: grid; gap: 10px; }

.progress { display: flex; align-items: center; gap: 8px; }
.progress-bar { height: 8px; background: rgba(226,232,240,0.9); border-radius: 999px; overflow: hidden; flex: 1; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #2f605a 0%, #0284c7 100%); border-radius: inherit; }
.progress-meta { font-size: 12px; font-weight: 800; color: #1E293B; width: 42px; text-align: right; }
.tag-row { display: flex; gap: 8px; flex-wrap: wrap; }

.task-list { display: grid; gap: 10px; }
.task-card.overdue { border-color: rgba(239, 68, 68, 0.35); }
.task-card.done { opacity: 0.78; }

.subpanel { margin-top: 12px; border-top: 1px solid rgba(217,231,223,0.9); padding-top: 12px; display: grid; gap: 10px; }
.section-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
.compact { gap: 8px; }
.badge { display: inline-flex; align-items: center; border-radius: 999px; padding: 3px 10px; font-size: 12px; background: #eef5f1; color: #2f605a; border: 1px solid rgba(209,226,218,0.9); font-weight: 800; }

.drawer-backdrop { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.18); backdrop-filter: blur(6px); z-index: 50; display: grid; place-items: center; padding: 14px; }
.drawer { width: min(720px, 96vw); max-height: min(82vh, 860px); overflow: auto; border-radius: 18px; background: rgba(255,255,255,0.96); border: 1px solid rgba(217,231,223,0.95); box-shadow: 0 24px 54px rgba(15, 23, 42, 0.18); padding: 14px; display: grid; gap: 10px; }
.drawer-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.drawer-kicker { font-size: 12px; color: #6a8278; font-weight: 900; letter-spacing: 0.06em; text-transform: uppercase; }
.drawer-title { margin-top: 4px; font-size: 18px; font-weight: 900; color: #23463f; }
.drawer-meta { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.drawer-tip { color: #6b7f75; font-size: 12px; }

.pc-fade-slide-enter-active, .pc-fade-slide-leave-active { transition: opacity 0.18s ease-out; }
.pc-fade-slide-enter-from, .pc-fade-slide-leave-to { opacity: 0; }

.drawer-fade-enter-active, .drawer-fade-leave-active { transition: opacity 0.22s ease; }
.drawer-fade-enter-from, .drawer-fade-leave-to { opacity: 0; }

@media (max-width: 1100px) {
  .pc-fixed-region { top: 6px; }
  .pc-stats-popover { grid-template-columns: repeat(2, minmax(0, 1fr)); width: min(360px, calc(100% - 20px)); right: 10px; top: 58px; }
  .board { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .pc-stats-popover { grid-template-columns: 1fr; width: calc(100% - 16px); right: 8px; }
  .board { grid-template-columns: 1fr; }
  .editor .grid { grid-template-columns: 1fr; }
  .banner-item { flex-direction: column; align-items: flex-start; }
}
</style>
