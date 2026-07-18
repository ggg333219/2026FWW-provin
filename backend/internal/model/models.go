package model

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

// BaseModel 基础模型
type BaseModel struct {
	ID        string         `gorm:"primaryKey;size:36" json:"id"`
	CreatedAt time.Time      `json:"created_at"`
	UpdatedAt time.Time      `json:"updated_at"`
	DeletedAt gorm.DeletedAt `gorm:"index" json:"-"`
}

// BeforeCreate 自动生成UUID
func (b *BaseModel) BeforeCreate(tx *gorm.DB) error {
	if b.ID == "" {
		b.ID = uuid.New().String()
	}
	return nil
}

// Course 课件表
type Course struct {
	BaseModel
	Title               string     `gorm:"size:200;not null;index" json:"title"`
	FileURL             string     `gorm:"size:500" json:"file_url"`
	FileType            string     `gorm:"size:20" json:"file_type"` // ppt, pdf, pptx
	TotalPage           int        `gorm:"default:0" json:"total_page"`
	TeachingCourseID    string     `gorm:"size:36;index" json:"teaching_course_id"`
	TeachingCourseTitle string     `gorm:"size:200" json:"teaching_course_title"`
	CourseClassID       string     `gorm:"size:36;index" json:"course_class_id"`
	CourseClassName     string     `gorm:"size:200" json:"course_class_name"`
	IsPublished         bool       `gorm:"default:false" json:"is_published"`
	PublishScope        string     `gorm:"size:50;default:'all'" json:"publish_scope"`
	PublishedAt         *time.Time `json:"published_at,omitempty"`

	// 关联
	Pages         []CoursePage   `gorm:"foreignKey:CourseID" json:"pages,omitempty"`
	TeachingNodes []TeachingNode `gorm:"foreignKey:CourseID" json:"teaching_nodes,omitempty"`
}

// CoursePage 课件页表
type CoursePage struct {
	BaseModel
	CourseID         string `gorm:"size:36;not null;index:idx_course_page,unique" json:"course_id"`
	PageIndex        int    `gorm:"not null;index:idx_course_page,unique" json:"page_index"`
	ImageURL         string `gorm:"size:500" json:"image_url"`
	SourceText       string `gorm:"type:text" json:"source_text"`
	ScriptText       string `gorm:"type:text" json:"script_text"`
	AudioURL         string `gorm:"size:500" json:"audio_url"`
	AudioStatus      string `gorm:"size:30;default:'not_generated'" json:"audio_status"`
	AudioProvider    string `gorm:"size:60" json:"audio_provider"`
	AudioDurationSec int    `gorm:"default:0" json:"audio_duration_sec"`
}

// TeachingNode 教学节点表
type TeachingNode struct {
	BaseModel
	CourseID             string `gorm:"size:36;not null;index:idx_course_teaching_node,priority:1" json:"course_id"`
	NodeID               string `gorm:"size:100;not null;index:idx_course_teaching_node,priority:2,unique" json:"node_id"`
	ChapterTitle         string `gorm:"size:200" json:"chapter_title"`
	PageIndex            int    `gorm:"default:0;index" json:"page_index"`
	EstimatedDuration    int    `gorm:"default:0" json:"estimated_duration"`
	Title                string `gorm:"size:200;not null" json:"title"`
	Summary              string `gorm:"type:text" json:"summary"`
	SourcePages          string `gorm:"type:text" json:"source_pages"`
	CorePoints           string `gorm:"type:text" json:"core_points"`
	Examples             string `gorm:"type:text" json:"examples"`
	CommonConfusions     string `gorm:"type:text" json:"common_confusions"`
	ScriptText           string `gorm:"type:text" json:"script_text"`
	ReteachScript        string `gorm:"type:text" json:"reteach_script"`
	InteractiveQuestions string `gorm:"type:text" json:"interactive_questions"`
	TransitionText       string `gorm:"type:text" json:"transition_text"`
	MindmapMarkdown      string `gorm:"type:text" json:"mindmap_markdown"`
	StructuredMarkdown   string `gorm:"type:text" json:"structured_markdown"`
	KnowledgeNodesJSON   string `gorm:"type:text" json:"knowledge_nodes_json"`
	ScriptSegmentsJSON   string `gorm:"type:text" json:"script_segments_json"`
	SchemaVersion        int    `gorm:"default:2" json:"schema_version"`
	AudioURL             string `gorm:"size:500" json:"audio_url"`
	AudioDurationSec     int    `gorm:"default:0" json:"audio_duration_sec"`
	AudioStartSec        int    `gorm:"default:0" json:"audio_start_sec"`
	AudioEndSec          int    `gorm:"default:0" json:"audio_end_sec"`
	TTSStatus            string `gorm:"size:30;default:'not_generated'" json:"tts_status"`
	VoiceProfile         string `gorm:"size:60" json:"voice_profile"`
	SortOrder            int    `gorm:"default:0" json:"sort_order"`
}

