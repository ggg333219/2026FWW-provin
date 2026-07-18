package handler

import (
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"

	"smart-teaching-backend/internal/model"
)

type platformListOptions struct {
	Page       int
	PageSize   int
	PlatformID string
	Role       string
	Status     string
	OrgCode    string
	CourseID   string
	ClassID    string
	UserID     string
	Keyword    string
}

func normalizePlatformListOptions(options platformListOptions) platformListOptions {
	if options.Page < 1 {
		options.Page = 1
	}
	if options.PageSize < 1 {
		options.PageSize = 20
	}
	if options.PageSize > 100 {
		options.PageSize = 100
	}
	options.PlatformID = strings.TrimSpace(options.PlatformID)
	options.Role = strings.TrimSpace(strings.ToLower(options.Role))
	options.Status = strings.TrimSpace(strings.ToLower(options.Status))
	options.OrgCode = strings.TrimSpace(options.OrgCode)
	options.CourseID = strings.TrimSpace(options.CourseID)
	options.ClassID = strings.TrimSpace(options.ClassID)
	options.UserID = strings.TrimSpace(options.UserID)
	options.Keyword = strings.TrimSpace(options.Keyword)
	return options
}

func paginateResult(page, pageSize int, total int64) gin.H {
	totalPages := 0
	if pageSize > 0 {
		totalPages = int((total + int64(pageSize) - 1) / int64(pageSize))
	}
	return gin.H{
		"page":       page,
		"pageSize":   pageSize,
		"total":      total,
		"totalPages": totalPages,
	}
}

func platformOverview(db *gorm.DB) (gin.H, error) {
	var userCount int64
	var courseCount int64
	var classCount int64
	var enrollmentCount int64

	if err := db.Model(&model.PlatformUser{}).Count(&userCount).Error; err != nil {
		return nil, err
	}
	if err := db.Model(&model.TeachingCourse{}).Count(&courseCount).Error; err != nil {
		return nil, err
	}
	if err := db.Model(&model.CourseClass{}).Count(&classCount).Error; err != nil {
		return nil, err
	}
	if err := db.Model(&model.CourseEnrollment{}).Count(&enrollmentCount).Error; err != nil {
		return nil, err
	}

	var users []model.PlatformUser
	var courses []model.TeachingCourse
	var classes []model.CourseClass
	var enrollments []model.CourseEnrollment

	_ = db.Order("updated_at desc").Limit(8).Find(&users).Error
	_ = db.Order("updated_at desc").Limit(8).Find(&courses).Error
	_ = db.Order("updated_at desc").Limit(8).Find(&classes).Error
	_ = db.Order("updated_at desc").Limit(12).Find(&enrollments).Error

	userItems := make([]gin.H, 0, len(users))
	for _, item := range users {
		userItems = append(userItems, gin.H{
			"userId":      item.ID,
			"platformId":  item.PlatformID,
			"externalId":  item.ExternalID,
			"displayName": item.DisplayName,
			"role":        item.Role,
			"orgCode":     item.OrgCode,
			"schoolName":  item.SchoolName,
			"className":   item.ClassName,
			"major":       item.Major,
			"grade":       item.Grade,
			"updatedAt":   item.UpdatedAt,
		})
	}

	courseItems := make([]gin.H, 0, len(courses))
	for _, item := range courses {
		courseItems = append(courseItems, gin.H{
			"courseId":   item.ID,
			"platformId": item.PlatformID,
			"externalId": item.ExternalID,
			"title":      item.Title,
			"teacherId":  item.TeacherID,
			"orgCode":    item.OrgCode,
			"schoolName": item.SchoolName,
			"semester":   item.Semester,
			"credit":     item.Credit,
			"period":     item.Period,
			"status":     item.Status,
			"updatedAt":  item.UpdatedAt,
		})
	}

	classItems := make([]gin.H, 0, len(classes))
	for _, item := range classes {
		classItems = append(classItems, gin.H{
			"classId":          item.ID,
			"platformId":       item.PlatformID,
			"externalId":       item.ExternalID,
			"teachingCourseId": item.TeachingCourseID,
			"teacherId":        item.TeacherID,
			"className":        item.ClassName,
			"classCode":        item.ClassCode,
			"semester":         item.Semester,
			"grade":            item.Grade,
			"major":            item.Major,
			"capacity":         item.Capacity,
			"status":           item.Status,
			"updatedAt":        item.UpdatedAt,
		})
	}

	enrollmentItems := make([]gin.H, 0, len(enrollments))
	for _, item := range enrollments {
		enrollmentItems = append(enrollmentItems, gin.H{
			"enrollmentId":     item.ID,
			"platformId":       item.PlatformID,
			"externalId":       item.ExternalID,
			"teachingCourseId": item.TeachingCourseID,
			"courseClassId":    item.CourseClassID,
			"userId":           item.UserID,
			"role":             item.Role,
			"status":           item.Status,
			"enrolledAt":       item.EnrolledAt,
			"updatedAt":        item.UpdatedAt,
		})
	}

	return gin.H{
		"counts": gin.H{
			"users":       userCount,
			"courses":     courseCount,
			"classes":     classCount,
			"enrollments": enrollmentCount,
		},
		"recentUsers":       userItems,
		"recentCourses":     courseItems,
		"recentClasses":     classItems,
		"recentEnrollments": enrollmentItems,
	}, nil
}

func listPlatformUsers(db *gorm.DB, options platformListOptions) (gin.H, error) {
	options = normalizePlatformListOptions(options)
	query := db.Model(&model.PlatformUser{})
	if options.PlatformID != "" {
		query = query.Where("platform_id = ?", options.PlatformID)
	}
	if options.Role != "" {
		query = query.Where("role = ?", options.Role)
	}
	if options.OrgCode != "" {
		query = query.Where("org_code = ?", options.OrgCode)
	}
	if options.Keyword != "" {
		like := "%" + options.Keyword + "%"
		query = query.Where("display_name LIKE ? OR external_id LIKE ? OR class_name LIKE ?", like, like, like)
	}
	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, err
	}
	var users []model.PlatformUser
	if err := query.Order("updated_at desc").Offset((options.Page - 1) * options.PageSize).Limit(options.PageSize).Find(&users).Error; err != nil {
		return nil, err
	}
	items := make([]gin.H, 0, len(users))
	for _, item := range users {
		items = append(items, gin.H{
			"userId":      item.ID,
			"platformId":  item.PlatformID,
			"externalId":  item.ExternalID,
			"displayName": item.DisplayName,
			"role":        item.Role,
			"orgCode":     item.OrgCode,
			"schoolName":  item.SchoolName,
			"major":       item.Major,
			"grade":       item.Grade,
			"className":   item.ClassName,
			"email":       DecryptString(item.Email),
			"phone":       DecryptString(item.Phone),
			"updatedAt":   item.UpdatedAt,
		})
	}
	return gin.H{"items": items, "pagination": paginateResult(options.Page, options.PageSize, total)}, nil
}

func listPlatformCourses(db *gorm.DB, options platformListOptions) (gin.H, error) {
	options = normalizePlatformListOptions(options)
	query := db.Model(&model.TeachingCourse{})
	if options.PlatformID != "" {
		query = query.Where("platform_id = ?", options.PlatformID)
	}
	if options.Status != "" {
		query = query.Where("status = ?", options.Status)
	}
	if options.OrgCode != "" {
		query = query.Where("org_code = ?", options.OrgCode)
	}
	if options.UserID != "" {
		query = query.Where("teacher_id = ?", options.UserID)
	}
	if options.Keyword != "" {
		like := "%" + options.Keyword + "%"
		query = query.Where("title LIKE ? OR external_id LIKE ? OR code LIKE ?", like, like, like)
	}
	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, err
	}
	var courses []model.TeachingCourse
	if err := query.Order("updated_at desc").Offset((options.Page - 1) * options.PageSize).Limit(options.PageSize).Find(&courses).Error; err != nil {
		return nil, err
	}
	items := make([]gin.H, 0, len(courses))
	for _, item := range courses {
		items = append(items, gin.H{
			"courseId":   item.ID,
			"platformId": item.PlatformID,
			"externalId": item.ExternalID,
			"code":       item.Code,
			"title":      item.Title,
			"teacherId":  item.TeacherID,
			"orgCode":    item.OrgCode,
			"schoolName": item.SchoolName,
			"semester":   item.Semester,
			"credit":     item.Credit,
			"period":     item.Period,
			"coverUrl":   item.CoverURL,
			"status":     item.Status,
			"updatedAt":  item.UpdatedAt,
		})
	}
	return gin.H{"items": items, "pagination": paginateResult(options.Page, options.PageSize, total)}, nil
}

