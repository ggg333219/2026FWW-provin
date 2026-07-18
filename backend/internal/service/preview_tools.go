package service

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

// PdftoppmPath 返回 pdftoppm 可执行路径：环境变量 PDFTOPPM_EXE > PATH > Windows 常见路径。
func PdftoppmPath() string {
	if p := strings.TrimSpace(os.Getenv("PDFTOPPM_EXE")); p != "" {
		return p
	}
	if p, err := exec.LookPath("pdftoppm"); err == nil {
		return p
	}
	if runtime.GOOS == "windows" {
		home, _ := os.UserHomeDir()
		candidates := []string{
			filepath.Join(home, "poppler-25.12.0", "Library", "bin", "pdftoppm.exe"),
			filepath.Join(home, "poppler", "Library", "bin", "pdftoppm.exe"),
			`C:\poppler\Library\bin\pdftoppm.exe`,
		}
		for _, c := range candidates {
			if st, err := os.Stat(c); err == nil && !st.IsDir() {
				return c
			}
		}
	}
	return "pdftoppm"
}

// SofficePath 返回 LibreOffice soffice 路径：环境变量 SOFFICE_EXE > PATH > Windows 常见路径。
func SofficePath() string {
	if p := strings.TrimSpace(os.Getenv("SOFFICE_EXE")); p != "" {
		return p
	}
	for _, name := range []string{"soffice", "soffice.exe"} {
		if p, err := exec.LookPath(name); err == nil {
			return p
		}
	}
	if runtime.GOOS == "windows" {
		candidates := []string{
			`C:\Program Files\LibreOffice\program\soffice.exe`,
			`C:\Program Files (x86)\LibreOffice\program\soffice.exe`,
		}
		for _, c := range candidates {
			if st, err := os.Stat(c); err == nil && !st.IsDir() {
				return c
			}
		}
	}
	return ""
}
