<template>
  <HomeLogin v-if="!isLoggedIn" @login-success="handleLoginSuccess" />
  <div v-else-if="!hasCourseSelected" class="course-selection-page">
    <StudentTopBar
      :backend-status-class="backendStatusClass"
      :backend-status-text="backendStatusText"
      :username="studentId"
      @logout="handleLogout"
    />
    <div class="selection-layout">
      <aside class="selection-user-sidebar">
        <div class="user-avatar">{{ (studentId || '学').slice(0, 1).toUpperCase() }}</div>
        <div class="user-name">{{ studentId || '学生' }}</div>
        <div class="user-subtitle">我的学习空间</div>

        <el-button class="refresh-btn" @click="loadCourseSelectionData" :loading="selectionLoading">刷新资源</el-button>
      </aside>

      <section class="selection-main-panel" v-loading="selectionLoading">
        <div class="selection-head">
          <div>
            <h2>选择你要学习的课件</h2>
            <p>左侧是用户栏，右侧平铺展示你的选课。点击任一卡片会直接进入学习页面。</p>
          </div>
        </div>

        <div class="selection-filters">
          <el-select v-model="selectedTeachingCourseId" placeholder="筛选课程" filterable>
            <el-option v-for="item in selectionCourseOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-select v-model="selectedCourseClassId" placeholder="筛选教学班级" filterable>
            <el-option v-for="item in filteredSelectionClassOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </div>

        <div class="course-tile-grid">
          <button
            v-for="card in selectionDisplayCards"
            :key="card.id"
            class="course-tile"
            :class="{ active: selectedCoursewareId === card.id, mock: card.mock }"
            @click="pickCoursewareCard(card)"
          >
            <div class="tile-badge">{{ card.mock ? '占位选课' : '我的选课' }}</div>
            <h3>{{ card.name }}</h3>
            <p>{{ card.desc }}</p>
            <div class="tile-meta">
              <span>{{ card.courseName || '未绑定课程' }}</span>
              <span>{{ card.className || '未绑定班级' }}</span>
            </div>
          </button>
        </div>

        <div class="selection-tip" v-if="selectionDisplayCards.length === 0">
          暂无可展示课件，请点击“刷新资源”重试。
        </div>
      </section>
    </div>
  </div>
  <div v-else class="student-app">
    <StudentTopBar
      :backend-status-class="backendStatusClass"
      :backend-status-text="backendStatusText"
      :username="studentId"
      @logout="handleLogout"
    />
    <div class="ambient-layer">
      <span class="orb orb-a"></span>
      <span class="orb orb-b"></span>
      <span class="orb orb-c"></span>
    </div>
    <div class="workspace-shell">
      <main class="main-layout">
        <aside class="left-sidebar-menu" :class="{ collapsed: isMenuCollapsed }">
          <div class="menu-header">
            <span v-show="!isMenuCollapsed">导航</span>
            <button class="menu-toggle-btn" @click="isMenuCollapsed = !isMenuCollapsed" :title="isMenuCollapsed ? '展开菜单' : '收起菜单'">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h18"></path><path d="M3 6h18"></path><path d="M3 18h18"></path></svg>
            </button>
          </div>
          <div class="menu-list">
            <button class="menu-item" :class="{ active: activeSection === 'classroom' }" @click="jumpToSection('classroom')" title="课堂学习">
              <span class="menu-icon">课</span>
              <span v-show="!isMenuCollapsed">课堂学习</span>
            </button>
            <button class="menu-item" :class="{ active: activeSection === 'analytics' }" @click="jumpToSection('analytics')" title="学习分析">
              <span class="menu-icon">析</span>
              <span v-show="!isMenuCollapsed">学习分析</span>
            </button>
            <button class="menu-item" :class="{ active: activeSection === 'recommend' }" @click="jumpToSection('recommend')" title="学习推荐">
              <span class="menu-icon">荐</span>
              <span v-show="!isMenuCollapsed">学习推荐</span>
            </button>
            <button class="menu-item" :class="{ active: activeSection === 'knowledge' }" @click="jumpToSection('knowledge')" title="知识拆解">
              <span class="menu-icon">知</span>
              <span v-show="!isMenuCollapsed">知识拆解</span>
            </button>
            <button class="menu-item" :class="{ active: activeSection === 'practice' }" @click="jumpToSection('practice')" title="随堂练习">
              <span class="menu-icon">练</span>
              <span v-show="!isMenuCollapsed">随堂练习</span>
            </button>
            <button class="menu-item" v-if="hasCourseSelected" @click="backToSelectionPage" title="返回选课页">
              <span class="menu-icon">返</span>
              <span v-show="!isMenuCollapsed">返回选课页</span>
            </button>
            <button class="menu-item" :class="{ active: activeSection === 'personal' }" @click="jumpToSection('personal')" title="个人中心">
              <span class="menu-icon">我</span>
              <span v-show="!isMenuCollapsed">个人中心</span>
            </button>
          </div>
        </aside>

        <section class="workspace-content">
          <transition name="page-fade" mode="out-in">
          <div v-if="activeSection === 'classroom'" key="classroom" class="page-layout classroom-workbench">
            <header class="classroom-header-row">
              <div class="classroom-title-group">
                <p class="classroom-kicker">课堂学习工作台</p>
                <h3>左侧学习区 · 右侧 AI 课堂助手</h3>
              </div>
              <div class="classroom-header-actions">
                <el-button v-if="isCompactViewport" size="small" plain @click="toggleQaPanel">
                  {{ isQaPanelCollapsed ? '展开 AI 助手' : '收起 AI 助手' }}
                </el-button>
              </div>
            </header>

            <div class="classroom-split-layout" :class="{ compact: isCompactViewport, collapsed: isQaPanelCollapsed }">
              <section class="workbench-main center-workbench-pane classroom-left-pane" :style="classroomLeftPaneStyle">
                <section v-if="isKnowledgeOutlineVisible" class="classroom-outline-fullscreen">
                  <header class="outline-preview-head">
                    <div>
                      <p class="outline-preview-kicker">Knowledge Outline</p>
                      <h4>遗传算法知识大纲</h4>
                    </div>
                    <div class="outline-preview-actions">
                      <el-button text size="small" @click="restartKnowledgeOutlineStream">重播</el-button>
                      <el-button text size="small" @click="closeKnowledgeOutline">关闭</el-button>
                    </div>
                  </header>
                  <div class="outline-preview-body">
                    <div v-if="knowledgeOutlineLoading" class="outline-skeleton-grid" aria-live="polite">
                      <article class="outline-skeleton-item" v-for="index in 3" :key="`outline-skeleton-${index}`">
                        <div class="outline-skeleton-line w-70"></div>
                        <div class="outline-skeleton-line w-35"></div>
                        <div class="outline-skeleton-line w-100"></div>
                        <div class="outline-skeleton-line w-85"></div>
                        <div class="outline-skeleton-line w-55"></div>
                      </article>
                    </div>
                    <article
                      v-else-if="knowledgeOutlineHtml"
                      class="outline-markdown-content"
                      v-html="knowledgeOutlineHtml"
                    ></article>
                    <div v-else class="outline-preview-empty">正在生成大纲内容...</div>
                  </div>
                </section>

                <div v-else class="classroom-left-stack" :class="{ expanded: isLowerWorkbenchExpanded, solo: !isLowerWorkbenchExpanded }">
                  <section class="center-stage" :class="{ expanded: isLowerWorkbenchExpanded, solo: !isLowerWorkbenchExpanded }">
                    <div class="playback-hud" v-if="playbackHudVisible">{{ playbackHudText }}</div>
                    <div class="shortcut-help-card" v-if="shortcutHelpVisible">
                      <div class="shortcut-help-header">
                        <strong>课堂快捷键</strong>
                        <button type="button" @click="closeShortcutHelp()">关闭</button>
                      </div>
                      <div class="shortcut-help-grid">
                        <span><kbd>Space</kbd> 播放/暂停</span>
                        <span><kbd>← / →</kbd> 快退/快进 5 秒</span>
                        <span><kbd>Shift + ← / →</kbd> 快退/快进 10 秒</span>
                        <span><kbd>[ / ]</kbd> 调整倍速</span>
                        <span><kbd>0</kbd> 恢复 1.0x</span>
                        <span><kbd>M</kbd> 语音开关</span>
                        <span><kbd>K</kbd> 打开/关闭帮助</span>
                      </div>
                    </div>
                    <div class="center-stage-toolbar">
                      <el-button
                        size="small"
                        class="expand-toggle-btn"
                        type="primary"
                        plain
                        @click="toggleLowerWorkbench"
                      >
                        {{ isLowerWorkbenchExpanded ? '收起下方面板' : '展开下方面板' }}
                      </el-button>
                      <el-button
                        size="small"
                        class="outline-toggle-btn"
                        type="success"
                        plain
                        @click="toggleKnowledgeOutline"
                      >
                        {{ isKnowledgeOutlineVisible ? '收起知识大纲' : '知识大纲' }}
                      </el-button>
                    </div>
                    <StudentCoursePanel
                      v-if="!isLowerWorkbenchExpanded"
                      :current-course-name="currentCourseName"
                      :current-page="currentPage"
                      :total-page="totalPage"
                      :page-timeline-duration="pageTimelineDuration"
                      :current-timeline-sec="currentTimelineSec"
                      :active-node-elapsed-sec="activeNodeElapsedSec"
                      :active-node-duration="activeNodeDuration"
                      :current-node-title="currentNodeMeta?.title || ''"
                      :active-node-type-label="activeNodeTypeLabel"
                      :playback-mode="playbackMode"
                      :playback-audio-meta="playbackAudioMeta"
                      :progress-percent="progressPercent"
                      :course-img="classroomCourseImageSrc"
                      :fallback-course-img="coursePreviewFallbackSrc"
                      :playback-nodes="playbackNodes"
                      :current-node-id="currentNodeId"
                      :tts-enabled="ttsEnabled"
                      :page-summary="''"
                      :script-content="currentPageMarkdown"
                      :is-script-loading="scriptLoading"
                      :trace-point="tracePoint"
                      :trace-top="traceTop"
                      :trace-left="traceLeft"
                      :is-play="isPlay"
                      :playback-rate="playbackRate"
                      :show-status-strip="isLowerWorkbenchExpanded"
                      :display-mode="isLowerWorkbenchExpanded ? 'voice' : 'script'"
                      @prev-page="prevPage"
                      @select-node="selectPlaybackNode"
                      @toggle-play="togglePlay"
                      @toggle-tts="toggleTts"
                      @speak-current-node="speakCurrentNode"
                      @seek-timeline="seekTimeline"
                      @seek-step="handleSeekStep"
                      @seek-to-start="handleSeekToStart"
                      @open-qa="openAskPanelIfNeeded"
                      @open-shortcuts="openShortcutHelp(true)"
                      @update:playback-rate="updatePlaybackRate"
                      @next-page="nextPage"
                    />
                    <div
                      v-if="!isLowerWorkbenchExpanded && hasClassroomSubtitle"
                      class="classroom-live-subtitle"
                      :class="{ qa: classroomSubtitleSource === 'qa', dragging: subtitleLayout.dragging }"
                      :style="classroomSubtitleStyle"
                      @pointerdown.stop="startSubtitleDrag"
                    >
                      <div class="subtitle-label">{{ classroomSubtitleSource === 'qa' ? 'AI 回答字幕' : '课堂字幕' }}</div>
                      <p class="subtitle-text">{{ classroomSubtitleText }}</p>
                    </div>
                    <div v-else class="center-stage-collapsed-title" aria-label="已折叠课堂面板">
                      <h4>{{ currentCourseName || '当前课件' }}</h4>
                      <span>第 {{ currentPage }} / {{ totalPage }} 页</span>
                    </div>
                  </section>

                  <div v-if="isLowerWorkbenchExpanded" class="tab-workspace-pane merged-tabs-pane left-unified-tabs-pane">
                  <el-tabs v-model="activeWorkbenchTab" class="workbench-tabs left-main-tabs">
                    <el-tab-pane label="知识树" name="tree">
                      <div class="tab-scroll-area">
                        <div class="knowledge-tree-pane merged-tree-pane">
                          <div class="tree-pane-header">
                            <div>
                              <div class="outline-label">Knowledge Tree</div>
                              <h3>知识节点树</h3>
                            </div>
                            <span>{{ filteredOutlineNodes.length }}/{{ displayOutlineNodes.length }}</span>
                          </div>
                          <div class="tree-progress-row">
                            <span>学习进度</span>
                            <strong>{{ currentPage }}/{{ totalPage }}</strong>
                          </div>
                          <div class="outline-tools">
                            <el-select v-model="outlineFilter" size="small" placeholder="筛选节点">
                              <el-option label="全部节点" value="all" />
                              <el-option label="关键讲解" value="core" />
                              <el-option label="开场节点" value="opening" />
                              <el-option label="过渡节点" value="transition" />
                            </el-select>
                            <el-button size="small" plain @click="focusCurrentNode">定位当前</el-button>
                          </div>
                          <div class="knowledge-tree-scroll" v-if="knowledgeWorkbenchTree.length">
                            <el-tree
                              :data="knowledgeWorkbenchTree"
                              :props="treeProps"
                              node-key="id"
                              default-expand-all
                              :expand-on-click-node="false"
                              :highlight-current="true"
                              :current-node-key="currentNodeId"
                              @node-click="handleWorkbenchTreeNodeClick"
                            />
                          </div>
                          <div class="outline-empty" v-else>当前页面暂无可用节点。</div>
                        </div>
                      </div>
                    </el-tab-pane>

                    <el-tab-pane label="学习状态" name="knowledge">
                      <div class="tab-scroll-area">
                        <div class="classroom-status-strip">
                          <div class="status-row">
                            <span class="status-pill">进度 {{ progressPercent }}%</span>
                            <span class="status-pill">{{ isPlay ? '正在讲解' : '已暂停' }}</span>
                            <span class="status-pill" v-if="currentNodeMeta?.title">节点 {{ currentNodeMeta.title }}</span>
                            <span class="status-pill" v-if="pageTimelineDuration > 0">{{ formatNodeTime(currentTimelineSec) }} / {{ formatNodeTime(pageTimelineDuration) }}</span>
                          </div>
                          <div class="status-track" v-if="pageTimelineDuration > 0">
                            <div class="status-fill" :style="{ width: timelinePercent + '%' }"></div>
                          </div>
                          <div class="status-track" v-else>
                            <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
                          </div>
                          <div class="status-note" v-if="courseAudioStatusText || activeNodeDuration > 0">
                            <span v-if="activeNodeDuration > 0">节点 {{ formatNodeTime(activeNodeElapsedSec) }} / {{ formatNodeTime(activeNodeDuration) }}</span>
                            <span>{{ activeNodeTypeLabel }}</span>
                            <span v-if="courseAudioStatusText">{{ courseAudioStatusText }}</span>
                          </div>
                        </div>

                        <div class="status-signal-grid">
                          <article v-for="signal in learningStatusSignals" :key="signal.id" class="status-signal-card">
                            <div class="signal-top">
                              <span class="signal-name">{{ signal.label }}</span>
                              <strong>{{ signal.value }}</strong>
                            </div>
                            <p>{{ signal.desc }}</p>
                          </article>
                        </div>

                        <div class="dashboard-grid">
                          <section class="status-group-card mastered">
                            <div class="group-head">
                              <h4>Mastered</h4>
                              <span>{{ masteredNodes.length }}</span>
                            </div>
                            <div class="node-card-list" v-if="masteredNodes.length">
                              <article v-for="node in masteredNodes" :key="`m_${node.node_id}`" class="knowledge-node-card">
                                <h5>{{ node.title || node.node_id }}</h5>
                                <p>{{ trimText(node.text, 64) || '该节点已掌握。' }}</p>
                              </article>
                            </div>
                            <div class="card-empty" v-else>暂无已掌握节点</div>
                          </section>

                          <section class="status-group-card unmastered">
                            <div class="group-head">
                              <h4>Unmastered</h4>
                              <span>{{ unmasteredNodes.length }}</span>
                            </div>
                            <div class="node-card-list" v-if="unmasteredNodes.length">
                              <article v-for="node in unmasteredNodes" :key="`u_${node.node_id}`" class="knowledge-node-card">
                                <h5>{{ node.title || node.node_id }}</h5>
                                <p>{{ trimText(node.text, 64) || '建议先补充示例再练习。' }}</p>
                                <div class="node-actions">
                                  <el-button size="small" type="primary" plain @click="askAboutUnmasteredNode(node)">问 AI</el-button>
                                  <el-button size="small" type="warning" plain @click="reinforceNode(node)">薄弱强化</el-button>
                                  <el-button size="small" type="danger" plain @click="findPracticeForNode(node)">查找习题</el-button>
                                </div>
                              </article>
                            </div>
                            <div class="card-empty" v-else>暂无未掌握节点</div>
                          </section>

                          <section class="status-group-card prerequisite">
                            <div class="group-head">
                              <h4>Prerequisite</h4>
                              <span>{{ prerequisiteNodes.length }}</span>
                            </div>
                            <div class="node-card-list" v-if="prerequisiteNodes.length">
                              <article v-for="node in prerequisiteNodes" :key="`p_${node.node_id}`" class="knowledge-node-card">
                                <h5>{{ node.title || node.node_id }}</h5>
                                <p>{{ trimText(node.text, 64) || '建议先预习该节点。' }}</p>
                              </article>
                            </div>
                            <div class="card-empty" v-else>暂无前置节点</div>
                          </section>
                        </div>
                      </div>
                    </el-tab-pane>

                    <el-tab-pane label="课堂交互" name="interaction">
                      <div class="tab-scroll-area interaction-layout">
                        <section class="interaction-card exercise-card">
                          <div class="interaction-title">随堂练习</div>
                          <div class="exercise-paper">
                            <div class="exercise-section">
                              <h4>一、选择题（每题2分，共10分）</h4>
                              <div class="exercise-question-group">
                                <div v-for="(item, index) in practiceChoiceQuestions" :key="item.id" class="exercise-question-card">
                                  <p class="exercise-question-title">{{ index + 1 }}. {{ item.question }}</p>
                                  <el-radio-group v-model="practiceAnswers[item.id]" class="exercise-radio-group">
                                    <el-radio v-for="option in item.options" :key="option.value" :label="option.value">
                                      {{ option.label }}
                                    </el-radio>
                                  </el-radio-group>
                                  <div class="exercise-answer-line" v-if="exerciseSubmitted">
                                    <span :class="practiceAnswers[item.id] === item.answer ? 'answer-correct' : 'answer-wrong'">
                                      正确答案：{{ item.answerLabel }}
                                    </span>
                                  </div>
                                </div>
                              </div>
                            </div>

                            <div class="exercise-section">
                              <h4>二、填空题（每空2分，共10分）</h4>
                              <div class="exercise-question-group">
                                <div class="exercise-question-card">
                                  <p class="exercise-question-title">1. 遗传算法中，个体通常用__________表示，其中的每个字符称为__________。</p>
                                  <div class="exercise-fill-row">
                                    <el-input v-model="practiceAnswers.fill1a" placeholder="第1空" />
                                    <el-input v-model="practiceAnswers.fill1b" placeholder="第2空" />
                                  </div>
                                  <div v-if="exerciseSubmitted" class="exercise-answer-line">
                                    <span :class="isFillAnswerCorrect('fill1a', ['染色体', '染色体串']) && isFillAnswerCorrect('fill1b', ['基因']) ? 'answer-correct' : 'answer-wrong'">
                                      参考答案：染色体 / 基因
                                    </span>
                                  </div>
                                </div>
                                <div class="exercise-question-card">
                                  <p class="exercise-question-title">2. 选择-复制操作中，个体被选中的概率与其__________成正比。</p>
                                  <el-input v-model="practiceAnswers.fill2" placeholder="请填写答案" />
                                  <div v-if="exerciseSubmitted" class="exercise-answer-line">
                                    <span :class="isFillAnswerCorrect('fill2', ['适应度']) ? 'answer-correct' : 'answer-wrong'">
                                      参考答案：适应度
                                    </span>
                                  </div>
                                </div>
                                <div class="exercise-question-card">
                                  <p class="exercise-question-title">3. 交叉操作是交换两个染色体的__________。</p>
                                  <el-input v-model="practiceAnswers.fill3" placeholder="请填写答案" />
                                  <div v-if="exerciseSubmitted" class="exercise-answer-line">
                                    <span :class="isFillAnswerCorrect('fill3', ['部分', '片段', '一部分']) ? 'answer-correct' : 'answer-wrong'">
                                      参考答案：部分 / 片段
                                    </span>
                                  </div>
                                </div>
                                <div class="exercise-question-card">
                                  <p class="exercise-question-title">4. 遗传算法中的“种群”是指__________的集合。</p>
                                  <el-input v-model="practiceAnswers.fill4" placeholder="请填写答案" />
                                  <div v-if="exerciseSubmitted" class="exercise-answer-line">
                                    <span :class="isFillAnswerCorrect('fill4', ['个体']) ? 'answer-correct' : 'answer-wrong'">
                                      参考答案：个体
                                    </span>
                                  </div>
                                </div>
                              </div>
                            </div>

                            <div class="exercise-section">
                              <h4>三、简答题（每题5分，共10分）</h4>
                              <div class="exercise-question-group">
                                <div class="exercise-question-card">
                                  <p class="exercise-question-title">1. 简述遗传算法中“选择-复制”操作的基本过程。</p>
                                  <el-input
                                    v-model="practiceAnswers.short1"
                                    type="textarea"
                                    :rows="3"
                                    placeholder="请在这里填写答案"
                                  />
                                  <div v-if="exerciseSubmitted" class="exercise-answer-line">
                                    <span class="exercise-reference">参考要点：按适应度选择个体，保留高适应度个体并复制到下一代。</span>
                                  </div>
                                </div>
                                <div class="exercise-question-card">
                                  <p class="exercise-question-title">2. 举例说明交叉操作是如何进行的（可用二进制串示例）。</p>
                                  <el-input
                                    v-model="practiceAnswers.short2"
                                    type="textarea"
                                    :rows="3"
                                    placeholder="请在这里填写答案"
                                  />
                                  <div v-if="exerciseSubmitted" class="exercise-answer-line">
                                    <span class="exercise-reference">参考要点：选择两个父代，在某一点后交换片段生成子代。</span>
                                  </div>
                                </div>
                              </div>
                            </div>

                            <div class="exercise-section">
                              <h4>四、应用题（10分）</h4>
                              <p>假设有一个二进制编码的遗传算法，种群大小为 4，个体如下：</p>
                              <div class="exercise-code-block">
                                <div>s1 = 1010</div>
                                <div>s2 = 0101</div>
                                <div>s3 = 1100</div>
                                <div>s4 = 0011</div>
                              </div>
                              <p>若采用轮盘赌选择，适应度分别为：s1=2, s2=3, s3=1, s4=4，请计算每个个体的选择概率。</p>
                              <div class="exercise-fill-row probability-row">
                                <el-input v-model="practiceAnswers.app1" placeholder="s1 选择概率" />
                                <el-input v-model="practiceAnswers.app2" placeholder="s2 选择概率" />
                                <el-input v-model="practiceAnswers.app3" placeholder="s3 选择概率" />
                                <el-input v-model="practiceAnswers.app4" placeholder="s4 选择概率" />
                              </div>
                              <p>若选择 s2 和 s4 进行单点交叉（交叉点在第 2 位之后），写出子代染色体。</p>
                              <el-input
                                v-model="practiceAnswers.app5"
                                type="textarea"
                                :rows="2"
                                placeholder="请写出子代染色体"
                              />
                              <div v-if="exerciseSubmitted" class="exercise-answer-line">
                                <span class="exercise-reference">参考答案：轮盘赌概率分别为 0.2、0.3、0.1、0.4；交叉子代为 0111 和 0001。</span>
                              </div>
                            </div>

                            <div class="exercise-actions">
                              <el-button type="primary" @click="submitPracticeExercise">提交练习</el-button>
                              <el-button plain @click="resetPracticeExercise">重置答案</el-button>
                              <span class="exercise-score" v-if="exerciseSubmitted">得分：{{ exerciseScore }} / 40</span>
                            </div>
                          </div>
                        </section>

                        <section class="interaction-card feedback-card">
                          <div class="interaction-title">满意度反馈</div>
                          <div class="feedback-row">
                            <span>本节点讲解满意度</span>
                            <el-rate v-model="lessonFeedbackRating" />
                          </div>
                          <el-input
                            v-model="lessonFeedbackComment"
                            type="textarea"
                            :rows="3"
                            placeholder="可选：填写你的反馈建议"
                          />
                          <el-button type="success" plain @click="submitLessonFeedback">提交反馈</el-button>
                        </section>
                      </div>
                    </el-tab-pane>

                    <el-tab-pane label="课堂笔记" name="notes">
                      <div class="tab-scroll-area notes-layout">
                        <div class="notes-head">
                          <h4>节点笔记</h4>
                          <span>{{ currentNodeMeta?.title || currentNodeId }}</span>
                        </div>
                        <el-input
                          v-model="currentNodeNoteTitle"
                          size="small"
                          placeholder="请填写笔记标题（会同步到个人中心）"
                        />
                        <el-input
                          v-model="currentNodeNote"
                          type="textarea"
                          :rows="16"
                          placeholder="在这里记录当前节点笔记，切换节点后会按 NodeID 自动区分保存。"
                        />
                        <div class="note-actions-row">
                          <el-button size="small" type="success" plain @click="saveCurrentNodeNote">保存到个人中心笔记</el-button>
                          <el-button size="small" type="warning" plain @click="openNoteFavoriteDialog">收藏到个人中心</el-button>
                          <el-button size="small" type="primary" plain @click="optimizeCurrentNoteWithAI">AI 优化</el-button>
                          <el-button size="small" plain @click="jumpToPersonalNotes">查看个人中心笔记</el-button>
                        </div>
                      </div>
                    </el-tab-pane>
                  </el-tabs>
                </div>
                </div>
              </section>

              <div
                v-if="!isCompactViewport && !isQaPanelCollapsed"
                class="classroom-resizer"
                role="separator"
                aria-orientation="vertical"
                title="拖拽调整左右栏宽度"
                @pointerdown.prevent="startClassroomResize"
              >
                <span></span>
              </div>

              <aside v-if="!isQaPanelCollapsed" class="classroom-qa-pane" :style="classroomQaPaneStyle">
                <div class="classroom-qa-head">
                  <div>
                    <p class="qa-kicker">AI课堂助手</p>
                    <h4>课程联动问答面板</h4>
                  </div>
                  <div class="qa-head-tags">
                    <el-tag size="small" :type="qaContextBinding ? 'success' : 'info'">
                      {{ qaContextBinding ? '已绑定当前知识点' : '未绑定上下文' }}
                    </el-tag>
                    <el-tag size="small" effect="plain" type="warning">
                      {{ currentExplainModeLabel }} · {{ currentExplainStyleLabel }}
                    </el-tag>
                  </div>
                </div>
                <StudentAskPanel
                  :question="question"
                  :ask-loading="askLoading"
                  :ai-reply="aiReply"
                  :stream-typing-active="streamTypingActive"
                  :qa-history="qaHistory"
                  :latest-answer-meta="latestAnswerMeta"
                  :summary-mode="summaryMode"
                  :merged-summary="mergedSummary"
                  :context-binding="qaContextBinding"
                  :deep-reasoning="qaDeepReasoning"
                  :web-search="qaWebSearch"
                  :explain-mode="aiExplainMode"
                  :explain-style="aiExplainStyle"
                  :auto-speak-answer="qaAutoSpeakAnswer"
                  :preset-lecture-script="presetLectureScriptOnPlay"
                  :can-ask="true"
                  :external-action="askPanelAction"
                  @update:question="question = $event"
                  @update:summaryMode="summaryMode = $event"
                  @update:context-binding="qaContextBinding = $event"
                  @update:deep-reasoning="qaDeepReasoning = $event"
                  @update:web-search="qaWebSearch = $event"
                  @update:explain-mode="aiExplainMode = $event"
                  @update:explain-style="aiExplainStyle = $event"
                  @update:auto-speak-answer="qaAutoSpeakAnswer = $event"
                  @update:preset-lecture-script="presetLectureScriptOnPlay = $event"
                  @open-upload="openUpload"
                  @generate-summary="generateMergedSummary"
                  @use-summary="injectSummaryToQuestion"
                  @clear-draft="clearQaDraft"
                  @send-question="sendMultiModalQuestion"
                  @play-answer-audio="playAnswerMessageAudio"
                />
              </aside>

              <aside v-if="showClassroomRightSidebar" class="workbench-right-sidebar">
                <div class="right-rail">
                  <button
                    class="rail-btn"
                    :class="{ active: activeRightPanel === 'courseware' }"
                    type="button"
                    @click="toggleRightPanel('courseware')"
                  >
                    <span>课件</span>
                  </button>
                  <button
                    class="rail-btn"
                    :class="{ active: activeRightPanel === 'mindmap' }"
                    type="button"
                    @click="toggleRightPanel('mindmap')"
                  >
                    <span>导图</span>
                  </button>
                </div>

                <transition name="drawer-slide">
                  <div v-if="isRightDrawerOpen" class="overlay-drawer">
                    <header class="section-header">
                      <h3>{{ activeRightPanel === 'mindmap' ? '思维导图' : '课件选择' }}</h3>
                      <button class="close-btn" type="button" @click="closeRightPanel">关闭</button>
                    </header>

                    <template v-if="activeRightPanel === 'courseware'">
                      <div class="panel-body courseware-select-body">
                        <div class="courseware-select-list" v-if="classroomCoursewareList.length">
                          <button
                            v-for="item in classroomCoursewareList"
                            :key="item.id"
                            class="courseware-select-item"
                            :class="{ active: item.id === courseId }"
                            type="button"
                            @click="selectCoursewareFromDrawer(item)"
                          >
                            <div class="courseware-item-main">
                              <strong>{{ item.name }}</strong>
                              <span>{{ item.courseName || '未绑定课程' }} · {{ item.className || '未绑定班级' }}</span>
                            </div>
                            <div class="courseware-item-meta">{{ Number(item.totalPage || 1) }}页</div>
                          </button>
                        </div>
                        <div v-else class="courseware-empty">暂无可选课件，请返回选课页刷新资源。</div>
                      </div>
                      <div class="drawer-page-nav" v-if="courseId">
                        <button class="nav-icon-btn" type="button" :disabled="currentPage <= 1" @click="prevPage">◀</button>
                        <span class="page-indicator">{{ currentPage }} / {{ totalPage }}</span>
                        <button class="nav-icon-btn" type="button" :disabled="currentPage >= totalPage" @click="nextPage">▶</button>
                      </div>
                    </template>

                    <div v-else class="graph-body">
                      <div class="mindmap-preview-shell">
                        <img class="mindmap-preview-image" :src="presetMindmapImageSrc" alt="思维导图预览" />
                      </div>
                    </div>
                  </div>
                </transition>
              </aside>
            </div>
          </div>

          <div v-else-if="activeSection === 'analytics'" key="analytics" class="page-layout single-col">
            <StudentStudyPanel
              :learning-stats="learningStats"
              :weak-point-tags="weakPointTags"
              :student-id="studentId"
              :course-id="courseId"
              :current-explain="currentExplain"
              :current-weak-point="currentWeakPoint"
              :current-test="currentTest"
              :test-result="testResult"
              @start-weak-point="handleStudyPanelAiExplain"
              @collect-weak-point="collectWeakPointToFavorite"
              @generate-test="generateTest"
              @check-answer="checkAnswer"
            />
          </div>

          <div v-else-if="activeSection === 'recommend'" key="recommend" class="page-layout single-col">
            <StudentRecommendPanel
              :course-name="currentCourseName"
              :current-node-title="currentNodeMeta?.title || ''"
              :current-page="currentPage"
              @navigate-section="handleDemoNavigation"
            />
          </div>

          <div v-else-if="activeSection === 'personal'" key="personal" class="page-layout single-col">
            <StudentPersonalCenter
              :student-id="studentId"
              :course-id="courseId"
              :current-course-name="currentCourseName"
              :learning-stats="learningStats"
              :weak-point-tags="weakPointTags"
              :initial-tab="personalCenterInitialTab"
              @jump-classroom="jumpToSection('classroom')"
              @jump-analytics="jumpToSection('analytics')"
            />
          </div>

          <div v-else-if="activeSection === 'practice'" key="practice" class="page-layout single-col">
            <StudentPracticePanel
              :course-name="currentCourseName"
              :current-node-title="currentNodeMeta?.title || ''"
              :student-id="studentId"
              :course-id="courseId"
              :node-id="currentNodeId"
              :page-num="currentPage"
              @jump-personal-practice="jumpToPersonalPractice"
              @navigate-section="handleDemoNavigation"
            />
          </div>

          <div v-else key="knowledge" class="page-layout single-col">
            <StudentKnowledgePanel
              :uploaded-file="uploadedFile"
              :is-parsing="isParsing"
              :parse-result="parseResult"
              :knowledge-list="knowledgeList"
              :tree-props="treeProps"
              @file-change="handleFileChange"
              @parse-knowledge="parseKnowledge"
              @reset-current="resetKnowledgeWorkspace"
              @node-click="handleNodeClick"
            />
          </div>
          </transition>
        </section>
      </main>
    </div>

    <StudentBreakpointDialog
      :model-value="showBreakpointDialog"
      :breakpoint-page="breakpointPage"
      @restart-study="restartStudy"
      @continue-study="continueStudy"
    />

    <el-dialog v-model="noteFavoriteDialogVisible" title="收藏到个人中心" width="560px">
      <div class="note-favorite-dialog">
        <el-input v-model="noteFavoriteForm.title" placeholder="笔记标题" />
        <el-select v-model="noteFavoriteForm.category" placeholder="请选择收藏分类">
          <el-option
            v-for="item in noteFavoriteCategoryOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-input
          v-model="noteFavoriteForm.content"
          type="textarea"
          :rows="7"
          placeholder="请输入要同步到个人中心的笔记内容"
        />
      </div>
      <template #footer>
        <div class="note-favorite-footer">
          <el-button @click="noteFavoriteDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="noteFavoriteSaving" @click="confirmSaveNoteFavorite">保存并收藏</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/* eslint-disable no-unused-vars */