// TeachingNodeRelation 讲授节点关系边
type TeachingNodeRelation struct {
	BaseModel
	CourseID     string  `gorm:"size:36;not null;index:idx_course_node_relation,priority:1" json:"course_id"`
	FromNodeID   string  `gorm:"size:100;not null;index:idx_course_node_relation,priority:2" json:"from_node_id"`
	ToNodeID     string  `gorm:"size:100;not null;index:idx_course_node_relation,priority:3" json:"to_node_id"`
	RelationType string  `gorm:"size:30;not null;index:idx_course_node_relation,priority:4" json:"relation_type"`
	Weight       float32 `gorm:"default:1" json:"weight"`
}

// UserProgress 用户进度表
type UserProgress struct {
	BaseModel
	UserID   string `gorm:"size:36;not null;index:idx_user_course,unique" json:"user_id"`
	CourseID string `gorm:"size:36;not null;index:idx_user_course,unique" json:"course_id"`
	LastPage int    `gorm:"default:0" json:"last_page"`
}

// DialogueSession 问答会话表
type DialogueSession struct {
	BaseModel
	UserID         string     `gorm:"size:36;index" json:"user_id"`
	CourseID       string     `gorm:"size:36;not null;index" json:"course_id"`
	CurrentPage    int        `gorm:"default:1" json:"current_page"`
	CurrentNodeID  string     `gorm:"size:100" json:"current_node_id"`
	CurrentTimeSec int        `gorm:"default:0" json:"current_time_sec"`
	PlaybackMode   string     `gorm:"size:30;default:'timeline'" json:"playback_mode"`
	LastAskedAt    *time.Time `json:"last_asked_at,omitempty"`
}

// AudioAsset 音频资产表
type AudioAsset struct {
	BaseModel
	CourseID         string `gorm:"size:36;not null;index:idx_audio_asset,priority:1" json:"course_id"`
	PageIndex        int    `gorm:"default:1;index:idx_audio_asset,priority:2" json:"page_index"`
	NodeID           string `gorm:"size:100;index:idx_audio_asset,priority:3" json:"node_id"`
	Provider         string `gorm:"size:60" json:"provider"`
	VoiceType        string `gorm:"size:60" json:"voice_type"`
	Format           string `gorm:"size:20;default:'mp3'" json:"format"`
	Status           string `gorm:"size:30;default:'placeholder'" json:"status"`
	AudioURL         string `gorm:"size:500" json:"audio_url"`
	DurationSec      int    `gorm:"default:0" json:"duration_sec"`
	StartSec         int    `gorm:"default:0" json:"start_sec"`
	EndSec           int    `gorm:"default:0" json:"end_sec"`
	SourceScriptHash string `gorm:"size:64" json:"source_script_hash"`
}

// PlatformUser 平台用户表
type PlatformUser struct {
	BaseModel
	PlatformID      string `gorm:"size:64;index" json:"platform_id"`
	ExternalID      string `gorm:"size:64;uniqueIndex" json:"external_id"`
	Username        string `gorm:"size:80;index" json:"username"`
	DisplayName     string `gorm:"size:120" json:"display_name"`
	Email           string `gorm:"size:255;index" json:"email"`
	Phone           string `gorm:"size:255;index" json:"phone"`
	Role            string `gorm:"size:30;default:'student';index" json:"role"`
	Status          string `gorm:"size:30;default:'active'" json:"status"`
	OrgCode         string `gorm:"size:64;index" json:"org_code"`
	SchoolName      string `gorm:"size:160" json:"school_name"`
	Major           string `gorm:"size:120" json:"major"`
	Grade           string `gorm:"size:40" json:"grade"`
	ClassExternalID string `gorm:"size:64;index" json:"class_external_id"`
	ClassName       string `gorm:"size:160" json:"class_name"`
	AvatarURL       string `gorm:"size:500" json:"avatar_url"`
}

