import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { authAPI } from '@/lib/api'
import { toast } from '@/hooks/use-toast'

interface User {
  id: number
  username: string
  email: string
  is_admin: boolean
  is_active: boolean
  totp_enabled: boolean
  email_verified: boolean
  created_at: string
  last_login?: string
}

interface AuthContextType {
  user: User | null
  isLoading: boolean
  login: (credentials: { username: string; password: string; totp_code?: string }) => Promise<boolean>
  register: (userData: { username: string; email: string; password: string }) => Promise<boolean>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Check for existing auth on mount
  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) {
      refreshUser()
    } else {
      setIsLoading(false)
    }
  }, [])

  const login = async (credentials: { username: string; password: string; totp_code?: string }): Promise<boolean> => {
    try {
      const response = await authAPI.login(credentials)
      const { access_token, refresh_token, user: userData } = response.data

      localStorage.setItem('access_token', access_token)
      localStorage.setItem('refresh_token', refresh_token)
      setUser(userData)

      toast({
        title: "Welcome back!",
        description: `Hello ${userData.username}`,
      })

      return true
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Login failed'
      toast({
        title: "Login Failed",
        description: message,
        variant: "destructive",
      })
      return false
    }
  }

  const register = async (userData: { username: string; email: string; password: string }): Promise<boolean> => {
    try {
      const response = await authAPI.register(userData)
      const { access_token, refresh_token, user: newUser } = response.data

      localStorage.setItem('access_token', access_token)
      localStorage.setItem('refresh_token', refresh_token)
      setUser(newUser)

      toast({
        title: "Welcome to DealerScope!",
        description: "Your account has been created successfully.",
      })

      return true
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Registration failed'
      toast({
        title: "Registration Failed",
        description: message,
        variant: "destructive",
      })
      return false
    }
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setUser(null)
    
    // Call logout endpoint (fire and forget)
    authAPI.logout().catch(() => {})
    
    toast({
      title: "Logged Out",
      description: "You have been logged out successfully.",
    })
  }

  const refreshUser = async () => {
    try {
      const response = await authAPI.getCurrentUser()
      setUser(response.data)
    } catch (error) {
      // Token is invalid, clear auth
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }

  const value: AuthContextType = {
    user,
    isLoading,
    login,
    register,
    logout,
    refreshUser,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}