import { ref, reactive, onMounted, onBeforeUnmount, onUnmounted, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { studentV1Api } from './services/v1'
import { API_BASE, AI_API_BASE } from './config/api'
import StudentCoursePanel from './components/student/StudentCoursePanel.vue'
import StudentAskPanel from './components/student/StudentAskPanel.vue'
import StudentStudyPanel from './components/student/StudentStudyPanel.vue'
import StudentRecommendPanel from './components/student/StudentRecommendPanel.vue'
import StudentKnowledgePanel from './components/student/StudentKnowledgePanel.vue'
import StudentBreakpointDialog from './components/student/StudentBreakpointDialog.vue'
import StudentPersonalCenter from './components/student/StudentPersonalCenter.vue'
import StudentPracticePanel from './components/student/StudentPracticePanel.vue'
import StudentTopBar from './components/StudentTopBar.vue'
import HomeLogin from './components/HomeLogin.vue'

const resolveStudentId = () => {
  const queryId = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search).get('studentId')
    : ''
  const normalizedQueryId = String(queryId || '').trim().toLowerCase()
  const cachedId = typeof window !== 'undefined'
    ? String(window.localStorage.getItem('fuww_student_id') || '').trim().toLowerCase()
    : ''
  const finalId = normalizedQueryId || cachedId || 'xuesheng'
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('fuww_student_id', finalId)
  }
  return finalId
}

const resolveTeacherOrigin = () => {
  if (typeof window === 'undefined') return 'http://localhost:5173'
  const cached = String(window.localStorage.getItem('fuww_teacher_origin') || '').trim()
  if (cached) return cached
  const protocol = window.location.protocol || 'http:'
  const hostname = window.location.hostname || 'localhost'
  return `${protocol}//${hostname}:5173`
}

const isLoggedIn = ref(false)
const hasCourseSelected = ref(false)
const selectionLoading = ref(false)
const selectionCourseOptions = ref([])
const selectionClassOptions = ref([])
const selectionCoursewares = ref([])
const selectedTeachingCourseId = ref('')
const selectedCourseClassId = ref('')
const selectedCoursewareId = ref('')

const backendStatus = ref('checking')
let backendHealthTimer = null

const backendStatusText = computed(() => {
  if (backendStatus.value === 'online') return '在线'
  if (backendStatus.value === 'offline') return '离线'
  return '检测中'
})

const backendStatusClass = computed(() => {
  if (backendStatus.value === 'online') return 'online'
  if (backendStatus.value === 'offline') return 'offline'
  return 'checking'
})

const studentId = ref('')
const courseId = ref('')
const sessionId = ref('')
const currentNodeId = ref('p1_n1')
const playbackNodes = ref([])
const pageSummary = ref('')
const currentPageMarkdown = ref('')
const scriptLoading = ref(false)
const playbackMode = ref('duration_timeline')
const playbackAudioMeta = ref(null)
const playbackState = ref('paused')
const ttsEnabled = ref(true)
const playbackRate = ref(1)
const seekNoticeText = ref('')
const seekNoticeVisible = ref(false)
let seekNoticeTimer = null
const playbackHudText = ref('')
const playbackHudVisible = ref(false)
let playbackHudTimer = null
const shortcutHelpVisible = ref(false)
const shortcutHelpSeenKey = 'fuww_student_shortcuts_seen'
let arrowSeekTimer = null
let arrowSeekDirection = ''
const currentCourseName = ref('')
const currentPage = ref(1)
const totalPage = ref(10)
const isPlay = ref(false)
const courseImg = ref('')
const selectedCoursePreviewImageUrl = ref('')
const activeSection = ref('classroom')
const personalCenterInitialTab = ref('notes')
const NAV_SECTIONS = Object.freeze(['classroom', 'analytics', 'recommend', 'knowledge', 'practice', 'personal'])
const isMenuCollapsed = ref(false)
const showAskWorkspace = ref(false)
const qaFabDragging = ref(false)
const qaFabLayout = reactive({
  left: 0,
  top: 0
})
const qaFabInteraction = reactive({
  mode: '',
  pointerId: null,
  startX: 0,
  startY: 0,
  startLeft: 0,
  startTop: 0,
  moved: false
})
const askWorkspaceLayout = reactive({
  left: 0,
  top: 0,
  width: 360,
  height: 620
})
const askWorkspaceInteraction = reactive({
  mode: '',
  pointerId: null,
  startX: 0,
  startY: 0,
  startLeft: 0,
  startTop: 0,
  startWidth: 0,
  startHeight: 0
})
const progressPercent = computed(() => Math.round((currentPage.value / totalPage.value) * 100))
const timelinePercent = computed(() => {
  if (!pageTimelineDuration.value) return 0
  return Math.min(100, Math.max(0, Math.round((currentTimelineSec.value / pageTimelineDuration.value) * 100)))
})
const filteredSelectionClassOptions = computed(() => {
  if (!selectedTeachingCourseId.value) return selectionClassOptions.value
  return selectionClassOptions.value.filter((item) => item.teachingCourseId === selectedTeachingCourseId.value)
})

const filteredSelectionCoursewares = computed(() => {
  return selectionCoursewares.value.filter((item) => {
    const courseMatch = !selectedTeachingCourseId.value || item.teachingCourseId === selectedTeachingCourseId.value
    const classMatch = !selectedCourseClassId.value || item.courseClassId === selectedCourseClassId.value
    return courseMatch && classMatch
  })
})

const selectionDisplayCards = computed(() => {
  const realCards = filteredSelectionCoursewares.value.map((item, index) => ({
    ...item,
    mock: false,
    desc: item.desc || `共 ${item.totalPage || 1} 页内容，点击卡片立即开始学习。`,
    order: index
  }))
  return realCards
})

const jumpToSection = (section, options = {}) => {
  const target = String(section || '').trim()
  const isValid = NAV_SECTIONS.includes(target)
  if (!isValid) {
    console.warn(`[student-nav] unsupported section: ${target}`)
    return
  }
  const personalTab = String(options?.personalTab || '').trim()
  if (target === 'personal' && personalTab) {
    personalCenterInitialTab.value = personalTab
  }
  activeSection.value = target
  if (target === 'knowledge') {
    void ensureKnowledgeWorkspaceDefaults({ autoParse: false, silent: true })
  }
}

const handleDemoNavigation = (payload) => {
  if (!payload) return
  if (typeof payload === 'string') {
    jumpToSection(payload)
    return
  }
  const section = String(payload.section || '').trim()
  if (!section) return
  const tab = String(payload.tab || '').trim()
  jumpToSection(section, { personalTab: tab })
}

const currentTimelineSec = ref(0)
let playbackTimer = null
let currentSpeechUtterance = null
let currentSpeechAudioElement = null
let currentSpeechCancel = null
let activeSpeechMark = ''
const classroomSubtitleText = ref('')
const classroomSubtitleSource = ref('')
let subtitleHideTimer = null
let subtitleVersion = 0
const ttsAudioUrlCache = new Map()
const hasClassroomSubtitle = computed(() => String(classroomSubtitleText.value || '').trim().length > 0)
let presetSpeechTaskId = 0
let streamTypingTimer = null
const streamTypingQueue = ref([])
const streamTypingActive = ref(false)
const TYPEWRITER_INTERVAL_MS = 38
const TYPEWRITER_FORCE_FLUSH_MS = 120000
const THINKING_DELAY_MS = 3000
const QA_RESUME_WAIT_TYPEWRITER_MS = 2200
const QA_ANSWER_SPEAK_TIMEOUT_MS = 7000
const TTS_MAX_CACHE_ENTRIES = 80
const TTS_DEFAULT_PROVIDER = 'openai-tts'
const TTS_DEFAULT_VOICE = 'alloy'
const TTS_DEFAULT_FORMAT = 'mp3'
const QA_AUTO_SPEAK_PREF_KEY = 'fuww_student_qa_auto_speak_answer_v1'
const PRESET_LECTURE_SPEAK_PREF_KEY = 'fuww_student_preset_lecture_speak_v1'
const AI_EXPLAIN_MODE_PREF_KEY = 'fuww_student_ai_explain_mode_v1'
const AI_EXPLAIN_STYLE_PREF_KEY = 'fuww_student_ai_explain_style_v1'
const STATIC_ASSET_BASE = (typeof process !== 'undefined' && process.env && process.env.BASE_URL)
  ? process.env.BASE_URL
  : '/'
const PRESET_MINDMAP_IMAGE = encodeURI(`${STATIC_ASSET_BASE}example/思维导图.jpeg`)
const PRESET_MINDMAP_IMAGES = [
  PRESET_MINDMAP_IMAGE
]
const COURSE_PREVIEW_FALLBACK_SRC = `${STATIC_ASSET_BASE}course-preview-fallback.png`
const LOCAL_GENETIC_PAGE_IMAGES = [
  `${STATIC_ASSET_BASE}example/yichuan_1.png`,
  `${STATIC_ASSET_BASE}example/yichuan_2.png`
]
const LOCAL_TEST_SAMPLE_PAGE_IMAGES = [
  `${STATIC_ASSET_BASE}example/ceshi.png`
]
const PRESET_LECTURE_SCRIPT_PATH = encodeURI(`${STATIC_ASSET_BASE}example/课堂讲稿.md`)
const KNOWLEDGE_OUTLINE_MARKDOWN_PATH = encodeURI(`${STATIC_ASSET_BASE}example/知识大纲.md`)
const KNOWLEDGE_OUTLINE_STREAM_INTERVAL_MS = 12
const KNOWLEDGE_OUTLINE_FIRST_LOAD_MIN_DELAY_MS = 500
const KNOWLEDGE_OUTLINE_FALLBACK_MARKDOWN = `# 遗传算法知识大纲

## 一、课程定位

- 主题：遗传算法基础与应用
- 目标：理解“编码-选择-交叉-变异”的完整流程
- 输出：能够完成参数判定与典型题型求解

## 二、核心模块

1. 编码与种群初始化
2. 适应度函数与选择机制
3. 交叉与变异策略
4. 收敛分析与参数调优

## 三、学习建议

- 先构建概念图，再做步骤推演
- 每学完一个模块立即做2道小题
- 错题按“错因-修正-复盘”闭环整理
`

const outlineMarkdownRenderer = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true
})

const resolveLocalCoursewareImages = (coursewareName = '') => {
  const normalized = String(coursewareName || '').trim().toLowerCase()
  if (!normalized) return null

  if (normalized.includes('第四讲_遗传算法') || normalized.includes('遗传算法') || normalized.includes('yichuan')) {
    return {
      key: 'yichuan',
      pages: LOCAL_GENETIC_PAGE_IMAGES
    }
  }

  if (normalized.includes('测试样例') || normalized.includes('ceshi')) {
    return {
      key: 'ceshi',
      pages: LOCAL_TEST_SAMPLE_PAGE_IMAGES
    }
  }

  return null
}

const resolveLocalCoursewarePageImage = (courseware, pageNo = 1) => {
  const pages = Array.isArray(courseware?.localPageImages) ? courseware.localPageImages : []
  if (!pages.length) return ''
  const index = Math.min(Math.max(0, Number(pageNo || 1) - 1), pages.length - 1)
  return String(pages[index] || '').trim()
}

const resolveActiveCourseware = () => {
  const activeId = String(selectedCoursewareId.value || courseId.value || '').trim()
  if (!activeId) return null
  return selectionCoursewares.value.find((item) => String(item?.id || '').trim() === activeId) || null
}

const resolveActiveCoursewarePageImages = () => {
  const activeCourseware = resolveActiveCourseware()
  const directPages = Array.isArray(activeCourseware?.localPageImages)
    ? activeCourseware.localPageImages.map((src) => String(src || '').trim()).filter(Boolean)
    : []
  if (directPages.length > 0) {
    return directPages
  }

  const fallbackPreset = resolveLocalCoursewareImages(activeCourseware?.name || currentCourseName.value || '')
  const presetPages = Array.isArray(fallbackPreset?.pages)
    ? fallbackPreset.pages.map((src) => String(src || '').trim()).filter(Boolean)
    : []
  return presetPages
}

const PRESET_LECTURE_SCRIPT_FALLBACK_TEXT = '同学们好，欢迎来到第四讲的课堂。今天我们要学习的遗传算法，是进化算法中最经典、应用最广泛的代表之一。它的核心思想，来自达尔文的生物进化论 —— 借鉴自然界中“物竞天择、适者生存”的进化过程，来解决传统算法难以处理的复杂优化问题。'

const isImageFileType = (value) => {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) return false
  return normalized.startsWith('image/') || ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg'].includes(normalized)
}

const isLikelyImageUrl = (value) => {
  const src = String(value || '').trim()
  if (!src) return false
  if (/^data:image\//i.test(src)) return true
  return /\.(png|jpe?g|webp|gif|bmp|svg)(\?|#|$)/i.test(src)
}

const normalizePreviewImageUrl = (value, { force = false } = {}) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^(https?:)?\/\//i.test(raw) || /^data:image\//i.test(raw) || /^blob:/i.test(raw)) {
    return raw
  }
  if (!force && !isLikelyImageUrl(raw)) return ''
  const base = String(API_BASE || '').replace(/\/+$/, '')
  const path = raw.startsWith('/') ? raw : `/${raw}`
  return `${base}${path}`
}

const loadBooleanPreference = (storageKey, fallbackValue) => {
  if (typeof window === 'undefined') return fallbackValue
  const raw = String(window.localStorage.getItem(storageKey) || '').trim().toLowerCase()
  if (!raw) return fallbackValue
  if (['1', 'true', 'yes', 'on'].includes(raw)) return true
  if (['0', 'false', 'no', 'off'].includes(raw)) return false
  return fallbackValue
}

const loadEnumPreference = (storageKey, allowedValues, fallbackValue) => {
  if (typeof window === 'undefined') return fallbackValue
  const raw = String(window.localStorage.getItem(storageKey) || '').trim().toLowerCase()
  if (!raw) return fallbackValue
  return allowedValues.includes(raw) ? raw : fallbackValue
}

const normalizeTextForSpeech = (value, maxLength = 900) => {
  const input = String(value || '')
  if (!input.trim()) return ''
  const stripped = input
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
  if (!stripped) return ''
  return stripped.slice(0, maxLength)
}

const question = ref('')
const aiReply = ref('')
const askLoading = ref(false)
const qaHistory = ref([])
const latestAnswerMeta = ref({
  sourcePage: 0,
  sourceNodeId: '',
  needReteach: false,
  understandingLevel: '',
  resumePage: null,
  resumeSec: null,
  followUpSuggestion: '',
  sessionId: ''
})

const FIXED_QA_MARKDOWN_REPLY = `## 一、核心概念

锦标赛选择算子，是遗传算法中选择操作的一种经典实现方式。
其核心思想为：在种群中随机抽取若干个体进行小规模“竞赛”，选取适应度最优的个体作为父代，重复该过程直至选出所需数量的父代个体，为后续交叉、变异操作提供优良基因来源。

## 二、基本原理

1. 遵循“优胜劣汰”的进化规则，以适应度作为竞赛评判标准；

2. 采用小规模随机抽样，避免单个超级个体主导整个种群；

3. 通过可控的竞赛规模，平衡算法的开发能力与探索能力。

## 三、执行步骤

1. 确定竞赛规模
设定每次参与竞赛的个体数量 k（k 为正整数，通常取 2~5）。

2. 随机抽取参赛个体
从当前代种群中，随机无放回（或有放回）抽取 k 个个体。

3. 进行适应度比较
计算并对比 k 个个体的适应度值，选出适应度最优的个体。

4. 记录优胜个体
将该优胜个体加入父代集合。

5. 重复迭代
重复步骤 2~4，直到选出满足下一代种群规模所需的父代数量。

## 四、特点与优势

1. 操作简单，计算开销小，易于编程实现；

2. 对适应度数值不敏感，无需归一化处理；

3. 稳定性强，不易出现早熟收敛现象；

4. 可通过调整竞赛规模 k 灵活控制选择压力。

## 五、在遗传算法中的作用

锦标赛选择算子是驱动种群向最优解进化的关键环节，能够有效保留优良个体、淘汰劣质个体，同时维持种群多样性，为交叉和变异操作奠定基础，保障算法持续迭代优化。`

const QA_EXPLAIN_MODE_PROFILE = Object.freeze({
  deep: {
    label: '深度讲解',
    intro: '以下内容将按“定义 -> 原理 -> 步骤 -> 易错点”四层结构展开。',
    outro: '如果你需要，我还可以继续补充推导细节和典型变式题。'
  },
  assist: {
    label: '辅助理解',
    intro: '以下先给出直观理解与最小步骤，再配一条可直接套用的解题思路。',
    outro: '如果你愿意，可以继续切回深度讲解模式完成完整推导。'
  }
})

const QA_EXPLAIN_STYLE_PROFILE = Object.freeze({
  gentle: {
    label: '温柔活泼',
    prefix: '好的呀，我们一步一步来，先把关键点理顺。',
    suffix: '你已经抓到重点啦，继续保持这个节奏就很好。'
  },
  rigorous: {
    label: '客观严谨',
    prefix: '下面给出结构化说明，并保持术语与逻辑一致。',
    suffix: '如需验证，可继续提供具体题目进行逐步推导。'
  }
})

const escapeHtmlForMarkdown = (text) => String(text || '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')

