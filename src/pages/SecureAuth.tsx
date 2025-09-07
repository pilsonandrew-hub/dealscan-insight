/**
 * Secure Authentication Pages
 * Implements login/signup with comprehensive security measures
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/ModernAuthContext';
import { logger } from '@/core/UnifiedLogger';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Eye, EyeOff, Shield, Lock, UserPlus, LogIn } from 'lucide-react';

export function AuthPage() {
  const { signIn, signUp, user, loading } = useAuth();
  const isAuthenticated = !!user;
  const navigate = useNavigate();
  const location = useLocation();
  
  const [activeTab, setActiveTab] = useState<'signin' | 'signup' | 'reset'>('signin');
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    displayName: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<{ [key: string]: string[] }>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated && !loading) {
      const redirectTo = (location.state as any)?.from?.pathname || '/';
      navigate(redirectTo, { replace: true });
    }
  }, [isAuthenticated, loading, navigate, location]);

  const validateForm = () => {
    const newErrors: { [key: string]: string[] } = {};

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!formData.email) {
      newErrors.email = ['Email is required'];
    } else if (!emailRegex.test(formData.email)) {
      newErrors.email = ['Invalid email format'];
    }

    // Password validation
    if (activeTab !== 'reset') {
      if (!formData.password) {
        newErrors.password = ['Password is required'];
      } else if (formData.password.length < 8) {
        newErrors.password = ['Password must be at least 8 characters'];
      } else if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(formData.password)) {
        newErrors.password = ['Password must contain uppercase, lowercase, and number'];
      }

      // Confirm password validation for signup
      if (activeTab === 'signup') {
        if (formData.password !== formData.confirmPassword) {
          newErrors.confirmPassword = ['Passwords do not match'];
        }

        // Display name validation
        if (!formData.displayName) {
          newErrors.displayName = ['Display name is required'];
        } else if (formData.displayName.length < 2) {
          newErrors.displayName = ['Display name must be at least 2 characters'];
        } else if (formData.displayName.length > 50) {
          newErrors.displayName = ['Display name must be less than 50 characters'];
        }
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);
    setMessage(null);

    try {
      let result;

      switch (activeTab) {
        case 'signin':
          result = await signIn(formData.email, formData.password);
          if (result.error) {
            if (result.error.message.includes('Invalid login credentials')) {
              setMessage({ type: 'error', text: 'Invalid email or password' });
            } else {
              setMessage({ type: 'error', text: result.error.message });
            }
          } else {
            logger.setContext('auth').info('User signed in successfully');
            // Navigation handled by useEffect
          }
          break;

        case 'signup':
          result = await signUp(formData.email, formData.password);
          if (result.error) {
            if (result.error.message.includes('User already registered')) {
              setMessage({ type: 'error', text: 'Account already exists. Please sign in instead.' });
            } else {
              setMessage({ type: 'error', text: result.error.message });
            }
          } else {
            setMessage({ 
              type: 'success', 
              text: 'Account created! Please check your email to verify your account.' 
            });
          }
          break;

        case 'reset':
          // For now, just show a message (can implement later if needed)
          setMessage({ 
            type: 'success', 
            text: 'Password reset functionality will be available soon.' 
          });
          break;
      }
    } catch (error) {
      logger.setContext('auth').error('Auth form error', error);
      setMessage({ type: 'error', text: 'An unexpected error occurred' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    
    // Clear errors for this field
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: [] }));
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-muted flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Shield className="h-6 w-6 text-primary" />
          </div>
          <CardTitle className="text-2xl font-bold">DealerScope</CardTitle>
          <CardDescription>
            Secure access to vehicle arbitrage platform
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)} className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="signin" className="text-xs">
                <LogIn className="h-4 w-4 mr-1" />
                Sign In
              </TabsTrigger>
              <TabsTrigger value="signup" className="text-xs">
                <UserPlus className="h-4 w-4 mr-1" />
                Sign Up
              </TabsTrigger>
              <TabsTrigger value="reset" className="text-xs">
                <Lock className="h-4 w-4 mr-1" />
                Reset
              </TabsTrigger>
            </TabsList>

            {message && (
              <Alert className={`mt-4 ${message.type === 'error' ? 'border-destructive' : 'border-success'}`}>
                <AlertDescription className={message.type === 'error' ? 'text-destructive' : 'text-success'}>
                  {message.text}
                </AlertDescription>
              </Alert>
            )}

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <TabsContent value="signin" className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={formData.email}
                    onChange={(e) => handleInputChange('email', e.target.value)}
                    placeholder="Enter your email"
                    disabled={isSubmitting}
                  />
                  {errors.email && (
                    <p className="text-sm text-destructive">{errors.email[0]}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <Input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      value={formData.password}
                      onChange={(e) => handleInputChange('password', e.target.value)}
                      placeholder="Enter your password"
                      disabled={isSubmitting}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </Button>
                  </div>
                  {errors.password && (
                    <p className="text-sm text-destructive">{errors.password[0]}</p>
                  )}
                </div>

                <Button type="submit" className="w-full" disabled={isSubmitting}>
                  {isSubmitting ? 'Signing in...' : 'Sign In'}
                </Button>
              </TabsContent>

              <TabsContent value="signup" className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="displayName">Display Name</Label>
                  <Input
                    id="displayName"
                    type="text"
                    value={formData.displayName}
                    onChange={(e) => handleInputChange('displayName', e.target.value)}
                    placeholder="Your display name"
                    disabled={isSubmitting}
                  />
                  {errors.displayName && (
                    <p className="text-sm text-destructive">{errors.displayName[0]}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={formData.email}
                    onChange={(e) => handleInputChange('email', e.target.value)}
                    placeholder="Enter your email"
                    disabled={isSubmitting}
                  />
                  {errors.email && (
                    <p className="text-sm text-destructive">{errors.email[0]}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <Input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      value={formData.password}
                      onChange={(e) => handleInputChange('password', e.target.value)}
                      placeholder="Create a strong password"
                      disabled={isSubmitting}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </Button>
                  </div>
                  {errors.password && (
                    <p className="text-sm text-destructive">{errors.password[0]}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="confirmPassword">Confirm Password</Label>
                  <Input
                    id="confirmPassword"
                    type="password"
                    value={formData.confirmPassword}
                    onChange={(e) => handleInputChange('confirmPassword', e.target.value)}
                    placeholder="Confirm your password"
                    disabled={isSubmitting}
                  />
                  {errors.confirmPassword && (
                    <p className="text-sm text-destructive">{errors.confirmPassword[0]}</p>
                  )}
                </div>

                <Button type="submit" className="w-full" disabled={isSubmitting}>
                  {isSubmitting ? 'Creating account...' : 'Create Account'}
                </Button>
              </TabsContent>

              <TabsContent value="reset" className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={formData.email}
                    onChange={(e) => handleInputChange('email', e.target.value)}
                    placeholder="Enter your email"
                    disabled={isSubmitting}
                  />
                  {errors.email && (
                    <p className="text-sm text-destructive">{errors.email[0]}</p>
                  )}
                </div>

                <Button type="submit" className="w-full" disabled={isSubmitting}>
                  {isSubmitting ? 'Sending reset email...' : 'Reset Password'}
                </Button>
              </TabsContent>
            </form>
          </Tabs>

          <div className="mt-6 text-center text-sm text-muted-foreground">
            <p>By signing in, you agree to our security policies</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}