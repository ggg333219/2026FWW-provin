package service

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"smart-teaching-backend/internal/model"
	"smart-teaching-backend/pkg/logger"
)

const previewMaxPage = 500

// RasterPagePreview 返回一页课件的 PNG 栅格图，便于教师端/浏览器 <img> 直接展示。
// 优先尝试对 PDF 使用本地 pdftoppm 渲染；失败或非 PDF 时返回内置占位 PNG（仍合法图片）。
func (s *courseService) RasterPagePreview(ctx context.Context, courseID string, pageNum int) ([]byte, error) {
	if pageNum < 1 || pageNum > previewMaxPage {
		return nil, fmt.Errorf("页码无效")
	}
	var course model.Course
	if err := s.db.First(&course, "id = ?", courseID).Error; err != nil {
		return nil, err
	}
	if course.TotalPage > 0 && pageNum > course.TotalPage {
		return nil, fmt.Errorf("页码超过总页数")
	}

	ft := strings.ToLower(strings.TrimSpace(course.FileType))
	switch ft {
	case "pdf":
		b, ok := s.tryRasterPDFFirstPage(ctx, &course, pageNum)
		if ok {
			return b, nil
		}
		return buildSlidePlaceholderPNG(course.Title, pageNum, maxInt(course.TotalPage, 1)), nil
	case "pptx", "ppt":
		b, ok := s.tryRasterOfficePresentation(ctx, &course, pageNum)
		if ok {
			return b, nil
		}
		return buildSlidePlaceholderPNG(course.Title, pageNum, maxInt(course.TotalPage, 1)), nil
	default:
		return buildSlidePlaceholderPNG(course.Title, pageNum, maxInt(course.TotalPage, 1)), nil
	}
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func (s *courseService) tryRasterPDFFirstPage(ctx context.Context, course *model.Course, pageNum int) ([]byte, bool) {
	url := strings.TrimSpace(course.FileURL)
	if url == "" {
		return nil, false
	}

	tmpPdf, err := os.CreateTemp("", "course_preview_*.pdf")
	if err != nil {
		logger.Errorf("创建临时 PDF 失败: %v", err)
		return nil, false
	}
	tmpPath := tmpPdf.Name()
	_ = tmpPdf.Close()
	defer os.Remove(tmpPath)

	if err := downloadURLToFile(ctx, url, tmpPath); err != nil {
		logger.Errorf("下载课件 PDF 失败: %v", err)
		return nil, false
	}

	return rasterSinglePagePNGFromPDF(ctx, tmpPath, pageNum)
}

// tryRasterOfficePresentation 将 PPT/PPTX 转 PDF 后渲染指定页（需 LibreOffice + Poppler）。
func (s *courseService) tryRasterOfficePresentation(ctx context.Context, course *model.Course, pageNum int) ([]byte, bool) {
	ft := strings.ToLower(strings.TrimSpace(course.FileType))
	url := strings.TrimSpace(course.FileURL)
	if url == "" {
		return nil, false
	}

	tmp, err := os.CreateTemp("", "ppt_preview_*."+ft)
	if err != nil {
		return nil, false
	}
	p := tmp.Name()
	_ = tmp.Close()
	defer os.Remove(p)

	if err := downloadURLToFile(ctx, url, p); err != nil {
		logger.Errorf("下载 Office 课件失败: %v", err)
		return nil, false
	}

	pdfPath, err := convertPptxToPdf(ctx, p)
	if err != nil {
		logger.Errorf("PPT 转 PDF 失败: %v", err)
		return nil, false
	}
	defer os.Remove(pdfPath)

	return rasterSinglePagePNGFromPDF(ctx, pdfPath, pageNum)
}

// rasterSinglePagePNGFromPDF 使用 pdftoppm 渲染 PDF 的某一页为 PNG。
func rasterSinglePagePNGFromPDF(ctx context.Context, pdfPath string, pageNum int) ([]byte, bool) {
	imgDir, err := os.MkdirTemp("", "pdftoppm_*")
	if err != nil {
		return nil, false
	}
	defer os.RemoveAll(imgDir)

	outBase := filepath.Join(imgDir, "slide")
	bin := PdftoppmPath()
	cmd := exec.CommandContext(ctx, bin, "-png",
		"-f", strconv.Itoa(pageNum),
		"-l", strconv.Itoa(pageNum),
		"-singlefile",
		pdfPath, outBase)
	out, err := cmd.CombinedOutput()
	if err != nil {
		logger.Errorf("pdftoppm 渲染失败: %v, %s", err, string(out))
		return nil, false
	}

	matches, _ := filepath.Glob(filepath.Join(imgDir, "*.png"))
	if len(matches) == 0 {
		return nil, false
	}
	b, err := os.ReadFile(matches[0])
	if err != nil || len(b) < 64 {
		return nil, false
	}
	return b, true
}

func downloadURLToFile(ctx context.Context, rawURL, dest string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return err
	}
	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = io.Copy(f, resp.Body)
	return err
}

// buildSlidePlaceholderPNG 生成简单 16:9 占位图，不依赖外网与系统字体。
func buildSlidePlaceholderPNG(title string, page, total int) []byte {
	const W, H = 960, 540
	img := image.NewNRGBA(image.Rect(0, 0, W, H))
	edge := color.NRGBA{R: 232, G: 241, B: 236, A: 255}
	mid := color.NRGBA{R: 248, G: 252, B: 250, A: 255}
	bar := color.NRGBA{R: 210, G: 232, B: 222, A: 255}
	for y := 0; y < H; y++ {
		for x := 0; x < W; x++ {
			t := float64(x+y) / float64(W+H)
			if y < 52 {
				img.SetNRGBA(x, y, bar)
				continue
			}
			if t < 0.5 {
				img.SetNRGBA(x, y, edge)
			} else {
				img.SetNRGBA(x, y, mid)
			}
		}
	}
	// 底部信息区（几何条模拟正文行）
	lineY := 120
	for i := 0; i < 5; i++ {
		y0 := lineY + i*42
		w := W - 160 - (i%3)*40
		if w < 200 {
			w = 200
		}
		for y := y0; y < y0+10; y++ {
			for x := 80; x < 80+w && x < W-80; x++ {
				img.SetNRGBA(x, y, color.NRGBA{R: 210, G: 220, B: 214, A: 255})
			}
		}
	}

	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		return minimal1x1PNG()
	}
	return buf.Bytes()
}

func minimal1x1PNG() []byte {
	img := image.NewNRGBA(image.Rect(0, 0, 1, 1))
	img.SetNRGBA(0, 0, color.NRGBA{R: 240, G: 248, B: 244, A: 255})
	var buf bytes.Buffer
	_ = png.Encode(&buf, img)
	return buf.Bytes()
}