const normalizePresetLectureScript = (text) => String(text || '')
  .replace(/^\uFEFF/, '')
  .replace(/^[\s"'“”‘’]+/, '')
  .replace(/[\s"'“”‘’]+$/, '')
  .trim()

const resolveExplainModeProfile = (mode) => QA_EXPLAIN_MODE_PROFILE[String(mode || '').trim()] || QA_EXPLAIN_MODE_PROFILE.deep

const resolveExplainStyleProfile = (style) => QA_EXPLAIN_STYLE_PROFILE[String(style || '').trim()] || QA_EXPLAIN_STYLE_PROFILE.rigorous

const buildProfiledQaReply = (baseMarkdown) => {
  const modeProfile = resolveExplainModeProfile(aiExplainMode.value)
  const styleProfile = resolveExplainStyleProfile(aiExplainStyle.value)
  const core = String(baseMarkdown || '').trim()
  return [
    `> 讲解模式：${modeProfile.label} · 表达风格：${styleProfile.label}`,
    styleProfile.prefix,
    modeProfile.intro,
    core,
    `${modeProfile.outro} ${styleProfile.suffix}`
  ].filter(Boolean).join('\n\n')
}

const tracePoint = ref(false)
const traceTop = ref(0)
const traceLeft = ref(0)
const outlineFilter = ref('all')
const activeWorkbenchTab = ref('tree')
const isLowerWorkbenchExpanded = ref(false)
const isKnowledgeOutlineVisible = ref(false)
const knowledgeOutlineLoading = ref(false)
const knowledgeOutlineMarkdown = ref('')
const knowledgeOutlineStreamText = ref('')
const knowledgeOutlineStreaming = ref(false)
const knowledgeOutlineLoadedOnce = ref(false)
const knowledgeOutlinePanelOpenedOnce = ref(false)
let knowledgeOutlineStreamTimer = null
const activeRightPanel = ref('')
const qaContextBinding = ref(true)
const qaDeepReasoning = ref(false)
const qaWebSearch = ref(false)
const aiExplainMode = ref('deep')
const aiExplainStyle = ref('rigorous')
const qaAutoSpeakAnswer = ref(true)
const presetLectureScriptOnPlay = ref(true)
const presetLectureScriptText = ref(PRESET_LECTURE_SCRIPT_FALLBACK_TEXT)
const presetLectureScriptLoaded = ref(false)
const isPresetLectureSpeaking = ref(false)
const shouldSpeakPresetOnNextPlay = ref(false)
const shouldResumeSpeechOnNextPlay = ref(false)
const shouldResumePlaybackAfterQa = ref(false)
const askPanelAction = ref(null)
const isCompactViewport = ref(false)
const isQaPanelCollapsed = ref(false)
const classroomLayout = reactive({
  leftPercent: 64,
  dragging: false,
  pointerId: null,
  startX: 0,
  startLeftPercent: 64
})
const subtitleLayout = reactive({
  leftPercent: 25,
  bottom: 96,
  dragging: false,
  pointerId: null,
  startX: 0,
  startY: 0,
  startLeftPercent: 25,
  startBottom: 96
})
const lastContextHintNodeId = ref('')
const summaryMode = ref('quick')
const mergedSummary = ref('')
const lessonFeedbackRating = ref(0)
const lessonFeedbackComment = ref('')
const nodeNotes = ref({})
const nodeNoteTitles = ref({})
const noteFavoriteDialogVisible = ref(false)
const noteFavoriteSaving = ref(false)
const noteFavoriteForm = reactive({
  title: '',
  category: 'to_learn',
  content: ''
})
const noteFavoriteCategoryOptions = [
  { value: 'to_learn', label: '待学习' },
  { value: 'mastered', label: '已掌握' },
  { value: 'weak', label: '薄弱点' },
  { value: 'key', label: '重难点' }
]
const graphSyncLoading = ref(false)
const graphScanLoading = ref(false)
const graphRepairLoading = ref(false)
const graphSyncPayload = ref(null)
const graphScanReport = ref(null)
const graphMessage = ref('')

const showBreakpointDialog = ref(false)
const breakpointPage = ref(3)

const uploadedFile = ref(null)
const isParsing = ref(false)
const parseResult = ref('')
const knowledgeList = ref([])
const treeProps = ref({
  label: 'name',
  children: 'children'
})

const currentWeakPoint = ref('')
const currentExplain = ref('')
const currentTest = ref(null)
const testResult = ref(null)
const weakPointTags = ref([])
const currentQuestionId = ref('')
const learningStats = ref({
  focusScore: 0,
  totalQuestions: 0,
  weakPointCount: 0,
  masteryRate: 100
})

const currentExplainModeLabel = computed(() => resolveExplainModeProfile(aiExplainMode.value).label)
const currentExplainStyleLabel = computed(() => resolveExplainStyleProfile(aiExplainStyle.value).label)

const knowledgeOutlineHtml = computed(() => {
  const source = String(knowledgeOutlineStreamText.value || '').trim()
  if (!source) return ''
  try {
    return outlineMarkdownRenderer.render(source)
  } catch (error) {
    return `<pre>${escapeHtmlForMarkdown(source)}</pre>`
  }
})

const practiceChoiceQuestions = [
  {
    id: 'choice1',
    question: '“遗传算法”这一术语最早出现在谁的博士论文中？',
    answer: 'B',
    answerLabel: 'B. J. D. Bagley',
    options: [
      { value: 'A', label: 'A. John Holland' },
      { value: 'B', label: 'B. J. D. Bagley' },
      { value: 'C', label: 'C. R.B. Hollstien' },
      { value: 'D', label: 'D. K.A. De Jong' }
    ]
  },
  {
    id: 'choice2',
    question: '在遗传算法中，用来衡量个体优劣的指标是：',
    answer: 'B',
    answerLabel: 'B. 适应度',
    options: [
      { value: 'A', label: 'A. 染色体长度' },
      { value: 'B', label: 'B. 适应度' },
      { value: 'C', label: 'C. 基因频率' },
      { value: 'D', label: 'D. 种群规模' }
    ]
  },
  {
    id: 'choice3',
    question: '下列哪一项不属于遗传算法的基本操作？',
    answer: 'D',
    answerLabel: 'D. 聚类',
    options: [
      { value: 'A', label: 'A. 选择-复制' },
      { value: 'B', label: 'B. 交叉' },
      { value: 'C', label: 'C. 突变' },
      { value: 'D', label: 'D. 聚类' }
    ]
  },
  {
    id: 'choice4',
    question: '染色体“10110”通过单点变异（第三位取反）后变成：',
    answer: 'A',
    answerLabel: 'A. 10010',
    options: [
      { value: 'A', label: 'A. 10010' },
      { value: 'B', label: 'B. 10110' },
      { value: 'C', label: 'C. 11110' },
      { value: 'D', label: 'D. 10100' }
    ]
  },
  {
    id: 'choice5',
    question: '适应度函数在遗传算法中的作用是：',
    answer: 'B',
    answerLabel: 'B. 指导搜索方向',
    options: [
      { value: 'A', label: 'A. 编码个体' },
      { value: 'B', label: 'B. 指导搜索方向' },
      { value: 'C', label: 'C. 控制种群大小' },
      { value: 'D', label: 'D. 随机生成个体' }
    ]
  }
]

const practiceAnswers = reactive({
  choice1: '',
  choice2: '',
  choice3: '',
  choice4: '',
  choice5: '',
  fill1a: '',
  fill1b: '',
  fill2: '',
  fill3: '',
  fill4: '',
  short1: '',
  short2: '',
  app1: '',
  app2: '',
  app3: '',
  app4: '',
  app5: ''
})
const exerciseSubmitted = ref(false)
const exerciseScore = ref(0)

const pageTimelineDuration = computed(() => {
  const lastNode = playbackNodes.value[playbackNodes.value.length - 1]
  return Number(lastNode?.end_sec || 0)
})

const normalizeExerciseText = (value) => String(value || '').trim().replace(/\s+/g, '').toLowerCase()

const isFillAnswerCorrect = (key, acceptedValues) => {
  const answer = normalizeExerciseText(practiceAnswers[key])
  if (!answer) return false
  return acceptedValues.some((item) => {
    const accepted = normalizeExerciseText(item)
    return answer === accepted || answer.includes(accepted) || accepted.includes(answer)
  })
}

const scoreEssayAnswer = (value, keywords, maxScore) => {
  const text = normalizeExerciseText(value)
  if (!text) return 0
  const matchedCount = keywords.filter((keyword) => text.includes(normalizeExerciseText(keyword))).length
  if (matchedCount >= 3) return maxScore
  if (matchedCount >= 2) return Math.ceil(maxScore * 0.6)
  if (matchedCount >= 1) return Math.ceil(maxScore * 0.3)
  return 0
}

const scoreProbabilityAnswer = (value, acceptedValues, maxScore) => {
  const answer = normalizeExerciseText(value)
  if (!answer) return 0
  return acceptedValues.some((item) => answer === normalizeExerciseText(item)) ? maxScore : 0
}

const scoreCrossOverAnswer = (value, maxScore) => {
  const answer = normalizeExerciseText(value)
  if (!answer) return 0
  const hasChildOne = answer.includes('0111')
  const hasChildTwo = answer.includes('0001')
  if (hasChildOne && hasChildTwo) return maxScore
  if (hasChildOne || hasChildTwo) return Math.ceil(maxScore * 0.5)
  return 0
}

const resetPracticeExercise = () => {
  Object.keys(practiceAnswers).forEach((key) => {
    practiceAnswers[key] = ''
  })
  exerciseSubmitted.value = false
  exerciseScore.value = 0
}

const submitPracticeExercise = () => {
  const choiceScore = practiceChoiceQuestions.reduce((total, item) => {
    return total + (practiceAnswers[item.id] === item.answer ? 2 : 0)
  }, 0)

  const fillScore = [
    isFillAnswerCorrect('fill1a', ['染色体', '染色体串']) ? 2 : 0,
    isFillAnswerCorrect('fill1b', ['基因']) ? 2 : 0,
    isFillAnswerCorrect('fill2', ['适应度']) ? 2 : 0,
    isFillAnswerCorrect('fill3', ['部分', '片段', '一部分']) ? 2 : 0,
    isFillAnswerCorrect('fill4', ['个体']) ? 2 : 0
  ].reduce((total, value) => total + value, 0)

  const shortScore = [
    scoreEssayAnswer(practiceAnswers.short1, ['选择', '适应度', '复制', '下一代'], 5),
    scoreEssayAnswer(practiceAnswers.short2, ['父代', '交叉点', '交换', '子代'], 5)
  ].reduce((total, value) => total + value, 0)

  const appScore = [
    scoreProbabilityAnswer(practiceAnswers.app1, ['0.2', '0.20', '20%', '1/5'], 2),
    scoreProbabilityAnswer(practiceAnswers.app2, ['0.3', '0.30', '30%', '3/10'], 2),
    scoreProbabilityAnswer(practiceAnswers.app3, ['0.1', '0.10', '10%', '1/10'], 2),
    scoreProbabilityAnswer(practiceAnswers.app4, ['0.4', '0.40', '40%', '2/5'], 2),
    scoreCrossOverAnswer(practiceAnswers.app5, 2)
  ].reduce((total, value) => total + value, 0)

  exerciseScore.value = choiceScore + fillScore + shortScore + appScore
  exerciseSubmitted.value = true
  ElMessage.success(`练习已提交，当前得分 ${exerciseScore.value} / 40`)
}

const currentNodeMeta = computed(() => {
  return playbackNodes.value.find(node => node.node_id === currentNodeId.value) || null
})

const activeNodeDuration = computed(() => Number(currentNodeMeta.value?.duration_sec || 0))

const activeNodeElapsedSec = computed(() => {
  const node = currentNodeMeta.value
  if (!node) return 0
  return Math.max(0, Math.min(activeNodeDuration.value, currentTimelineSec.value - Number(node.start_sec || 0)))
})

const activeNodeTypeLabel = computed(() => {
  const type = currentNodeMeta.value?.type
  if (type === 'opening') return '开场讲解'
  if (type === 'transition') return '过渡收束'
  return '核心讲解'
})

const courseAudioStatusText = computed(() => {
  const status = playbackAudioMeta.value?.audio_status
  const duration = Number(playbackAudioMeta.value?.audio_duration_sec || 0)
  if (!status) return ''
  if (status === 'ready' && duration > 0) {
    return `音频已生成 ${formatNodeTime(duration)}`
  }
  if (status === 'processing') return '音频生成中'
  return '使用时长驱动讲解'
})

const displayOutlineNodes = computed(() => {
  const realNodes = (playbackNodes.value || []).map((node, index) => ({
    ...node,
    type: node.type || (index === 0 ? 'opening' : 'core')
  }))
  return realNodes
})

const filteredOutlineNodes = computed(() => {
  if (outlineFilter.value === 'all') return displayOutlineNodes.value
  if (outlineFilter.value === 'core') {
    return displayOutlineNodes.value.filter(node => (node.type || 'core') === 'core')
  }
  return displayOutlineNodes.value.filter(node => node.type === outlineFilter.value)
})

const prerequisiteNodes = computed(() => {
  return filteredOutlineNodes.value.filter((node, idx) => {
    if (node.mockBucket) return node.mockBucket === 'prerequisite'
    if (Number(node.start_sec || 0) === 0) return true
    return (node.type === 'opening' || node.type === 'transition') && idx < 3
  })
})

const masteredNodes = computed(() => {
  return filteredOutlineNodes.value.filter((node) => {
    if (node.mockBucket) return node.mockBucket === 'mastered'
    return Number(node.end_sec || 0) <= currentTimelineSec.value
  })
})

const unmasteredNodes = computed(() => {
  const prerequisiteIdSet = new Set(prerequisiteNodes.value.map(node => node.node_id))
  return filteredOutlineNodes.value.filter((node) => {
    if (node.mockBucket) return node.mockBucket === 'unmastered'
    if (prerequisiteIdSet.has(node.node_id)) return false
    return Number(node.end_sec || 0) > currentTimelineSec.value
  })
})

const learningStatusSignals = computed(() => {
  const total = Math.max(1, filteredOutlineNodes.value.length)
  const masteredRate = Math.round((masteredNodes.value.length / total) * 100)
  const weakRate = Math.round((unmasteredNodes.value.length / total) * 100)
  const rhythmScore = Math.min(98, Math.max(60, 72 + Math.round((progressPercent.value - 50) * 0.22)))
  const interactionScore = Math.min(99, 76 + Math.min(18, Math.round((qaHistory.value.length || 0) * 1.5)))
  return [
    { id: 'mastery', label: '掌握完成率', value: `${masteredRate}%`, desc: '依据节点掌握状态实时计算（结合课堂互动数据）。' },
    { id: 'weak', label: '薄弱节点占比', value: `${weakRate}%`, desc: '薄弱点会联动“薄弱强化/查找习题”按钮。' },
    { id: 'rhythm', label: '学习节奏评分', value: `${rhythmScore} 分`, desc: '结合进度推进、暂停频次与节点切换节奏评估。' },
    { id: 'interaction', label: '课堂互动活跃度', value: `${interactionScore} 分`, desc: '根据问答次数与练习提交记录生成互动指标。' }
  ]
})

const knowledgeWorkbenchTree = computed(() => {
  if (knowledgeList.value.length > 0) {
    return knowledgeList.value
  }
  return filteredOutlineNodes.value.map((node) => ({
    id: node.node_id,
    name: node.title || node.node_id,
    children: []
  }))
})


const buildDefaultNodeNoteTitle = () => {
  const nodeTitle = currentNodeMeta.value?.title || currentNodeId.value || `第${currentPage.value}页要点`
  const courseName = currentCourseName.value || '课堂笔记'
  return `${courseName} · ${nodeTitle}`
}

const currentNodeNoteTitle = computed({
  get: () => {
    const nodeId = currentNodeId.value || 'default'
    return nodeNoteTitles.value[nodeId] || buildDefaultNodeNoteTitle()
  },
  set: (value) => {
    const nodeId = currentNodeId.value || 'default'
    const nextTitle = String(value || '').trim()
    nodeNoteTitles.value = {
      ...nodeNoteTitles.value,
      [nodeId]: nextTitle || buildDefaultNodeNoteTitle()
    }
  }
})
const currentNodeNote = computed({
  get: () => {
    const nodeId = currentNodeId.value || 'default'
    return nodeNotes.value[nodeId] || ''
  },
  set: (value) => {
    const nodeId = currentNodeId.value || 'default'
    nodeNotes.value = {
      ...nodeNotes.value,
      [nodeId]: value
    }
  }
})

const isRightDrawerOpen = computed(() => activeRightPanel.value !== '')
const showClassroomRightSidebar = computed(() => !isCompactViewport.value)
const classroomCoursewareList = computed(() => {
  if (filteredSelectionCoursewares.value.length > 0) return filteredSelectionCoursewares.value
  return selectionCoursewares.value
})
const classroomCourseImageSrc = computed(() => {
  const selectedCourseware = selectionCoursewares.value.find((item) => item.id === selectedCoursewareId.value || item.id === courseId.value)
  const localPageImage = resolveLocalCoursewarePageImage(selectedCourseware, currentPage.value)
  if (localPageImage) return localPageImage

  const preferred = String(selectedCoursePreviewImageUrl.value || '').trim()
  if (preferred) return preferred

  const imageFileFallback = String(selectedCourseware?.imageFileUrl || '').trim()
  if (imageFileFallback) return imageFileFallback

  const pagePreview = String(courseImg.value || '').trim()
  if (pagePreview) return pagePreview

  return COURSE_PREVIEW_FALLBACK_SRC
})
const graphSummaryVisible = computed(() => Boolean(graphSyncPayload.value || graphScanReport.value))
const graphEdgeCount = computed(() => Number(graphSyncPayload.value?.edgeCount || 0))
const graphOrphanCount = computed(() => Number(graphScanReport.value?.unionOrphanNodeIds?.length || 0))
const graphBucketCount = computed(() => Number(graphScanReport.value?.buckets?.length || 0))
const presetMindmapImageSrc = computed(() => {
  const images = PRESET_MINDMAP_IMAGES
  if (!images.length) return ''
  const imageIndex = Math.min(images.length - 1, Math.max(0, Number(currentPage.value || 1) - 1))
  return images[imageIndex] || images[0]
})
const coursePreviewFallbackSrc = computed(() => COURSE_PREVIEW_FALLBACK_SRC)
const qaFabStyle = computed(() => ({
  left: `${qaFabLayout.left}px`,
  top: `${qaFabLayout.top}px`,
  right: 'auto',
  bottom: 'auto'
}))

const classroomSubtitleStyle = computed(() => ({
  left: `${subtitleLayout.leftPercent}%`,
  bottom: `${subtitleLayout.bottom}px`
}))

const getClassroomPaneBasis = (percentValue) => {
  const ratio = Math.min(1, Math.max(0, Number(percentValue || 0) / 100))
  if (!showClassroomRightSidebar.value) {
    return `${Math.round(Number(percentValue || 0))}%`
  }
  return `calc((100% - ${CLASSROOM_RIGHT_RAIL_WIDTH}px) * ${ratio.toFixed(4)})`
}

const classroomLeftPaneStyle = computed(() => {
  if (isCompactViewport.value || isQaPanelCollapsed.value) return {}
  return {
    flexBasis: getClassroomPaneBasis(classroomLayout.leftPercent)
  }
})

const classroomQaPaneStyle = computed(() => {
  if (isCompactViewport.value || isQaPanelCollapsed.value) return {}
  return {
    flexBasis: getClassroomPaneBasis(100 - classroomLayout.leftPercent)
  }
})

const normalizeTimeSec = (value, fallback = 0) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return fallback
  return Math.max(0, Math.floor(numeric))
}

const formatNodeTime = (seconds) => {
  const normalized = normalizeTimeSec(seconds)
  const mins = String(Math.floor(normalized / 60)).padStart(2, '0')
  const secs = String(normalized % 60).padStart(2, '0')
  return `${mins}:${secs}`
}

const trimText = (text, length = 56) => {
  const value = String(text || '').replace(/\s+/g, ' ').trim()
  if (!value) return ''
  if (value.length <= length) return value
  return `${value.slice(0, length)}...`
}

const focusCurrentNode = () => {
  if (!currentNodeId.value) return
  const exists = filteredOutlineNodes.value.some(node => node.node_id === currentNodeId.value)
  if (!exists) {
    outlineFilter.value = 'all'
  }
}

const handleWorkbenchTreeNodeClick = async (data) => {
  const nodeId = String(data?.id || '')
  const targetNode = filteredOutlineNodes.value.find(node => node.node_id === nodeId)
  if (targetNode?.mockBucket) {
    ElMessage.info(`这是示例节点：${targetNode.title || targetNode.node_id}`)
    // 保留节点定位交互反馈
    currentNodeId.value = nodeId
    activeWorkbenchTab.value = 'knowledge'
    return
  }
  if (targetNode?.node_id) {
    await selectPlaybackNode(targetNode.node_id)
    if (lastContextHintNodeId.value !== targetNode.node_id) {
      pushKnowledgeContextHint(targetNode.title || targetNode.node_id)
      lastContextHintNodeId.value = targetNode.node_id
    }
    return
  }
  handleNodeClick(data)
}

const reinforceNode = async (node) => {
  activeWorkbenchTab.value = 'interaction'
  await startWeakPointLearn({ id: node.node_id, name: node.title || node.node_id })
}

const findPracticeForNode = async (node) => {
  activeWorkbenchTab.value = 'interaction'
  currentWeakPoint.value = node.title || node.node_id
  currentTest.value = {
    question: `围绕“${currentWeakPoint.value}”生成一道随堂测验：以下哪项描述最准确？`,
    options: ['概念定义', '应用场景', '常见误区', '以上都需要结合理解']
  }
  testResult.value = null
}

const createAskPanelAction = (mode, text) => {
  askPanelAction.value = {
    id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    mode,
    text: String(text || '')
  }
}

const openAskPanelIfNeeded = () => {
  if (isQaPanelCollapsed.value) {
    isQaPanelCollapsed.value = false
  }
}

const pushKnowledgeContextHint = (nodeTitle) => {
  const cleanTitle = String(nodeTitle || '').trim()
  if (!cleanTitle) return
  createAskPanelAction('system', `当前学生正在学习【${cleanTitle}】，请基于该知识点内容进行解答。`)
}

const askAboutUnmasteredNode = async (node) => {
  const nodeId = String(node?.node_id || '')
  const nodeTitle = String(node?.title || nodeId || '当前知识点')
  if (nodeId) {
    await selectPlaybackNode(nodeId)
    if (lastContextHintNodeId.value !== nodeId) {
      pushKnowledgeContextHint(nodeTitle)
      lastContextHintNodeId.value = nodeId
    }
  }
  activeWorkbenchTab.value = 'knowledge'
  openAskPanelIfNeeded()
  const presetQuestion = `请给我详细讲解一下【${nodeTitle}】`
  question.value = presetQuestion
  createAskPanelAction('draft', presetQuestion)
  ElMessage.success('已将问题填入右侧 AI 助手输入框')
}

const toggleLowerWorkbench = () => {
  isLowerWorkbenchExpanded.value = !isLowerWorkbenchExpanded.value
  if (isLowerWorkbenchExpanded.value && !activeWorkbenchTab.value) {
    activeWorkbenchTab.value = 'tree'
  }
}

const loadPresetLectureScriptText = async () => {
  if (presetLectureScriptLoaded.value && String(presetLectureScriptText.value || '').trim()) {
    return presetLectureScriptText.value
  }

  try {
    const response = await fetch(PRESET_LECTURE_SCRIPT_PATH, {
      cache: 'no-store'
    })
    if (!response.ok) {
      throw new Error(`读取课堂讲稿失败: ${response.status}`)
    }
    const content = await response.text()
    const normalized = normalizePresetLectureScript(content)
    presetLectureScriptText.value = normalized || PRESET_LECTURE_SCRIPT_FALLBACK_TEXT
  } catch (error) {
    presetLectureScriptText.value = PRESET_LECTURE_SCRIPT_FALLBACK_TEXT
    console.warn('加载课堂讲稿失败，已使用兜底文案', error)
  } finally {
    presetLectureScriptLoaded.value = true
  }

  return presetLectureScriptText.value
}

const stopKnowledgeOutlineStream = () => {
  if (knowledgeOutlineStreamTimer) {
    window.clearInterval(knowledgeOutlineStreamTimer)
    knowledgeOutlineStreamTimer = null
  }
  knowledgeOutlineStreaming.value = false
}

const startKnowledgeOutlineStream = ({ restart = true } = {}) => {
  const source = String(knowledgeOutlineMarkdown.value || '')
  if (!source) {
    knowledgeOutlineStreamText.value = ''
    knowledgeOutlineStreaming.value = false
    return
  }

  stopKnowledgeOutlineStream()

  if (restart) {
    knowledgeOutlineStreamText.value = ''
  }

  let cursor = restart ? 0 : knowledgeOutlineStreamText.value.length
  if (cursor >= source.length) {
    knowledgeOutlineStreamText.value = source
    knowledgeOutlineStreaming.value = false
    return
  }

  knowledgeOutlineStreaming.value = true
  knowledgeOutlineStreamTimer = window.setInterval(() => {
    const step = 2
    cursor = Math.min(source.length, cursor + step)
    knowledgeOutlineStreamText.value = source.slice(0, cursor)
    if (cursor >= source.length) {
      stopKnowledgeOutlineStream()
    }
  }, KNOWLEDGE_OUTLINE_STREAM_INTERVAL_MS)
}

const loadKnowledgeOutlineMarkdown = async () => {
  if (knowledgeOutlineLoadedOnce.value && String(knowledgeOutlineMarkdown.value || '').trim()) {
    return knowledgeOutlineMarkdown.value
  }

  const loadStartAt = Date.now()
  knowledgeOutlineLoading.value = true
  try {
    const response = await fetch(KNOWLEDGE_OUTLINE_MARKDOWN_PATH, {
      cache: 'no-store'
    })
    if (!response.ok) {
      throw new Error(`读取大纲失败: ${response.status}`)
    }
    const content = await response.text()
    knowledgeOutlineMarkdown.value = String(content || '').trim() || KNOWLEDGE_OUTLINE_FALLBACK_MARKDOWN
  } catch (error) {
    knowledgeOutlineMarkdown.value = KNOWLEDGE_OUTLINE_FALLBACK_MARKDOWN
    console.warn('加载知识大纲失败，已使用兜底文案', error)
  } finally {
    if (!knowledgeOutlineLoadedOnce.value) {
      const elapsed = Date.now() - loadStartAt
      if (elapsed < KNOWLEDGE_OUTLINE_FIRST_LOAD_MIN_DELAY_MS) {
        await new Promise(resolve => window.setTimeout(resolve, KNOWLEDGE_OUTLINE_FIRST_LOAD_MIN_DELAY_MS - elapsed))
      }
    }
    knowledgeOutlineLoading.value = false
    knowledgeOutlineLoadedOnce.value = true
  }

  return knowledgeOutlineMarkdown.value
}

const toggleKnowledgeOutline = async () => {
  if (isKnowledgeOutlineVisible.value) {
    closeKnowledgeOutline()
    return
  }

  isKnowledgeOutlineVisible.value = true
  if (!knowledgeOutlinePanelOpenedOnce.value && knowledgeOutlineLoadedOnce.value) {
    knowledgeOutlineLoading.value = true
    await new Promise(resolve => window.setTimeout(resolve, KNOWLEDGE_OUTLINE_FIRST_LOAD_MIN_DELAY_MS))
    knowledgeOutlineLoading.value = false
  }
  await loadKnowledgeOutlineMarkdown()
  knowledgeOutlinePanelOpenedOnce.value = true
  startKnowledgeOutlineStream({ restart: true })
}

const closeKnowledgeOutline = () => {
  isKnowledgeOutlineVisible.value = false
  stopKnowledgeOutlineStream()
}

const restartKnowledgeOutlineStream = async () => {
  if (!isKnowledgeOutlineVisible.value) {
    isKnowledgeOutlineVisible.value = true
  }
  await loadKnowledgeOutlineMarkdown()
  startKnowledgeOutlineStream({ restart: true })
}

const getNodeNoteTitleStoreKey = () => `fuww_student_note_title_map:${String(studentId.value || '').trim().toLowerCase()}`

const getFavoriteBoardStoreKey = () => `fuww_student_favorite_board:${String(studentId.value || '').trim().toLowerCase()}`

const resolveFavoriteCategoryLabel = (category) => {
  if (category === 'to_learn') return '待学习'
  if (category === 'mastered') return '已掌握'
  if (category === 'weak') return '薄弱点'
  return '重点难点'
}

const persistNoteTitleByCoursePage = (title) => {
  if (typeof window === 'undefined') return
  if (!courseId.value || !currentPage.value) return
  const cleanTitle = String(title || '').trim()
  if (!cleanTitle) return
  const key = getNodeNoteTitleStoreKey()
  let map = {}
  try {
    map = JSON.parse(window.localStorage.getItem(key) || '{}') || {}
  } catch (error) {
    map = {}
  }
  map[`${courseId.value}::${currentPage.value}`] = cleanTitle
  window.localStorage.setItem(key, JSON.stringify(map))
}

const setFavoriteBoardColumn = (favoriteId, category) => {
  if (typeof window === 'undefined') return
  if (!favoriteId) return
  const key = getFavoriteBoardStoreKey()
  let map = {}
  try {
    map = JSON.parse(window.localStorage.getItem(key) || '{}') || {}
  } catch (error) {
    map = {}
  }
  map[String(favoriteId)] = category
  window.localStorage.setItem(key, JSON.stringify(map))
}

const saveCurrentNodeNote = async (options = {}) => {
  const safeOptions = options && typeof options === 'object' && !Object.prototype.hasOwnProperty.call(options, 'target')
    ? options
    : {}
  const noteContent = String(safeOptions.contentOverride ?? currentNodeNote.value ?? '').trim()
  const noteTitle = String(safeOptions.titleOverride ?? currentNodeNoteTitle.value ?? '').trim()
  if (!noteContent) {
    if (!safeOptions.silent) {
      ElMessage.warning('请先填写课堂笔记内容，再保存到个人中心')
    }
    return false
  }
  if (!courseId.value || !studentId.value) {
    if (!safeOptions.silent) {
      ElMessage.warning('当前没有可用课程上下文，无法同步到个人中心')
    }
    return false
  }

  const nodeId = currentNodeId.value || 'default'
  nodeNotes.value = {
    ...nodeNotes.value,
    [nodeId]: noteContent
  }
  nodeNoteTitles.value = {
    ...nodeNoteTitles.value,
    [nodeId]: noteTitle || buildDefaultNodeNoteTitle()
  }

  try {
    await studentV1Api.coursewares.saveNote({
      studentId: studentId.value,
      courseId: courseId.value,
      pageNum: currentPage.value,
      content: noteContent
    })
    persistNoteTitleByCoursePage(noteTitle || buildDefaultNodeNoteTitle())
    if (!safeOptions.silent) {
      ElMessage.success('课堂笔记已同步到个人中心')
    }
    return true
  } catch (error) {
    if (!safeOptions.silent) {
      ElMessage.error(`同步课堂笔记失败：${error.message || error}`)
    }
    return false
  }
}

const openNoteFavoriteDialog = () => {
  const noteContent = String(currentNodeNote.value || '').trim()
  if (!noteContent) {
    ElMessage.warning('请先填写课堂笔记，再执行收藏')
    return
  }
  noteFavoriteForm.title = String(currentNodeNoteTitle.value || buildDefaultNodeNoteTitle()).trim()
  noteFavoriteForm.category = 'to_learn'
  noteFavoriteForm.content = noteContent
  noteFavoriteDialogVisible.value = true
}

const confirmSaveNoteFavorite = async () => {
  if (noteFavoriteSaving.value) return
  const title = String(noteFavoriteForm.title || '').trim()
  const content = String(noteFavoriteForm.content || '').trim()
  const category = String(noteFavoriteForm.category || 'to_learn')
  if (!title) {
    ElMessage.warning('请先填写笔记标题')
    return
  }
  if (!content) {
    ElMessage.warning('请先填写笔记内容')
    return
  }

  noteFavoriteSaving.value = true
  try {
    const noteSaved = await saveCurrentNodeNote({
      silent: true,
      contentOverride: content,
      titleOverride: title
    })
    if (!noteSaved) {
      ElMessage.warning('笔记同步失败，请先检查课程上下文或稍后重试')
      return
    }

    const response = await studentV1Api.coursewares.addFavorite({
      studentId: studentId.value,
      courseId: courseId.value,
      nodeId: currentNodeId.value || null,
      pageNum: currentPage.value,
      title,
      tags: [resolveFavoriteCategoryLabel(category), '课堂笔记']
    })
    const favoriteId = response?.data?.id || response?.data?.favoriteId || ''
    setFavoriteBoardColumn(favoriteId, category)

    noteFavoriteDialogVisible.value = false
    personalCenterInitialTab.value = 'favorites'
    ElMessage.success(`已收藏到个人中心「${resolveFavoriteCategoryLabel(category)}」`) 
  } catch (error) {
    ElMessage.error(`收藏失败：${error.message || error}`)
  } finally {
    noteFavoriteSaving.value = false
  }
}

const jumpToPersonalNotes = () => {
  jumpToSection('personal', { personalTab: 'notes' })
}

const optimizeCurrentNoteWithAI = () => {
  const noteText = String(currentNodeNote.value || '').trim()
  if (!noteText) {
    ElMessage.warning('请先填写课堂笔记，再执行 AI 优化')
    return
  }
  openAskPanelIfNeeded()
  const nodeTitle = currentNodeMeta.value?.title || currentNodeId.value || '当前知识点'
  const optimizePrompt = [
    '请优化润色以下课堂笔记：',
    `知识点：${nodeTitle}`,
    '要求：保持术语准确、结构清晰，并补充遗漏的关键点。',
    '原笔记：',
    noteText
  ].join('\n')
  createAskPanelAction('send', optimizePrompt)
}

const toggleQaPanel = () => {
  isQaPanelCollapsed.value = !isQaPanelCollapsed.value
}

const submitLessonFeedback = () => {
  const rating = Number(lessonFeedbackRating.value || 0)
  if (!rating) {
    ElMessage.warning('请先给出满意度评分')
    return
  }
  const nodeTitle = currentNodeMeta.value?.title || currentNodeId.value
  ElMessage.success(`已提交反馈：${nodeTitle}，评分 ${rating} 星`)
  lessonFeedbackComment.value = ''
}

const toggleRightPanel = (panel) => {
  if (panel === 'graph' && !courseId.value) return
  activeRightPanel.value = activeRightPanel.value === panel ? '' : panel
}

const closeRightPanel = () => {
  activeRightPanel.value = ''
}

const selectCoursewareFromDrawer = async (courseware) => {
  const nextCourseId = String(courseware?.id || '').trim()
  if (!nextCourseId) return

  if (courseware?.teachingCourseId) {
    selectedTeachingCourseId.value = String(courseware.teachingCourseId)
  }
  if (courseware?.courseClassId) {
    selectedCourseClassId.value = String(courseware.courseClassId)
  }

  selectedCoursewareId.value = nextCourseId
  selectedCoursePreviewImageUrl.value = String(courseware?.previewImageUrl || courseware?.imageFileUrl || '').trim()

  if (nextCourseId === courseId.value) return

  isPlay.value = false
  stopSpeechNarration()
  courseId.value = nextCourseId
  currentCourseName.value = String(courseware?.name || '未命名课件')
  resetKnowledgeWorkspace()
  totalPage.value = Number(courseware?.totalPage || 1)
  currentPage.value = 1
  currentNodeId.value = 'p1_n1'

  try {
    await refreshCurrentPageData({ preserveCurrentNode: false })
    const session = await studentV1Api.sessions.start({
      userId: studentId.value,
      courseId: courseId.value
    })
    sessionId.value = session?.data?.sessionId || sessionId.value
    await Promise.all([loadWeakPoints(), loadStudyData(), saveBreakpoint()])
  } catch (error) {
    console.warn('切换课件失败', error)
  }
}

const collectWeakPointToFavorite = async (weakPoint) => {
  const weakName = String(weakPoint?.name || '').trim() || '薄弱知识点'
  personalCenterInitialTab.value = 'favorites'

  if (!courseId.value || !studentId.value) {
    console.warn('收藏薄弱点失败：缺少课程或学生上下文')
    return
  }

  try {
    const response = await studentV1Api.coursewares.addFavorite({
      studentId: studentId.value,
      courseId: courseId.value,
      nodeId: currentNodeId.value || null,
      pageNum: currentPage.value,
      title: `${weakName} · 学习分析收藏`,
      tags: [resolveFavoriteCategoryLabel('weak'), '学习分析']
    })
    const favoriteId = response?.data?.id || response?.data?.favoriteId || ''
    setFavoriteBoardColumn(favoriteId, 'weak')
    ElMessage.success(`已收藏「${weakName}」到个人中心`) 
  } catch (error) {
    console.warn('收藏薄弱点失败（已忽略弹窗）', error)
  }
}

const handleGraphSync = async () => {
  if (!courseId.value || graphSyncLoading.value) return
  graphSyncLoading.value = true
  graphMessage.value = ''
  try {
    const resp = await studentV1Api.coursewares.syncKnowledgeGraph(courseId.value)
    graphSyncPayload.value = resp?.data || {}
    graphMessage.value = `同步完成：共 ${graphEdgeCount.value} 条关系边。`
  } catch (err) {
    graphMessage.value = `同步失败：${err.message || err}`
  } finally {
    graphSyncLoading.value = false
  }
}

const handleGraphScan = async () => {
  if (!courseId.value || graphScanLoading.value) return
  graphScanLoading.value = true
  graphMessage.value = ''
  try {
    const resp = await studentV1Api.coursewares.getKnowledgeGraphReferenceHealth(courseId.value)
    graphScanReport.value = resp?.data || null
    if (graphScanReport.value?.hasOrphans) {
      graphMessage.value = `发现 ${graphOrphanCount.value} 个孤儿引用，建议修复。`
    } else {
      graphMessage.value = '扫描完成：未发现孤儿引用。'
    }
  } catch (err) {
    graphMessage.value = `扫描失败：${err.message || err}`
  } finally {
    graphScanLoading.value = false
  }
}

const handleGraphRepair = async () => {
  if (!courseId.value || graphRepairLoading.value || !graphScanReport.value?.hasOrphans) return
  graphRepairLoading.value = true
  graphMessage.value = ''
  try {
    await studentV1Api.coursewares.repairKnowledgeGraphReferences(courseId.value, {
      confirm: true,
      nodeIds: graphScanReport.value.unionOrphanNodeIds || []
    })
    graphMessage.value = '修复完成，正在自动重新扫描...'
    await handleGraphScan()
  } catch (err) {
    graphMessage.value = `修复失败：${err.message || err}`
  } finally {
    graphRepairLoading.value = false
  }
}

const generateMergedSummary = () => {
  const points = playbackNodes.value
    .slice(0, 3)
    .map((node) => `${node.title || node.node_id}：${trimText(node.text, 44)}`)
  const baseSummary = pageSummary.value || points.join('；') || '本页暂未解析出可用摘要。'

  if (summaryMode.value === 'exam') {
    mergedSummary.value = `【考试速记】${baseSummary}\n重点节点：${points.join(' | ') || '无'}\n建议：优先理解定义、过程和结论。`
    return
  }
  if (summaryMode.value === 'teach') {
    mergedSummary.value = `【讲解版】本页核心：${baseSummary}\n可先讲“${currentNodeMeta.value?.title || '当前节点'}”，再用例子解释。`
    return
  }
  mergedSummary.value = `【速览】${baseSummary}`
}

const injectSummaryToQuestion = () => {
  if (!mergedSummary.value) {
    ElMessage.info('请先生成摘要，再用于提问')
    return
  }
  question.value = `请基于以下摘要，帮我用更通俗的方式讲解：\n${mergedSummary.value}`
  ElMessage.success('摘要已写入提问框')
}

const closeAskWorkspace = () => {
  showAskWorkspace.value = false
}

const toggleAskWorkspace = () => {
  ensureAskWorkspaceLayout()
  showAskWorkspace.value = !showAskWorkspace.value
}

const QA_FAB_LAYOUT_KEY = 'fuww_student_qa_fab_layout'
const QA_FAB_MARGIN = 14
const QA_FAB_SIZE = 64

const getDefaultQaFabLayout = () => {
  const viewport = getViewportBounds()
  return {
    left: Math.max(QA_FAB_MARGIN, viewport.width - QA_FAB_SIZE - QA_FAB_MARGIN),
    top: Math.max(QA_FAB_MARGIN, Math.round(viewport.height / 2 - QA_FAB_SIZE / 2))
  }
}

const clampQaFabLayout = (layout) => {
  const viewport = getViewportBounds()
  const maxLeft = Math.max(QA_FAB_MARGIN, viewport.width - QA_FAB_SIZE - QA_FAB_MARGIN)
  const maxTop = Math.max(QA_FAB_MARGIN, viewport.height - QA_FAB_SIZE - QA_FAB_MARGIN)
  return {
    left: clamp(Math.round(layout.left || 0), QA_FAB_MARGIN, maxLeft),
    top: clamp(Math.round(layout.top || 0), QA_FAB_MARGIN, maxTop)
  }
}

const ensureQaFabLayout = () => {
  const clamped = clampQaFabLayout(qaFabLayout)
  qaFabLayout.left = clamped.left
  qaFabLayout.top = clamped.top
}

const loadQaFabLayout = () => {
  if (typeof window === 'undefined') return
  let parsed = null
  try {
    parsed = JSON.parse(window.localStorage.getItem(QA_FAB_LAYOUT_KEY) || 'null')
  } catch (error) {
    parsed = null
  }
  const merged = parsed && typeof parsed === 'object'
    ? {
        left: Number(parsed.left),
        top: Number(parsed.top)
      }
    : getDefaultQaFabLayout()
  const clamped = clampQaFabLayout(merged)
  qaFabLayout.left = clamped.left
  qaFabLayout.top = clamped.top
}

const persistQaFabLayout = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(QA_FAB_LAYOUT_KEY, JSON.stringify({
    left: qaFabLayout.left,
    top: qaFabLayout.top
  }))
}

const stopQaFabInteraction = () => {
  if (typeof window === 'undefined') return
  window.removeEventListener('pointermove', handleQaFabPointerMove)
  window.removeEventListener('pointerup', handleQaFabPointerUp)
  window.removeEventListener('pointercancel', handleQaFabPointerUp)
  window.removeEventListener('blur', handleQaFabPointerUp)
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  qaFabInteraction.mode = ''
  qaFabInteraction.pointerId = null
  qaFabDragging.value = false
}

const handleQaFabPointerMove = (event) => {
  if (!qaFabInteraction.mode || typeof window === 'undefined') return
  const deltaX = event.clientX - qaFabInteraction.startX
  const deltaY = event.clientY - qaFabInteraction.startY
  if (!qaFabInteraction.moved && Math.abs(deltaX) + Math.abs(deltaY) < 4) {
    return
  }
  qaFabInteraction.moved = true
  qaFabDragging.value = true
  const nextLayout = clampQaFabLayout({
    left: qaFabInteraction.startLeft + deltaX,
    top: qaFabInteraction.startTop + deltaY
  })
  qaFabLayout.left = nextLayout.left
  qaFabLayout.top = nextLayout.top
}

const handleQaFabPointerUp = () => {
  const wasDragging = qaFabInteraction.moved
  stopQaFabInteraction()
  ensureQaFabLayout()
  persistQaFabLayout()
  qaFabInteraction.moved = wasDragging
}

const startQaFabDrag = (event) => {
  if (event.button !== 0) return
  ensureQaFabLayout()
  qaFabInteraction.mode = 'drag'
  qaFabInteraction.pointerId = event.pointerId
  qaFabInteraction.startX = event.clientX
  qaFabInteraction.startY = event.clientY
  qaFabInteraction.startLeft = qaFabLayout.left
  qaFabInteraction.startTop = qaFabLayout.top
  qaFabInteraction.moved = false
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'grab'
  window.addEventListener('pointermove', handleQaFabPointerMove)
  window.addEventListener('pointerup', handleQaFabPointerUp)
  window.addEventListener('pointercancel', handleQaFabPointerUp)
  window.addEventListener('blur', handleQaFabPointerUp)
}

const handleQaFabClick = () => {
  if (qaFabInteraction.moved) {
    qaFabInteraction.moved = false
    return
  }
  toggleAskWorkspace()
}

const ASK_WORKSPACE_LAYOUT_KEY = 'fuww_student_ask_workspace_layout'
const ASK_WORKSPACE_MARGIN = 12
const ASK_WORKSPACE_TOP = 68
const ASK_WORKSPACE_MIN_WIDTH = 320
const ASK_WORKSPACE_MIN_HEIGHT = 420

const clamp = (value, min, max) => Math.min(Math.max(value, min), max)

const getViewportBounds = () => {
  if (typeof window === 'undefined') {
    return { width: 1280, height: 720 }
  }
  return {
    width: window.innerWidth || 1280,
    height: window.innerHeight || 720
  }
}

const SUBTITLE_LAYOUT_KEY = 'fuww_student_subtitle_layout_v1'
const SUBTITLE_MIN_LEFT_PERCENT = 14
const SUBTITLE_MAX_LEFT_PERCENT = 86
const SUBTITLE_DEFAULT_BOTTOM = 96
const SUBTITLE_MIN_BOTTOM = 48

const clampSubtitleBottom = (value) => {
  const viewport = getViewportBounds()
  const maxBottom = Math.max(SUBTITLE_MIN_BOTTOM, viewport.height - 180)
  return clamp(Math.round(Number(value) || SUBTITLE_DEFAULT_BOTTOM), SUBTITLE_MIN_BOTTOM, maxBottom)
}

const clampSubtitleLayout = ({ leftPercent, bottom }) => ({
  leftPercent: clamp(Number(leftPercent) || 25, SUBTITLE_MIN_LEFT_PERCENT, SUBTITLE_MAX_LEFT_PERCENT),
  bottom: clampSubtitleBottom(bottom)
})

const ensureSubtitleLayout = () => {
  const normalized = clampSubtitleLayout(subtitleLayout)
  subtitleLayout.leftPercent = normalized.leftPercent
  subtitleLayout.bottom = normalized.bottom
}

const loadSubtitleLayout = () => {
  if (typeof window === 'undefined') return
  let parsed = null
  try {
    parsed = JSON.parse(window.localStorage.getItem(SUBTITLE_LAYOUT_KEY) || 'null')
  } catch (error) {
    parsed = null
  }
  const normalized = clampSubtitleLayout({
    leftPercent: parsed?.leftPercent,
    bottom: parsed?.bottom
  })
  subtitleLayout.leftPercent = normalized.leftPercent
  subtitleLayout.bottom = normalized.bottom
}

const persistSubtitleLayout = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(SUBTITLE_LAYOUT_KEY, JSON.stringify({
    leftPercent: subtitleLayout.leftPercent,
    bottom: subtitleLayout.bottom
  }))
}

const stopSubtitleDrag = () => {
  if (typeof window === 'undefined') return
  window.removeEventListener('pointermove', handleSubtitleDragMove)
  window.removeEventListener('pointerup', handleSubtitleDragUp)
  window.removeEventListener('pointercancel', handleSubtitleDragUp)
  window.removeEventListener('blur', handleSubtitleDragUp)
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  subtitleLayout.dragging = false
  subtitleLayout.pointerId = null
}

const handleSubtitleDragMove = (event) => {
  if (!subtitleLayout.dragging) return
  const viewport = getViewportBounds()
  const deltaX = Number(event.clientX || 0) - subtitleLayout.startX
  const deltaY = Number(event.clientY || 0) - subtitleLayout.startY
  const deltaPercent = (deltaX / Math.max(1, viewport.width)) * 100
  subtitleLayout.leftPercent = clamp(
    subtitleLayout.startLeftPercent + deltaPercent,
    SUBTITLE_MIN_LEFT_PERCENT,
    SUBTITLE_MAX_LEFT_PERCENT
  )
  subtitleLayout.bottom = clampSubtitleBottom(subtitleLayout.startBottom - deltaY)
}

const handleSubtitleDragUp = () => {
  if (!subtitleLayout.dragging) return
  stopSubtitleDrag()
  ensureSubtitleLayout()
  persistSubtitleLayout()
}

const startSubtitleDrag = (event) => {
  if (isKnowledgeOutlineVisible.value) return
  if (event.button !== 0) return
  ensureSubtitleLayout()
  subtitleLayout.dragging = true
  subtitleLayout.pointerId = event.pointerId
  subtitleLayout.startX = Number(event.clientX || 0)
  subtitleLayout.startY = Number(event.clientY || 0)
  subtitleLayout.startLeftPercent = subtitleLayout.leftPercent
  subtitleLayout.startBottom = subtitleLayout.bottom
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'grabbing'
  window.addEventListener('pointermove', handleSubtitleDragMove)
  window.addEventListener('pointerup', handleSubtitleDragUp)
  window.addEventListener('pointercancel', handleSubtitleDragUp)
  window.addEventListener('blur', handleSubtitleDragUp)
}

const CLASSROOM_LAYOUT_KEY = 'fuww_student_classroom_split_layout_v1'
const CLASSROOM_MIN_LEFT = 52
const CLASSROOM_MAX_LEFT = 78
const CLASSROOM_COMPACT_BREAKPOINT = 1180
const CLASSROOM_RIGHT_RAIL_WIDTH = 56

const clampClassroomLeftPercent = (value) => clamp(Math.round(Number(value) || 64), CLASSROOM_MIN_LEFT, CLASSROOM_MAX_LEFT)

const persistClassroomLayout = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(CLASSROOM_LAYOUT_KEY, JSON.stringify({
    leftPercent: classroomLayout.leftPercent
  }))
}

