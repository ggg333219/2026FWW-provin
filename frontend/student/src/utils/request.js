/**
 * 统一请求封装，适配 API v2.0 规范
 */
import { ElMessage } from 'element-plus'
import { API_BASE } from '../config/api'

// 基础配置
const BASE_URL = `${API_BASE}/api/v1`
const TOKEN = localStorage.getItem('student-token') || 'default-token-2025'

/**
 * 通用请求方法
 * @param {string} url 接口路径（无需 /api/v1 前缀）
 * @param {Object} options 请求配置
 * @returns {Promise} 响应数据
 */
export const request = async (url, options = {}) => {
  let fullUrl = `${BASE_URL}${url}`
  const defaultHeaders = {
    'Content-Type': 'application/json; charset=utf-8',
    'Authorization': `Bearer ${TOKEN}`
  }

  const fetchOptions = {
    method: options.method || 'GET',
    headers: { ...defaultHeaders, ...options.headers },
  }

  // POST/PUT 请求处理
  if (['POST', 'PUT', 'PATCH'].includes(fetchOptions.method) && options.data) {
    if (options.data instanceof FormData) {
      delete fetchOptions.headers['Content-Type']
      fetchOptions.body = options.data
    } else {
      fetchOptions.body = JSON.stringify(options.data)
    }
  }

  // GET 请求处理参数
  if (fetchOptions.method === 'GET' && options.params) {
    const params = new URLSearchParams(options.params)
    fullUrl += `?${params.toString()}`
  }

  try {
    const response = await fetch(fullUrl, fetchOptions)
    const result = await response.json()

    if (result.code !== 200) {
      throw new Error(result.message || `请求失败（${result.code}）`)
    }

    if (options.showSuccess) {
      ElMessage.success(result.message || '操作成功')
    }

    return result.data
  } catch (error) {
    ElMessage.error(error.message || '网络异常，请重试')
    throw error
  }
}

// 快捷请求方法
export const get = (url, params, options = {}) => request(url, { method: 'GET', params, ...options })
export const post = (url, data, options = {}) => request(url, { method: 'POST', data, ...options })
export const put = (url, data, options = {}) => request(url, { method: 'PUT', data, ...options })
export const del = (url, options = {}) => request(url, { method: 'DELETE', ...options })