// TeachingCourse 教学课程表
type TeachingCourse struct {
	BaseModel
	PlatformID  string     `gorm:"size:64;index" json:"platform_id"`
	ExternalID  string     `gorm:"size:64;uniqueIndex" json:"external_id"`
	Code        string     `gorm:"size:80;index" json:"code"`
	Title       string     `gorm:"size:200;not null;index" json:"title"`
	Description string     `gorm:"type:text" json:"description"`
	TeacherID   string     `gorm:"size:36;index" json:"teacher_id"`
	OrgCode     string     `gorm:"size:64;index" json:"org_code"`
	SchoolName  string     `gorm:"size:160" json:"school_name"`
	Status      string     `gorm:"size:30;default:'draft';index" json:"status"`
	Semester    string     `gorm:"size:60" json:"semester"`
	Credit      float64    `gorm:"default:0" json:"credit"`
	Period      int        `gorm:"default:0" json:"period"`
	CoverURL    string     `gorm:"size:500" json:"cover_url"`
	StartsAt    *time.Time `json:"starts_at,omitempty"`
	EndsAt      *time.Time `json:"ends_at,omitempty"`
}

// CourseClass 教学班级表
type CourseClass struct {
	BaseModel
	PlatformID       string `gorm:"size:64;index" json:"platform_id"`
	ExternalID       string `gorm:"size:64;uniqueIndex" json:"external_id"`
	TeachingCourseID string `gorm:"size:36;not null;index" json:"teaching_course_id"`
	TeacherID        string `gorm:"size:36;index" json:"teacher_id"`
	ClassName        string `gorm:"size:160;not null" json:"class_name"`
	ClassCode        string `gorm:"size:80;index" json:"class_code"`
	Semester         string `gorm:"size:60" json:"semester"`
	Grade            string `gorm:"size:40" json:"grade"`
	Major            string `gorm:"size:120" json:"major"`
	Capacity         int    `gorm:"default:0" json:"capacity"`
	Status           string `gorm:"size:30;default:'active'" json:"status"`
}

// CourseEnrollment 选课关系表
type CourseEnrollment struct {
	BaseModel
	PlatformID       string     `gorm:"size:64;index" json:"platform_id"`
	ExternalID       string     `gorm:"size:64;index" json:"external_id"`
	TeachingCourseID string     `gorm:"size:36;not null;index:idx_enrollment_scope,priority:1" json:"teaching_course_id"`
	CourseClassID    string     `gorm:"size:36;index:idx_enrollment_scope,priority:2" json:"course_class_id"`
	UserID           string     `gorm:"size:36;not null;index:idx_enrollment_scope,priority:3" json:"user_id"`
	Role             string     `gorm:"size:30;default:'student'" json:"role"`
	Status           string     `gorm:"size:30;default:'active'" json:"status"`
	EnrolledAt       *time.Time `json:"enrolled_at,omitempty"`
}

// DialogueTurn 问答轮次表
type DialogueTurn struct {
	BaseModel
	SessionID          string `gorm:"size:36;not null;index" json:"session_id"`
	CourseID           string `gorm:"size:36;not null;index" json:"course_id"`
	UserID             string `gorm:"size:36;index" json:"user_id"`
	TurnIndex          int    `gorm:"default:1" json:"turn_index"`
	PageIndex          int    `gorm:"default:1;index" json:"page_index"`
	NodeID             string `gorm:"size:100" json:"node_id"`
	Question           string `gorm:"type:text;not null" json:"question"`
	Answer             string `gorm:"type:text" json:"answer"`
	SourcePage         int    `gorm:"default:1" json:"source_page"`
	NeedReteach        bool   `gorm:"default:false" json:"need_reteach"`
	FollowUpSuggestion string `gorm:"type:text" json:"follow_up_suggestion"`
}

// QuestionLog 提问日志表
type QuestionLog struct {
	BaseModel
	UserID    string `gorm:"size:36;not null;index" json:"user_id"`
	CourseID  string `gorm:"size:36;not null;index" json:"course_id"`
	PageIndex int    `gorm:"not null" json:"page_index"`
	NodeID    string `gorm:"size:100;index" json:"node_id"`
	Question  string `gorm:"type:text;not null" json:"question"`
	Answer    string `gorm:"type:text" json:"answer"`
}

// TeacherEdit 教师编辑记录表
type TeacherEdit struct {
	BaseModel
	TeacherID string `gorm:"size:36;not null" json:"teacher_id"`
	CourseID  string `gorm:"size:36;not null" json:"course_id"`
	PageIndex int    `json:"page_index"`
	OldScript string `gorm:"type:text" json:"old_script"`
	NewScript string `gorm:"type:text" json:"new_script"`
}