const loadClassroomLayout = () => {
  if (typeof window === 'undefined') return
  let parsed = null
  try {
    parsed = JSON.parse(window.localStorage.getItem(CLASSROOM_LAYOUT_KEY) || 'null')
  } catch (error) {
    parsed = null
  }
  const leftPercent = clampClassroomLeftPercent(parsed?.leftPercent)
  classroomLayout.leftPercent = leftPercent
}

const updateViewportMode = () => {
  if (typeof window === 'undefined') return
  const compact = window.innerWidth <= CLASSROOM_COMPACT_BREAKPOINT
  isCompactViewport.value = compact
  if (compact) {
    isQaPanelCollapsed.value = true
  } else {
    isQaPanelCollapsed.value = false
  }
}

const stopClassroomResize = () => {
  if (typeof window === 'undefined') return
  window.removeEventListener('pointermove', handleClassroomResizeMove)
  window.removeEventListener('pointerup', handleClassroomResizeUp)
  window.removeEventListener('pointercancel', handleClassroomResizeUp)
  window.removeEventListener('blur', handleClassroomResizeUp)
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  classroomLayout.dragging = false
  classroomLayout.pointerId = null
}

const handleClassroomResizeMove = (event) => {
  if (!classroomLayout.dragging || isCompactViewport.value || typeof window === 'undefined') return
  const deltaX = event.clientX - classroomLayout.startX
  const viewport = getViewportBounds()
  const deltaPercent = (deltaX / Math.max(1, viewport.width)) * 100
  classroomLayout.leftPercent = clampClassroomLeftPercent(classroomLayout.startLeftPercent + deltaPercent)
}

const handleClassroomResizeUp = () => {
  if (!classroomLayout.dragging) return
  stopClassroomResize()
  persistClassroomLayout()
}

const startClassroomResize = (event) => {
  if (isCompactViewport.value || isQaPanelCollapsed.value) return
  if (event.button !== 0) return
  classroomLayout.dragging = true
  classroomLayout.pointerId = event.pointerId
  classroomLayout.startX = event.clientX
  classroomLayout.startLeftPercent = classroomLayout.leftPercent
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  window.addEventListener('pointermove', handleClassroomResizeMove)
  window.addEventListener('pointerup', handleClassroomResizeUp)
  window.addEventListener('pointercancel', handleClassroomResizeUp)
  window.addEventListener('blur', handleClassroomResizeUp)
}

const getDefaultAskWorkspaceLayout = () => {
  const viewport = getViewportBounds()
  const width = clamp(980, ASK_WORKSPACE_MIN_WIDTH, Math.max(ASK_WORKSPACE_MIN_WIDTH, viewport.width - ASK_WORKSPACE_MARGIN * 2))
  const height = clamp(700, ASK_WORKSPACE_MIN_HEIGHT, Math.max(ASK_WORKSPACE_MIN_HEIGHT, viewport.height - ASK_WORKSPACE_TOP - ASK_WORKSPACE_MARGIN))
  return {
    left: Math.max(ASK_WORKSPACE_MARGIN, viewport.width - width - ASK_WORKSPACE_MARGIN),
    top: ASK_WORKSPACE_TOP,
    width,
    height
  }
}

const clampAskWorkspaceLayout = (layout) => {
  const viewport = getViewportBounds()
  const widthLimit = Math.max(ASK_WORKSPACE_MIN_WIDTH, viewport.width - ASK_WORKSPACE_MARGIN * 2)
  const heightLimit = Math.max(ASK_WORKSPACE_MIN_HEIGHT, viewport.height - ASK_WORKSPACE_TOP - ASK_WORKSPACE_MARGIN)
  const width = clamp(Math.round(layout.width || 0), ASK_WORKSPACE_MIN_WIDTH, widthLimit)
  const height = clamp(Math.round(layout.height || 0), ASK_WORKSPACE_MIN_HEIGHT, heightLimit)
  const leftLimit = Math.max(ASK_WORKSPACE_MARGIN, viewport.width - width - ASK_WORKSPACE_MARGIN)
  const topLimit = Math.max(ASK_WORKSPACE_TOP, viewport.height - height - ASK_WORKSPACE_MARGIN)
  const left = clamp(Math.round(layout.left || 0), ASK_WORKSPACE_MARGIN, leftLimit)
  const top = clamp(Math.round(layout.top || 0), ASK_WORKSPACE_TOP, topLimit)
  return { left, top, width, height }
}

const ensureAskWorkspaceLayout = () => {
  const clamped = clampAskWorkspaceLayout(askWorkspaceLayout)
  askWorkspaceLayout.left = clamped.left
  askWorkspaceLayout.top = clamped.top
  askWorkspaceLayout.width = clamped.width
  askWorkspaceLayout.height = clamped.height
}

const persistAskWorkspaceLayout = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(ASK_WORKSPACE_LAYOUT_KEY, JSON.stringify({
    left: askWorkspaceLayout.left,
    top: askWorkspaceLayout.top,
    width: askWorkspaceLayout.width,
    height: askWorkspaceLayout.height
  }))
}

const loadAskWorkspaceLayout = () => {
  if (typeof window === 'undefined') return
  let parsed = null
  try {
    parsed = JSON.parse(window.localStorage.getItem(ASK_WORKSPACE_LAYOUT_KEY) || 'null')
  } catch (error) {
    parsed = null
  }
  const merged = parsed && typeof parsed === 'object'
    ? {
        left: Number(parsed.left),
        top: Number(parsed.top),
        width: Number(parsed.width),
        height: Number(parsed.height)
      }
    : getDefaultAskWorkspaceLayout()
  const clamped = clampAskWorkspaceLayout(merged)
  askWorkspaceLayout.left = clamped.left
  askWorkspaceLayout.top = clamped.top
  askWorkspaceLayout.width = clamped.width
  askWorkspaceLayout.height = clamped.height
}

const loadNodeNotes = () => {
  if (typeof window === 'undefined') return
  try {
    const saved = JSON.parse(window.localStorage.getItem('fuww_student_node_notes') || '{}')
    if (saved && typeof saved === 'object') {
      nodeNotes.value = saved
    }
  } catch (error) {
    nodeNotes.value = {}
  }
}

const loadNodeNoteTitles = () => {
  if (typeof window === 'undefined') return
  try {
    const saved = JSON.parse(window.localStorage.getItem('fuww_student_node_note_titles') || '{}')
    if (saved && typeof saved === 'object') {
      nodeNoteTitles.value = saved
    }
  } catch (error) {
    nodeNoteTitles.value = {}
  }
}

const qaFlyoutStyle = computed(() => ({
  left: `${askWorkspaceLayout.left}px`,
  top: `${askWorkspaceLayout.top}px`,
  width: `${askWorkspaceLayout.width}px`,
  height: `${askWorkspaceLayout.height}px`
}))

const stopAskWorkspaceInteraction = () => {
  if (typeof window === 'undefined') return
  window.removeEventListener('pointermove', handleAskWorkspacePointerMove)
  window.removeEventListener('pointerup', handleAskWorkspacePointerUp)
  window.removeEventListener('pointercancel', handleAskWorkspacePointerUp)
  window.removeEventListener('blur', handleAskWorkspacePointerUp)
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  askWorkspaceInteraction.mode = ''
  askWorkspaceInteraction.pointerId = null
}