func listPlatformClasses(db *gorm.DB, options platformListOptions) (gin.H, error) {
	options = normalizePlatformListOptions(options)
	query := db.Model(&model.CourseClass{})
	if options.PlatformID != "" {
		query = query.Where("platform_id = ?", options.PlatformID)
	}
	if options.Status != "" {
		query = query.Where("status = ?", options.Status)
	}
	if options.CourseID != "" {
		query = query.Where("teaching_course_id = ? OR external_id = ?", options.CourseID, options.CourseID)
	}
	if options.UserID != "" {
		query = query.Where("teacher_id = ?", options.UserID)
	}
	if options.Keyword != "" {
		like := "%" + options.Keyword + "%"
		query = query.Where("class_name LIKE ? OR external_id LIKE ? OR class_code LIKE ?", like, like, like)
	}
	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, err
	}
	var classes []model.CourseClass
	if err := query.Order("updated_at desc").Offset((options.Page - 1) * options.PageSize).Limit(options.PageSize).Find(&classes).Error; err != nil {
		return nil, err
	}
	items := make([]gin.H, 0, len(classes))
	for _, item := range classes {
		items = append(items, gin.H{
			"classId":          item.ID,
			"platformId":       item.PlatformID,
			"externalId":       item.ExternalID,
			"teachingCourseId": item.TeachingCourseID,
			"teacherId":        item.TeacherID,
			"className":        item.ClassName,
			"classCode":        item.ClassCode,
			"semester":         item.Semester,
			"grade":            item.Grade,
			"major":            item.Major,
			"capacity":         item.Capacity,
			"status":           item.Status,
			"updatedAt":        item.UpdatedAt,
		})
	}
	return gin.H{"items": items, "pagination": paginateResult(options.Page, options.PageSize, total)}, nil
}

func listPlatformEnrollments(db *gorm.DB, options platformListOptions) (gin.H, error) {
	options = normalizePlatformListOptions(options)
	query := db.Model(&model.CourseEnrollment{})
	if options.PlatformID != "" {
		query = query.Where("platform_id = ?", options.PlatformID)
	}
	if options.Role != "" {
		query = query.Where("role = ?", options.Role)
	}
	if options.Status != "" {
		query = query.Where("status = ?", options.Status)
	}
	if options.CourseID != "" {
		query = query.Where("teaching_course_id = ?", options.CourseID)
	}
	if options.ClassID != "" {
		query = query.Where("course_class_id = ?", options.ClassID)
	}
	if options.UserID != "" {
		query = query.Where("user_id = ?", options.UserID)
	}
	if options.Keyword != "" {
		like := "%" + options.Keyword + "%"
		query = query.Where("external_id LIKE ?", like)
	}
	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, err
	}
	var enrollments []model.CourseEnrollment
	if err := query.Order("updated_at desc").Offset((options.Page - 1) * options.PageSize).Limit(options.PageSize).Find(&enrollments).Error; err != nil {
		return nil, err
	}
	items := make([]gin.H, 0, len(enrollments))
	for _, item := range enrollments {
		items = append(items, gin.H{
			"enrollmentId":     item.ID,
			"platformId":       item.PlatformID,
			"externalId":       item.ExternalID,
			"teachingCourseId": item.TeachingCourseID,
			"courseClassId":    item.CourseClassID,
			"userId":           item.UserID,
			"role":             item.Role,
			"status":           item.Status,
			"enrolledAt":       item.EnrolledAt,
			"updatedAt":        item.UpdatedAt,
		})
	}
	return gin.H{"items": items, "pagination": paginateResult(options.Page, options.PageSize, total)}, nil
}

func platformUserDetail(db *gorm.DB, userID string) (gin.H, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return nil, fmt.Errorf("userId 不能为空")
	}

	var user model.PlatformUser
	if err := db.Where("id = ? OR external_id = ?", userID, userID).First(&user).Error; err != nil {
		return nil, err
	}

	var enrollments []model.CourseEnrollment
	if err := db.Where("user_id = ?", user.ID).Order("updated_at desc").Find(&enrollments).Error; err != nil {
		return nil, err
	}

	courseIDs := make([]string, 0)
	classIDs := make([]string, 0)
	courseSeen := make(map[string]struct{})
	classSeen := make(map[string]struct{})
	roleCounts := make(map[string]int)
	statusCounts := make(map[string]int)
	for _, enrollment := range enrollments {
		if enrollment.TeachingCourseID != "" {
			if _, ok := courseSeen[enrollment.TeachingCourseID]; !ok {
				courseSeen[enrollment.TeachingCourseID] = struct{}{}
				courseIDs = append(courseIDs, enrollment.TeachingCourseID)
			}
		}
		if enrollment.CourseClassID != "" {
			if _, ok := classSeen[enrollment.CourseClassID]; !ok {
				classSeen[enrollment.CourseClassID] = struct{}{}
				classIDs = append(classIDs, enrollment.CourseClassID)
			}
		}
		roleCounts[firstNonEmptyString(enrollment.Role, "unknown")]++
		statusCounts[firstNonEmptyString(enrollment.Status, "unknown")]++
	}

	var courses []model.TeachingCourse
	if len(courseIDs) > 0 {
		if err := db.Where("id IN ?", courseIDs).Order("updated_at desc").Find(&courses).Error; err != nil {
			return nil, err
		}
	}

	var classes []model.CourseClass
	if len(classIDs) > 0 {
		if err := db.Where("id IN ?", classIDs).Order("updated_at desc").Find(&classes).Error; err != nil {
			return nil, err
		}
	}

	courseItems := make([]gin.H, 0, len(courses))
	for _, item := range courses {
		courseItems = append(courseItems, gin.H{
			"courseId":   item.ID,
			"externalId": item.ExternalID,
			"title":      item.Title,
			"teacherId":  item.TeacherID,
			"status":     item.Status,
			"semester":   item.Semester,
			"updatedAt":  item.UpdatedAt,
		})
	}

	classItems := make([]gin.H, 0, len(classes))
	for _, item := range classes {
		classItems = append(classItems, gin.H{
			"classId":          item.ID,
			"externalId":       item.ExternalID,
			"teachingCourseId": item.TeachingCourseID,
			"className":        item.ClassName,
			"classCode":        item.ClassCode,
			"semester":         item.Semester,
			"status":           item.Status,
			"updatedAt":        item.UpdatedAt,
		})
	}

	enrollmentItems := make([]gin.H, 0, len(enrollments))
	for _, item := range enrollments {
		enrollmentItems = append(enrollmentItems, gin.H{
			"enrollmentId":     item.ID,
			"externalId":       item.ExternalID,
			"teachingCourseId": item.TeachingCourseID,
			"courseClassId":    item.CourseClassID,
			"role":             item.Role,
			"status":           item.Status,
			"enrolledAt":       item.EnrolledAt,
			"updatedAt":        item.UpdatedAt,
		})
	}

	return gin.H{
		"profile": gin.H{
			"userId":          user.ID,
			"platformId":      user.PlatformID,
			"externalId":      user.ExternalID,
			"username":        user.Username,
			"displayName":     user.DisplayName,
			"role":            user.Role,
			"status":          user.Status,
			"orgCode":         user.OrgCode,
			"schoolName":      user.SchoolName,
			"major":           user.Major,
			"grade":           user.Grade,
			"classExternalId": user.ClassExternalID,
			"className":       user.ClassName,
			"email":           DecryptString(user.Email),
			"phone":           DecryptString(user.Phone),
			"updatedAt":       user.UpdatedAt,
		},
		"summary": gin.H{
			"courseCount":        len(courses),
			"classCount":         len(classes),
			"enrollmentCount":    len(enrollments),
			"roleDistribution":   roleCounts,
			"statusDistribution": statusCounts,
		},
		"courses":     courseItems,
		"classes":     classItems,
		"enrollments": enrollmentItems,
	}, nil
}

