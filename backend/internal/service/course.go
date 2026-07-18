package service

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"os"
	"os/exec"
	"path/filepath"
	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/pkg/logger"
	"smart-teaching-backend/pkg/oss"
	"sort"
	"strings"

	"gorm.io/gorm"
)

type CourseService interface {
	UploadCourse(ctx context.Context, file *multipart.FileHeader, title string) (*model.Course, error)
	GetCourse(id string) (*model.Course, error)
	GetCoursePages(courseID string) ([]model.CoursePage, error)
	UpdatePageScript(pageID string, script string) error
	DeleteCourse(id string) error
	// RasterPagePreview 生成单页 PNG，供 <img> 引用；课件不存在时返回错误。
	RasterPagePreview(ctx context.Context, courseID string, pageNum int) ([]byte, error)
}

type courseService struct {
	db        *gorm.DB
	ossClient *oss.MinioClient
	aiClient  AIEngine
}

func NewCourseService(db *gorm.DB, ossClient *oss.MinioClient, aiClient AIEngine) CourseService {
	return &courseService{
		db:        db,
		ossClient: ossClient,
		aiClient:  aiClient,
	}
}

// UploadCourse 上传课件
func (s *courseService) UploadCourse(ctx context.Context, file *multipart.FileHeader, title string) (*model.Course, error) {
	// 开启事务
	tx := s.db.Begin()

	// 创建课件记录（仅依赖数据库，不依赖 AI）
	course := &model.Course{
		Title:    title,
		FileType: strings.TrimPrefix(filepath.Ext(file.Filename), "."),
	}

	if err := tx.Create(course).Error; err != nil {
		tx.Rollback()
		return nil, fmt.Errorf("创建课件记录失败: %w", err)
	}

	// 打开上传的文件用于上传
	src, err := file.Open()
	if err != nil {
		tx.Rollback()
		return nil, fmt.Errorf("打开文件失败: %w", err)
	}
	defer src.Close()

	// 生成对象名：courses/{course_id}/{filename}
	objectName := fmt.Sprintf("courses/%s/%s", course.ID, file.Filename)

	// 上传到MinIO
	fileURL, err := s.ossClient.UploadFile(ctx, objectName, src, file.Size, file.Header.Get("Content-Type"))
	if err != nil {
		tx.Rollback()
		return nil, fmt.Errorf("上传文件到MinIO失败: %w", err)
	}

	// 更新课件记录的文件URL
	course.FileURL = fileURL

	// 下面这段 AI 解析逻辑在很多本地/测试环境下容易因为 AI 引擎未启动、
	// 第三方依赖（如 pdftoppm / LibreOffice）缺失而失败。
	// 为了保证“上传课件”接口本身尽量成功，这里将 AI 部分改为“最佳努力”：
	// 任何 AI 相关错误仅记录日志，不再导致整个上传事务回滚。
	if s.aiClient != nil {
		if err := s.enrichCourseWithAI(ctx, tx, course, file); err != nil {
			logger.Errorf("AI 解析/重构课件失败，将仅保存原始课件文件: %v", err)
		}
	}

	// 无 AI 页数据时，用本机 pdftoppm / LibreOffice 从源文件生成切片并写入 CoursePage（PDF/PPT/PPTX）。
	if err := s.materializeRasterCoursePages(ctx, tx, course); err != nil {
		tx.Rollback()
		return nil, fmt.Errorf("生成课件页预览失败: %w", err)
	}

	// 无论 AI 是否可用，至少要把课件元信息和文件 URL 落库
	if err := tx.Save(course).Error; err != nil {
		tx.Rollback()
		return nil, fmt.Errorf("更新课件信息失败: %w", err)
	}

	// 提交事务
	if err := tx.Commit().Error; err != nil {
		return nil, fmt.Errorf("提交事务失败: %w", err)
	}

	logger.Infof("课件上传成功: %s, URL: %s", course.ID, fileURL)

	return course, nil
}