const handleAskWorkspacePointerMove = (event) => {
  if (!askWorkspaceInteraction.mode || typeof window === 'undefined') return
  const viewport = getViewportBounds()
  if (askWorkspaceInteraction.mode === 'drag') {
    const nextLayout = clampAskWorkspaceLayout({
      left: askWorkspaceInteraction.startLeft + (event.clientX - askWorkspaceInteraction.startX),
      top: askWorkspaceInteraction.startTop + (event.clientY - askWorkspaceInteraction.startY),
      width: askWorkspaceLayout.width,
      height: askWorkspaceLayout.height
    })
    askWorkspaceLayout.left = nextLayout.left
    askWorkspaceLayout.top = nextLayout.top
    return
  }

  const nextWidth = clamp(
    askWorkspaceInteraction.startWidth + (event.clientX - askWorkspaceInteraction.startX),
    ASK_WORKSPACE_MIN_WIDTH,
    Math.max(ASK_WORKSPACE_MIN_WIDTH, viewport.width - askWorkspaceLayout.left - ASK_WORKSPACE_MARGIN)
  )
  const nextHeight = clamp(
    askWorkspaceInteraction.startHeight + (event.clientY - askWorkspaceInteraction.startY),
    ASK_WORKSPACE_MIN_HEIGHT,
    Math.max(ASK_WORKSPACE_MIN_HEIGHT, viewport.height - askWorkspaceLayout.top - ASK_WORKSPACE_MARGIN)
  )
  askWorkspaceLayout.width = nextWidth
  askWorkspaceLayout.height = nextHeight
}

const handleAskWorkspacePointerUp = () => {
  stopAskWorkspaceInteraction()
  ensureAskWorkspaceLayout()
  persistAskWorkspaceLayout()
}

const startAskWorkspaceDrag = (event) => {
  if (!showAskWorkspace.value) return
  if (event.button !== 0) return
  ensureAskWorkspaceLayout()
  askWorkspaceInteraction.mode = 'drag'
  askWorkspaceInteraction.pointerId = event.pointerId
  askWorkspaceInteraction.startX = event.clientX
  askWorkspaceInteraction.startY = event.clientY
  askWorkspaceInteraction.startLeft = askWorkspaceLayout.left
  askWorkspaceInteraction.startTop = askWorkspaceLayout.top
  askWorkspaceInteraction.startWidth = askWorkspaceLayout.width
  askWorkspaceInteraction.startHeight = askWorkspaceLayout.height
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'move'
  window.addEventListener('pointermove', handleAskWorkspacePointerMove)
  window.addEventListener('pointerup', handleAskWorkspacePointerUp)
  window.addEventListener('pointercancel', handleAskWorkspacePointerUp)
  window.addEventListener('blur', handleAskWorkspacePointerUp)
}

const startAskWorkspaceResize = (event) => {
  if (!showAskWorkspace.value) return
  if (event.button !== 0) return
  ensureAskWorkspaceLayout()
  askWorkspaceInteraction.mode = 'resize'
  askWorkspaceInteraction.pointerId = event.pointerId
  askWorkspaceInteraction.startX = event.clientX
  askWorkspaceInteraction.startY = event.clientY
  askWorkspaceInteraction.startLeft = askWorkspaceLayout.left
  askWorkspaceInteraction.startTop = askWorkspaceLayout.top
  askWorkspaceInteraction.startWidth = askWorkspaceLayout.width
  askWorkspaceInteraction.startHeight = askWorkspaceLayout.height
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'nwse-resize'
  window.addEventListener('pointermove', handleAskWorkspacePointerMove)
  window.addEventListener('pointerup', handleAskWorkspacePointerUp)
  window.addEventListener('pointercancel', handleAskWorkspacePointerUp)
  window.addEventListener('blur', handleAskWorkspacePointerUp)
}

const clearQaDraft = () => {
  question.value = ''
  aiReply.value = ''
  stopStreamTypewriter()
}

const clampTimelineSec = (value) => {
  const normalized = normalizeTimeSec(value)
  if (pageTimelineDuration.value <= 0) return normalized
  return Math.min(pageTimelineDuration.value, normalized)
}

const normalizeTimelineForNode = (nodeId) => {
  const node = playbackNodes.value.find(item => item.node_id === nodeId)
  currentTimelineSec.value = node ? Number(node.start_sec || 0) : 0
}

const applyPlaybackPosition = ({ nodeId = '', timeSec = null } = {}) => {
  if (!playbackNodes.value.length) {
    currentNodeId.value = `p${currentPage.value}_n1`
    currentTimelineSec.value = 0
    return
  }

  const matchedNode = playbackNodes.value.find(item => item.node_id === nodeId)
  const fallbackNode = matchedNode || playbackNodes.value[0]
  currentNodeId.value = fallbackNode?.node_id || `p${currentPage.value}_n1`

  if (timeSec !== null && timeSec !== undefined) {
    currentTimelineSec.value = clampTimelineSec(timeSec)
    syncCurrentNodeWithTimeline()
    return
  }

  normalizeTimelineForNode(currentNodeId.value)
}

const syncCurrentNodeWithTimeline = () => {
  if (!playbackNodes.value.length) return
  const matched = playbackNodes.value.find((node) => {
    const start = Number(node.start_sec || 0)
    const end = Number(node.end_sec || 0)
    return currentTimelineSec.value >= start && currentTimelineSec.value < end
  }) || playbackNodes.value[playbackNodes.value.length - 1]
  if (matched?.node_id && matched.node_id !== currentNodeId.value) {
    currentNodeId.value = matched.node_id
  }
}

const stopPlaybackTimer = () => {
  if (playbackTimer) {
    window.clearInterval(playbackTimer)
    playbackTimer = null
  }
}

const stopStreamTypewriter = () => {
  if (streamTypingTimer) {
    window.clearInterval(streamTypingTimer)
    streamTypingTimer = null
  }
  streamTypingQueue.value = []
  streamTypingActive.value = false
}

const startStreamTypewriter = () => {
  if (streamTypingTimer || streamTypingQueue.value.length === 0) return
  streamTypingActive.value = true
  streamTypingTimer = window.setInterval(() => {
    if (!streamTypingQueue.value.length) {
      window.clearInterval(streamTypingTimer)
      streamTypingTimer = null
      streamTypingActive.value = false
      return
    }
    const nextChar = streamTypingQueue.value.shift()
    aiReply.value += nextChar
  }, TYPEWRITER_INTERVAL_MS)
}

const pushTypewriterText = (text) => {
  const value = String(text || '')
  if (!value) return
  streamTypingQueue.value.push(...value.split(''))
  startStreamTypewriter()
}

const waitTypewriterDrain = async () => {
  const startedAt = Date.now()
  while (streamTypingQueue.value.length > 0 || streamTypingActive.value) {
    if (Date.now() - startedAt > TYPEWRITER_FORCE_FLUSH_MS) {
      aiReply.value += streamTypingQueue.value.join('')
      stopStreamTypewriter()
      break
    }
    await new Promise(resolve => window.setTimeout(resolve, 50))
  }
}

const waitTypewriterReadyForResume = async (maxWaitMs = QA_RESUME_WAIT_TYPEWRITER_MS) => {
  const startedAt = Date.now()
  while (streamTypingQueue.value.length > 0 || streamTypingActive.value) {
    if (Date.now() - startedAt >= maxWaitMs) break
    await new Promise(resolve => window.setTimeout(resolve, 50))
  }
}

const setClassroomSubtitle = (text, source = 'lecture', autoHideMs = 0) => {
  const normalized = normalizeTextForSpeech(text, 260)
  if (!normalized) return subtitleVersion
  subtitleVersion += 1
  const currentVersion = subtitleVersion
  classroomSubtitleText.value = normalized
  classroomSubtitleSource.value = source === 'qa' ? 'qa' : 'lecture'
  if (subtitleHideTimer) {
    window.clearTimeout(subtitleHideTimer)
    subtitleHideTimer = null
  }
  if (autoHideMs > 0) {
    subtitleHideTimer = window.setTimeout(() => {
      subtitleHideTimer = null
      if (currentVersion !== subtitleVersion) return
      classroomSubtitleText.value = ''
      classroomSubtitleSource.value = ''
    }, autoHideMs)
  }
  return currentVersion
}

const clearClassroomSubtitle = (delayMs = 0, expectedVersion = null) => {
  const expected = expectedVersion === null ? subtitleVersion : Number(expectedVersion)
  if (subtitleHideTimer) {
    window.clearTimeout(subtitleHideTimer)
    subtitleHideTimer = null
  }
  if (delayMs > 0) {
    subtitleHideTimer = window.setTimeout(() => {
      subtitleHideTimer = null
      if (expected !== subtitleVersion) return
      subtitleVersion += 1
      classroomSubtitleText.value = ''
      classroomSubtitleSource.value = ''
    }, delayMs)
    return
  }
  if (expected !== subtitleVersion) return
  subtitleVersion += 1
  classroomSubtitleText.value = ''
  classroomSubtitleSource.value = ''
}

const canUseSpeechSynthesis = () => (
  typeof window !== 'undefined'
    && Boolean(window.speechSynthesis)
    && typeof window.SpeechSynthesisUtterance !== 'undefined'
)

const resolveServiceAudioUrl = (value) => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (/^(https?:)?\/\//i.test(raw) || /^data:/i.test(raw) || /^blob:/i.test(raw)) {
    return raw
  }
  const base = String(AI_API_BASE || '').trim() || 'http://localhost:8000'
  try {
    const normalizedBase = base.endsWith('/') ? base : `${base}/`
    return new URL(raw, normalizedBase).toString()
  } catch (error) {
    return raw
  }
}

const getPlaybackNodeAudioUrl = (nodeId) => {
  const targetNodeId = String(nodeId || '').trim()
  if (!targetNodeId) return ''
  const sections = Array.isArray(playbackAudioMeta.value?.sections)
    ? playbackAudioMeta.value.sections
    : []
  const section = sections.find(item => String(item?.node_id || '').trim() === targetNodeId)
  return resolveServiceAudioUrl(section?.audio_url || '')
}

const buildTtsCacheKey = (normalizedText, options = {}) => {
  const provider = String(options.provider || TTS_DEFAULT_PROVIDER).trim().toLowerCase()
  const voiceType = String(options.voiceType || TTS_DEFAULT_VOICE).trim().toLowerCase()
  return `${provider}|${voiceType}|${normalizedText}`
}

const pushTtsAudioCache = (cacheKey, audioUrl) => {
  if (!cacheKey || !audioUrl) return
  ttsAudioUrlCache.set(cacheKey, audioUrl)
  if (ttsAudioUrlCache.size <= TTS_MAX_CACHE_ENTRIES) return
  const oldestKey = ttsAudioUrlCache.keys().next().value
  if (oldestKey) {
    ttsAudioUrlCache.delete(oldestKey)
  }
}

const requestServiceTtsAudio = async (normalizedText, options = {}) => {
  const cacheKey = buildTtsCacheKey(normalizedText, options)
  const cachedAudioUrl = ttsAudioUrlCache.get(cacheKey)
  if (cachedAudioUrl) {
    return {
      audioUrl: cachedAudioUrl,
      provider: 'cache',
      status: 'cached',
      fromMeta: false
    }
  }

  const provider = String(options.provider || TTS_DEFAULT_PROVIDER).trim()
  const voiceType = String(options.voiceType || TTS_DEFAULT_VOICE).trim()
  const format = String(options.format || TTS_DEFAULT_FORMAT).trim().toLowerCase()
  const endpoint = `${String(AI_API_BASE || '').replace(/\/+$/, '')}/generate-audio`
  const payload = {
    course_id: String(options.courseId || courseId.value || 'student-course'),
    page: Math.max(1, Number(options.page || currentPage.value || 1)),
    voice_type: voiceType,
    format,
    provider,
    playback_id: String(options.mark || `student-tts-${Date.now()}`),
    nodes: [
      {
        node_id: String(options.nodeId || `node_${Date.now()}`),
        title: String(options.title || ''),
        text: normalizedText,
        duration_sec: 0,
        start_sec: 0,
        end_sec: 0
      }
    ]
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  })
  if (!response.ok) {
    throw new Error(`TTS服务请求失败: ${response.status}`)
  }

  const data = await response.json().catch(() => ({}))
  const sections = Array.isArray(data?.sections) ? data.sections : []
  const firstAudioSection = sections.find(section => String(section?.audio_url || '').trim())
  const audioUrl = resolveServiceAudioUrl(firstAudioSection?.audio_url || data?.audio_url || '')
  if (audioUrl) {
    pushTtsAudioCache(cacheKey, audioUrl)
  }

  return {
    audioUrl,
    provider: String(data?.provider || provider || '').trim().toLowerCase(),
    status: String(data?.status || '').trim().toLowerCase(),
    fromMeta: false
  }
}

const createSpeechUtterance = (text, { mark = '', rate = playbackRate.value, maxLength = 900 } = {}) => {
  const normalizedText = normalizeTextForSpeech(text, maxLength)
  if (!normalizedText) return null
  const utter = new SpeechSynthesisUtterance(normalizedText)
  utter.lang = 'zh-CN'
  utter.rate = Math.min(2, Math.max(0.5, Number(rate || 1)))
  utter.pitch = 1
  utter.volume = 1
  utter.__mark = String(mark || `speech:${normalizedText.slice(0, 64)}`)
  return utter
}

const speakWithBrowserTtsAndWait = (text, options = {}) => new Promise((resolve) => {
  if (!canUseSpeechSynthesis()) {
    resolve(false)
    return
  }
  const utter = createSpeechUtterance(text, options)
  if (!utter) {
    resolve(false)
    return
  }
  const speakingMark = String(utter.__mark || options.mark || '')
  if (
    speakingMark
    && currentSpeechUtterance?.__mark === speakingMark
    && typeof window !== 'undefined'
    && window.speechSynthesis?.speaking
  ) {
    resolve(true)
    return
  }

  stopSpeechNarration()

  let settled = false
  const settleOnce = (result) => {
    if (settled) return
    settled = true
    if (currentSpeechCancel === cancelSpeech) {
      currentSpeechCancel = null
    }
    if (currentSpeechUtterance === utter) {
      currentSpeechUtterance = null
    }
    if (activeSpeechMark === speakingMark) {
      activeSpeechMark = ''
    }
    resolve(result)
  }

  const cancelSpeech = () => {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    settleOnce(false)
  }

  currentSpeechUtterance = utter
  activeSpeechMark = speakingMark
  currentSpeechCancel = cancelSpeech

  utter.onend = () => settleOnce(true)
  utter.onerror = () => settleOnce(false)

  window.speechSynthesis.speak(utter)
})

const playAudioUrlAndWait = (audioUrl, { mark = '', rate = playbackRate.value } = {}) => new Promise((resolve) => {
  if (!audioUrl || typeof Audio === 'undefined') {
    resolve(false)
    return
  }

  if (
    mark
    && activeSpeechMark === mark
    && currentSpeechAudioElement
    && !currentSpeechAudioElement.paused
  ) {
    resolve(true)
    return
  }

  stopSpeechNarration()

  const audio = new Audio(audioUrl)
  audio.preload = 'auto'
  audio.playbackRate = Math.min(2, Math.max(0.5, Number(rate || 1)))
  currentSpeechAudioElement = audio
  activeSpeechMark = String(mark || `audio:${Date.now()}`)
  const speakingMark = activeSpeechMark

  let settled = false
  const settleOnce = (result) => {
    if (settled) return
    settled = true
    if (currentSpeechCancel === cancelAudio) {
      currentSpeechCancel = null
    }
    if (currentSpeechAudioElement === audio) {
      currentSpeechAudioElement = null
    }
    if (activeSpeechMark === speakingMark) {
      activeSpeechMark = ''
    }
    resolve(result)
  }

  const cancelAudio = () => {
    audio.pause()
    settleOnce(false)
  }

  currentSpeechCancel = cancelAudio
  audio.addEventListener('ended', () => settleOnce(true), { once: true })
  audio.addEventListener('error', () => settleOnce(false), { once: true })

  const playPromise = audio.play()
  if (playPromise && typeof playPromise.catch === 'function') {
    playPromise.catch(() => settleOnce(false))
  }
})

const speakTextAndWait = async (text, options = {}) => {
  if (!ttsEnabled.value) return false
  const maxLength = Number(options.maxLength || 900)
  const normalizedText = normalizeTextForSpeech(text, maxLength)
  if (!normalizedText) return false

  const speakingMark = String(options.mark || `speech:${normalizedText.slice(0, 64)}`)
  if (
    speakingMark
    && activeSpeechMark === speakingMark
    && (
      (currentSpeechAudioElement && !currentSpeechAudioElement.paused)
      || (currentSpeechUtterance && canUseSpeechSynthesis() && window.speechSynthesis?.speaking)
    )
  ) {
    return true
  }

  const subtitleSource = String(options.source || 'lecture').trim().toLowerCase() === 'qa' ? 'qa' : 'lecture'
  const subtitleSnapshot = setClassroomSubtitle(normalizedText, subtitleSource)

  const preferService = options.preferService !== false
  if (preferService) {
    try {
      const nodeAudioUrl = options.nodeId ? getPlaybackNodeAudioUrl(options.nodeId) : ''
      const serviceResult = nodeAudioUrl
        ? {
            audioUrl: nodeAudioUrl,
            provider: 'course-meta',
            status: 'ready',
            fromMeta: true
          }
        : await requestServiceTtsAudio(normalizedText, {
            mark: speakingMark,
            nodeId: options.nodeId,
            title: options.title,
            page: options.page,
            courseId: options.courseId,
            provider: options.provider,
            voiceType: options.voiceType,
            format: options.format
          })

      const shouldSkipServiceAudio = (
        !serviceResult.fromMeta
        && canUseSpeechSynthesis()
        && (
          serviceResult.provider === 'mock-tts'
          || serviceResult.status === 'fallback_ready'
        )
      )

      if (serviceResult.audioUrl && !shouldSkipServiceAudio) {
        const played = await playAudioUrlAndWait(serviceResult.audioUrl, {
          mark: speakingMark,
          rate: options.rate
        })
        if (played) {
          if (subtitleSource === 'qa') {
            clearClassroomSubtitle(1600, subtitleSnapshot)
          }
          return true
        }
      }
    } catch (error) {
      console.warn('TTS服务播报失败，准备回退浏览器语音', error)
    }
  }

  const fallbackSpoken = await speakWithBrowserTtsAndWait(normalizedText, {
    mark: speakingMark,
    rate: options.rate,
    maxLength
  })
  if (subtitleSource === 'qa') {
    clearClassroomSubtitle(1600, subtitleSnapshot)
  }
  return fallbackSpoken
}

const speakText = (text, options = {}) => {
  void speakTextAndWait(text, options)
}

const splitSpeechSegments = (text) => {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return []

  const major = normalized
    .split(/(?<=[。！？；!?;])/)
    .map((segment) => segment.trim())
    .filter(Boolean)

  if (major.length >= 2) return major

  const minor = normalized
    .split(/[，,]/)
    .map((segment) => segment.trim())
    .filter(Boolean)

  if (minor.length >= 2) return minor
  return [normalized]
}

const buildResumeSpeechText = (text, elapsedSec, durationSec) => {
  const source = String(text || '').trim()
  if (!source) return ''

  const elapsed = Math.max(0, Number(elapsedSec || 0))
  if (elapsed <= 1) return source

  const segments = splitSpeechSegments(source)
  if (segments.length <= 1) return source

  const duration = Math.max(0, Number(durationSec || 0))
  const ratio = duration > 1
    ? Math.min(0.95, Math.max(0, elapsed / duration))
    : Math.min(0.92, elapsed / Math.max(6, segments.length * 2))

  const startIndex = Math.min(segments.length - 1, Math.floor(segments.length * ratio))
  const remainder = segments.slice(startIndex).join('')
  if (remainder.trim().length >= 8) return remainder

  return segments.slice(Math.max(0, segments.length - 2)).join('')
}

const stopSpeechNarration = () => {
  const cancelCurrentSpeech = currentSpeechCancel
  currentSpeechCancel = null
  cancelCurrentSpeech?.()

  if (currentSpeechAudioElement) {
    currentSpeechAudioElement.pause()
    currentSpeechAudioElement = null
  }
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    window.speechSynthesis.cancel()
  }
  currentSpeechUtterance = null
  activeSpeechMark = ''
}

const cancelPresetSpeechTask = () => {
  presetSpeechTaskId += 1
  isPresetLectureSpeaking.value = false
}

const speakCurrentNode = ({ resumeFromBreakpoint = false } = {}) => {
  if (!ttsEnabled.value || !isPlay.value || isPresetLectureSpeaking.value) return
  const node = currentNodeMeta.value
  if (!node) return

  const rawText = String(node.text || node.title || '').trim()
  if (!rawText) return

  const nodeStart = Number(node.start_sec || 0)
  const nodeDuration = Number(node.duration_sec || 0) || Math.max(1, Number(node.end_sec || nodeStart) - nodeStart)
  const elapsedInNode = Math.max(0, Number(activeNodeElapsedSec.value || 0))
  const text = resumeFromBreakpoint
    ? buildResumeSpeechText(rawText, elapsedInNode, nodeDuration)
    : rawText
  if (!text) return

  const speakingOffset = resumeFromBreakpoint ? normalizeTimeSec(elapsedInNode) : normalizeTimeSec(nodeStart)
  const speakingMark = `node:${currentPage.value}:${node.node_id}:${speakingOffset}:${resumeFromBreakpoint ? 'resume' : 'start'}`
  speakText(text, {
    mark: speakingMark,
    maxLength: 500,
    source: 'lecture',
    nodeId: node.node_id,
    title: node.title,
    page: currentPage.value,
    courseId: courseId.value,
    provider: TTS_DEFAULT_PROVIDER,
    voiceType: TTS_DEFAULT_VOICE,
    format: TTS_DEFAULT_FORMAT
  })
}

const playPresetLectureScriptThenCurrentNode = async () => {
  if (!isPlay.value || askLoading.value) return
  if (!presetLectureScriptOnPlay.value || !ttsEnabled.value) {
    speakCurrentNode()
    return
  }

  const presetScript = await loadPresetLectureScriptText()
  const speakingText = normalizePresetLectureScript(presetScript) || PRESET_LECTURE_SCRIPT_FALLBACK_TEXT

  const taskId = ++presetSpeechTaskId
  isPresetLectureSpeaking.value = true
  await speakTextAndWait(speakingText, {
    mark: `preset-lecture:${currentPage.value}:${Date.now()}`,
    rate: Math.min(1.2, Math.max(0.85, Number(playbackRate.value || 1))),
    maxLength: 1200,
    source: 'lecture',
    page: currentPage.value,
    courseId: courseId.value,
    provider: TTS_DEFAULT_PROVIDER,
    voiceType: TTS_DEFAULT_VOICE,
    format: TTS_DEFAULT_FORMAT
  })
  if (taskId !== presetSpeechTaskId) {
    return
  }
  isPresetLectureSpeaking.value = false

  if (!isPlay.value || askLoading.value) return
  speakCurrentNode()
}

const startPlaybackTimer = () => {
  stopPlaybackTimer()
  if (!playbackNodes.value.length) return
  playbackTimer = window.setInterval(async () => {
    if (!isPlay.value) return
    currentTimelineSec.value += Number(playbackRate.value || 1)
    syncCurrentNodeWithTimeline()

    if (pageTimelineDuration.value > 0 && currentTimelineSec.value >= pageTimelineDuration.value) {
      if (currentPage.value < totalPage.value) {
        currentPage.value += 1
        await refreshCurrentPageData({ preserveCurrentNode: false })
        await saveBreakpoint()
      } else {
        isPlay.value = false
        stopPlaybackTimer()
      }
    }
  }, 1000)
}

const prevPage = async () => {
  if (!courseId.value || currentPage.value <= 1) return
  isPlay.value = false
  currentPage.value--
  await refreshCurrentPageData({ preserveCurrentNode: false })
  await saveBreakpoint()
}

const nextPage = async () => {
  if (!courseId.value || currentPage.value >= totalPage.value) return
  isPlay.value = false
  currentPage.value++
  await refreshCurrentPageData({ preserveCurrentNode: false })
  await saveBreakpoint()
}

const updateCourseContent = () => {
  if (!courseId.value) {
    courseImg.value = ''
    return
  }
  const localPageImages = resolveActiveCoursewarePageImages()
  if (localPageImages.length > 0) {
    const index = Math.min(Math.max(0, Number(currentPage.value || 1) - 1), localPageImages.length - 1)
    courseImg.value = String(localPageImages[index] || '').trim()
    return
  }
  courseImg.value = `${API_BASE}/api/courseware/${courseId.value}/page/${currentPage.value}`
}

const loadStudentScript = async () => {
  scriptLoading.value = true
  if (!courseId.value) {
    currentNodeId.value = 'p1_n1'
    playbackNodes.value = []
    pageSummary.value = ''
    currentPageMarkdown.value = ''
    playbackMode.value = 'duration_timeline'
    playbackAudioMeta.value = null
    currentTimelineSec.value = 0
    scriptLoading.value = false
    return
  }
  try {
    const data = await studentV1Api.coursewares.getPlaybackScript(courseId.value, currentPage.value)
    const payload = data?.data || {}
    const payloadTotalPage = Number(payload.total_page || payload.totalPage || payload.page_total || 0)
    const activeCourseware = resolveActiveCourseware()
    const localPageImages = resolveActiveCoursewarePageImages()
    const selectedTotalPage = Number(activeCourseware?.totalPage || 0)
    const resolvedTotalPage = Math.max(payloadTotalPage, selectedTotalPage, localPageImages.length)
    if (resolvedTotalPage > 0) {
      totalPage.value = resolvedTotalPage
    }
    const nodes = data?.data?.nodes || []
    playbackNodes.value = nodes
    pageSummary.value = payload.page_summary || ''
    mergedSummary.value = payload.page_summary || ''
    currentPageMarkdown.value = String(
      payload.script || payload.content || payload.markdown || payload.raw_script || ''
    )
    playbackAudioMeta.value = payload.audio_meta || null
    playbackMode.value = payload.playback_mode || payload.audio_meta?.playback_mode || 'duration_timeline'
    applyPlaybackPosition({ nodeId: currentNodeId.value })
  } catch (error) {
    playbackNodes.value = []
    pageSummary.value = ''
    mergedSummary.value = ''
    currentPageMarkdown.value = ''
    playbackMode.value = 'duration_timeline'
    playbackAudioMeta.value = null
    currentNodeId.value = `p${currentPage.value}_n1`
    currentTimelineSec.value = 0
  } finally {
    scriptLoading.value = false
  }
}

const selectPlaybackNode = async (nodeId) => {
  currentNodeId.value = nodeId
  normalizeTimelineForNode(nodeId)
  const node = playbackNodes.value.find(item => item.node_id === nodeId)
  flashSeekNotice(currentTimelineSec.value, node?.title || '')
  await saveBreakpoint()
}

const seekTimeline = async (targetSec) => {
  currentTimelineSec.value = clampTimelineSec(targetSec)
  syncCurrentNodeWithTimeline()
  flashSeekNotice(currentTimelineSec.value, currentNodeMeta.value?.title || '')
  await saveBreakpoint()
}

const handleSeekStep = async (deltaSec) => {
  const step = Number(deltaSec || 0)
  if (!step) return
  await seekTimeline(currentTimelineSec.value + step)
  flashPlaybackHud(step > 0 ? `⏩ +${Math.abs(step)} 秒` : `⏪ -${Math.abs(step)} 秒`)
}