// MindMapNode 思维导图节点表
type MindMapNode struct {
	BaseModel
	CourseID  string `gorm:"size:36;not null;index" json:"course_id"`
	ParentID  string `gorm:"size:36" json:"parent_id"`
	Title     string `gorm:"size:200;not null" json:"title"`
	Content   string `gorm:"type:text" json:"content"`
	PageIndex int    `gorm:"default:0" json:"page_index"`
	SortOrder int    `gorm:"default:0" json:"sort_order"`
}

// StudentNote 学生笔记表
type StudentNote struct {
	BaseModel
	UserID   string `gorm:"size:36;not null;index" json:"user_id"`
	CourseID string `gorm:"size:36;not null;index" json:"course_id"`
	NodeID   string `gorm:"size:100;index" json:"node_id"`
	PageNum  int    `gorm:"not null" json:"page_num"`
	Note     string `gorm:"type:text" json:"note"`
}

// StudentFavorite 收藏模型
type StudentFavorite struct {
	BaseModel
	UserID   string `gorm:"size:36;not null;index:idx_user_course_node,unique" json:"user_id"`
	CourseID string `gorm:"size:36;index:idx_user_course_node,unique" json:"course_id"`
	NodeID   string `gorm:"size:100;index:idx_user_course_node,unique" json:"node_id"`
	PageNum  int    `gorm:"default:0" json:"page_num"`
	Title    string `gorm:"size:300" json:"title"`
	Tags     string `gorm:"type:text" json:"tags"` // JSON array of tag strings
}

// PracticeTask 学生练习任务
type PracticeTask struct {
	BaseModel
	TaskID     string `gorm:"size:100;not null;index:idx_task_user,unique" json:"task_id"`
	UserID     string `gorm:"size:36;not null;index:idx_task_user,unique" json:"user_id"`
	CourseID   string `gorm:"size:36;index" json:"course_id"`
	NodeID     string `gorm:"size:100" json:"node_id"`
	PageNum    int    `json:"page_num"`
	Difficulty int    `json:"difficulty"`
	Count      int    `json:"count"`
	Questions  string `gorm:"type:text" json:"questions"` // JSON字符串
}

// PracticeAttempt 练习提交记录
type PracticeAttempt struct {
	BaseModel
	TaskID  string `gorm:"size:100;not null;index:idx_attempt_task_user,unique" json:"task_id"`
	UserID  string `gorm:"size:36;not null;index:idx_attempt_task_user,unique" json:"user_id"`
	Score   int    `json:"score"`
	Correct int    `json:"correct"`
	Total   int    `json:"total"`
	Details string `gorm:"type:text" json:"details"` // JSON字符串
}

// WeakPoint 薄弱点模型
type WeakPoint struct {
	BaseModel
	StudentID    string `gorm:"size:36;not null;index" json:"student_id"`
	CourseID     string `gorm:"size:36;not null;index" json:"course_id"`
	Name         string `gorm:"size:100;not null" json:"name"`
	Description  string `gorm:"type:text" json:"description"`
	Count        int    `gorm:"default:0" json:"count"`         // 出现次数
	MasteryLevel int    `gorm:"default:0" json:"mastery_level"` // 掌握程度 0-100
}

// KnowledgePoint 知识点模型
type KnowledgePoint struct {
	BaseModel
	CourseID string `gorm:"size:36;not null;index" json:"course_id"`
	ParentID string `gorm:"size:36" json:"parent_id"` // 父知识点ID
	Name     string `gorm:"size:100;not null" json:"name"`
	Level    int    `gorm:"default:1" json:"level"` // 1:章节 2:知识点 3:子知识点
	Content  string `gorm:"type:text" json:"content"`
	Examples string `gorm:"type:text" json:"examples"` // 示例代码/案例
}

// Question 习题模型
type Question struct {
	BaseModel
	WeakPointID       string `gorm:"size:36;index" json:"weak_point_id"`
	KnowledgePointID  string `gorm:"size:36;index" json:"knowledge_point_id"`
	CourseID          string `gorm:"size:36;index" json:"course_id"`
	NodeID            string `gorm:"size:100;index" json:"node_id"`
	PageNum           int    `gorm:"default:0;index" json:"page_num"`
	QuestionType      string `gorm:"size:20" json:"question_type"`                // single/multiple/judge/fill/subjective
	SourceType        string `gorm:"size:20;default:'manual'" json:"source_type"` // manual, ai, practice
	Content           string `gorm:"type:text;not null" json:"content"`
	Options           string `gorm:"type:text" json:"options"`     // JSON格式的选项
	Answer            string `gorm:"type:text;not null" json:"-"`  // 正确答案
	Explanation       string `gorm:"type:text" json:"explanation"` // 解析
	Difficulty        int    `gorm:"default:1" json:"difficulty"`  // 1-5
	Score             int    `gorm:"default:100" json:"score"`
	Metadata          string `gorm:"type:text" json:"metadata"` // JSON扩展字段
	AIReferenceAnswer string `gorm:"type:text" json:"ai_reference_answer"`
}

