import axios, { AxiosError, AxiosResponse } from 'axios'
import { toast } from '@/hooks/use-toast'

// API Configuration
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Create axios instance
export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for error handling
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as any

    // Handle 401 errors (token expired)
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken
          })
          
          const { access_token, refresh_token: newRefreshToken } = response.data
          localStorage.setItem('access_token', access_token)
          localStorage.setItem('refresh_token', newRefreshToken)
          
          // Retry original request
          originalRequest.headers.Authorization = `Bearer ${access_token}`
          return api(originalRequest)
        } catch (refreshError) {
          // Refresh failed, redirect to login
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
          return Promise.reject(refreshError)
        }
      } else {
        // No refresh token, redirect to login
        window.location.href = '/login'
      }
    }

    // Handle other errors
    if (error.response?.status === 429) {
      toast({
        title: "Rate Limit Exceeded",
        description: "Too many requests. Please try again later.",
        variant: "destructive",
      })
    } else if (error.response?.status >= 500) {
      toast({
        title: "Server Error",
        description: "Something went wrong on our end. Please try again.",
        variant: "destructive",
      })
    }

    return Promise.reject(error)
  }
)

// API Functions
export const authAPI = {
  login: (credentials: { username: string; password: string; totp_code?: string }) =>
    api.post('/auth/login', credentials),
  
  register: (userData: { username: string; email: string; password: string }) =>
    api.post('/auth/register', userData),
  
  logout: () => api.post('/auth/logout'),
  
  refreshToken: (refreshToken: string) =>
    api.post('/auth/refresh', { refresh_token: refreshToken }),
  
  getCurrentUser: () => api.get('/auth/me'),
  
  enableTOTP: () => api.post('/auth/enable-totp'),
  
  verifyTOTP: (code: string) => api.post('/auth/verify-totp', { totp_code: code }),
  
  changePassword: (data: { current_password: string; new_password: string }) =>
    api.post('/auth/change-password', data),
}

export const vehiclesAPI = {
  getVehicles: (params?: any) => api.get('/vehicles', { params }),
  getVehicle: (id: number) => api.get(`/vehicles/${id}`),
  getStats: () => api.get('/vehicles/stats/summary'),
}

export const opportunitiesAPI = {
  getOpportunities: (params?: any) => api.get('/opportunities', { params }),
  getOpportunity: (id: number) => api.get(`/opportunities/${id}`),
  saveOpportunity: (id: number) => api.post(`/opportunities/${id}/save`),
  ignoreOpportunity: (id: number) => api.post(`/opportunities/${id}/ignore`),
  getSavedOpportunities: (params?: any) => api.get('/opportunities/saved/list', { params }),
  rescoreAll: () => api.post('/opportunities/rescore-all'),
}

export const uploadAPI = {
  uploadCSV: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/upload/csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  getTemplate: () => api.get('/upload/template', { responseType: 'blob' }),
  getHistory: () => api.get('/upload/history'),
}

export const mlAPI = {
  predictPrice: (data: any) => api.post('/ml/predict-price', data),
  batchPredict: (data: any) => api.post('/ml/batch-predict', data),
  scoreOpportunity: (data: any) => api.post('/ml/score-opportunity', data),
  getModelStatus: () => api.get('/ml/model-status'),
  getFeatureImportance: (modelType: string) => api.get(`/ml/feature-importance/${modelType}`),
  explainPrediction: (data: any) => api.post('/ml/explain-prediction', data),
  retrainModels: () => api.post('/ml/retrain-models'),
}

export const adminAPI = {
  getStats: () => api.get('/admin/stats'),
  triggerSecurityScan: () => api.post('/admin/security/scan'),
}

export default api