const handleSeekToStart = async () => {
  await seekTimeline(0)
  flashPlaybackHud('↺ 回到页首')
}

const stopContinuousArrowSeek = () => {
  if (arrowSeekTimer) {
    window.clearInterval(arrowSeekTimer)
    arrowSeekTimer = null
  }
  arrowSeekDirection = ''
}

const flashPlaybackHud = (text) => {
  const message = String(text || '').trim()
  if (!message) return
  if (playbackHudTimer) {
    window.clearTimeout(playbackHudTimer)
    playbackHudTimer = null
  }
  playbackHudText.value = message
  playbackHudVisible.value = true
  playbackHudTimer = window.setTimeout(() => {
    playbackHudVisible.value = false
    playbackHudText.value = ''
    playbackHudTimer = null
  }, 900)
}

const openShortcutHelp = (markSeen = false) => {
  shortcutHelpVisible.value = true
  if (markSeen && typeof window !== 'undefined') {
    window.localStorage.setItem(shortcutHelpSeenKey, '1')
  }
}

const closeShortcutHelp = () => {
  shortcutHelpVisible.value = false
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(shortcutHelpSeenKey, '1')
  }
}

const startContinuousArrowSeek = (direction) => {
  if (!['left', 'right'].includes(direction)) return
  if (arrowSeekDirection === direction && arrowSeekTimer) return
  stopContinuousArrowSeek()
  arrowSeekDirection = direction
  arrowSeekTimer = window.setInterval(() => {
    if (arrowSeekDirection === 'left') {
      void seekTimeline(currentTimelineSec.value - 5)
      return
    }
    if (arrowSeekDirection === 'right') {
      void seekTimeline(currentTimelineSec.value + 5)
    }
  }, 220)
}

const handlePlaybackShortcut = (event) => {
  if (!hasCourseSelected.value || activeSection.value !== 'classroom') return
  const target = event.target
  const tag = String(target?.tagName || '').toLowerCase()
  const isTyping = tag === 'input' || tag === 'textarea' || tag === 'select' || target?.isContentEditable
  if (isTyping) return

  if (event.code === 'Space') {
    event.preventDefault()
    togglePlay()
    flashPlaybackHud(isPlay.value ? '▶ 播放' : '⏸ 暂停')
    return
  }
  if (event.code === 'ArrowLeft') {
    event.preventDefault()
    const step = event.shiftKey ? 10 : 5
    if (event.repeat) {
      startContinuousArrowSeek('left')
      flashPlaybackHud(event.shiftKey ? '⏪ 连续快退 10 秒' : '⏪ 连续快退')
      return
    }
    void handleSeekStep(-step)
    return
  }
  if (event.code === 'ArrowRight') {
    event.preventDefault()
    const step = event.shiftKey ? 10 : 5
    if (event.repeat) {
      startContinuousArrowSeek('right')
      flashPlaybackHud(event.shiftKey ? '⏩ 连续快进 10 秒' : '⏩ 连续快进')
      return
    }
    void handleSeekStep(step)
    return
  }
  if (event.code === 'BracketLeft') {
    event.preventDefault()
    const rates = [0.75, 1, 1.25, 1.5]
    const idx = rates.indexOf(Number(playbackRate.value || 1))
    const next = rates[Math.max(0, idx - 1)]
    updatePlaybackRate(next)
    return
  }
  if (event.code === 'BracketRight') {
    event.preventDefault()
    const rates = [0.75, 1, 1.25, 1.5]
    const idx = rates.indexOf(Number(playbackRate.value || 1))
    const next = rates[Math.min(rates.length - 1, idx + 1)]
    updatePlaybackRate(next)
    return
  }
  if (event.code === 'KeyM') {
    event.preventDefault()
    toggleTts()
    flashPlaybackHud(ttsEnabled.value ? '🔊 语音已开' : '🔇 语音已关')
    return
  }
  if (event.code === 'Digit0') {
    event.preventDefault()
    updatePlaybackRate(1)
    flashPlaybackHud('🎯 1.0x')
    return
  }
  if (event.code === 'KeyK') {
    event.preventDefault()
    shortcutHelpVisible.value = !shortcutHelpVisible.value
    if (shortcutHelpVisible.value && typeof window !== 'undefined') {
      window.localStorage.setItem(shortcutHelpSeenKey, '1')
    }
    flashPlaybackHud(shortcutHelpVisible.value ? '⌨️ 已打开快捷键帮助' : '⌨️ 已关闭快捷键帮助')
  }
}

const handlePlaybackShortcutKeyup = (event) => {
  if (event.code === 'ArrowLeft' || event.code === 'ArrowRight') {
    stopContinuousArrowSeek()
  }
}

const updatePlaybackRate = (rate) => {
  const normalized = Number(rate || 1)
  playbackRate.value = [0.75, 1, 1.25, 1.5].includes(normalized) ? normalized : 1
  if (isPlay.value && ttsEnabled.value && !isPresetLectureSpeaking.value) {
    speakCurrentNode()
  }
  flashPlaybackHud(`⚡ ${playbackRate.value}x`)
}

const flashSeekNotice = (sec, nodeTitle = '') => {
  if (seekNoticeTimer) {
    window.clearTimeout(seekNoticeTimer)
    seekNoticeTimer = null
  }
  const title = String(nodeTitle || '').trim()
  seekNoticeText.value = title ? `已定位 ${formatNodeTime(sec)} · ${title}` : `已定位 ${formatNodeTime(sec)}`
  seekNoticeVisible.value = true
  seekNoticeTimer = window.setTimeout(() => {
    seekNoticeVisible.value = false
    seekNoticeText.value = ''
    seekNoticeTimer = null
  }, 1500)
}

const refreshCurrentPageData = async ({ preserveCurrentNode = true, targetNodeId = '', targetTimeSec = null } = {}) => {
  const nextNodeId = preserveCurrentNode ? currentNodeId.value : (targetNodeId || `p${currentPage.value}_n1`)
  currentNodeId.value = nextNodeId
  updateCourseContent()
  await loadStudentScript()
  applyPlaybackPosition({ nodeId: targetNodeId || nextNodeId, timeSec: targetTimeSec })
}

const togglePlay = () => {
  if (!playbackNodes.value.length) {
    ElMessage.warning('当前页暂无可播放的讲授节点')
    return
  }

  const hadProgress = Number(currentTimelineSec.value || 0) > 0 || Number(activeNodeElapsedSec.value || 0) > 0
  const nextPlay = !isPlay.value
  if (nextPlay) {
    shouldSpeakPresetOnNextPlay.value = !hadProgress
    shouldResumeSpeechOnNextPlay.value = hadProgress
  } else {
    shouldSpeakPresetOnNextPlay.value = false
    shouldResumeSpeechOnNextPlay.value = hadProgress
  }

  isPlay.value = nextPlay
  playbackState.value = nextPlay ? 'lecturing' : 'paused'
  if (!nextPlay) {
    cancelPresetSpeechTask()
    stopSpeechNarration()
    clearClassroomSubtitle()
  }
}

const toggleTts = () => {
  ttsEnabled.value = !ttsEnabled.value
  if (!ttsEnabled.value) {
    cancelPresetSpeechTask()
    stopSpeechNarration()
    clearClassroomSubtitle()
    ElMessage.info('已关闭语音讲稿')
    return
  }
  if (isPlay.value) {
    speakCurrentNode()
  }
  ElMessage.success('已开启语音讲稿')
}

const openUpload = () => {
  ElMessage.info('已打开截图/圈图提问')
}

const playAnswerMessageAudio = async (payload) => {
  const answerText = String(payload?.content || '').trim()
  if (!answerText) {
    ElMessage.info('该条回答暂无可播放内容')
    return
  }

  if (!ttsEnabled.value) {
    ttsEnabled.value = true
  }

  cancelPresetSpeechTask()
  isPlay.value = false
  playbackState.value = 'tutoring'
  stopSpeechNarration()

  const played = await speakTextAndWait(answerText, {
    mark: `qa-bubble:${payload?.messageId || 'unknown'}:${Date.now()}`,
    rate: Math.min(1.2, Math.max(0.9, Number(playbackRate.value || 1))),
    maxLength: 1800,
    source: 'qa',
    provider: TTS_DEFAULT_PROVIDER,
    voiceType: TTS_DEFAULT_VOICE,
    format: TTS_DEFAULT_FORMAT
  })

  if (!played) {
    ElMessage.warning('当前语音播放不可用，请稍后重试')
  }
}

const sendMultiModalQuestion = async () => {
  if (askLoading.value) {
    ElMessage.info('当前正在处理上一条提问，请稍后')
    return
  }
  if (!question.value.trim()) {
    ElMessage.warning('请输入问题后再发送')
    return
  }

  const currentQuestion = String(question.value || '').trim()
  const wasPlaying = Boolean(isPlay.value)
  shouldResumePlaybackAfterQa.value = wasPlaying
  shouldResumeSpeechOnNextPlay.value = wasPlaying
  askLoading.value = true
  isPlay.value = false
  playbackState.value = 'tutoring'
  stopSpeechNarration()
  clearClassroomSubtitle()
  cancelPresetSpeechTask()
  shouldSpeakPresetOnNextPlay.value = false
  stopStreamTypewriter()
  question.value = ''
  try {
    const profiledReply = buildProfiledQaReply(FIXED_QA_MARKDOWN_REPLY)
    aiReply.value = ''
    latestAnswerMeta.value = {
      sourcePage: 0,
      sourceNodeId: '',
      needReteach: false,
      understandingLevel: '',
      followUpSuggestion: '',
      sessionId: sessionId.value
    }
    await new Promise(resolve => window.setTimeout(resolve, THINKING_DELAY_MS))
    pushTypewriterText(profiledReply)
    await waitTypewriterReadyForResume()
    latestAnswerMeta.value = {
      sourcePage: currentPage.value,
      sourceNodeId: currentNodeId.value,
      needReteach: false,
      followUpSuggestion: '',
      sessionId: sessionId.value
    }

    qaHistory.value.unshift({
      question: currentQuestion,
      answer: profiledReply,
      sourcePage: latestAnswerMeta.value.sourcePage,
      sourceNodeId: latestAnswerMeta.value.sourceNodeId
    })
    if (qaHistory.value.length > 5) {
      qaHistory.value = qaHistory.value.slice(0, 5)
    }
    question.value = ''

    if (qaAutoSpeakAnswer.value && ttsEnabled.value) {
      await Promise.race([
        speakTextAndWait(aiReply.value || profiledReply, {
          mark: `qa-answer:${sessionId.value || 'default'}:${Date.now()}`,
          rate: Math.min(1.2, Math.max(0.9, Number(playbackRate.value || 1))),
          maxLength: 720,
          source: 'qa',
          provider: TTS_DEFAULT_PROVIDER,
          voiceType: TTS_DEFAULT_VOICE,
          format: TTS_DEFAULT_FORMAT
        }),
        new Promise(resolve => {
          window.setTimeout(() => resolve(false), QA_ANSWER_SPEAK_TIMEOUT_MS)
        })
      ])
    }

    if (shouldResumePlaybackAfterQa.value) {
      playbackState.value = 'resuming'
      shouldSpeakPresetOnNextPlay.value = false
      shouldResumeSpeechOnNextPlay.value = true
      isPlay.value = true
      playbackState.value = 'lecturing'
      ElMessage.success('AI 答疑完成，已从断点继续讲解')
    } else {
      playbackState.value = 'paused'
      ElMessage.success('AI 答疑完成')
    }
  } catch (error) {
    aiReply.value = ''
    ElMessage.error(`提问失败：${error.message || '固定答复输出异常'}`)
  } finally {
    shouldResumePlaybackAfterQa.value = false
    if (!latestAnswerMeta.value.needReteach) {
      playbackState.value = isPlay.value ? 'lecturing' : 'paused'
    }
    askLoading.value = false
  }
}

const pickCoursewareCard = async (card) => {
  if (!card) return
  if (card.mock) {
    const fallback = filteredSelectionCoursewares.value[0] || selectionCoursewares.value[0]
    if (fallback) {
      selectedCoursewareId.value = fallback.id
      if (fallback.teachingCourseId) selectedTeachingCourseId.value = fallback.teachingCourseId
      if (fallback.courseClassId) selectedCourseClassId.value = fallback.courseClassId
    } else {
      // 无真实课件时仍允许进入后续页面，后续由课程初始化阶段给出提示。
      selectedCoursewareId.value = ''
    }
    await enterWorkspaceFromSelection({ allowPlaceholder: true })
    return
  }
  if (card.teachingCourseId) {
    selectedTeachingCourseId.value = card.teachingCourseId
  }
  if (card.courseClassId) {
    selectedCourseClassId.value = card.courseClassId
  }
  selectedCoursewareId.value = card.id
  await enterWorkspaceFromSelection()
}

const loadCourseSelectionData = async () => {
  selectionLoading.value = true
  try {
    const [courseRes, classRes, coursewareRes] = await Promise.all([
      studentV1Api.platform.listCourses({ page: 1, pageSize: 100 }),
      studentV1Api.platform.listClasses({ page: 1, pageSize: 200 }),
      studentV1Api.coursewares.list()
    ])

    const platformCourses = Array.isArray(courseRes?.data?.items) ? courseRes.data.items : []
    const platformClasses = Array.isArray(classRes?.data?.items) ? classRes.data.items : []
    const coursewareList = Array.isArray(coursewareRes?.data) ? coursewareRes.data : []

    selectionCourseOptions.value = platformCourses.map((item) => ({
      id: String(item.courseId || ''),
      name: item.title || '未命名课程'
    }))

    selectionClassOptions.value = platformClasses.map((item) => ({
      id: String(item.classId || ''),
      name: item.className || '未命名班级',
      teachingCourseId: String(item.teachingCourseId || '')
    }))

    selectionCoursewares.value = coursewareList.map((item) => {
      const fileType = String(item.file_type || item.fileType || '')
      const localImagePreset = resolveLocalCoursewareImages(item.title || '')
      const localPageImages = Array.isArray(localImagePreset?.pages) ? localImagePreset.pages : []
      const localPreviewImage = String(localPageImages[0] || '').trim()
      const rawPreview = item.cover_url || item.coverUrl || item.image_url || item.imageUrl || item.preview_url || item.previewUrl || ''
      const rawFileUrl = item.file_url || item.fileUrl || ''
      const normalizedPreview = normalizePreviewImageUrl(rawPreview, { force: true })
      const normalizedFileUrl = normalizePreviewImageUrl(rawFileUrl, { force: true })
      const imageFileUrl = (isImageFileType(fileType) || isLikelyImageUrl(rawFileUrl)) ? normalizedFileUrl : ''
      const resolvedTotalPage = Math.max(Number(item.total_page || 1), localPageImages.length || 1)

      return {
        id: String(item.id || item.courseId || ''),
        name: item.title || '未命名课件',
        totalPage: resolvedTotalPage,
        teachingCourseId: String(item.teaching_course_id || ''),
        courseName: String(item.teaching_course_title || ''),
        courseClassId: String(item.course_class_id || ''),
        className: String(item.course_class_name || ''),
        fileType,
        fileUrl: normalizedFileUrl,
        imageFileUrl: localPreviewImage || imageFileUrl,
        previewImageUrl: localPreviewImage || normalizedPreview || imageFileUrl,
        localPageImages,
        desc: item.is_published ? '已发布，可进入学习' : '未发布，暂为教师侧预览资源',
        published: Boolean(item.is_published)
      }
    })

    if (!selectedTeachingCourseId.value && selectionCourseOptions.value.length > 0) {
      selectedTeachingCourseId.value = selectionCourseOptions.value[0].id
    }
    if (!selectedCourseClassId.value && filteredSelectionClassOptions.value.length > 0) {
      selectedCourseClassId.value = filteredSelectionClassOptions.value[0].id
    }
    if (!selectedCoursewareId.value && filteredSelectionCoursewares.value.length > 0) {
      selectedCoursewareId.value = filteredSelectionCoursewares.value[0].id
    }
  } catch (error) {
    selectionCourseOptions.value = []
    selectionClassOptions.value = []
    selectionCoursewares.value = []
    ElMessage.error(`课件选择数据加载失败：${error.message}`)
  } finally {
    selectionLoading.value = false
  }
}

const startStudentWorkspace = async () => {
  checkBackendHealth()
  if (backendHealthTimer) {
    window.clearInterval(backendHealthTimer)
  }
  backendHealthTimer = window.setInterval(checkBackendHealth, 30000)
  startPlaybackTimer()
  await initializeCourseContext()
}

const enterWorkspaceFromSelection = async ({ allowPlaceholder = false } = {}) => {
  const selected = selectionCoursewares.value.find((item) => item.id === selectedCoursewareId.value)
  if (!selected && !allowPlaceholder) {
    ElMessage.warning('请先选择要学习的课件')
    return
  }

  if (selected) {
    courseId.value = selected.id
    currentCourseName.value = selected.name
    totalPage.value = selected.totalPage || 1
    selectedCoursePreviewImageUrl.value = String(selected.previewImageUrl || selected.imageFileUrl || '').trim()
  } else {
    courseId.value = ''
    currentCourseName.value = '临时占位学习空间'
    totalPage.value = 1
    selectedCoursePreviewImageUrl.value = ''
  }
  currentPage.value = 1
  jumpToSection('classroom')
  personalCenterInitialTab.value = 'notes'
  resetKnowledgeWorkspace()
  hasCourseSelected.value = true
  await startStudentWorkspace()
}

const backToSelectionPage = () => {
  hasCourseSelected.value = false
  cancelPresetSpeechTask()
  shouldSpeakPresetOnNextPlay.value = false
  showAskWorkspace.value = false
  selectedCoursePreviewImageUrl.value = ''
  stopSpeechNarration()
  void loadCourseSelectionData()
}

const jumpToPersonalPractice = () => {
  personalCenterInitialTab.value = 'practice'
  jumpToSection('personal', { personalTab: 'practice' })
}

const handleLoginSuccess = (user) => {
  const role = String(user?.role || '').trim().toLowerCase()
  const username = String(user?.username || '').trim().toLowerCase() || 'xuesheng'

  if (role === 'teacher') {
    const teacherOrigin = resolveTeacherOrigin()
    const encodedUsername = encodeURIComponent(username)
    window.location.href = `${teacherOrigin}/?role=teacher&username=${encodedUsername}`
    return
  }

  isLoggedIn.value = true
  studentId.value = username
  hasCourseSelected.value = false
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('fuww_student_id', username)
    window.localStorage.setItem('fuww_student_origin', window.location.origin)
  }
  void loadCourseSelectionData()
}

const handleLogout = () => {
  isLoggedIn.value = false
  hasCourseSelected.value = false
  showAskWorkspace.value = false
  studentId.value = ''
  selectedTeachingCourseId.value = ''
  selectedCourseClassId.value = ''
  selectedCoursewareId.value = ''
  selectedCoursePreviewImageUrl.value = ''
  selectionCourseOptions.value = []
  selectionClassOptions.value = []
  selectionCoursewares.value = []
  question.value = ''
  aiReply.value = ''
  qaHistory.value = []
  resetPracticeExercise()
  isPlay.value = false
  cancelPresetSpeechTask()
  shouldSpeakPresetOnNextPlay.value = false
  stopPlaybackTimer()
  stopSpeechNarration()
  clearClassroomSubtitle()
  stopStreamTypewriter()
  stopSubtitleDrag()
  if (backendHealthTimer) {
    window.clearInterval(backendHealthTimer)
    backendHealthTimer = null
  }
}

const handleViewportResize = () => {
  ensureQaFabLayout()
  ensureAskWorkspaceLayout()
  ensureSubtitleLayout()
  updateViewportMode()
}

onMounted(() => {
  if (typeof window !== 'undefined') {
    loadQaFabLayout()
    loadAskWorkspaceLayout()
    loadClassroomLayout()
    loadSubtitleLayout()
    qaAutoSpeakAnswer.value = loadBooleanPreference(QA_AUTO_SPEAK_PREF_KEY, true)
    presetLectureScriptOnPlay.value = loadBooleanPreference(PRESET_LECTURE_SPEAK_PREF_KEY, true)
    aiExplainMode.value = loadEnumPreference(AI_EXPLAIN_MODE_PREF_KEY, ['deep', 'assist'], 'deep')
    aiExplainStyle.value = loadEnumPreference(AI_EXPLAIN_STYLE_PREF_KEY, ['gentle', 'rigorous'], 'rigorous')
    loadNodeNotes()
    loadNodeNoteTitles()
    updateViewportMode()
    window.addEventListener('keydown', handlePlaybackShortcut)
    window.addEventListener('keyup', handlePlaybackShortcutKeyup)
    window.addEventListener('blur', stopContinuousArrowSeek)
    if (window.localStorage.getItem(shortcutHelpSeenKey) !== '1') {
      openShortcutHelp(true)
    }
    window.localStorage.setItem('fuww_student_origin', window.location.origin)
    window.addEventListener('resize', handleViewportResize)
    const params = new URLSearchParams(window.location.search)
    const role = String(params.get('role') || '').trim().toLowerCase()
    const username = String(params.get('username') || '').trim().toLowerCase()

    if (role && username) {
      if (role === 'teacher') {
        const teacherOrigin = resolveTeacherOrigin()
        window.location.replace(`${teacherOrigin}/?role=teacher&username=${encodeURIComponent(username)}`)
        return
      }
      isLoggedIn.value = true
      hasCourseSelected.value = false
      studentId.value = username
      window.localStorage.setItem('fuww_student_id', username)
      window.history.replaceState({}, document.title, window.location.pathname)
      void loadCourseSelectionData()
      return
    }

    studentId.value = resolveStudentId()
  }
})

onUnmounted(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', handlePlaybackShortcut)
    window.removeEventListener('keyup', handlePlaybackShortcutKeyup)
    window.removeEventListener('blur', stopContinuousArrowSeek)
    window.removeEventListener('resize', handleViewportResize)
  }
  stopContinuousArrowSeek()
  if (playbackHudTimer) {
    window.clearTimeout(playbackHudTimer)
    playbackHudTimer = null
  }
  if (backendHealthTimer) {
    window.clearInterval(backendHealthTimer)
    backendHealthTimer = null
  }
  if (seekNoticeTimer) {
    window.clearTimeout(seekNoticeTimer)
    seekNoticeTimer = null
  }
  stopPlaybackTimer()
  stopSpeechNarration()
  clearClassroomSubtitle()
  stopStreamTypewriter()
  stopKnowledgeOutlineStream()
  stopAskWorkspaceInteraction()
  stopClassroomResize()
  stopSubtitleDrag()
})

onBeforeUnmount(() => {
  stopAskWorkspaceInteraction()
  stopClassroomResize()
  stopSubtitleDrag()
})

watch(selectedTeachingCourseId, () => {
  const classValid = filteredSelectionClassOptions.value.some((item) => item.id === selectedCourseClassId.value)
  if (!classValid) {
    selectedCourseClassId.value = filteredSelectionClassOptions.value[0]?.id || ''
  }
  const coursewareValid = filteredSelectionCoursewares.value.some((item) => item.id === selectedCoursewareId.value)
  if (!coursewareValid) {
    selectedCoursewareId.value = filteredSelectionCoursewares.value[0]?.id || ''
  }
})

watch(selectedCourseClassId, () => {
  const coursewareValid = filteredSelectionCoursewares.value.some((item) => item.id === selectedCoursewareId.value)
  if (!coursewareValid) {
    selectedCoursewareId.value = filteredSelectionCoursewares.value[0]?.id || ''
  }
})

watch(selectedCoursewareId, (nextId) => {
  const selected = selectionCoursewares.value.find((item) => item.id === nextId)
  selectedCoursePreviewImageUrl.value = String(selected?.previewImageUrl || selected?.imageFileUrl || '').trim()
})

watch(isPlay, (value) => {
  if (value) {
    playbackState.value = askLoading.value ? 'tutoring' : 'lecturing'
    startPlaybackTimer()
    const shouldSpeakPreset = shouldSpeakPresetOnNextPlay.value
    const shouldResumeSpeech = shouldResumeSpeechOnNextPlay.value
    shouldSpeakPresetOnNextPlay.value = false
    shouldResumeSpeechOnNextPlay.value = false
    if (shouldSpeakPreset) {
      void playPresetLectureScriptThenCurrentNode()
      return
    }
    speakCurrentNode({ resumeFromBreakpoint: shouldResumeSpeech })
    return
  }
  shouldSpeakPresetOnNextPlay.value = false
  cancelPresetSpeechTask()
  playbackState.value = askLoading.value ? 'tutoring' : 'paused'
  stopPlaybackTimer()
  stopSpeechNarration()
  clearClassroomSubtitle(240)
})

watch(playbackNodes, () => {
  if (isPlay.value && !isPresetLectureSpeaking.value) {
    startPlaybackTimer()
    speakCurrentNode()
  }
})

watch(currentNodeId, () => {
  if (isPlay.value && !isPresetLectureSpeaking.value) {
    speakCurrentNode()
  }
})

watch(activeSection, (nextSection) => {
  if (nextSection !== 'classroom') {
    closeKnowledgeOutline()
  }
})

watch(courseId, (nextCourseId) => {
  if (!nextCourseId && activeRightPanel.value === 'graph') {
    activeRightPanel.value = 'courseware'
  }
  lastContextHintNodeId.value = ''
  if (!nextCourseId) {
    graphSyncPayload.value = null
    graphScanReport.value = null
    graphMessage.value = ''
    clearClassroomSubtitle()
  }
})

watch(nodeNotes, (nextValue) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem('fuww_student_node_notes', JSON.stringify(nextValue || {}))
}, { deep: true })

watch(nodeNoteTitles, (nextValue) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem('fuww_student_node_note_titles', JSON.stringify(nextValue || {}))
}, { deep: true })

watch(qaAutoSpeakAnswer, (nextValue) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(QA_AUTO_SPEAK_PREF_KEY, nextValue ? '1' : '0')
})

watch(presetLectureScriptOnPlay, (nextValue) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(PRESET_LECTURE_SPEAK_PREF_KEY, nextValue ? '1' : '0')
})

watch(aiExplainMode, (nextValue) => {
  const normalized = String(nextValue || '').trim().toLowerCase()
  if (!['deep', 'assist'].includes(normalized)) {
    aiExplainMode.value = 'deep'
    return
  }
  if (typeof window === 'undefined') return
  window.localStorage.setItem(AI_EXPLAIN_MODE_PREF_KEY, normalized)
})

watch(aiExplainStyle, (nextValue) => {
  const normalized = String(nextValue || '').trim().toLowerCase()
  if (!['gentle', 'rigorous'].includes(normalized)) {
    aiExplainStyle.value = 'rigorous'
    return
  }
  if (typeof window === 'undefined') return
  window.localStorage.setItem(AI_EXPLAIN_STYLE_PREF_KEY, normalized)
})