func platformCourseDetail(db *gorm.DB, courseID string) (gin.H, error) {
	courseID = strings.TrimSpace(courseID)
	if courseID == "" {
		return nil, fmt.Errorf("courseId 不能为空")
	}

	var course model.TeachingCourse
	if err := db.Where("id = ? OR external_id = ?", courseID, courseID).First(&course).Error; err != nil {
		return nil, err
	}

	var teacher model.PlatformUser
	teacherFound := false
	if strings.TrimSpace(course.TeacherID) != "" {
		if err := db.Where("id = ?", course.TeacherID).First(&teacher).Error; err == nil {
			teacherFound = true
		}
	}

	var classes []model.CourseClass
	if err := db.Where("teaching_course_id = ?", course.ID).Order("updated_at desc").Find(&classes).Error; err != nil {
		return nil, err
	}

	var enrollments []model.CourseEnrollment
	if err := db.Where("teaching_course_id = ?", course.ID).Order("updated_at desc").Find(&enrollments).Error; err != nil {
		return nil, err
	}

	userIDs := make([]string, 0)
	userSeen := make(map[string]struct{})
	roleCounts := make(map[string]int)
	statusCounts := make(map[string]int)
	for _, enrollment := range enrollments {
		if enrollment.UserID != "" {
			if _, ok := userSeen[enrollment.UserID]; !ok {
				userSeen[enrollment.UserID] = struct{}{}
				userIDs = append(userIDs, enrollment.UserID)
			}
		}
		roleCounts[firstNonEmptyString(enrollment.Role, "unknown")]++
		statusCounts[firstNonEmptyString(enrollment.Status, "unknown")]++
	}

	var users []model.PlatformUser
	if len(userIDs) > 0 {
		if err := db.Where("id IN ?", userIDs).Order("updated_at desc").Find(&users).Error; err != nil {
			return nil, err
		}
	}

	classItems := make([]gin.H, 0, len(classes))
	for _, item := range classes {
		classItems = append(classItems, gin.H{
			"classId":    item.ID,
			"externalId": item.ExternalID,
			"className":  item.ClassName,
			"classCode":  item.ClassCode,
			"teacherId":  item.TeacherID,
			"semester":   item.Semester,
			"grade":      item.Grade,
			"major":      item.Major,
			"capacity":   item.Capacity,
			"status":     item.Status,
			"updatedAt":  item.UpdatedAt,
		})
	}

	memberItems := make([]gin.H, 0, len(users))
	for _, item := range users {
		memberItems = append(memberItems, gin.H{
			"userId":      item.ID,
			"externalId":  item.ExternalID,
			"displayName": item.DisplayName,
			"role":        item.Role,
			"orgCode":     item.OrgCode,
			"className":   item.ClassName,
			"updatedAt":   item.UpdatedAt,
		})
	}

	response := gin.H{
		"courseInfo": gin.H{
			"courseId":    course.ID,
			"platformId":  course.PlatformID,
			"externalId":  course.ExternalID,
			"code":        course.Code,
			"title":       course.Title,
			"description": course.Description,
			"teacherId":   course.TeacherID,
			"orgCode":     course.OrgCode,
			"schoolName":  course.SchoolName,
			"status":      course.Status,
			"semester":    course.Semester,
			"credit":      course.Credit,
			"period":      course.Period,
			"coverUrl":    course.CoverURL,
			"updatedAt":   course.UpdatedAt,
		},
		"summary": gin.H{
			"classCount":         len(classes),
			"memberCount":        len(users),
			"enrollmentCount":    len(enrollments),
			"roleDistribution":   roleCounts,
			"statusDistribution": statusCounts,
		},
		"classes": classItems,
		"members": memberItems,
	}
	if teacherFound {
		response["teacher"] = gin.H{
			"userId":      teacher.ID,
			"externalId":  teacher.ExternalID,
			"displayName": teacher.DisplayName,
			"role":        teacher.Role,
			"orgCode":     teacher.OrgCode,
			"schoolName":  teacher.SchoolName,
		}
	}
	return response, nil
}

func platformClassDetail(db *gorm.DB, classID string) (gin.H, error) {
	classID = strings.TrimSpace(classID)
	if classID == "" {
		return nil, fmt.Errorf("classId 不能为空")
	}

	var classRecord model.CourseClass
	if err := db.Where("id = ? OR external_id = ?", classID, classID).First(&classRecord).Error; err != nil {
		return nil, err
	}

	var course model.TeachingCourse
	courseFound := false
	if strings.TrimSpace(classRecord.TeachingCourseID) != "" {
		if err := db.Where("id = ?", classRecord.TeachingCourseID).First(&course).Error; err == nil {
			courseFound = true
		}
	}

	var teacher model.PlatformUser
	teacherFound := false
	if strings.TrimSpace(classRecord.TeacherID) != "" {
		if err := db.Where("id = ?", classRecord.TeacherID).First(&teacher).Error; err == nil {
			teacherFound = true
		}
	}

	var enrollments []model.CourseEnrollment
	if err := db.Where("course_class_id = ?", classRecord.ID).Order("updated_at desc").Find(&enrollments).Error; err != nil {
		return nil, err
	}

	userIDs := make([]string, 0)
	userSeen := make(map[string]struct{})
	roleCounts := make(map[string]int)
	statusCounts := make(map[string]int)
	for _, enrollment := range enrollments {
		if enrollment.UserID != "" {
			if _, ok := userSeen[enrollment.UserID]; !ok {
				userSeen[enrollment.UserID] = struct{}{}
				userIDs = append(userIDs, enrollment.UserID)
			}
		}
		roleCounts[firstNonEmptyString(enrollment.Role, "unknown")]++
		statusCounts[firstNonEmptyString(enrollment.Status, "unknown")]++
	}

	var users []model.PlatformUser
	if len(userIDs) > 0 {
		if err := db.Where("id IN ?", userIDs).Order("updated_at desc").Find(&users).Error; err != nil {
			return nil, err
		}
	}

	roster := make([]gin.H, 0, len(users))
	for _, item := range users {
		roster = append(roster, gin.H{
			"userId":      item.ID,
			"externalId":  item.ExternalID,
			"displayName": item.DisplayName,
			"role":        item.Role,
			"major":       item.Major,
			"grade":       item.Grade,
			"className":   item.ClassName,
			"updatedAt":   item.UpdatedAt,
		})
	}

	response := gin.H{
		"classInfo": gin.H{
			"classId":          classRecord.ID,
			"platformId":       classRecord.PlatformID,
			"externalId":       classRecord.ExternalID,
			"teachingCourseId": classRecord.TeachingCourseID,
			"teacherId":        classRecord.TeacherID,
			"className":        classRecord.ClassName,
			"classCode":        classRecord.ClassCode,
			"semester":         classRecord.Semester,
			"grade":            classRecord.Grade,
			"major":            classRecord.Major,
			"capacity":         classRecord.Capacity,
			"status":           classRecord.Status,
			"updatedAt":        classRecord.UpdatedAt,
		},
		"summary": gin.H{
			"memberCount":        len(users),
			"enrollmentCount":    len(enrollments),
			"roleDistribution":   roleCounts,
			"statusDistribution": statusCounts,
		},
		"members": roster,
	}
	if courseFound {
		response["course"] = gin.H{
			"courseId":   course.ID,
			"externalId": course.ExternalID,
			"title":      course.Title,
			"teacherId":  course.TeacherID,
			"status":     course.Status,
			"semester":   course.Semester,
		}
	}
	if teacherFound {
		response["teacher"] = gin.H{
			"userId":      teacher.ID,
			"externalId":  teacher.ExternalID,
			"displayName": teacher.DisplayName,
			"role":        teacher.Role,
			"schoolName":  teacher.SchoolName,
		}
	}
	return response, nil
}

func platformEnrollmentDetail(db *gorm.DB, enrollmentID string) (gin.H, error) {
	enrollmentID = strings.TrimSpace(enrollmentID)
	if enrollmentID == "" {
		return nil, fmt.Errorf("enrollmentId 不能为空")
	}

	var enrollment model.CourseEnrollment
	if err := db.Where("id = ? OR external_id = ?", enrollmentID, enrollmentID).First(&enrollment).Error; err != nil {
		return nil, err
	}

	var user model.PlatformUser
	userFound := false
	if strings.TrimSpace(enrollment.UserID) != "" {
		if err := db.Where("id = ?", enrollment.UserID).First(&user).Error; err == nil {
			userFound = true
		}
	}

	var course model.TeachingCourse
	courseFound := false
	if strings.TrimSpace(enrollment.TeachingCourseID) != "" {
		if err := db.Where("id = ?", enrollment.TeachingCourseID).First(&course).Error; err == nil {
			courseFound = true
		}
	}

	var classRecord model.CourseClass
	classFound := false
	if strings.TrimSpace(enrollment.CourseClassID) != "" {
		if err := db.Where("id = ?", enrollment.CourseClassID).First(&classRecord).Error; err == nil {
			classFound = true
		}
	}

	response := gin.H{
		"enrollmentInfo": gin.H{
			"enrollmentId":     enrollment.ID,
			"platformId":       enrollment.PlatformID,
			"externalId":       enrollment.ExternalID,
			"teachingCourseId": enrollment.TeachingCourseID,
			"courseClassId":    enrollment.CourseClassID,
			"userId":           enrollment.UserID,
			"role":             enrollment.Role,
			"status":           enrollment.Status,
			"enrolledAt":       enrollment.EnrolledAt,
			"updatedAt":        enrollment.UpdatedAt,
		},
	}
	if userFound {
		response["user"] = gin.H{
			"userId":      user.ID,
			"externalId":  user.ExternalID,
			"displayName": user.DisplayName,
			"role":        user.Role,
			"className":   user.ClassName,
			"major":       user.Major,
			"grade":       user.Grade,
		}
	}
	if courseFound {
		response["course"] = gin.H{
			"courseId":   course.ID,
			"externalId": course.ExternalID,
			"title":      course.Title,
			"status":     course.Status,
			"semester":   course.Semester,
		}
	}
	if classFound {
		response["class"] = gin.H{
			"classId":    classRecord.ID,
			"externalId": classRecord.ExternalID,
			"className":  classRecord.ClassName,
			"classCode":  classRecord.ClassCode,
			"semester":   classRecord.Semester,
			"status":     classRecord.Status,
		}
	}
	return response, nil
}

