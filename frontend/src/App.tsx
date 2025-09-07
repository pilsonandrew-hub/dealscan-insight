import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from '@/components/ui/toaster'
import { AuthProvider } from '@/contexts/UnifiedAuthContext'
import ProtectedRoute from '@/components/ProtectedRoute'

// Pages
import Login from '@/pages/Login'
import Register from '@/pages/Register'
import Dashboard from '@/pages/Dashboard'
import Opportunities from '@/pages/Opportunities'
import Vehicles from '@/pages/Vehicles'
import Upload from '@/pages/Upload'
import Settings from '@/pages/Settings'
import Admin from '@/pages/Admin'
import NotFound from '@/pages/NotFound'

function App() {
  return (
    <AuthProvider>
      <div className="min-h-screen bg-background">
        <Routes>
          {/* Public routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          
          {/* Protected routes */}
          <Route path="/" element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          } />
          
          <Route path="/opportunities" element={
            <ProtectedRoute>
              <Opportunities />
            </ProtectedRoute>
          } />
          
          <Route path="/vehicles" element={
            <ProtectedRoute>
              <Vehicles />
            </ProtectedRoute>
          } />
          
          <Route path="/upload" element={
            <ProtectedRoute>
              <Upload />
            </ProtectedRoute>
          } />
          
          <Route path="/settings" element={
            <ProtectedRoute>
              <Settings />
            </ProtectedRoute>
          } />
          
          <Route path="/admin" element={
            <ProtectedRoute requireAdmin>
              <Admin />
            </ProtectedRoute>
          } />
          
          {/* Fallback routes */}
          <Route path="/404" element={<NotFound />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Routes>
        
        <Toaster />
      </div>
    </AuthProvider>
  )
}

export default App