// AnswerRecord 答题记录
type AnswerRecord struct {
	BaseModel
	StudentID       string  `gorm:"size:36;not null;index" json:"student_id"`
	QuestionID      string  `gorm:"size:36;not null;index" json:"question_id"`
	TaskID          string  `gorm:"size:100;index" json:"task_id"`
	AttemptID       string  `gorm:"size:36;index" json:"attempt_id"`
	UserAnswer      string  `gorm:"type:text" json:"user_answer"`
	IsCorrect       bool    `json:"is_correct"`
	Score           float64 `gorm:"default:0" json:"score"`
	MaxScore        float64 `gorm:"default:100" json:"max_score"`
	AIComment       string  `gorm:"type:text" json:"ai_comment"`
	ReviewStatus    string  `gorm:"size:20;default:'pending'" json:"review_status"` // pending, auto, manual
	KnowledgePoints string  `gorm:"type:text" json:"knowledge_points"`              // JSON数组
	MasteryDelta    int     `json:"mastery_delta"`                                  // 掌握度变化
}

// ReviewPlan 复习计划模型
type ReviewPlan struct {
	BaseModel
	StudentID      string     `gorm:"size:36;not null;index" json:"student_id"`
	Name           string     `gorm:"size:200;not null" json:"name"`
	Description    string     `gorm:"type:text" json:"description"`
	Frequency      string     `gorm:"size:50;not null" json:"frequency"` // daily, weekly, monthly
	NextReviewDate *time.Time `json:"next_review_date"`
	Status         string     `gorm:"size:20;default:'active'" json:"status"` // active, paused, completed
}

// ReviewPlanItem 复习计划项模型
type ReviewPlanItem struct {
	BaseModel
	ReviewPlanID   string     `gorm:"size:36;not null;index" json:"review_plan_id"`
	ItemType       string     `gorm:"size:20;not null" json:"item_type"` // note, favorite
	ItemID         string     `gorm:"size:36;not null" json:"item_id"`
	Priority       int        `gorm:"default:1" json:"priority"` // 1-5
	LastReviewedAt *time.Time `json:"last_reviewed_at"`
	ReviewCount    int        `gorm:"default:0" json:"review_count"`
	NextReviewDate *time.Time `json:"next_review_date"`
}

// StudentKnowledgeMap 学生知识图谱模型
type StudentKnowledgeMap struct {
	BaseModel
	StudentID        string         `gorm:"size:36;not null;index:idx_student_knowledge,unique" json:"student_id"`
	KnowledgePointID string         `gorm:"size:36;not null;index:idx_student_knowledge,unique" json:"knowledge_point_id"`
	MasteryScore     float32        `gorm:"type:decimal(5,4);default:0.0" json:"mastery_score"`    // 0.0-1.0
	ConfidenceLevel  float32        `gorm:"type:decimal(5,4);default:0.0" json:"confidence_level"` // 置信度
	AttemptCount     int            `gorm:"default:0" json:"attempt_count"`
	CorrectCount     int            `gorm:"default:0" json:"correct_count"`
	LastUpdated      time.Time      `json:"last_updated"`
	LearningCurve    string         `gorm:"type:text" json:"learning_curve"` // JSON: 时间序列数据
	StrengthAreas    string         `gorm:"type:text" json:"strength_areas"` // JSON: 强项领域
	WeakAreas        string         `gorm:"type:text" json:"weak_areas"`     // JSON: 薄弱领域
	KnowledgePoint   KnowledgePoint `gorm:"foreignKey:KnowledgePointID;references:ID" json:"knowledge_point,omitempty"`
}