const initializeCourseContext = async () => {
  try {
    if (!courseId.value) {
      const data = await studentV1Api.coursewares.list({
        teachingCourseId: selectedTeachingCourseId.value,
        courseClassId: selectedCourseClassId.value
      })
      const list = Array.isArray(data?.data) ? data.data : []
      const published = list.filter(item => item.is_published)
      const target = published[0] || list[0]

      if (!target) {
        courseId.value = ''
        currentCourseName.value = ''
        totalPage.value = 1
        updateCourseContent()
        ElMessage.warning('当前课程/班级暂无可学习课件，请联系教师发布课件')
        return
      }

      courseId.value = String(target.id || target.courseId || '')
      currentCourseName.value = target.title || '未命名课件'
      totalPage.value = target.total_page || 1
    }

    currentPage.value = 1
    await refreshCurrentPageData({ preserveCurrentNode: false })

    const session = await studentV1Api.sessions.start({
      userId: studentId.value,
      courseId: courseId.value
    })
    sessionId.value = session?.data?.sessionId || ''

    await loadBreakpoint()
    await loadWeakPoints()
    await loadStudyData()
  } catch (error) {
    courseId.value = ''
    currentCourseName.value = ''
    updateCourseContent()
    ElMessage.error(`加载课程失败：${error.message}`)
  }
}

const checkBackendHealth = async () => {
  try {
    const res = await studentV1Api.health()
    backendStatus.value = res.ok ? 'online' : 'offline'
  } catch (error) {
    backendStatus.value = 'offline'
  }
}

const loadBreakpoint = async () => {
  if (!courseId.value) return
  try {
    const data = await studentV1Api.coursewares.getBreakpoint(studentId.value, courseId.value)
    breakpointPage.value = data?.data?.pageNum || data?.data?.lastPageNum || 1
    showBreakpointDialog.value = breakpointPage.value > 1
  } catch (error) {
    breakpointPage.value = 1
    showBreakpointDialog.value = false
  }
}

const saveBreakpoint = async () => {
  if (!courseId.value) return
  try {
    await studentV1Api.coursewares.updateBreakpoint({
      studentId: studentId.value,
      courseId: courseId.value,
      pageNum: currentPage.value
    })
    await studentV1Api.sessions.updateProgress({
      sessionId: sessionId.value,
      userId: studentId.value,
      courseId: courseId.value,
      currentPage: currentPage.value,
      currentNodeId: currentNodeId.value,
      currentTimeSec: currentTimelineSec.value
    })
  } catch (error) {
    console.warn('断点保存失败', error)
  }
}

const loadStudyData = async () => {
  if (!courseId.value) return
  try {
    const data = await studentV1Api.coursewares.getStats(studentId.value, courseId.value)
    const payload = data.data || {}
    const weakPoints = payload.weakPoints || []
    learningStats.value = {
      focusScore: payload.focusScore || 0,
      totalQuestions: payload.totalQuestions || 0,
      weakPointCount: weakPoints.length,
      masteryRate: Math.max(35, 100 - (weakPoints.length * 10))
    }
  } catch (error) {
    console.warn('学习数据加载失败', error)
  }
}

const loadWeakPoints = async () => {
  if (!courseId.value) return
  try {
    const data = await studentV1Api.coursewares.getWeakPoints(studentId.value, courseId.value)
    if (Array.isArray(data.data) && data.data.length > 0) {
      weakPointTags.value = data.data.map(item => ({ id: item.weakPointId, name: item.name }))
    } else {
      weakPointTags.value = []
    }
  } catch (error) {
    weakPointTags.value = []
    console.warn('加载薄弱点失败', error)
  }
}

const continueStudy = async () => {
  currentPage.value = breakpointPage.value
  await refreshCurrentPageData({ preserveCurrentNode: false })
  showBreakpointDialog.value = false
  await saveBreakpoint()
  ElMessage.success(`已为你跳转到第 ${breakpointPage.value} 页`)
}

const restartStudy = async () => {
  currentPage.value = 1
  await refreshCurrentPageData({ preserveCurrentNode: false })
  showBreakpointDialog.value = false
  await saveBreakpoint()
  ElMessage.info('已回到第1页重新开始学习')
}

const handleFileChange = (file) => {
  uploadedFile.value = file?.raw || file || buildCurrentPptPlaceholder()
  parseResult.value = ''
  knowledgeList.value = []
}

