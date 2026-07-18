package handler

import (
	"github.com/gin-gonic/gin"

	"smart-teaching-backend/pkg/apiresp"
)

// Platform V1：标准 REST 响应格式（code/message/data），无需 OpenAPI 签名

func (h *CompatibilityHandler) PlatformV1Overview(c *gin.Context) {
	data, err := platformOverview(h.db)
	if err != nil {
		apiresp.Internal(c, "平台总览获取失败", "")
		return
	}
	apiresp.OK(c, "请求成功", data)
}

func (h *CompatibilityHandler) PlatformV1Users(c *gin.Context) {
	data, err := listPlatformUsers(h.db, platformListOptions{
		Page:       intValue(c.Query("page")),
		PageSize:   intValue(c.Query("pageSize")),
		PlatformID: c.Query("platformId"),
		Role:       c.Query("role"),
		OrgCode:    c.Query("orgCode"),
		Keyword:    c.Query("keyword"),
	})
	if err != nil {
		apiresp.Internal(c, "平台用户列表获取失败", "")
		return
	}
	apiresp.OK(c, "请求成功", data)
}

func (h *CompatibilityHandler) PlatformV1UserDetail(c *gin.Context) {
	data, err := platformUserDetail(h.db, c.Param("userId"))
	if err != nil {
		apiresp.NotFound(c, "平台用户详情获取失败", "")
		return
	}
	apiresp.OK(c, "请求成功", data)
}

func (h *CompatibilityHandler) PlatformV1SyncUser(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}
	data, err := syncUserFromPlatform(h.db, req)
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "用户同步成功", data)
}

func (h *CompatibilityHandler) PlatformV1Courses(c *gin.Context) {
	data, err := listPlatformCourses(h.db, platformListOptions{
		Page:       intValue(c.Query("page")),
		PageSize:   intValue(c.Query("pageSize")),
		PlatformID: c.Query("platformId"),
		Status:     c.Query("status"),
		OrgCode:    c.Query("orgCode"),
		UserID:     c.Query("teacherId"),
		Keyword:    c.Query("keyword"),
	})
	if err != nil {
		apiresp.Internal(c, "平台课程列表获取失败", "")
		return
	}
	apiresp.OK(c, "请求成功", data)
}

func (h *CompatibilityHandler) PlatformV1CreateCourse(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}
	data, err := createPlatformCourse(h.db, req)
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "课程创建成功", data)
}

func (h *CompatibilityHandler) PlatformV1CourseDetail(c *gin.Context) {
	data, err := platformCourseDetail(h.db, c.Param("courseId"))
	if err != nil {
		apiresp.NotFound(c, "平台课程详情获取失败", "")
		return
	}
	apiresp.OK(c, "请求成功", data)
}

func (h *CompatibilityHandler) PlatformV1UpdateCourse(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}
	data, err := updatePlatformCourse(h.db, c.Param("courseId"), req)
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "课程更新成功", data)
}

func (h *CompatibilityHandler) PlatformV1DeleteCourse(c *gin.Context) {
	data, err := deletePlatformCourse(h.db, c.Param("courseId"))
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "课程删除成功", data)
}

func (h *CompatibilityHandler) PlatformV1SyncCourse(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}
	data, err := syncCourseFromPlatform(h.db, req)
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "课程同步成功", data)
}

func (h *CompatibilityHandler) PlatformV1Classes(c *gin.Context) {
	data, err := listPlatformClasses(h.db, platformListOptions{
		Page:       intValue(c.Query("page")),
		PageSize:   intValue(c.Query("pageSize")),
		PlatformID: c.Query("platformId"),
		Status:     c.Query("status"),
		CourseID:   c.Query("courseId"),
		UserID:     c.Query("teacherId"),
		Keyword:    c.Query("keyword"),
	})
	if err != nil {
		apiresp.Internal(c, "平台班级列表获取失败", "")
		return
	}
	apiresp.OK(c, "请求成功", data)
}

func (h *CompatibilityHandler) PlatformV1CreateClass(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}
	data, err := createPlatformClass(h.db, req)
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "班级创建成功", data)
}

func (h *CompatibilityHandler) PlatformV1ClassDetail(c *gin.Context) {
	data, err := platformClassDetail(h.db, c.Param("classId"))
	if err != nil {
		apiresp.NotFound(c, "平台班级详情获取失败", "")
		return
	}
	apiresp.OK(c, "请求成功", data)
}

func (h *CompatibilityHandler) PlatformV1UpdateClass(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}
	data, err := updatePlatformClass(h.db, c.Param("classId"), req)
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "班级更新成功", data)
}

func (h *CompatibilityHandler) PlatformV1DeleteClass(c *gin.Context) {
	data, err := deletePlatformClass(h.db, c.Param("classId"))
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "班级删除成功", data)
}

func (h *CompatibilityHandler) PlatformV1Enrollments(c *gin.Context) {
	data, err := listPlatformEnrollments(h.db, platformListOptions{
		Page:       intValue(c.Query("page")),
		PageSize:   intValue(c.Query("pageSize")),
		PlatformID: c.Query("platformId"),
		CourseID:   c.Query("courseId"),
		ClassID:    c.Query("classId"),
		UserID:     c.Query("userId"),
		Role:       c.Query("role"),
		Status:     c.Query("status"),
		Keyword:    c.Query("keyword"),
	})
	if err != nil {
		apiresp.Internal(c, "平台选课列表获取失败", "")
		return
	}
	apiresp.OK(c, "请求成功", data)
}

func (h *CompatibilityHandler) PlatformV1CreateEnrollment(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}
	data, err := createPlatformEnrollment(h.db, req)
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "选课创建成功", data)
}

func (h *CompatibilityHandler) PlatformV1EnrollmentDetail(c *gin.Context) {
	data, err := platformEnrollmentDetail(h.db, c.Param("enrollmentId"))
	if err != nil {
		apiresp.NotFound(c, "平台选课详情获取失败", "")
		return
	}
	apiresp.OK(c, "请求成功", data)
}

func (h *CompatibilityHandler) PlatformV1UpdateEnrollment(c *gin.Context) {
	var req map[string]any
	if err := c.ShouldBindJSON(&req); err != nil {
		apiresp.BadRequest(c, "参数错误", "")
		return
	}
	data, err := updatePlatformEnrollment(h.db, c.Param("enrollmentId"), req)
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "选课更新成功", data)
}

func (h *CompatibilityHandler) PlatformV1DeleteEnrollment(c *gin.Context) {
	data, err := deletePlatformEnrollment(h.db, c.Param("enrollmentId"))
	if err != nil {
		apiresp.BadRequest(c, err.Error(), "")
		return
	}
	apiresp.OK(c, "选课删除成功", data)
}