// StudentKnowledgeMastery 学生知识点掌握度（轻量统计）
type StudentKnowledgeMastery struct {
	BaseModel
	StudentID        string     `gorm:"size:36;not null;index:idx_student_kp_mastery,priority:1" json:"student_id"`
	KnowledgePointID string     `gorm:"size:36;not null;index:idx_student_kp_mastery,priority:2" json:"knowledge_point_id"`
	MasteryScore     float64    `gorm:"type:decimal(6,4);default:0.5" json:"mastery_score"`
	CorrectCount     int        `gorm:"default:0" json:"correct_count"`
	IncorrectCount   int        `gorm:"default:0" json:"incorrect_count"`
	LastResponseMs   int        `gorm:"default:0" json:"last_response_ms"`
	LastPracticedAt  *time.Time `json:"last_practiced_at,omitempty"`
}

// ScheduledTask 定时任务模型
type ScheduledTask struct {
	BaseModel
	TaskType     string     `gorm:"size:50;not null;index" json:"task_type"` // review_plan, practice_generation, notification
	TaskData     string     `gorm:"type:text;not null" json:"task_data"`     // JSON: 任务参数
	CronExpr     string     `gorm:"size:100" json:"cron_expr"`
	Description  string     `gorm:"size:255" json:"description"`
	ScheduledAt  time.Time  `gorm:"not null;index" json:"scheduled_at"`
	Status       string     `gorm:"size:20;default:'pending'" json:"status"` // pending, queued, processing, completed, failed
	Priority     int        `gorm:"default:1" json:"priority"`               // 1-5
	MaxRetries   int        `gorm:"default:3" json:"max_retries"`
	RetryCount   int        `gorm:"default:0" json:"retry_count"`
	LastAttempt  *time.Time `json:"last_attempt"`
	NextAttempt  *time.Time `json:"next_attempt"`
	ErrorMessage string     `gorm:"type:text" json:"error_message"`
	StudentID    string     `gorm:"size:36;index" json:"student_id"` // 可选，用于特定学生任务
}

// Notification 消息提醒模型
type Notification struct {
	BaseModel
	StudentID   string     `gorm:"size:36;not null;index" json:"student_id"`
	Title       string     `gorm:"size:200;not null" json:"title"`
	Content     string     `gorm:"type:text;not null" json:"content"`
	Type        string     `gorm:"size:50;not null" json:"type"`             // review_reminder, practice_due, achievement, system
	Priority    string     `gorm:"size:20;default:'normal'" json:"priority"` // low, normal, high, urgent
	Status      string     `gorm:"size:20;default:'unread'" json:"status"`   // scheduled, unread, read, archived
	RelatedID   string     `gorm:"size:36" json:"related_id"`                // 关联对象ID
	RelatedType string     `gorm:"size:50" json:"related_type"`              // review_plan, practice_task, etc.
	ScheduledAt *time.Time `json:"scheduled_at"`                             // 定时发送时间
	SentAt      *time.Time `json:"sent_at"`                                  // 实际发送时间
	Channels    string     `gorm:"type:text" json:"channels"`                // JSON: 发送渠道 [app, email, sms]
}

// TaskStatus 任务状态模型
type TaskStatus struct {
	BaseModel
	TaskID    string     `gorm:"size:36;not null;index" json:"task_id"`
	TaskType  string     `gorm:"size:50;not null;index" json:"task_type"`
	StudentID string     `gorm:"size:36;not null;index" json:"student_id"`
	Status    string     `gorm:"size:20;not null" json:"status"` // pending, running, completed, failed, cancelled
	Progress  int        `gorm:"default:0" json:"progress"`      // 0-100
	Message   string     `gorm:"type:text" json:"message"`
	StartTime *time.Time `json:"start_time"`
	EndTime   *time.Time `json:"end_time"`
	Metadata  string     `gorm:"type:text" json:"metadata"` // JSON: 额外信息
}

// NodeFavorite 节点/页面收藏
type NodeFavorite struct {
	BaseModel
	UserID    string `gorm:"size:36;not null;index:idx_favorite_scope,priority:1" json:"user_id"`
	CourseID  string `gorm:"size:36;not null;index:idx_favorite_scope,priority:2" json:"course_id"`
	NodeID    string `gorm:"size:100;index:idx_favorite_scope,priority:3" json:"node_id"`
	PageIndex int    `gorm:"default:1;index:idx_favorite_scope,priority:4" json:"page_index"`
	Title     string `gorm:"size:200" json:"title"`
}

// User 系统用户表（用于登录认证）
type User struct {
	BaseModel
	Username     string `gorm:"size:100;uniqueIndex;not null" json:"username"`
	PasswordHash string `gorm:"size:255;not null" json:"-"`
	// 角色：teacher / student
	Role string `gorm:"size:20;not null;default:'teacher'" json:"role"`
}