func (s *courseService) ensurePreviewFallback(tx *gorm.DB, course *model.Course) error {
	if course == nil {
		return fmt.Errorf("course 不能为空")
	}

	var pageCount int64
	if err := tx.Model(&model.CoursePage{}).Where("course_id = ?", course.ID).Count(&pageCount).Error; err != nil {
		return err
	}
	if pageCount > 0 {
		if course.TotalPage <= 0 {
			course.TotalPage = int(pageCount)
		}
		return nil
	}

	if course.TotalPage <= 0 {
		course.TotalPage = 1
	}

	page := model.CoursePage{
		CourseID:   course.ID,
		PageIndex:  1,
		ImageURL:   "",
		SourceText: "课件解析服务暂不可用，当前为占位预览。",
	}
	if err := tx.Create(&page).Error; err != nil {
		return err
	}

	return nil
}

// materializeRasterCoursePages 在尚未有任何 CoursePage 时，从 MinIO 源文件生成各页 PNG 并上传，写入 image_url。
func (s *courseService) materializeRasterCoursePages(ctx context.Context, tx *gorm.DB, course *model.Course) error {
	if course == nil {
		return fmt.Errorf("course 不能为空")
	}
	var n int64
	if err := tx.Model(&model.CoursePage{}).Where("course_id = ?", course.ID).Count(&n).Error; err != nil {
		return err
	}
	if n > 0 {
		return nil
	}
	if strings.TrimSpace(course.FileURL) == "" {
		return s.ensurePreviewFallback(tx, course)
	}

	ft := strings.ToLower(strings.TrimSpace(course.FileType))
	ext := "." + strings.TrimPrefix(ft, ".")
	if ext == "." {
		ext = ".pdf"
	}
	if ext != ".pdf" && ext != ".pptx" && ext != ".ppt" {
		return s.ensurePreviewFallback(tx, course)
	}

	tmpFile, err := os.CreateTemp("", "course_raster_*"+ext)
	if err != nil {
		return s.ensurePreviewFallback(tx, course)
	}
	tmpPath := tmpFile.Name()
	_ = tmpFile.Close()
	defer os.Remove(tmpPath)

	if err := downloadURLToFile(ctx, strings.TrimSpace(course.FileURL), tmpPath); err != nil {
		logger.Errorf("下载课件用于预览生成失败: %v", err)
		return s.ensurePreviewFallback(tx, course)
	}

	m, err := s.generatePagePreviewImages(ctx, tmpPath, course.ID, ext)
	if err != nil || len(m) == 0 {
		logger.Errorf("生成课件预览切片失败: %v", err)
		return s.ensurePreviewFallback(tx, course)
	}

	keys := make([]int, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Ints(keys)

	pages := make([]model.CoursePage, 0, len(keys))
	for _, pidx := range keys {
		url := strings.TrimSpace(m[pidx])
		if url == "" {
			continue
		}
		pages = append(pages, model.CoursePage{
			CourseID:   course.ID,
			PageIndex:  pidx,
			ImageURL:   url,
			SourceText: "",
		})
	}
	if len(pages) == 0 {
		return s.ensurePreviewFallback(tx, course)
	}

	if err := tx.Create(&pages).Error; err != nil {
		return err
	}
	course.TotalPage = len(pages)
	return tx.Save(course).Error
}

// enrichCourseWithAI 使用 AI 引擎为课件生成解析页、预览图和教学节点。
// 注意：这里任何错误都应该被上层捕获为“非致命”，不影响上传主流程。
func (s *courseService) enrichCourseWithAI(ctx context.Context, tx *gorm.DB, course *model.Course, file *multipart.FileHeader) error {
	parsed, err := s.aiClient.ParseDocument(ctx, file)
	if err != nil {
		return fmt.Errorf("解析课件失败: %w", err)
	}

	// 优先尝试基于原始文件生成真实预览图，失败时回退到占位图
	pagePreviewURLs := map[int]string{}
	tmpPath, tmpErr := saveUploadedFileToTemp(file)
	if tmpErr == nil {
		defer os.Remove(tmpPath)
		generated, genErr := s.generatePagePreviewImages(ctx, tmpPath, course.ID, strings.ToLower(filepath.Ext(file.Filename)))
		if genErr == nil {
			pagePreviewURLs = generated
		} else {
			logger.Errorf("生成课件预览图失败，使用占位图: %v", genErr)
		}
	} else {
		logger.Errorf("保存课件临时文件失败，使用占位预览图: %v", tmpErr)
	}

	course.TotalPage = parsed.TotalPages
	if err := tx.Save(course).Error; err != nil {
		return fmt.Errorf("更新课件信息失败: %w", err)
	}

	pages := make([]model.CoursePage, 0, len(parsed.ParsedPages))
	for _, page := range parsed.ParsedPages {
		imageURL := strings.TrimSpace(pagePreviewURLs[page.Page])
		if imageURL == "" {
			// 占位置空，GetPagePreview 走 RasterPagePreview 本地渲染
		}
		pages = append(pages, model.CoursePage{
			CourseID:   course.ID,
			PageIndex:  page.Page,
			ImageURL:   imageURL,
			SourceText: strings.TrimSpace(page.Content),
		})
	}
	if len(pages) > 0 {
		if err := tx.Create(&pages).Error; err != nil {
			return fmt.Errorf("保存解析页面失败: %w", err)
		}
	}

	reconstructed, err := s.aiClient.ReconstructDocument(ctx, ReconstructDocumentRequest{
		ParsedDocument: map[string]any{
			"doc_id":       parsed.DocID,
			"doc_name":     parsed.DocName,
			"doc_type":     parsed.DocType,
			"total_pages":  parsed.TotalPages,
			"parsed_pages": parsed.ParsedPages,
		},
		Mode: "hybrid",
	})
	if err != nil {
		return fmt.Errorf("重构课件内容失败: %w", err)
	}
	if err := s.saveTeachingNodes(tx, course.ID, reconstructed); err != nil {
		return fmt.Errorf("保存教学节点失败: %w", err)
	}
	return nil
}

// GetCourse 获取课件信息
func (s *courseService) GetCourse(id string) (*model.Course, error) {
	var course model.Course
	err := s.db.Preload("Pages").First(&course, "id = ?", id).Error
	if err != nil {
		return nil, fmt.Errorf("获取课件失败: %w", err)
	}
	return &course, nil
}

// GetCoursePages 获取课件所有页面
func (s *courseService) GetCoursePages(courseID string) ([]model.CoursePage, error) {
	var pages []model.CoursePage
	err := s.db.Where("course_id = ?", courseID).Order("page_index asc").Find(&pages).Error
	if err != nil {
		return nil, fmt.Errorf("获取课件页面失败: %w", err)
	}
	return pages, nil
}

// UpdatePageScript 更新页面讲稿
func (s *courseService) UpdatePageScript(pageID string, script string) error {
	return s.db.Model(&model.CoursePage{}).Where("id = ?", pageID).Update("script_text", script).Error
}

// DeleteCourse 删除课件
func (s *courseService) DeleteCourse(id string) error {
	// 开启事务
	tx := s.db.Begin()

	// 先删除关联的页面
	if err := tx.Where("course_id = ?", id).Delete(&model.CoursePage{}).Error; err != nil {
		tx.Rollback()
		return err
	}

	if err := tx.Where("course_id = ?", id).Delete(&model.TeachingNode{}).Error; err != nil {
		tx.Rollback()
		return err
	}

	if err := tx.Unscoped().Where("course_id = ?", id).Delete(&model.TeachingNodeRelation{}).Error; err != nil {
		tx.Rollback()
		return err
	}

	// 删除课件
	if err := tx.Delete(&model.Course{}, "id = ?", id).Error; err != nil {
		tx.Rollback()
		return err
	}

	return tx.Commit().Error
}

func (s *courseService) saveTeachingNodes(tx *gorm.DB, courseID string, reconstructed *ReconstructDocumentResponse) error {
	if reconstructed == nil || len(reconstructed.TeachingNodes) == 0 {
		return nil
	}

	chapterByNodeID := map[string]string{}
	for _, chapter := range reconstructed.Chapters {
		for _, nodeID := range chapter.NodeIDs {
			chapterByNodeID[nodeID] = chapter.Title
		}
	}

	nodes := make([]model.TeachingNode, 0, len(reconstructed.TeachingNodes))
	for index, node := range reconstructed.TeachingNodes {
		sourcePages, _ := json.Marshal(node.SourcePages)
		corePoints, _ := json.Marshal(node.CorePoints)
		examples, _ := json.Marshal(node.Examples)
		commonConfusions, _ := json.Marshal(node.CommonConfusions)
		pageIndex := 0
		if len(node.SourcePages) > 0 {
			pageIndex = node.SourcePages[0]
		}

		nodes = append(nodes, model.TeachingNode{
			CourseID:          courseID,
			NodeID:            node.NodeID,
			ChapterTitle:      chapterByNodeID[node.NodeID],
			PageIndex:         pageIndex,
			EstimatedDuration: node.EstimatedDuration,
			Title:             node.Title,
			Summary:           node.Summary,
			SourcePages:       string(sourcePages),
			CorePoints:        string(corePoints),
			Examples:          string(examples),
			CommonConfusions:  string(commonConfusions),
			SortOrder:         index,
		})
	}

	return tx.Create(&nodes).Error
}

// saveUploadedFileToTemp 将上传的课件文件保存到本地临时路径，供后续预览图生成使用
func saveUploadedFileToTemp(file *multipart.FileHeader) (string, error) {
	src, err := file.Open()
	if err != nil {
		return "", err
	}
	defer src.Close()

	ext := filepath.Ext(file.Filename)
	tmpFile, err := os.CreateTemp("", "course_*"+ext)
	if err != nil {
		return "", err
	}
	defer tmpFile.Close()

	if _, err := io.Copy(tmpFile, src); err != nil {
		return "", err
	}
	return tmpFile.Name(), nil
}

// generatePagePreviewImages 使用本地渲染工具生成每页 PNG 预览，并上传到 MinIO，返回 pageIndex 到 URL 的映射
func (s *courseService) generatePagePreviewImages(ctx context.Context, localPath string, courseID string, ext string) (map[int]string, error) {
	// 目前仅支持 PDF/PPTX，其它类型直接跳过
	if ext != ".pdf" && ext != ".pptx" && ext != ".ppt" {
		return map[int]string{}, nil
	}

	pdfPath := localPath
	// PPT/PPTX 先转换为 PDF
	if ext == ".pptx" || ext == ".ppt" {
		var err error
		pdfPath, err = convertPptxToPdf(ctx, localPath)
		if err != nil {
			return nil, fmt.Errorf("PPT 转 PDF 失败: %w", err)
		}
		defer os.Remove(pdfPath)
	}

	imgDir, err := os.MkdirTemp("", "course_imgs_*")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(imgDir)

	base := filepath.Join(imgDir, "page")
	pdfBin := PdftoppmPath()
	cmd := exec.CommandContext(ctx, pdfBin, "-png", pdfPath, base)
	if output, err := cmd.CombinedOutput(); err != nil {
		return nil, fmt.Errorf("pdftoppm 生成预览失败: %w, output=%s", err, string(output))
	}

	files, err := filepath.Glob(filepath.Join(imgDir, "page-*.png"))
	if err != nil {
		return nil, err
	}
	if len(files) == 0 {
		return map[int]string{}, nil
	}
	sort.Strings(files)

	result := make(map[int]string, len(files))
	for idx, imgPath := range files {
		pageIndex := idx + 1

		f, err := os.Open(imgPath)
		if err != nil {
			continue
		}
		info, err := f.Stat()
		if err != nil {
			f.Close()
			continue
		}

		objectName := fmt.Sprintf("courses/%s/previews/page-%d.png", courseID, pageIndex)
		url, err := s.ossClient.UploadFile(ctx, objectName, f, info.Size(), "image/png")
		f.Close()
		if err != nil {
			logger.Errorf("上传预览图失败: %v", err)
			continue
		}
		result[pageIndex] = url
	}
	return result, nil
}

// convertPptxToPdf 使用本地 LibreOffice 将 PPT/PPTX 转换为 PDF
func convertPptxToPdf(ctx context.Context, pptPath string) (string, error) {
	bin := SofficePath()
	if bin == "" {
		return "", fmt.Errorf("未找到 LibreOffice(soffice)，请安装或设置环境变量 SOFFICE_EXE")
	}
	outDir := filepath.Dir(pptPath)
	cmd := exec.CommandContext(ctx, bin, "--headless", "--convert-to", "pdf", "--outdir", outDir, pptPath)
	if output, err := cmd.CombinedOutput(); err != nil {
		return "", fmt.Errorf("LibreOffice 转 PDF 失败: %w, output=%s", err, string(output))
	}
	pdfPath := strings.TrimSuffix(pptPath, filepath.Ext(pptPath)) + ".pdf"
	if _, err := os.Stat(pdfPath); err != nil {
		return "", fmt.Errorf("未找到转换后的 PDF 文件: %s", pdfPath)
	}
	return pdfPath, nil
}