func createPlatformCourse(db *gorm.DB, req map[string]any) (gin.H, error) {
	root := asNormalizedMap(req)
	title := firstNonEmptyString(
		stringValue(findValue(root, "title", "coursename", "name")),
		stringValue(findValue(root, "code", "coursecode")),
	)
	if title == "" {
		return nil, fmt.Errorf("title 不能为空")
	}

	externalID := firstNonEmptyString(
		stringValue(findValue(root, "externalId", "courseId", "id")),
		uuid.NewString(),
	)
	var existing model.TeachingCourse
	if err := db.Where("external_id = ?", externalID).First(&existing).Error; err == nil {
		return nil, fmt.Errorf("课程 externalId 已存在")
	}

	teacherID, err := resolvePlatformUserID(db, firstNonEmptyString(
		stringValue(findValue(root, "teacherId")),
		stringValue(findValue(root, "teacherExternalId")),
	))
	if err != nil {
		return nil, err
	}

	status := normalizePlatformLifecycleStatus(stringValue(findValue(root, "status")), "draft")
	startsAt, err := optionalTimeValue(findValue(root, "startsAt", "startAt"))
	if err != nil {
		return nil, fmt.Errorf("startsAt 格式错误")
	}
	endsAt, err := optionalTimeValue(findValue(root, "endsAt", "endAt"))
	if err != nil {
		return nil, fmt.Errorf("endsAt 格式错误")
	}

	course := model.TeachingCourse{
		PlatformID:  stringValue(findValue(root, "platformId", "platform")),
		ExternalID:  externalID,
		Code:        firstNonEmptyString(stringValue(findValue(root, "code", "courseCode")), externalID),
		Title:       title,
		Description: stringValue(findValue(root, "description", "desc")),
		TeacherID:   teacherID,
		OrgCode:     stringValue(findValue(root, "orgCode", "schoolId")),
		SchoolName:  stringValue(findValue(root, "schoolName")),
		Status:      status,
		Semester:    stringValue(findValue(root, "semester", "term")),
		Credit:      numberValue(findValue(root, "credit")),
		Period:      intValue(findValue(root, "period", "hours")),
		CoverURL:    stringValue(findValue(root, "coverUrl", "coverURL", "cover")),
		StartsAt:    startsAt,
		EndsAt:      endsAt,
	}
	if err := db.Create(&course).Error; err != nil {
		return nil, err
	}
	return platformCourseDetail(db, course.ID)
}

func updatePlatformCourse(db *gorm.DB, courseID string, req map[string]any) (gin.H, error) {
	root := asNormalizedMap(req)
	course, err := findTeachingCourseRecord(db, courseID)
	if err != nil {
		return nil, err
	}

	updates := map[string]any{}
	if hasAnyNormalizedKey(root, "platformId", "platform") {
		updates["platform_id"] = stringValue(findValue(root, "platformId", "platform"))
	}
	if hasAnyNormalizedKey(root, "externalId", "courseId") {
		externalID := stringValue(findValue(root, "externalId", "courseId"))
		if externalID == "" {
			return nil, fmt.Errorf("externalId 不能为空")
		}
		updates["external_id"] = externalID
	}
	if hasAnyNormalizedKey(root, "code", "courseCode") {
		updates["code"] = stringValue(findValue(root, "code", "courseCode"))
	}
	if hasAnyNormalizedKey(root, "title", "courseName", "name") {
		title := stringValue(findValue(root, "title", "courseName", "name"))
		if title == "" {
			return nil, fmt.Errorf("title 不能为空")
		}
		updates["title"] = title
	}
	if hasAnyNormalizedKey(root, "description", "desc") {
		updates["description"] = stringValue(findValue(root, "description", "desc"))
	}
	if hasAnyNormalizedKey(root, "teacherId", "teacherExternalId") {
		teacherID, err := resolvePlatformUserID(db, firstNonEmptyString(
			stringValue(findValue(root, "teacherId")),
			stringValue(findValue(root, "teacherExternalId")),
		))
		if err != nil {
			return nil, err
		}
		updates["teacher_id"] = teacherID
	}
	if hasAnyNormalizedKey(root, "orgCode", "schoolId") {
		updates["org_code"] = stringValue(findValue(root, "orgCode", "schoolId"))
	}
	if hasAnyNormalizedKey(root, "schoolName") {
		updates["school_name"] = stringValue(findValue(root, "schoolName"))
	}
	if hasAnyNormalizedKey(root, "status") {
		updates["status"] = normalizePlatformLifecycleStatus(stringValue(findValue(root, "status")), course.Status)
	}
	if hasAnyNormalizedKey(root, "semester", "term") {
		updates["semester"] = stringValue(findValue(root, "semester", "term"))
	}
	if hasAnyNormalizedKey(root, "credit") {
		updates["credit"] = numberValue(findValue(root, "credit"))
	}
	if hasAnyNormalizedKey(root, "period", "hours") {
		updates["period"] = intValue(findValue(root, "period", "hours"))
	}
	if hasAnyNormalizedKey(root, "coverUrl", "coverURL", "cover") {
		updates["cover_url"] = stringValue(findValue(root, "coverUrl", "coverURL", "cover"))
	}
	if hasAnyNormalizedKey(root, "startsAt", "startAt") {
		startsAt, err := optionalTimeValue(findValue(root, "startsAt", "startAt"))
		if err != nil {
			return nil, fmt.Errorf("startsAt 格式错误")
		}
		updates["starts_at"] = startsAt
	}
	if hasAnyNormalizedKey(root, "endsAt", "endAt") {
		endsAt, err := optionalTimeValue(findValue(root, "endsAt", "endAt"))
		if err != nil {
			return nil, fmt.Errorf("endsAt 格式错误")
		}
		updates["ends_at"] = endsAt
	}

	if len(updates) == 0 {
		return platformCourseDetail(db, course.ID)
	}
	if err := db.Model(&course).Updates(updates).Error; err != nil {
		return nil, err
	}
	return platformCourseDetail(db, course.ID)
}

