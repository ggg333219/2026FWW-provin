// Package sqlmigrate applies versioned SQL files once per environment (PostgreSQL).
package sqlmigrate

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"gorm.io/gorm"

	"smart-teaching-backend/pkg/logger"
)

// Run executes each *.sql file in dir exactly once, in lexical order by filename.
func Run(db *gorm.DB, migrationsDir string) error {
	if db == nil {
		return nil
	}
	if err := db.Exec(`
CREATE TABLE IF NOT EXISTS schema_migrations (
	version VARCHAR(255) PRIMARY KEY,
	applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)`).Error; err != nil {
		return fmt.Errorf("schema_migrations table: %w", err)
	}

	entries, err := os.ReadDir(migrationsDir)
	if err != nil {
		return fmt.Errorf("read migrations directory: %w", err)
	}

	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.EqualFold(filepath.Ext(name), ".sql") {
			continue
		}
		names = append(names, name)
	}
	sort.Strings(names)

	for _, name := range names {
		var n int64
		if err := db.Table("schema_migrations").Where("version = ?", name).Count(&n).Error; err != nil {
			return err
		}
		if n > 0 {
			continue
		}

		full := filepath.Join(migrationsDir, name)
		body, err := os.ReadFile(full)
		if err != nil {
			return fmt.Errorf("read %s: %w", name, err)
		}
		sql := strings.TrimSpace(string(body))
		if sql == "" {
			continue
		}

		err = db.Transaction(func(tx *gorm.DB) error {
			if err := tx.Exec(sql).Error; err != nil {
				return err
			}
			return tx.Exec(
				`INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)`,
				name, time.Now().UTC(),
			).Error
		})
		if err != nil {
			return fmt.Errorf("migration %s: %w", name, err)
		}
		logger.Infof("applied SQL migration: %s", name)
	}
	return nil
}