const buildCurrentPptPlaceholder = () => {
  const sourceName = String(currentCourseName.value || '当前PPT').trim() || '当前PPT'
  const safeName = sourceName.replace(/[\\/:*?"<>|]/g, '_')
  return {
    name: `${safeName}.pptx`,
    size: 0,
    type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    mockCurrentPpt: true
  }
}

const resolveKnowledgeSourceName = (fileLike) => {
  const rawName = String(fileLike?.name || '当前PPT').trim()
  return rawName.replace(/\.[^/.]+$/, '') || '当前PPT'
}

const ensureKnowledgeWorkspaceDefaults = async ({ autoParse = false, silent = false } = {}) => {
  if (!uploadedFile.value) {
    uploadedFile.value = buildCurrentPptPlaceholder()
  }
  if (autoParse && !isParsing.value && knowledgeList.value.length === 0) {
    await parseKnowledge({ silent })
  }
}

const resetKnowledgeWorkspace = () => {
  uploadedFile.value = buildCurrentPptPlaceholder()
  parseResult.value = ''
  knowledgeList.value = []
}

const normalizeKnowledgeLabel = (value, fallback = '未命名知识点') => {
  const normalized = String(value || '')
    .replace(/[`*_>#]/g, ' ')
    .replace(/^[-*+\d.\s]+/, '')
    .replace(/\s+/g, ' ')
    .trim()
  return normalized || fallback
}

const buildOutlineTreeFromMarkdown = (markdownText, sourceName = '当前资料') => {
  const lines = String(markdownText || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  if (!lines.length) return []

  const tree = []
  let chapterIndex = 0
  let pointIndex = 0
  let currentChapter = null
  let currentPoint = null

  const createChapter = (title) => {
    chapterIndex += 1
    pointIndex = 0
    currentChapter = {
      id: `ch-${chapterIndex}`,
      name: normalizeKnowledgeLabel(title, `${sourceName}核心章节 ${chapterIndex}`),
      children: []
    }
    tree.push(currentChapter)
    currentPoint = null
    return currentChapter
  }

  const ensureChapter = (fallbackTitle = `${sourceName}知识主线`) => {
    if (!currentChapter) {
      return createChapter(fallbackTitle)
    }
    return currentChapter
  }

  const createPoint = (title) => {
    const chapter = ensureChapter()
    pointIndex += 1
    currentPoint = {
      id: `kp-${chapterIndex}-${pointIndex}`,
      name: normalizeKnowledgeLabel(title, `知识点 ${pointIndex}`),
      children: []
    }
    chapter.children.push(currentPoint)
    return currentPoint
  }

  const ensurePoint = (fallbackTitle = '本章关键要点') => {
    if (!currentPoint) {
      return createPoint(fallbackTitle)
    }
    return currentPoint
  }

  lines.forEach((line) => {
    const chapterMatch = line.match(/^#{1,2}\s+(.+)$/)
    if (chapterMatch) {
      createChapter(chapterMatch[1])
      return
    }

    const pointMatch = line.match(/^#{3,4}\s+(.+)$/)
    if (pointMatch) {
      createPoint(pointMatch[1])
      return
    }

    const bulletMatch = line.match(/^(?:[-*+]|\d+\.)\s+(.+)$/)
    if (!bulletMatch) return

    const point = ensurePoint()
    const childIndex = point.children.length + 1
    point.children.push({
      id: `sub-${chapterIndex}-${pointIndex}-${childIndex}`,
      name: normalizeKnowledgeLabel(bulletMatch[1], `要点 ${childIndex}`)
    })
  })

  return tree
    .map((chapter, chapterPosition) => {
      const chapterChildren = Array.isArray(chapter.children) ? chapter.children : []
      const normalizedChildren = chapterChildren.map((point, pointPosition) => {
        const pointId = String(point.id || `kp-${chapterPosition + 1}-${pointPosition + 1}`)
        const pointChildren = Array.isArray(point.children) && point.children.length
          ? point.children
          : [{ id: `${pointId}-sub-1`, name: '本节核心结论' }]
        return {
          ...point,
          id: pointId,
          name: normalizeKnowledgeLabel(point.name, `知识点 ${pointPosition + 1}`),
          children: pointChildren
        }
      })

      return {
        ...chapter,
        id: String(chapter.id || `ch-${chapterPosition + 1}`),
        name: normalizeKnowledgeLabel(chapter.name, `${sourceName}章节 ${chapterPosition + 1}`),
        children: normalizedChildren.length
          ? normalizedChildren
          : [
              {
                id: `kp-${chapterPosition + 1}-1`,
                name: '关键知识点',
                children: [{ id: `sub-${chapterPosition + 1}-1-1`, name: '本章核心要点' }]
              }
            ]
      }
    })
    .filter((chapter) => Array.isArray(chapter.children) && chapter.children.length > 0)
    .slice(0, 10)
}

const createFallbackKnowledgeTree = (sourceName = '个人学习资料') => {
  return [
    {
      id: 'ch-1',
      name: `${sourceName}：课程目标与概念边界`,
      children: [
        {
          id: 'kp-1-1',
          name: '核心概念定义',
          children: [
            { id: 'sub-1-1-1', name: '术语解释与适用范围' },
            { id: 'sub-1-1-2', name: '常见概念混淆点' }
          ]
        },
        {
          id: 'kp-1-2',
          name: '问题建模方式',
          children: [
            { id: 'sub-1-2-1', name: '输入输出约束识别' },
            { id: 'sub-1-2-2', name: '目标函数设定原则' }
          ]
        }
      ]
    },
    {
      id: 'ch-2',
      name: `${sourceName}：流程拆解与执行顺序`,
      children: [
        {
          id: 'kp-2-1',
          name: '阶段一：初始化',
          children: [
            { id: 'sub-2-1-1', name: '编码方式确定' },
            { id: 'sub-2-1-2', name: '初始群体生成' }
          ]
        },
        {
          id: 'kp-2-2',
          name: '阶段二：迭代更新',
          children: [
            { id: 'sub-2-2-1', name: '选择策略对比' },
            { id: 'sub-2-2-2', name: '交叉与变异协同' },
            { id: 'sub-2-2-3', name: '收敛判断标准' }
          ]
        }
      ]
    },
    {
      id: 'ch-3',
      name: `${sourceName}：参数调优与误差控制`,
      children: [
        {
          id: 'kp-3-1',
          name: '关键参数影响',
          children: [
            { id: 'sub-3-1-1', name: '种群规模影响分析' },
            { id: 'sub-3-1-2', name: '交叉率与变异率平衡' }
          ]
        },
        {
          id: 'kp-3-2',
          name: '稳定性与鲁棒性',
          children: [
            { id: 'sub-3-2-1', name: '边界条件处理' },
            { id: 'sub-3-2-2', name: '异常结果回溯' }
          ]
        }
      ]
    },
    {
      id: 'ch-4',
      name: `${sourceName}：题型映射与实战应用`,
      children: [
        {
          id: 'kp-4-1',
          name: '典型题型拆解',
          children: [
            { id: 'sub-4-1-1', name: '概念判断题' },
            { id: 'sub-4-1-2', name: '流程计算题' },
            { id: 'sub-4-1-3', name: '综合应用题' }
          ]
        },
        {
          id: 'kp-4-2',
          name: '解题模板库',
          children: [
            { id: 'sub-4-2-1', name: '四步解题框架' },
            { id: 'sub-4-2-2', name: '常见错因定位模板' }
          ]
        }
      ]
    },
    {
      id: 'ch-5',
      name: `${sourceName}：复盘与迁移计划`,
      children: [
        {
          id: 'kp-5-1',
          name: '知识闭环复盘',
          children: [
            { id: 'sub-5-1-1', name: '错题二次归档' },
            { id: 'sub-5-1-2', name: '高频考点重练' }
          ]
        },
        {
          id: 'kp-5-2',
          name: '迁移应用建议',
          children: [
            { id: 'sub-5-2-1', name: '跨章节联动训练' },
            { id: 'sub-5-2-2', name: '阶段性测验计划' }
          ]
        }
      ]
    }
  ]
}

const buildMockKnowledgeTree = (fileName = '个人学习资料') => {
  const stem = String(fileName || '个人学习资料').replace(/\.[^/.]+$/, '')
  const outlineTree = buildOutlineTreeFromMarkdown(knowledgeOutlineMarkdown.value, stem)
  if (outlineTree.length > 0) {
    return outlineTree
  }
  return createFallbackKnowledgeTree(stem)
}

const parseKnowledge = async ({ silent = false } = {}) => {
  const sourceFile = uploadedFile.value || buildCurrentPptPlaceholder()
  uploadedFile.value = sourceFile

  isParsing.value = true
  try {
    await loadKnowledgeOutlineMarkdown()
    await new Promise((resolve) => window.setTimeout(resolve, 1100))
    const sourceName = resolveKnowledgeSourceName(sourceFile)
    knowledgeList.value = buildMockKnowledgeTree(`${sourceName}.pptx`)
    parseResult.value = `已按当前PPT「${sourceName}」完成知识拆解，共生成 ${countNodes(knowledgeList.value)} 个知识点`
    if (!silent) {
      ElMessage.success('知识拆解已完成')
    }
  } catch (error) {
    knowledgeList.value = buildMockKnowledgeTree('当前PPT')
    parseResult.value = `已生成知识拆解结果，共生成 ${countNodes(knowledgeList.value)} 个知识点`
  } finally {
    isParsing.value = false
  }
}

const countNodes = (tree) => {
  let count = 0
  tree.forEach((node) => {
    count++
    if (node.children && node.children.length) {
      count += countNodes(node.children)
    }
  })
  return count
}

const handleNodeClick = (data) => {
  ElMessage.info(`已定位到知识点：${data.name}`)
  tracePoint.value = true
  traceTop.value = 200
  traceLeft.value = 300
}

const startWeakPointLearn = async (point = {}) => {
  const pointId = String(point?.id || '').trim()
  const pointName = String(point?.name || '').trim() || '当前薄弱点'
  currentWeakPoint.value = pointName
  try {
    const data = await studentV1Api.weakPoints.explain(pointId, pointName)
    currentExplain.value = data?.data?.content || '暂无讲解内容'
  } catch (error) {
    currentExplain.value = '暂时无法获取讲解，请稍后重试。'
    ElMessage.error(`讲解加载失败：${error.message}`)
  }
  currentTest.value = null
  testResult.value = null
}

const handleStudyPanelAiExplain = async (point) => {
  await startWeakPointLearn(point)
  jumpToSection('classroom')
  openAskPanelIfNeeded()

  const pointName = String(point?.name || currentWeakPoint.value || '').trim()
  if (!pointName) return

  const draftQuestion = `请结合当前课堂内容，详细讲解薄弱点【${pointName}】，并给我2道巩固练习。`
  question.value = draftQuestion
  createAskPanelAction('draft', draftQuestion)
}

const generateTest = async () => {
  try {
    const currentPoint = weakPointTags.value.find(item => item.name === currentWeakPoint.value)
    const data = await studentV1Api.weakPoints.generateTest({
      weakPointId: currentPoint?.id || '',
      weakPointName: currentWeakPoint.value,
      studentId: studentId.value,
      questionType: 'single'
    })
    currentQuestionId.value = data?.data?.questionId || ''
    currentTest.value = {
      question: data?.data?.content || '暂无题目',
      options: data?.data?.options || []
    }
    testResult.value = null
  } catch (error) {
    ElMessage.error(`生成习题失败：${error.message}`)
  }
}

const checkAnswer = async (option) => {
  try {
    const data = await studentV1Api.weakPoints.checkAnswer({
      studentId: studentId.value,
      questionId: currentQuestionId.value,
      userAnswer: option
    })
    testResult.value = {
      correct: data?.data?.isCorrect,
      msg: data?.data?.isCorrect ? '✅ 回答正确！' : '❌ 回答错误',
      analysis: data?.data?.explanation || ''
    }
  } catch (error) {
    ElMessage.error(`答案校验失败：${error.message}`)
  }
}
</script>

<style scoped>
.course-selection-page {
  min-height: 100vh;
  padding: 14px;
  box-sizing: border-box;
  background: radial-gradient(circle at 12% 8%, #f5fbf8 0%, #edf3ef 45%, #e8efeb 100%);
}

.course-selection-page :deep(.top-nav) {
  margin-bottom: 14px;
}

.selection-layout {
  margin-top: 14px;
  min-height: calc(100vh - 102px);
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 14px;
}

.selection-user-sidebar {
  border-radius: 18px;
  border: 1px solid #cfe4da;
  background: linear-gradient(180deg, #f3faf6 0%, #e7f4ed 100%);
  color: #2f605a;
  padding: 18px 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.user-avatar {
  width: 58px;
  height: 58px;
  border-radius: 50%;
  background: linear-gradient(180deg, #ffffff 0%, #dceee6 100%);
  box-shadow: 0 10px 18px rgba(33, 61, 54, 0.16);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 700;
}

.user-name {
  margin-top: 12px;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.user-subtitle {
  margin-top: 2px;
  font-size: 12px;
  color: #6d877d;
}

.refresh-btn {
  margin-top: auto;
  width: 100%;
  border: 1px solid #bdd8cb;
  background: #ffffff;
}

.refresh-btn :deep(span) {
  color: #2f605a;
  font-weight: 700;
}

.selection-main-panel {
  border-radius: 18px;
  border: 1px solid #d9e7df;
  background: linear-gradient(180deg, #ffffff 0%, #f7faf8 100%);
  box-shadow: 0 20px 42px rgba(33, 61, 54, 0.08);
  padding: 18px;
  overflow: hidden;
}

.selection-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.selection-head h2 {
  margin: 0;
  font-size: 24px;
  color: #1f3f38;
}

.selection-head p {
  margin: 8px 0 0;
  font-size: 14px;
  color: #5f7b71;
}

.selection-filters {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 240px));
  gap: 10px;
}

.course-tile-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
  max-height: calc(100vh - 290px);
  overflow: auto;
  padding-right: 4px;
}

.course-tile {
  border: 1px solid #d9e7df;
  border-radius: 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f6fbf8 100%);
  padding: 14px;
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.course-tile:hover {
  transform: translateY(-2px);
  border-color: #90c0b5;
  box-shadow: 0 12px 20px rgba(33, 61, 54, 0.1);
}

.course-tile.active {
  border-color: #5d8f83;
  box-shadow: 0 0 0 2px rgba(93, 143, 131, 0.18);
}

.course-tile.mock {
  background: linear-gradient(180deg, #fcfcff 0%, #f4f6fd 100%);
}

.tile-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  background: #edf5f2;
  color: #2f605a;
  font-size: 11px;
  font-weight: 700;
}

.course-tile h3 {
  margin: 10px 0 6px;
  font-size: 16px;
  color: #24453f;
}

.course-tile p {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: #648177;
}

.tile-meta {
  margin-top: 10px;
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: #4d665d;
}

.selection-tip {
  margin-top: 12px;
  font-size: 13px;
  color: #6f867d;
}

@media (max-width: 980px) {
  .selection-layout {
    grid-template-columns: 1fr;
  }

  .selection-user-sidebar {
    align-items: flex-start;
  }

  .user-avatar {
    width: 46px;
    height: 46px;
    font-size: 20px;
  }

  .selection-filters {
    grid-template-columns: minmax(0, 1fr);
  }

  .course-tile-grid {
    max-height: none;
  }
}

.student-app {
  position: relative;
  width: 100%;
  height: 100vh;
  min-height: 100vh;
  padding: 14px;
  box-sizing: border-box;
  background: radial-gradient(circle at 12% 8%, #f5fbf8 0%, #edf3ef 45%, #e8efeb 100%);
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.student-app :deep(.top-nav) {
  position: relative;
  z-index: 2;
  margin-bottom: 14px;
}

.ambient-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(38px);
  opacity: 0.45;
  animation: floatOrb 14s ease-in-out infinite;
}

.orb-a {
  width: 220px;
  height: 220px;
  background: #9ccfc3;
  left: 4%;
  top: 8%;
}

.orb-b {
  width: 280px;
  height: 280px;
  background: #bddfd6;
  right: 6%;
  top: 18%;
  animation-delay: -4s;
}

.orb-c {
  width: 180px;
  height: 180px;
  background: #d4e8e1;
  right: 20%;
  bottom: 10%;
  animation-delay: -8s;
}

.workspace-shell {
  position: relative;
  z-index: 1;
  width: 100%;
  flex: 1;
  min-height: 0;
  border-radius: 28px;
  background: #f7faf8;
  border: 1px solid #d8e4dc;
  box-shadow: 0 24px 48px rgba(45, 72, 66, 0.08);
  overflow: hidden;
}

.main-layout {
  height: 100%;
  min-height: 0;
  padding: 12px 18px 18px;
  display: flex;
  gap: 14px;
}

.left-sidebar-menu {
  flex: 0 0 180px;
  background: #ffffff;
  border: 1px solid #d9e7df;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.left-sidebar-menu.collapsed {
  flex-basis: 70px;
}

.menu-header {
  padding: 14px 14px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  letter-spacing: 0.08em;
  color: #6b7f75;
  text-transform: uppercase;
  font-weight: 700;
}

.left-sidebar-menu.collapsed .menu-header {
  justify-content: center;
}

.menu-toggle-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border-radius: 4px;
}

.menu-toggle-btn svg {
  width: 18px;
  height: 18px;
}

.menu-list {
  display: flex;
  flex-direction: column;
  padding: 0 8px 8px;
  gap: 4px;
}

.menu-item {
  border: 1px solid #d4e4db;
  background: #fff;
  color: #536a61;
  font-size: 13px;
  font-weight: 600;
  border-radius: 10px;
  padding: 8px 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
  transform: translateY(0);
}

.left-sidebar-menu.collapsed .menu-item {
  justify-content: center;
}

.menu-icon {
  width: 22px;
  height: 22px;
  border-radius: 8px;
  background: #e8f2ed;
  color: #2f605a;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
}

.menu-item:hover {
  border-color: #7ea497;
  color: #2f605a;
  transform: translateY(-1px);
}

.menu-item.active {
  color: #fff;
  background: linear-gradient(135deg, #2f605a 0%, #4d8a80 100%);
  border-color: #2f605a;
  box-shadow: 0 8px 16px rgba(47, 96, 90, 0.25);
}

.menu-item.active .menu-icon {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.qa-fab {
  position: fixed;
  z-index: 45;
  width: 64px;
  height: 64px;
  border-radius: 999px;
  border: 1px solid rgba(172, 196, 186, 0.9);
  background:
    radial-gradient(circle at 30% 30%, #f8fffc 0%, #dcefe7 58%, #c5ddd2 100%);
  box-shadow:
    0 14px 24px rgba(61, 92, 85, 0.22),
    0 2px 0 rgba(255, 255, 255, 0.65) inset;
  color: #2f605a;
  cursor: pointer;
  touch-action: none;
  user-select: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease, box-shadow 0.2s ease, filter 0.2s ease, left 0.12s ease, top 0.12s ease;
  animation: qa-fab-float 2.8s ease-in-out infinite;
}

.qa-fab:hover {
  transform: scale(1.02);
  box-shadow:
    0 16px 28px rgba(61, 92, 85, 0.26),
    0 2px 0 rgba(255, 255, 255, 0.7) inset;
}

.qa-fab:active {
  transform: scale(0.98);
}

.qa-fab.active {
  filter: saturate(1.06);
  box-shadow:
    0 18px 32px rgba(38, 92, 81, 0.32),
    0 0 0 5px rgba(83, 128, 116, 0.2);
}

.qa-fab.dragging {
  animation: none;
  transition: none;
  cursor: grabbing;
}

.qa-fab-core {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: #214842;
  background: linear-gradient(160deg, #f3f8f6 0%, #d9e7e1 100%);
  border: 1px solid rgba(159, 186, 176, 0.9);
}

.qa-fab-tip {
  position: absolute;
  right: calc(100% + 10px);
  top: 50%;
  transform: translateY(-50%) translateX(6px);
  font-size: 12px;
  font-weight: 700;
  color: #2d5c52;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #d6e5de;
  border-radius: 999px;
  padding: 5px 10px;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.qa-fab:hover .qa-fab-tip,
.qa-fab.active .qa-fab-tip {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
}

.workspace-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
  position: relative;
}

.logout-btn {
  border: 1px solid #cfe0d7;
  background: #ffffff;
  color: #2f605a;
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.logout-btn:hover {
  border-color: #2f605a;
}

.page-layout {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.page-fade-enter-active,
.page-fade-leave-active {
  transition: all 0.26s ease;
}

.page-fade-enter-from,
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.995);
}

.page-layout.two-col {
  display: flex;
  gap: 14px;
}

.page-layout.single-col {
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
  border: 1px solid #d8e5de;
  border-radius: 20px;
  padding: 8px;
  background:
    radial-gradient(circle at 94% 8%, rgba(112, 167, 144, 0.15) 0%, rgba(112, 167, 144, 0) 38%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(245, 251, 248, 0.98) 100%);
  box-shadow: 0 10px 24px rgba(34, 64, 57, 0.06);
}

.page-layout.single-col > * {
  flex: 1;
  min-height: 0;
  animation: singleColReveal 0.22s ease-out;
}

.left-stage {
  flex: 1 1 62%;
  min-width: 0;
}

.right-stage {
  flex: 1 1 38%;
  min-width: 360px;
  max-width: 560px;
}


.page-layout.classroom-workbench {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.classroom-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #d7e4dd;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f6faf8 100%);
  padding: 10px 12px;
}

.classroom-title-group h3 {
  margin: 2px 0 0;
  font-size: 17px;
  color: #1f473d;
}

.classroom-kicker {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6a8278;
  font-weight: 700;
}

.classroom-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.classroom-split-layout {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 8px;
  overflow: hidden;
}

.classroom-left-pane {
  min-width: 0;
  min-height: 0;
  display: flex;
}

.classroom-left-stack {
  width: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.classroom-left-stack.expanded {
  display: grid;
  grid-template-rows: 72px minmax(0, 1fr);
  gap: 10px;
}

.classroom-left-stack.solo {
  height: 100%;
}

.classroom-left-stack.solo .center-stage {
  flex: 1 1 auto;
  min-height: 0;
}

.classroom-left-stack.expanded .center-stage {
  min-height: 0;
}

.center-stage-collapsed-title {
  height: 100%;
  border: 1px solid #d6e5dd;
  border-radius: 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f5faf7 100%);
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.center-stage-collapsed-title h4 {
  margin: 0;
  font-size: 15px;
  color: #1f4b42;
  font-weight: 700;
}

.center-stage-collapsed-title span {
  font-size: 12px;
  color: #5f7b71;
  border: 1px solid #d2e3da;
  border-radius: 999px;
  padding: 3px 10px;
  background: #eef6f2;
  white-space: nowrap;
}

.classroom-left-stack.expanded .left-unified-tabs-pane {
  flex: unset;
  min-height: 0;
}

.workbench-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.left-unified-tabs-pane {
  flex: 1;
  min-height: 0;
}

.center-stage-toolbar {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 5;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.expand-toggle-btn {
  border-radius: 999px;
  font-weight: 600;
}

.outline-toggle-btn {
  border-radius: 999px;
  font-weight: 600;
}

.classroom-outline-fullscreen {
  flex: 1;
  min-height: 0;
  border: 1px solid #d4e4dc;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18px 30px rgba(35, 70, 59, 0.14);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin: 10px;
}

.outline-preview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid #d9e7df;
  background: linear-gradient(180deg, #f8fcfa 0%, #eef7f2 100%);
  padding: 14px 16px;
}

.outline-preview-kicker {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #5f786f;
  font-weight: 700;
}

.outline-preview-head h4 {
  margin: 3px 0 0;
  font-size: 20px;
  color: #1f473d;
}

.outline-preview-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.outline-preview-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 18px;
}

.outline-preview-empty {
  border: 1px dashed #cfe0d8;
  border-radius: 12px;
  padding: 14px;
  color: #688177;
  font-size: 15px;
}

.outline-markdown-content {
  color: #274b43;
  font-size: 16px;
  line-height: 1.85;
}

.outline-skeleton-grid {
  display: grid;
  gap: 12px;
}

.outline-skeleton-item {
  border: 1px solid #d9e7df;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbf9 100%);
  padding: 12px;
  display: grid;
  gap: 10px;
}

.outline-skeleton-line {
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(90deg, #e8f0eb 25%, #dce9e2 40%, #e8f0eb 65%);
  background-size: 240% 100%;
  animation: skeleton-shimmer 1.2s linear infinite;
}

.outline-markdown-content :deep(h1),
.outline-markdown-content :deep(h2),
.outline-markdown-content :deep(h3) {
  margin: 0.65em 0 0.35em;
  color: #1f473d;
  line-height: 1.35;
}

.outline-markdown-content :deep(p) {
  margin: 0.45em 0;
}

.outline-markdown-content :deep(ul),
.outline-markdown-content :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.3em;
}

.outline-markdown-content :deep(li + li) {
  margin-top: 0.35em;
}

.outline-markdown-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0;
  font-size: 14px;
}

.outline-markdown-content :deep(th),
.outline-markdown-content :deep(td) {
  border: 1px solid #d5e5dd;
  padding: 8px 10px;
}

.outline-markdown-content :deep(th) {
  background: #edf6f1;
  color: #315b50;
  text-align: left;
}

.left-main-tabs :deep(.el-tabs__item) {
  font-weight: 700;
}

.left-main-tabs :deep(.el-tabs__item.is-active) {
  color: #2f605a;
}

.left-main-tabs :deep(.el-tabs__active-bar) {
  background-color: #2f605a;
}

.classroom-resizer {
  flex: 0 0 8px;
  border-radius: 999px;
  background: linear-gradient(180deg, #e6f0eb 0%, #d7e5de 100%);
  border: 1px solid #c8dbd1;
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s ease;
}

.classroom-resizer span {
  width: 2px;
  height: 48px;
  border-radius: 999px;
  background: #6a8d7f;
}

.classroom-resizer:hover {
  background: linear-gradient(180deg, #d7e8e0 0%, #c7dcd2 100%);
}

.classroom-qa-pane {
  min-width: 340px;
  min-height: 0;
  border: 1px solid #d6e4dc;
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbf9 100%);
  box-shadow: 0 14px 28px rgba(45, 72, 66, 0.09);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.classroom-qa-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid #d9e7df;
  border-radius: 12px;
  padding: 8px 10px;
  background: linear-gradient(180deg, #f8fcfa 0%, #eef6f2 100%);
}

.qa-kicker {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #5f786f;
  font-weight: 700;
}

.classroom-qa-head h4 {
  margin: 3px 0 0;
  font-size: 14px;
  color: #1f473d;
}

.qa-head-tags {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.classroom-qa-pane :deep(.chat-shell) {
  flex: 1;
  min-height: 0;
}

.classroom-split-layout.compact {
  flex-direction: column;
}

.classroom-split-layout.compact .classroom-left-pane,
.classroom-split-layout.compact .classroom-qa-pane {
  width: 100%;
  flex-basis: auto !important;
}

.classroom-split-layout.compact .classroom-qa-pane {
  min-height: 520px;
}

.classroom-split-layout.compact .classroom-resizer {
  display: none;
}

.knowledge-tree-pane {
  min-width: 0;
  border: 1px solid transparent;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f6faf8 100%);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
}

.tab-workspace-pane {
  min-width: 0;
  flex: 1;
  border: 1px solid #d8e5de;
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fcfa 100%);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  max-height: none;
  overflow: hidden;
}

.tree-pane-header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.tree-pane-header span {
  font-size: 12px;
  border-radius: 999px;
  border: 1px solid #d1e2da;
  padding: 3px 8px;
  color: #42665d;
  background: #eef5f1;
}

.tree-pane-header h3 {
  margin-top: 3px;
  font-size: 17px;
  color: #23463f;
}

.merged-tree-pane {
  min-height: 0;
}

.merged-tabs-pane {
  min-height: 0;
}

.tree-progress-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-radius: 10px;
  background: #edf5f1;
  color: #48665e;
  font-size: 12px;
}

.knowledge-tree-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid #dce9e2;
  border-radius: 12px;
  padding: 8px;
  background: #fff;
}

.workbench-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.workbench-tabs :deep(.el-tabs__header) {
  flex: 0 0 auto;
}

.workbench-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
}

.workbench-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.tab-scroll-area {
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-signal-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.status-signal-card {
  border: 1px solid #d8e5de;
  border-radius: 12px;
  background: #ffffff;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.signal-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.signal-name {
  font-size: 12px;
  color: #5b786f;
  font-weight: 600;
}

.signal-top strong {
  font-size: 15px;
  color: #1f4c43;
}

.status-signal-card p {
  margin: 0;
  font-size: 12px;
  color: #5f776f;
  line-height: 1.45;
}

.dashboard-grid {
  margin-top: 12px;
  min-height: calc(100% - 12px);
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  gap: 10px;
}

.status-group-card {
  border-radius: 14px;
  border: 1px solid #d7e5dd;
  padding: 10px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.status-group-card.mastered {
  background: linear-gradient(180deg, #ecf9f1 0%, #ffffff 100%);
}

.status-group-card.unmastered {
  background: linear-gradient(180deg, #fff9ec 0%, #fff2ea 100%);
}

.status-group-card.prerequisite {
  background: linear-gradient(180deg, #f4f6f8 0%, #ffffff 100%);
  grid-column: 1 / -1;
}

.group-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.group-head h4 {
  margin: 0;
  font-size: 14px;
  color: #23463f;
}

.group-head span {
  font-size: 12px;
  color: #5f7b71;
}

.node-card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
}

.knowledge-node-card {
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(204, 222, 214, 0.92);
  padding: 8px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.knowledge-node-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 18px rgba(43, 77, 65, 0.12);
}

.knowledge-node-card h5 {
  margin: 0;
  font-size: 13px;
  color: #2a4f47;
}

.knowledge-node-card p {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #567067;
}

.node-actions {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.card-empty {
  font-size: 12px;
  color: #70857c;
}

.interaction-layout {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 100%;
}

.interaction-card {
  border: 1px solid #d8e6de;
  border-radius: 14px;
  background: #fff;
  padding: 12px;
}

.interaction-title {
  font-size: 14px;
  font-weight: 700;
  color: #2c5148;
  margin-bottom: 8px;
}

.exercise-card {
  gap: 10px;
  flex: 1;
}

.exercise-paper {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: #36544c;
  font-size: 13px;
  line-height: 1.7;
}

.exercise-section {
  padding: 10px 12px;
  border-radius: 12px;
  background: linear-gradient(180deg, #f9fcfa 0%, #f3f8f5 100%);
  border: 1px solid #dbe8e1;
}

.exercise-section h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #274e46;
}

.exercise-list {
  margin: 0;
  padding-left: 18px;
}

.exercise-question-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.exercise-question-card {
  padding: 10px 12px;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid #d9e6de;
}

.exercise-question-title {
  margin: 0 0 8px;
  font-weight: 600;
  color: #2a4f47;
}

.exercise-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
}

.exercise-radio-group :deep(.el-radio) {
  margin-right: 0;
}

.exercise-fill-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.probability-row {
  margin: 8px 0 10px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.exercise-answer-line {
  margin-top: 8px;
  font-size: 12px;
}

.answer-correct {
  color: #15803d;
}

.answer-wrong {
  color: #b91c1c;
}

.exercise-reference {
  color: #315d54;
}

.exercise-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.exercise-score {
  font-weight: 700;
  color: #23463f;
}

.exercise-list li + li {
  margin-top: 10px;
}

.exercise-list p {
  margin: 0 0 8px;
}

.exercise-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 12px;
}

.exercise-options span {
  padding: 4px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid #d9e6de;
}

.exercise-code-block {
  margin: 8px 0 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid #d9e6de;
  font-family: Consolas, Monaco, 'Courier New', monospace;
}

.quiz-question {
  font-size: 13px;
  color: #3e5c54;
}

.quiz-options {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quiz-result {
  margin-top: 8px;
  font-size: 13px;
}

.quiz-result.correct {
  color: #15803d;
}

.quiz-result.wrong {
  color: #b91c1c;
}

.feedback-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.feedback-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #547067;
}

.notes-layout {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  height: 100%;
}

.note-actions-row {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.notes-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.notes-head h4 {
  margin: 0;
  font-size: 16px;
  color: #274b43;
}

.notes-head span {
  font-size: 12px;
  color: #648177;
}

.note-favorite-dialog {
  display: grid;
  gap: 12px;
}

.note-favorite-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.workbench-right-sidebar {
  position: relative;
  flex: 0 0 56px;
  width: 56px;
  min-width: 56px;
  min-height: 0;
  height: 100%;
  z-index: 5;
}

.right-rail {
  width: 100%;
  height: 100%;
  border-radius: 16px;
  background: linear-gradient(180deg, #f7fcf9 0%, #eef6f2 100%);
  border: 1px solid rgba(120, 156, 140, 0.28);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px 8px;
}

.rail-btn {
  width: 100%;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: #5f7467;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 4px;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.rail-btn svg {
  width: 16px;
  height: 16px;
}

.rail-btn span {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.rail-btn:hover:not(:disabled) {
  background: rgba(92, 166, 143, 0.12);
  color: #2f5e52;
  transform: translateY(-1px);
}

.rail-btn.active {
  background: linear-gradient(180deg, #79c3ab 0%, #5ca68f 100%);
  color: #ffffff;
  box-shadow: 0 8px 16px rgba(92, 166, 143, 0.24);
}

.rail-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.overlay-drawer {
  position: absolute;
  top: 8px;
  right: 66px;
  width: min(560px, 62vw);
  height: fit-content;
  max-height: calc(100% - 16px);
  border-radius: 20px;
  background: #ffffff;
  border: 1px solid rgba(120, 156, 140, 0.2);
  box-shadow: 0 24px 44px rgba(15, 23, 42, 0.18);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.section-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 12px;
  border-bottom: 1px solid rgba(120, 156, 140, 0.22);
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: #0f172a;
}

.close-btn {
  border: none;
  padding: 6px 10px;
  border-radius: 10px;
  font-size: 12px;
  background: #e8f2ed;
  color: #2f5e52;
  cursor: pointer;
}

.panel-body {
  flex: 0 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
  padding: 8px 8px 4px;
}

.courseware-select-body {
  gap: 10px;
}

.courseware-select-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.courseware-select-item {
  width: 100%;
  border: 1px solid #d5e4dc;
  border-radius: 12px;
  background: #ffffff;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.courseware-select-item:hover {
  border-color: #9dc4b5;
  background: #f5faf7;
}

.courseware-select-item.active {
  border-color: #5ca68f;
  background: #eef8f3;
  box-shadow: 0 10px 18px rgba(92, 166, 143, 0.18);
}

.courseware-item-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.courseware-item-main strong {
  font-size: 14px;
  color: #214a3f;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.courseware-item-main span {
  font-size: 12px;
  color: #5f7b71;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.courseware-item-meta {
  flex: 0 0 auto;
  font-size: 12px;
  color: #3f6b5d;
  border: 1px solid #cde2d8;
  border-radius: 999px;
  padding: 3px 8px;
  background: #f1f8f4;
}

.courseware-empty {
  border: 1px dashed #bfd6cb;
  border-radius: 12px;
  padding: 16px;
  font-size: 13px;
  color: #618076;
  text-align: center;
  background: #f7fbf9;
}

.mindmap-preview-shell {
  border: 1px solid #d5e4dc;
  border-radius: 12px;
  width: min(100%, 520px);
  min-width: 280px;
  min-height: 260px;
  height: min(72vh, 680px);
  max-height: calc(100vh - 240px);
  background: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  resize: both;
  box-sizing: border-box;
  padding: 6px;
}

.mindmap-preview-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.panel-body :deep(.course-card) {
  height: auto;
  min-height: 0;
  border-radius: 0;
  border: 0;
  box-shadow: none;
}

.panel-body :deep(.course-content) {
  min-height: 240px;
}

.panel-body :deep(.course-img) {
  max-height: min(70vh, calc(100vh - 420px));
}

.drawer-page-nav {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 4px 0 10px;
}

.nav-icon-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid #d2e3db;
  background: #fff;
  color: #3b6358;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.nav-icon-btn svg {
  width: 15px;
  height: 15px;
}

.nav-icon-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.page-indicator {
  font-size: 12px;
  color: #49675f;
  font-weight: 700;
  min-width: 66px;
  text-align: center;
}

.graph-body {
  padding: 8px 8px 4px;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  overflow: auto;
}

.graph-panel-shell {
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(92, 166, 143, 0.28);
  background: linear-gradient(180deg, #f8fcfa 0%, #f1f8f4 100%);
  box-shadow: 0 12px 24px rgba(46, 89, 74, 0.12);
}

.graph-panel-head h4 {
  margin: 0;
  font-size: 15px;
  color: #1f473d;
}

.graph-panel-head p {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: #5f7a70;
}

.action-row {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.action-btn {
  border: 1px solid #b9d7ca;
  border-radius: 10px;
  padding: 8px 10px;
  background: #ffffff;
  color: #2f605a;
  font-size: 12px;
  cursor: pointer;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn.primary {
  background: linear-gradient(180deg, #7dc3ad 0%, #5ca68f 100%);
  color: #ffffff;
  border-color: transparent;
}

.action-btn.warn {
  background: linear-gradient(180deg, #fff8ef 0%, #fff0dc 100%);
  border-color: #f5d5a5;
  color: #925900;
}

.summary-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.metric-card {
  border: 1px solid rgba(92, 166, 143, 0.2);
  border-radius: 10px;
  background: #ffffff;
  padding: 8px;
  min-width: 0;
}

.metric-card span {
  font-size: 11px;
  color: #6a847a;
}

.metric-card strong {
  margin-top: 4px;
  display: block;
  font-size: 14px;
  color: #21483e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-card.danger {
  border-color: rgba(228, 92, 92, 0.28);
  background: linear-gradient(180deg, #fffaf9 0%, #fff1f0 100%);
}

.orphan-chip-list {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 96px;
  overflow: auto;
}

.orphan-chip {
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid rgba(228, 92, 92, 0.3);
  background: #fff5f4;
  color: #b14a4a;
  font-size: 11px;
}

.result-box {
  margin-top: 10px;
  border-radius: 9px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: #365b52;
  border: 1px solid #d2e5dc;
  background: #ffffff;
}

.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: all 0.24s ease;
}

.drawer-slide-enter-from,
.drawer-slide-leave-to {
  opacity: 0;
  transform: translateX(8px);
}

.outline-stage {
  border: 1px solid #d8e5de;
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f6faf8 100%);
  padding: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.outline-header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.outline-label {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #6a8278;
  font-weight: 700;
}

.outline-header h3 {
  margin-top: 3px;
  font-size: 17px;
  color: #23463f;
}

.outline-header span {
  font-size: 12px;
  border-radius: 999px;
  border: 1px solid #d1e2da;
  padding: 3px 8px;
  color: #42665d;
  background: #eef5f1;
}

.outline-tools {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.outline-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
  padding-right: 2px;
}

.outline-item {
  border: 1px solid #d7e5dd;
  background: #fff;
  border-radius: 12px;
  padding: 8px;
  text-align: left;
  display: flex;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.outline-item:hover {
  border-color: #8caea2;
  transform: translateY(-1px);
}

.outline-item.active {
  border-color: #2f605a;
  box-shadow: 0 10px 16px rgba(47, 96, 90, 0.16);
  background: linear-gradient(180deg, #eff6f3 0%, #ffffff 100%);
}

.outline-item.jump-highlight {
  animation: nodePulse 0.85s ease;
}

.outline-index {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #e4efe9;
  color: #2f605a;
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.outline-content {
  min-width: 0;
}

.outline-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.outline-row strong {
  font-size: 13px;
  color: #274d46;
}

.outline-time {
  color: #6d847b;
  font-size: 11px;
}

.outline-content p {
  margin-top: 5px;
  font-size: 12px;
  line-height: 1.45;
  color: #577068;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.outline-empty {
  margin-top: 12px;
  border: 1px dashed #cfddd5;
  border-radius: 12px;
  padding: 12px;
  color: #70857c;
  font-size: 13px;
}

.classroom-status-strip {
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(244, 250, 247, 0.96) 100%);
  border-radius: 12px;
  padding: 10px 12px;
}

.classroom-status-strip .status-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 7px;
}

.classroom-status-strip .status-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 12px;
  color: #3b5d54;
  background: #edf4f0;
  border: 1px solid #d5e4dc;
}

.classroom-status-strip .status-pill.seek-notice {
  color: #0f766e;
  border-color: rgba(15, 118, 110, 0.35);
  background: rgba(240, 253, 250, 0.98);
  animation: noticePop 0.25s ease-out;
}

.classroom-status-strip .status-track,
.classroom-status-strip .progress-track {
  height: 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  overflow: hidden;
}

.classroom-status-strip .status-fill,
.classroom-status-strip .progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0f766e 0%, #0284c7 100%);
}

.classroom-status-strip .status-note {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 7px;
  font-size: 12px;
  color: #628075;
}

@keyframes nodePulse {
  0% {
    box-shadow: 0 0 0 0 rgba(15, 118, 110, 0.35);
  }
  100% {
    box-shadow: 0 0 0 8px rgba(15, 118, 110, 0);
  }
}

@keyframes noticePop {
  0% {
    transform: translateY(2px);
    opacity: 0;
  }
  100% {
    transform: translateY(0);
    opacity: 1;
  }
}

.center-stage {
  min-width: 0;
  position: relative;
  flex: 0 0 auto;
}

.playback-hud {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 4;
  padding: 6px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  color: #0f766e;
  background: rgba(236, 253, 245, 0.96);
  border: 1px solid rgba(15, 118, 110, 0.25);
  box-shadow: 0 10px 18px rgba(15, 118, 110, 0.12);
  animation: hudPop 0.2s ease-out;
}

.classroom-live-subtitle {
  position: absolute;
  left: 25%;
  right: auto;
  width: min(46%, 560px);
  max-width: calc(100% - 120px);
  transform: translateX(-50%);
  bottom: 96px;
  z-index: 4;
  pointer-events: auto;
  cursor: grab;
  user-select: none;
  touch-action: none;
  border-radius: 12px;
  border: 1px solid rgba(22, 101, 52, 0.32);
  background: linear-gradient(180deg, rgba(246, 255, 251, 0.96) 0%, rgba(231, 249, 241, 0.94) 100%);
  box-shadow: 0 14px 24px rgba(17, 94, 89, 0.14);
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.classroom-live-subtitle.dragging {
  cursor: grabbing;
  box-shadow: 0 16px 28px rgba(17, 94, 89, 0.22);
}

.classroom-live-subtitle.qa {
  border-color: rgba(2, 132, 199, 0.34);
  background: linear-gradient(180deg, rgba(242, 249, 255, 0.97) 0%, rgba(227, 243, 255, 0.94) 100%);
}

.subtitle-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #1f7661;
}

.classroom-live-subtitle.qa .subtitle-label {
  color: #045885;
}

.subtitle-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: #1f3f35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.shortcut-help-card {
  position: absolute;
  top: 50px;
  right: 12px;
  z-index: 4;
  width: min(360px, calc(100% - 24px));
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.12);
}

.shortcut-help-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.shortcut-help-header strong {
  font-size: 13px;
  color: #0f172a;
}

.shortcut-help-header button {
  border: 1px solid #dbe3ef;
  background: #ffffff;
  color: #334155;
  border-radius: 8px;
  padding: 2px 8px;
  font-size: 12px;
  cursor: pointer;
}

.shortcut-help-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
  font-size: 12px;
  color: #3f5b53;
}

.shortcut-help-grid kbd {
  font-family: inherit;
  border-radius: 6px;
  border: 1px solid #d5e4dc;
  background: #f8fbf9;
  padding: 1px 6px;
  font-size: 11px;
}

@keyframes hudPop {
  0% {
    opacity: 0;
    transform: translateY(-3px);
  }
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes singleColReveal {
  0% {
    opacity: 0;
    transform: translateY(6px);
  }
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}

.qa-flyout-backdrop {
  position: fixed;
  inset: 56px 0 0 0;
  z-index: 40;
  background: rgba(255, 255, 255, 0.02);
  backdrop-filter: none;
}

.qa-flyout-panel {
  position: fixed;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 22px;
  background: rgba(247, 250, 248, 0.9);
  border: 1px solid rgba(216, 229, 222, 0.88);
  box-shadow: 0 18px 34px rgba(45, 72, 66, 0.12);
  overflow: hidden;
}

.qa-flyout-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  cursor: move;
  user-select: none;
}

.qa-flyout-drag-handle {
  min-width: 0;
}

.qa-flyout-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6a8278;
}

.qa-flyout-header h3 {
  margin-top: 4px;
  font-size: 18px;
  color: #23463f;
}

.qa-flyout-header p {
  margin-top: 6px;
  font-size: 13px;
  color: #6f867d;
}

.qa-flyout-close {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 1px solid #d0dfd7;
  background: #fff;
  color: #50695f;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}

.qa-flyout-resize-handle {
  position: absolute;
  right: 8px;
  bottom: 8px;
  width: 18px;
  height: 18px;
  border-right: 2px solid rgba(47, 96, 90, 0.42);
  border-bottom: 2px solid rgba(47, 96, 90, 0.42);
  border-radius: 0 0 14px 0;
  cursor: nwse-resize;
  opacity: 0.85;
}

.qa-flyout-panel :deep(.panel-box) {
  height: 100%;
  min-height: 0;
  background:
    radial-gradient(circle at top right, rgba(143, 193, 181, 0.14), transparent 34%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.88) 0%, rgba(246, 251, 248, 0.84) 100%);
}

.qa-flyout-panel :deep(.chat-shell) {
  flex: 1;
  min-height: 0;
  height: 100%;
}

.qa-flyout-panel :deep(.conversation-board) {
  flex: 1;
  min-height: 0;
}

.qa-flyout-panel :deep(.conversation-thread) {
  max-height: none;
}

.qa-flyout-panel :deep(.message-thread) {
  max-height: none;
}

.qa-flyout-panel:active .qa-flyout-resize-handle,
.qa-flyout-panel:hover .qa-flyout-resize-handle {
  opacity: 1;
}

@keyframes qa-flyout-pop {
  from {
    opacity: 0;
    transform: translateY(16px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes qa-fab-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}

.qa-flyout-fade-enter-active,
.qa-flyout-fade-leave-active {
  transition: opacity 0.22s ease;
}

.qa-flyout-fade-enter-from,
.qa-flyout-fade-leave-to {
  opacity: 0;
}

.qa-flyout-fade-enter-active .qa-flyout-panel {
  animation: qa-flyout-pop 0.24s ease both;
}

.qa-flyout-fade-leave-active .qa-flyout-panel {
  animation: qa-flyout-pop 0.18s ease reverse both;
}

@keyframes floatOrb {
  0%, 100% { transform: translateY(0) translateX(0); }
  50% { transform: translateY(-10px) translateX(8px); }
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -40% 0; }
}

@media (max-width: 1280px) {
  .main-layout {
    gap: 10px;
  }

  .classroom-header-row {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .classroom-qa-pane {
    min-width: 300px;
  }

  .right-stage {
    min-width: 0;
    max-width: 100%;
  }

  .outline-stage {
    max-height: 280px;
  }

  .qa-flyout-panel {
    width: min(360px, calc(100vw - 24px));
    height: min(620px, calc(100vh - 80px));
  }

  .classroom-live-subtitle {
    left: 24%;
    right: auto;
    width: min(50%, 460px);
    max-width: calc(100% - 110px);
    transform: translateX(-50%);
    bottom: 88px;
  }

  .classroom-outline-fullscreen {
    border-radius: 14px;
    margin: 8px;
  }
  
}

@media (min-width: 1500px) {
  .classroom-left-stack.solo .center-stage {
    min-height: 560px;
  }

  .classroom-left-stack.expanded {
    grid-template-rows: 80px minmax(0, 1fr);
  }

  .classroom-left-stack.expanded .center-stage {
    min-height: 0;
  }
}

@media (max-width: 768px) {
  .student-app {
    padding: 8px;
  }

  .workspace-shell {
    border-radius: 18px;
  }

  .main-layout {
    padding: 10px;
    flex-direction: column;
  }

  .classroom-header-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .classroom-title-group h3 {
    font-size: 15px;
  }

  .classroom-header-actions {
    width: 100%;
    justify-content: space-between;
  }

  .classroom-split-layout {
    gap: 10px;
  }

  .classroom-qa-pane {
    min-width: 0;
    min-height: 460px;
    padding: 8px;
  }

  .classroom-qa-head {
    flex-wrap: wrap;
  }

  .qa-head-tags {
    width: 100%;
    justify-content: flex-start;
  }

  .center-stage-toolbar {
    right: 10px;
    left: 10px;
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .classroom-outline-fullscreen {
    border-radius: 12px;
    margin: 6px;
  }

  .outline-preview-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .outline-preview-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .classroom-live-subtitle {
    left: 10px;
    right: 10px;
    width: auto;
    max-width: none;
    transform: none;
    bottom: 132px;
    padding: 8px;
  }

  .subtitle-text {
    font-size: 13px;
    -webkit-line-clamp: 3;
  }

  .left-sidebar-menu {
    flex: 0 0 auto;
    width: 100%;
  }

  .left-sidebar-menu.collapsed {
    flex-basis: auto;
  }

  .menu-list {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .menu-item {
    flex: 1 1 calc(50% - 4px);
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .status-signal-grid {
    grid-template-columns: 1fr;
  }

  .tab-scroll-area {
    max-height: none;
  }

  .action-row {
    grid-template-columns: 1fr;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .qa-fab {
    right: 10px;
    width: 56px;
    height: 56px;
    top: auto;
    bottom: 88px;
    transform: none;
    animation: none;
  }

  .qa-fab:hover {
    transform: translateY(-2px) scale(1.02);
  }

  .qa-fab:active {
    transform: scale(0.98);
  }

  .qa-fab-core {
    width: 40px;
    height: 40px;
    font-size: 15px;
  }

  .qa-fab-tip {
    display: none;
  }

  .qa-flyout-backdrop {
    inset: 56px 0 0 0;
  }

  .qa-flyout-panel {
    width: min(calc(100vw - 16px), 420px);
    height: min(calc(100vh - 72px), 620px);
    border-radius: 18px;
  }

  .qa-flyout-header {
    cursor: default;
  }
}
</style>