func deletePlatformCourse(db *gorm.DB, courseID string) (gin.H, error) {
	course, err := findTeachingCourseRecord(db, courseID)
	if err != nil {
		return nil, err
	}

	deleted := gin.H{}
	err = db.Transaction(func(tx *gorm.DB) error {
		var classes []model.CourseClass
		if err := tx.Where("teaching_course_id = ?", course.ID).Find(&classes).Error; err != nil {
			return err
		}
		classIDs := make([]string, 0, len(classes))
		for _, classRecord := range classes {
			classIDs = append(classIDs, classRecord.ID)
		}

		var enrollmentCount int64
		if len(classIDs) > 0 {
			if err := tx.Model(&model.CourseEnrollment{}).
				Where("teaching_course_id = ? OR course_class_id IN ?", course.ID, classIDs).
				Count(&enrollmentCount).Error; err != nil {
				return err
			}
			if err := tx.Where("teaching_course_id = ? OR course_class_id IN ?", course.ID, classIDs).
				Delete(&model.CourseEnrollment{}).Error; err != nil {
				return err
			}
		} else {
			if err := tx.Model(&model.CourseEnrollment{}).
				Where("teaching_course_id = ?", course.ID).
				Count(&enrollmentCount).Error; err != nil {
				return err
			}
			if err := tx.Where("teaching_course_id = ?", course.ID).
				Delete(&model.CourseEnrollment{}).Error; err != nil {
				return err
			}
		}

		classCount := int64(len(classIDs))
		if len(classIDs) > 0 {
			if err := tx.Where("id IN ?", classIDs).Delete(&model.CourseClass{}).Error; err != nil {
				return err
			}
		}

		if err := tx.Delete(&course).Error; err != nil {
			return err
		}

		deleted = gin.H{
			"deleted": gin.H{
				"courseId":               course.ID,
				"externalId":             course.ExternalID,
				"title":                  course.Title,
				"deletedClassCount":      classCount,
				"deletedEnrollmentCount": enrollmentCount,
			},
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return deleted, nil
}

func createPlatformClass(db *gorm.DB, req map[string]any) (gin.H, error) {
	root := asNormalizedMap(req)
	courseID := firstNonEmptyString(
		stringValue(findValue(root, "courseId", "teachingCourseId")),
		stringValue(findValue(root, "courseExternalId")),
	)
	if courseID == "" {
		return nil, fmt.Errorf("courseId 不能为空")
	}
	course, err := findTeachingCourseRecord(db, courseID)
	if err != nil {
		return nil, err
	}

	className := stringValue(findValue(root, "className", "name"))
	if className == "" {
		return nil, fmt.Errorf("className 不能为空")
	}

	externalID := firstNonEmptyString(
		stringValue(findValue(root, "externalId", "classId", "id")),
		uuid.NewString(),
	)
	var existing model.CourseClass
	if err := db.Where("external_id = ?", externalID).First(&existing).Error; err == nil {
		return nil, fmt.Errorf("班级 externalId 已存在")
	}

	teacherID, err := resolvePlatformUserID(db, firstNonEmptyString(
		stringValue(findValue(root, "teacherId")),
		stringValue(findValue(root, "teacherExternalId")),
		course.TeacherID,
	))
	if err != nil {
		return nil, err
	}

	classRecord := model.CourseClass{
		PlatformID:       firstNonEmptyString(stringValue(findValue(root, "platformId", "platform")), course.PlatformID),
		ExternalID:       externalID,
		TeachingCourseID: course.ID,
		TeacherID:        teacherID,
		ClassName:        className,
		ClassCode:        firstNonEmptyString(stringValue(findValue(root, "classCode", "code")), externalID),
		Semester:         firstNonEmptyString(stringValue(findValue(root, "semester", "term")), course.Semester),
		Grade:            stringValue(findValue(root, "grade")),
		Major:            stringValue(findValue(root, "major")),
		Capacity:         intValue(findValue(root, "capacity", "classSize")),
		Status:           normalizePlatformLifecycleStatus(stringValue(findValue(root, "status")), "active"),
	}
	if err := db.Create(&classRecord).Error; err != nil {
		return nil, err
	}
	return platformClassDetail(db, classRecord.ID)
}

func updatePlatformClass(db *gorm.DB, classID string, req map[string]any) (gin.H, error) {
	root := asNormalizedMap(req)
	classRecord, err := findCourseClassRecord(db, classID)
	if err != nil {
		return nil, err
	}

	updates := map[string]any{}
	if hasAnyNormalizedKey(root, "platformId", "platform") {
		updates["platform_id"] = stringValue(findValue(root, "platformId", "platform"))
	}
	if hasAnyNormalizedKey(root, "externalId", "classId") {
		externalID := stringValue(findValue(root, "externalId", "classId"))
		if externalID == "" {
			return nil, fmt.Errorf("externalId 不能为空")
		}
		updates["external_id"] = externalID
	}
	if hasAnyNormalizedKey(root, "courseId", "teachingCourseId", "courseExternalId") {
		courseRef := firstNonEmptyString(
			stringValue(findValue(root, "courseId", "teachingCourseId")),
			stringValue(findValue(root, "courseExternalId")),
		)
		if courseRef == "" {
			return nil, fmt.Errorf("courseId 不能为空")
		}
		course, err := findTeachingCourseRecord(db, courseRef)
		if err != nil {
			return nil, err
		}
		updates["teaching_course_id"] = course.ID
	}
	if hasAnyNormalizedKey(root, "teacherId", "teacherExternalId") {
		teacherID, err := resolvePlatformUserID(db, firstNonEmptyString(
			stringValue(findValue(root, "teacherId")),
			stringValue(findValue(root, "teacherExternalId")),
		))
		if err != nil {
			return nil, err
		}
		updates["teacher_id"] = teacherID
	}
	if hasAnyNormalizedKey(root, "className", "name") {
		className := stringValue(findValue(root, "className", "name"))
		if className == "" {
			return nil, fmt.Errorf("className 不能为空")
		}
		updates["class_name"] = className
	}
	if hasAnyNormalizedKey(root, "classCode", "code") {
		updates["class_code"] = stringValue(findValue(root, "classCode", "code"))
	}
	if hasAnyNormalizedKey(root, "semester", "term") {
		updates["semester"] = stringValue(findValue(root, "semester", "term"))
	}
	if hasAnyNormalizedKey(root, "grade") {
		updates["grade"] = stringValue(findValue(root, "grade"))
	}
	if hasAnyNormalizedKey(root, "major") {
		updates["major"] = stringValue(findValue(root, "major"))
	}
	if hasAnyNormalizedKey(root, "capacity", "classSize") {
		updates["capacity"] = intValue(findValue(root, "capacity", "classSize"))
	}
	if hasAnyNormalizedKey(root, "status") {
		updates["status"] = normalizePlatformLifecycleStatus(stringValue(findValue(root, "status")), classRecord.Status)
	}

	if len(updates) == 0 {
		return platformClassDetail(db, classRecord.ID)
	}
	if err := db.Model(&classRecord).Updates(updates).Error; err != nil {
		return nil, err
	}
	return platformClassDetail(db, classRecord.ID)
}

func deletePlatformClass(db *gorm.DB, classID string) (gin.H, error) {
	classRecord, err := findCourseClassRecord(db, classID)
	if err != nil {
		return nil, err
	}

	deleted := gin.H{}
	err = db.Transaction(func(tx *gorm.DB) error {
		var enrollmentCount int64
		if err := tx.Model(&model.CourseEnrollment{}).Where("course_class_id = ?", classRecord.ID).Count(&enrollmentCount).Error; err != nil {
			return err
		}
		if err := tx.Where("course_class_id = ?", classRecord.ID).Delete(&model.CourseEnrollment{}).Error; err != nil {
			return err
		}
		if err := tx.Delete(&classRecord).Error; err != nil {
			return err
		}
		deleted = gin.H{
			"deleted": gin.H{
				"classId":                classRecord.ID,
				"externalId":             classRecord.ExternalID,
				"className":              classRecord.ClassName,
				"deletedEnrollmentCount": enrollmentCount,
			},
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return deleted, nil
}

func createPlatformEnrollment(db *gorm.DB, req map[string]any) (gin.H, error) {
	root := asNormalizedMap(req)
	courseRef := firstNonEmptyString(
		stringValue(findValue(root, "courseId", "teachingCourseId")),
		stringValue(findValue(root, "courseExternalId")),
	)
	userRef := firstNonEmptyString(
		stringValue(findValue(root, "userId")),
		stringValue(findValue(root, "userExternalId")),
	)
	if courseRef == "" || userRef == "" {
		return nil, fmt.Errorf("courseId 和 userId 不能为空")
	}
	course, err := findTeachingCourseRecord(db, courseRef)
	if err != nil {
		return nil, err
	}
	userID, err := resolvePlatformUserID(db, userRef)
	if err != nil {
		return nil, err
	}
	classRef := firstNonEmptyString(
		stringValue(findValue(root, "classId", "courseClassId")),
		stringValue(findValue(root, "classExternalId")),
	)
	classID := ""
	if classRef != "" {
		classRecord, err := findCourseClassRecord(db, classRef)
		if err != nil {
			return nil, err
		}
		classID = classRecord.ID
	} else {
		defaultClass, err := ensureDefaultCourseClass(db, course, course.TeacherID)
		if err != nil {
			return nil, err
		}
		classID = defaultClass.ID
	}

	externalID := firstNonEmptyString(
		stringValue(findValue(root, "externalId", "enrollmentId", "id")),
		fmt.Sprintf("%s_%s_%s", course.ExternalID, classID, userID),
	)
	role := normalizePlatformRole(stringValue(findValue(root, "role")), "student")
	status := normalizePlatformLifecycleStatus(stringValue(findValue(root, "status")), "active")
	enrolledAt, err := optionalTimeValue(findValue(root, "enrolledAt"))
	if err != nil {
		return nil, fmt.Errorf("enrolledAt 格式错误")
	}
	if enrolledAt == nil {
		now := time.Now()
		enrolledAt = &now
	}

	var existing model.CourseEnrollment
	if err := db.Where("teaching_course_id = ? AND course_class_id = ? AND user_id = ?", course.ID, classID, userID).First(&existing).Error; err == nil {
		return nil, fmt.Errorf("选课关系已存在")
	}

	enrollment := model.CourseEnrollment{
		PlatformID:       firstNonEmptyString(stringValue(findValue(root, "platformId", "platform")), course.PlatformID),
		ExternalID:       externalID,
		TeachingCourseID: course.ID,
		CourseClassID:    classID,
		UserID:           userID,
		Role:             role,
		Status:           status,
		EnrolledAt:       enrolledAt,
	}
	if err := db.Create(&enrollment).Error; err != nil {
		return nil, err
	}
	return platformEnrollmentDetail(db, enrollment.ID)
}

func updatePlatformEnrollment(db *gorm.DB, enrollmentID string, req map[string]any) (gin.H, error) {
	root := asNormalizedMap(req)
	enrollment, err := findEnrollmentRecord(db, enrollmentID)
	if err != nil {
		return nil, err
	}

	updates := map[string]any{}
	if hasAnyNormalizedKey(root, "platformId", "platform") {
		updates["platform_id"] = stringValue(findValue(root, "platformId", "platform"))
	}
	if hasAnyNormalizedKey(root, "externalId", "enrollmentId") {
		externalID := stringValue(findValue(root, "externalId", "enrollmentId"))
		if externalID == "" {
			return nil, fmt.Errorf("externalId 不能为空")
		}
		updates["external_id"] = externalID
	}
	if hasAnyNormalizedKey(root, "courseId", "teachingCourseId", "courseExternalId") {
		courseRef := firstNonEmptyString(
			stringValue(findValue(root, "courseId", "teachingCourseId")),
			stringValue(findValue(root, "courseExternalId")),
		)
		course, err := findTeachingCourseRecord(db, courseRef)
		if err != nil {
			return nil, err
		}
		updates["teaching_course_id"] = course.ID
	}
	if hasAnyNormalizedKey(root, "classId", "courseClassId", "classExternalId") {
		classRef := firstNonEmptyString(
			stringValue(findValue(root, "classId", "courseClassId")),
			stringValue(findValue(root, "classExternalId")),
		)
		classRecord, err := findCourseClassRecord(db, classRef)
		if err != nil {
			return nil, err
		}
		updates["course_class_id"] = classRecord.ID
	}
	if hasAnyNormalizedKey(root, "userId", "userExternalId") {
		userID, err := resolvePlatformUserID(db, firstNonEmptyString(
			stringValue(findValue(root, "userId")),
			stringValue(findValue(root, "userExternalId")),
		))
		if err != nil {
			return nil, err
		}
		updates["user_id"] = userID
	}
	if hasAnyNormalizedKey(root, "role") {
		updates["role"] = normalizePlatformRole(stringValue(findValue(root, "role")), enrollment.Role)
	}
	if hasAnyNormalizedKey(root, "status") {
		updates["status"] = normalizePlatformLifecycleStatus(stringValue(findValue(root, "status")), enrollment.Status)
	}
	if hasAnyNormalizedKey(root, "enrolledAt") {
		enrolledAt, err := optionalTimeValue(findValue(root, "enrolledAt"))
		if err != nil {
			return nil, fmt.Errorf("enrolledAt 格式错误")
		}
		updates["enrolled_at"] = enrolledAt
	}

	if len(updates) == 0 {
		return platformEnrollmentDetail(db, enrollment.ID)
	}
	if err := db.Model(&enrollment).Updates(updates).Error; err != nil {
		return nil, err
	}
	return platformEnrollmentDetail(db, enrollment.ID)
}

func deletePlatformEnrollment(db *gorm.DB, enrollmentID string) (gin.H, error) {
	enrollment, err := findEnrollmentRecord(db, enrollmentID)
	if err != nil {
		return nil, err
	}
	if err := db.Delete(&enrollment).Error; err != nil {
		return nil, err
	}
	return gin.H{
		"deleted": gin.H{
			"enrollmentId": enrollment.ID,
			"externalId":   enrollment.ExternalID,
			"courseId":     enrollment.TeachingCourseID,
			"classId":      enrollment.CourseClassID,
			"userId":       enrollment.UserID,
		},
	}, nil
}

func syncCourseFromPlatform(db *gorm.DB, req map[string]any) (gin.H, error) {
	root := asNormalizedMap(req)
	platformID := stringValue(findValue(root, "platformId", "platform"))
	courseInfo := asNormalizedMap(findValue(root, "courseInfo", "course", "course_data"))
	courseExternalID := firstNonEmptyString(
		stringValue(findValue(courseInfo, "courseId", "id", "externalId")),
		stringValue(findValue(root, "courseId", "id")),
	)
	if courseExternalID == "" {
		return nil, fmt.Errorf("courseInfo.courseId 不能为空")
	}

	courseName := firstNonEmptyString(
		stringValue(findValue(courseInfo, "courseName", "title", "name")),
		courseExternalID,
	)
	schoolID := stringValue(findValue(courseInfo, "schoolId", "orgCode", "schoolCode"))
	schoolName := stringValue(findValue(courseInfo, "schoolName", "orgName"))
	term := stringValue(findValue(courseInfo, "term", "semester"))
	credit := numberValue(findValue(courseInfo, "credit"))
	period := intValue(findValue(courseInfo, "period", "periods", "hours"))
	courseCover := stringValue(findValue(courseInfo, "courseCover", "cover", "coverUrl"))

	teachers := make([]model.PlatformUser, 0)
	teacherInternalID := ""
	for _, raw := range toSlice(findValue(courseInfo, "teacherInfo", "teachers", "teacherList")) {
		teacherInfo := asNormalizedMap(raw)
		teacher, err := upsertPlatformUserRecord(db, platformUserPayload{
			PlatformID:  platformID,
			ExternalID:  firstNonEmptyString(stringValue(findValue(teacherInfo, "teacherId", "userId", "id")), uuid.NewString()),
			DisplayName: firstNonEmptyString(stringValue(findValue(teacherInfo, "teacherName", "userName", "name")), "未命名教师"),
			Role:        "teacher",
			OrgCode:     schoolID,
			SchoolName:  schoolName,
		})
		if err != nil {
			return nil, err
		}
		if teacherInternalID == "" {
			teacherInternalID = teacher.ID
		}
		teachers = append(teachers, teacher)
	}

	teachingCourse := model.TeachingCourse{}
	err := db.Where("external_id = ?", courseExternalID).First(&teachingCourse).Error
	payload := map[string]any{
		"platform_id": platformID,
		"code":        courseExternalID,
		"title":       courseName,
		"description": strings.TrimSpace(schoolName),
		"teacher_id":  teacherInternalID,
		"org_code":    schoolID,
		"school_name": schoolName,
		"status":      "active",
		"semester":    term,
		"credit":      credit,
		"period":      period,
		"cover_url":   courseCover,
	}
	if err == nil {
		if updateErr := db.Model(&teachingCourse).Updates(payload).Error; updateErr != nil {
			return nil, updateErr
		}
	} else {
		teachingCourse = model.TeachingCourse{
			PlatformID:  platformID,
			ExternalID:  courseExternalID,
			Code:        courseExternalID,
			Title:       courseName,
			Description: strings.TrimSpace(schoolName),
			TeacherID:   teacherInternalID,
			OrgCode:     schoolID,
			SchoolName:  schoolName,
			Status:      "active",
			Semester:    term,
			Credit:      credit,
			Period:      period,
			CoverURL:    courseCover,
		}
		if createErr := db.Create(&teachingCourse).Error; createErr != nil {
			return nil, createErr
		}
	}

	classPayloads := buildCourseClassPayloads(platformID, courseInfo, teachingCourse)
	classes := make([]model.CourseClass, 0, len(classPayloads))
	for _, classPayload := range classPayloads {
		courseClass, classErr := upsertCourseClassRecord(db, teachingCourse, teacherInternalID, classPayload)
		if classErr != nil {
			return nil, classErr
		}
		classes = append(classes, courseClass)
		for _, teacher := range teachers {
			if enrollErr := upsertEnrollmentRecord(db, platformID, "", teachingCourse.ID, courseClass.ID, teacher.ID, "teacher", "active"); enrollErr != nil {
				return nil, enrollErr
			}
		}
	}
	primaryClass := model.CourseClass{}
	if len(classes) > 0 {
		primaryClass = classes[0]
	}
	teacherSummaries := make([]gin.H, 0, len(teachers))
	for _, teacher := range teachers {
		teacherSummaries = append(teacherSummaries, gin.H{"userId": teacher.ID, "externalId": teacher.ExternalID, "displayName": teacher.DisplayName})
	}
	classSummaries := make([]gin.H, 0, len(classes))
	for _, class := range classes {
		classSummaries = append(classSummaries, gin.H{"classId": class.ID, "externalClassId": class.ExternalID, "className": class.ClassName, "semester": class.Semester, "grade": class.Grade, "major": class.Major, "capacity": class.Capacity})
	}

	return gin.H{
		"internalCourseId": teachingCourse.ID,
		"syncStatus":       "success",
		"syncTime":         time.Now().Format("2006-01-02 15:04:05"),
		"teacherCount":     len(teachers),
		"teachers":         teacherSummaries,
		"classes":          classSummaries,
		"courseMeta": gin.H{
			"courseName":  courseName,
			"schoolId":    schoolID,
			"schoolName":  schoolName,
			"term":        term,
			"credit":      credit,
			"period":      period,
			"courseCover": courseCover,
		},
		"classInfo": gin.H{
			"classId":   primaryClass.ID,
			"className": primaryClass.ClassName,
		},
	}, nil
}

func syncUserFromPlatform(db *gorm.DB, req map[string]any) (gin.H, error) {
	root := asNormalizedMap(req)
	platformID := stringValue(findValue(root, "platformId", "platform"))
	userInfo := asNormalizedMap(findValue(root, "userInfo", "user", "user_data"))
	userExternalID := firstNonEmptyString(
		stringValue(findValue(userInfo, "userId", "id", "externalId")),
		stringValue(findValue(root, "userId", "id")),
	)
	if userExternalID == "" {
		return nil, fmt.Errorf("userInfo.userId 不能为空")
	}

	contactInfo := asNormalizedMap(findValue(userInfo, "contactInfo", "contact"))
	schoolID := stringValue(findValue(userInfo, "schoolId", "orgCode"))
	schoolName := stringValue(findValue(userInfo, "schoolName", "orgName"))
	classExternalID := stringValue(findValue(userInfo, "classId", "classCode"))
	className := stringValue(findValue(userInfo, "className"))
	major := stringValue(findValue(userInfo, "major"))
	grade := stringValue(findValue(userInfo, "grade"))
	userRole := strings.ToLower(firstNonEmptyString(stringValue(findValue(userInfo, "role")), "student"))
	platformUser, err := upsertPlatformUserRecord(db, platformUserPayload{
		PlatformID:      platformID,
		ExternalID:      userExternalID,
		DisplayName:     firstNonEmptyString(stringValue(findValue(userInfo, "userName", "name", "displayName")), userExternalID),
		Role:            userRole,
		OrgCode:         schoolID,
		SchoolName:      schoolName,
		Major:           major,
		Grade:           grade,
		ClassExternalID: classExternalID,
		ClassName:       className,
		Email:           stringValue(findValue(contactInfo, "email")),
		Phone:           stringValue(findValue(contactInfo, "phone", "mobile")),
	})
	if err != nil {
		return nil, err
	}

	enrollmentCount := 0
	linkedCourses := make([]gin.H, 0)
	for _, ref := range buildUserCourseRefs(userInfo, classExternalID, className, userRole) {
		teachingCourse, err := ensureTeachingCoursePlaceholder(db, platformID, ref.CourseExternalID, platformUser.OrgCode, platformUser.SchoolName)
		if err != nil {
			return nil, err
		}
		courseClass, err := upsertCourseClassRecord(db, teachingCourse, teachingCourse.TeacherID, platformClassPayload{
			PlatformID: platformID,
			ExternalID: firstNonEmptyString(ref.ClassExternalID, fmt.Sprintf("%s_%s_default", teachingCourse.ExternalID, firstNonEmptyString(teachingCourse.Semester, "default"))),
			ClassName:  firstNonEmptyString(ref.ClassName, className, firstNonEmptyString(teachingCourse.Title, teachingCourse.ExternalID)+"默认班级"),
			ClassCode:  firstNonEmptyString(ref.ClassExternalID, classExternalID, teachingCourse.Code),
			Semester:   teachingCourse.Semester,
			Grade:      grade,
			Major:      major,
		})
		if err != nil {
			return nil, err
		}
		enrollmentExternalID := firstNonEmptyString(ref.ExternalID, fmt.Sprintf("%s_%s_%s", teachingCourse.ExternalID, courseClass.ExternalID, platformUser.ExternalID))
		if err := upsertEnrollmentRecord(db, platformID, enrollmentExternalID, teachingCourse.ID, courseClass.ID, platformUser.ID, firstNonEmptyString(ref.Role, userRole), firstNonEmptyString(ref.Status, "active")); err != nil {
			return nil, err
		}
		enrollmentCount++
		linkedCourses = append(linkedCourses, gin.H{"courseId": teachingCourse.ID, "externalCourseId": teachingCourse.ExternalID, "classId": courseClass.ID, "externalClassId": courseClass.ExternalID, "className": courseClass.ClassName, "role": firstNonEmptyString(ref.Role, userRole)})
	}

	return gin.H{
		"internalUserId":  platformUser.ID,
		"authToken":       "sync_" + uuid.NewString(),
		"syncStatus":      "success",
		"enrollmentCount": enrollmentCount,
		"linkedCourses":   linkedCourses,
		"userProfile": gin.H{
			"role":        platformUser.Role,
			"displayName": platformUser.DisplayName,
			"orgCode":     platformUser.OrgCode,
			"schoolName":  platformUser.SchoolName,
			"major":       platformUser.Major,
			"grade":       platformUser.Grade,
			"className":   platformUser.ClassName,
		},
	}, nil
}

type platformUserPayload struct {
	PlatformID      string
	ExternalID      string
	DisplayName     string
	Role            string
	OrgCode         string
	SchoolName      string
	Major           string
	Grade           string
	ClassExternalID string
	ClassName       string
	Email           string
	Phone           string
}

type platformClassPayload struct {
	PlatformID string
	ExternalID string
	ClassName  string
	ClassCode  string
	Semester   string
	Grade      string
	Major      string
	Capacity   int
}

type platformCourseRef struct {
	ExternalID       string
	CourseExternalID string
	ClassExternalID  string
	ClassName        string
	Role             string
	Status           string
}

func upsertPlatformUserRecord(db *gorm.DB, payload platformUserPayload) (model.PlatformUser, error) {
	payload.Role = strings.ToLower(firstNonEmptyString(payload.Role, "student"))
	user := model.PlatformUser{}
	err := db.Where("external_id = ?", payload.ExternalID).First(&user).Error
	// 对敏感字段进行加密后再写入数据库
	encryptedEmail := EncryptString(payload.Email)
	encryptedPhone := EncryptString(payload.Phone)
	updates := map[string]any{
		"platform_id":       payload.PlatformID,
		"username":          payload.ExternalID,
		"display_name":      payload.DisplayName,
		"email":             encryptedEmail,
		"phone":             encryptedPhone,
		"role":              payload.Role,
		"status":            "active",
		"org_code":          payload.OrgCode,
		"school_name":       payload.SchoolName,
		"major":             payload.Major,
		"grade":             payload.Grade,
		"class_external_id": payload.ClassExternalID,
		"class_name":        payload.ClassName,
	}
	if err == nil {
		if updateErr := db.Model(&user).Updates(updates).Error; updateErr != nil {
			return user, updateErr
		}
		_ = db.First(&user, "id = ?", user.ID).Error
		return user, nil
	}

	user = model.PlatformUser{
		PlatformID:      payload.PlatformID,
		ExternalID:      payload.ExternalID,
		Username:        payload.ExternalID,
		DisplayName:     payload.DisplayName,
		Email:           encryptedEmail,
		Phone:           encryptedPhone,
		Role:            payload.Role,
		Status:          "active",
		OrgCode:         payload.OrgCode,
		SchoolName:      payload.SchoolName,
		Major:           payload.Major,
		Grade:           payload.Grade,
		ClassExternalID: payload.ClassExternalID,
		ClassName:       payload.ClassName,
	}
	if createErr := db.Create(&user).Error; createErr != nil {
		return user, createErr
	}
	return user, nil
}

func ensureTeachingCoursePlaceholder(db *gorm.DB, platformID, externalID, orgCode, schoolName string) (model.TeachingCourse, error) {
	course := model.TeachingCourse{}
	if err := db.Where("external_id = ?", externalID).First(&course).Error; err == nil {
		return course, nil
	}
	course = model.TeachingCourse{
		PlatformID: platformID,
		ExternalID: externalID,
		Code:       externalID,
		Title:      externalID,
		OrgCode:    orgCode,
		SchoolName: schoolName,
		Status:     "draft",
	}
	return course, db.Create(&course).Error
}

func ensureDefaultCourseClass(db *gorm.DB, course model.TeachingCourse, teacherID string) (model.CourseClass, error) {
	semester := firstNonEmptyString(course.Semester, "default")
	return upsertCourseClassRecord(db, course, teacherID, platformClassPayload{
		PlatformID: course.PlatformID,
		ExternalID: fmt.Sprintf("%s_%s_default", course.ExternalID, semester),
		ClassName:  firstNonEmptyString(course.Title, course.ExternalID) + "默认班级",
		ClassCode:  course.Code,
		Semester:   course.Semester,
	})
}

func upsertEnrollmentRecord(db *gorm.DB, platformID, externalID, teachingCourseID, courseClassID, userID, role, status string) error {
	enrollment := model.CourseEnrollment{}
	err := db.Where("teaching_course_id = ? AND course_class_id = ? AND user_id = ?", teachingCourseID, courseClassID, userID).First(&enrollment).Error
	if err == nil {
		return db.Model(&enrollment).Updates(map[string]any{"platform_id": platformID, "external_id": externalID, "role": role, "status": firstNonEmptyString(status, "active")}).Error
	}
	now := time.Now()
	return db.Create(&model.CourseEnrollment{
		PlatformID:       platformID,
		ExternalID:       externalID,
		TeachingCourseID: teachingCourseID,
		CourseClassID:    courseClassID,
		UserID:           userID,
		Role:             role,
		Status:           firstNonEmptyString(status, "active"),
		EnrolledAt:       &now,
	}).Error
}

func upsertCourseClassRecord(db *gorm.DB, course model.TeachingCourse, teacherID string, payload platformClassPayload) (model.CourseClass, error) {
	payload.ExternalID = firstNonEmptyString(payload.ExternalID, fmt.Sprintf("%s_%s_default", course.ExternalID, firstNonEmptyString(payload.Semester, "default")))
	payload.ClassName = firstNonEmptyString(payload.ClassName, firstNonEmptyString(course.Title, course.ExternalID)+"默认班级")
	payload.ClassCode = firstNonEmptyString(payload.ClassCode, course.Code)
	payload.Semester = firstNonEmptyString(payload.Semester, course.Semester)
	classRecord := model.CourseClass{}
	err := db.Where("external_id = ?", payload.ExternalID).First(&classRecord).Error
	updates := map[string]any{
		"platform_id":        payload.PlatformID,
		"teaching_course_id": course.ID,
		"teacher_id":         teacherID,
		"class_name":         payload.ClassName,
		"class_code":         payload.ClassCode,
		"semester":           payload.Semester,
		"grade":              payload.Grade,
		"major":              payload.Major,
		"capacity":           payload.Capacity,
		"status":             "active",
	}
	if err == nil {
		if updateErr := db.Model(&classRecord).Updates(updates).Error; updateErr != nil {
			return classRecord, updateErr
		}
		_ = db.First(&classRecord, "id = ?", classRecord.ID).Error
		return classRecord, nil
	}
	classRecord = model.CourseClass{
		PlatformID:       payload.PlatformID,
		ExternalID:       payload.ExternalID,
		TeachingCourseID: course.ID,
		TeacherID:        teacherID,
		ClassName:        payload.ClassName,
		ClassCode:        payload.ClassCode,
		Semester:         payload.Semester,
		Grade:            payload.Grade,
		Major:            payload.Major,
		Capacity:         payload.Capacity,
		Status:           "active",
	}
	return classRecord, db.Create(&classRecord).Error
}

func buildCourseClassPayloads(platformID string, courseInfo map[string]any, course model.TeachingCourse) []platformClassPayload {
	rawClasses := toObjectSlice(findValue(courseInfo, "classList", "classes", "classInfo"))
	result := make([]platformClassPayload, 0, len(rawClasses))
	for _, raw := range rawClasses {
		classInfo := asNormalizedMap(raw)
		result = append(result, platformClassPayload{
			PlatformID: platformID,
			ExternalID: stringValue(findValue(classInfo, "classId", "externalId", "id")),
			ClassName:  stringValue(findValue(classInfo, "className", "name")),
			ClassCode:  stringValue(findValue(classInfo, "classCode", "code")),
			Semester:   firstNonEmptyString(stringValue(findValue(classInfo, "term", "semester")), course.Semester),
			Grade:      stringValue(findValue(classInfo, "grade")),
			Major:      stringValue(findValue(classInfo, "major")),
			Capacity:   intValue(findValue(classInfo, "capacity", "classSize")),
		})
	}
	if len(result) > 0 {
		return result
	}
	return []platformClassPayload{{
		PlatformID: platformID,
		ExternalID: fmt.Sprintf("%s_%s_default", course.ExternalID, firstNonEmptyString(course.Semester, "default")),
		ClassName:  firstNonEmptyString(course.Title, course.ExternalID) + "默认班级",
		ClassCode:  course.Code,
		Semester:   course.Semester,
	}}
}

func buildUserCourseRefs(userInfo map[string]any, defaultClassExternalID, defaultClassName, defaultRole string) []platformCourseRef {
	refs := make([]platformCourseRef, 0)
	for _, item := range toSlice(findValue(userInfo, "relatedCourseIds", "courseIds", "teachingCourseIds")) {
		switch typed := item.(type) {
		case string:
			courseID := strings.TrimSpace(typed)
			if courseID != "" {
				refs = append(refs, platformCourseRef{CourseExternalID: courseID, ClassExternalID: defaultClassExternalID, ClassName: defaultClassName, Role: defaultRole, Status: "active"})
			}
		default:
			value := asNormalizedMap(typed)
			courseID := stringValue(findValue(value, "courseId", "teachingCourseId", "id", "externalId"))
			if courseID == "" {
				continue
			}
			refs = append(refs, platformCourseRef{
				ExternalID:       stringValue(findValue(value, "enrollmentId", "externalEnrollmentId")),
				CourseExternalID: courseID,
				ClassExternalID:  firstNonEmptyString(stringValue(findValue(value, "classId", "classCode")), defaultClassExternalID),
				ClassName:        firstNonEmptyString(stringValue(findValue(value, "className")), defaultClassName),
				Role:             firstNonEmptyString(stringValue(findValue(value, "role")), defaultRole),
				Status:           firstNonEmptyString(stringValue(findValue(value, "status")), "active"),
			})
		}
	}
	return refs
}

func asNormalizedMap(value any) map[string]any {
	result := make(map[string]any)
	raw, ok := value.(map[string]any)
	if !ok {
		return result
	}
	for key, item := range raw {
		result[normalizeSyncKey(key)] = item
	}
	return result
}

func findValue(data map[string]any, keys ...string) any {
	for _, key := range keys {
		if value, ok := data[normalizeSyncKey(key)]; ok {
			return value
		}
	}
	return nil
}

func findTeachingCourseRecord(db *gorm.DB, courseID string) (model.TeachingCourse, error) {
	courseID = strings.TrimSpace(courseID)
	if courseID == "" {
		return model.TeachingCourse{}, fmt.Errorf("courseId 不能为空")
	}
	var course model.TeachingCourse
	if err := db.Where("id = ? OR external_id = ?", courseID, courseID).First(&course).Error; err != nil {
		return course, err
	}
	return course, nil
}

func findCourseClassRecord(db *gorm.DB, classID string) (model.CourseClass, error) {
	classID = strings.TrimSpace(classID)
	if classID == "" {
		return model.CourseClass{}, fmt.Errorf("classId 不能为空")
	}
	var classRecord model.CourseClass
	if err := db.Where("id = ? OR external_id = ?", classID, classID).First(&classRecord).Error; err != nil {
		return classRecord, err
	}
	return classRecord, nil
}

func findEnrollmentRecord(db *gorm.DB, enrollmentID string) (model.CourseEnrollment, error) {
	enrollmentID = strings.TrimSpace(enrollmentID)
	if enrollmentID == "" {
		return model.CourseEnrollment{}, fmt.Errorf("enrollmentId 不能为空")
	}
	var enrollment model.CourseEnrollment
	if err := db.Where("id = ? OR external_id = ?", enrollmentID, enrollmentID).First(&enrollment).Error; err != nil {
		return enrollment, err
	}
	return enrollment, nil
}

func resolvePlatformUserID(db *gorm.DB, userRef string) (string, error) {
	userRef = strings.TrimSpace(userRef)
	if userRef == "" {
		return "", nil
	}
	var user model.PlatformUser
	if err := db.Where("id = ? OR external_id = ?", userRef, userRef).First(&user).Error; err != nil {
		return "", fmt.Errorf("teacherId/userId 对应的平台用户不存在")
	}
	return user.ID, nil
}

func hasAnyNormalizedKey(data map[string]any, keys ...string) bool {
	for _, key := range keys {
		if _, ok := data[normalizeSyncKey(key)]; ok {
			return true
		}
	}
	return false
}

func normalizePlatformLifecycleStatus(value, fallback string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if value == "" {
		return fallback
	}
	switch value {
	case "draft", "active", "archived", "inactive", "completed":
		return value
	default:
		return value
	}
}

func normalizePlatformRole(value, fallback string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if value == "" {
		return fallback
	}
	switch value {
	case "student", "teacher", "assistant", "ta", "observer":
		return value
	default:
		return value
	}
}

func optionalTimeValue(value any) (*time.Time, error) {
	text := stringValue(value)
	if text == "" {
		return nil, nil
	}
	layouts := []string{time.RFC3339, "2006-01-02 15:04:05", "2006-01-02"}
	for _, layout := range layouts {
		if parsed, err := time.Parse(layout, text); err == nil {
			return &parsed, nil
		}
	}
	return nil, fmt.Errorf("invalid time")
}

func normalizeSyncKey(value string) string {
	replacer := strings.NewReplacer(" ", "", "_", "", "-", "", ".", "")
	return strings.ToLower(replacer.Replace(strings.TrimSpace(value)))
}

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	case fmt.Stringer:
		return strings.TrimSpace(typed.String())
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case int:
		return strconv.Itoa(typed)
	case int64:
		return strconv.FormatInt(typed, 10)
	default:
		return strings.TrimSpace(fmt.Sprintf("%v", value))
	}
}

func intValue(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case string:
		parsed, _ := strconv.Atoi(strings.TrimSpace(typed))
		return parsed
	default:
		return 0
	}
}

func numberValue(value any) float64 {
	switch typed := value.(type) {
	case float64:
		return typed
	case float32:
		return float64(typed)
	case int:
		return float64(typed)
	case int64:
		return float64(typed)
	case string:
		parsed, _ := strconv.ParseFloat(strings.TrimSpace(typed), 64)
		return parsed
	default:
		return 0
	}
}

func toSlice(value any) []any {
	if value == nil {
		return nil
	}
	if items, ok := value.([]any); ok {
		return items
	}
	return nil
}

func toObjectSlice(value any) []any {
	if value == nil {
		return nil
	}
	if items := toSlice(value); len(items) > 0 {
		return items
	}
	if _, ok := value.(map[string]any); ok {
		return []any{value}
	}
	return nil
}

func toStringSlice(value any) []string {
	items := toSlice(value)
	result := make([]string, 0, len(items))
	for _, item := range items {
		text := stringValue(item)
		if text != "" {
			result = append(result, text)
		}
	}
	return result
}

func firstNonEmptyString(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}
