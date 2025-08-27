import React, { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/UnifiedAuthContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Loader2, Eye, EyeOff } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
  totp_code: z.string().optional(),
})

type LoginForm = z.infer<typeof loginSchema>

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [needsTOTP, setNeedsTOTP] = useState(false)
  const [error, setError] = useState('')

  const {
    register,
    handleSubmit,
    formState: { errors },
    setError: setFormError,
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data: LoginForm) => {
    setIsLoading(true)
    setError('')

    try {
      const success = await login(data)
      if (success) {
        const from = location.state?.from?.pathname || '/'
        navigate(from, { replace: true })
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Login failed'
      
      if (errorMessage.includes('TOTP code required')) {
        setNeedsTOTP(true)
        setError('Please enter your 2FA code')
      } else if (errorMessage.includes('Invalid TOTP')) {
        setFormError('totp_code', { message: 'Invalid 2FA code' })
      } else {
        setError(errorMessage)
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h1 className="text-center text-3xl font-bold text-gray-900">DealerScope</h1>
          <h2 className="mt-6 text-center text-2xl font-semibold text-gray-900">
            Sign in to your account
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Or{' '}
            <Link
              to="/register"
              className="font-medium text-primary hover:text-primary/80"
            >
              create a new account
            </Link>
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Welcome back</CardTitle>
            <CardDescription>
              Enter your credentials to access your dashboard
            </CardDescription>
          </CardHeader>

          <form onSubmit={handleSubmit(onSubmit)}>
            <CardContent className="space-y-4">
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <div className="space-y-2">
                <Label htmlFor="username">Username or Email</Label>
                <Input
                  id="username"
                  type="text"
                  autoComplete="username"
                  {...register('username')}
                  className={errors.username ? 'border-destructive' : ''}
                />
                {errors.username && (
                  <p className="text-sm text-destructive">{errors.username.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    {...register('password')}
                    className={errors.password ? 'border-destructive pr-10' : 'pr-10'}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                {errors.password && (
                  <p className="text-sm text-destructive">{errors.password.message}</p>
                )}
              </div>

              {needsTOTP && (
                <div className="space-y-2">
                  <Label htmlFor="totp_code">2FA Code</Label>
                  <Input
                    id="totp_code"
                    type="text"
                    placeholder="Enter 6-digit code"
                    maxLength={6}
                    {...register('totp_code')}
                    className={errors.totp_code ? 'border-destructive' : ''}
                  />
                  {errors.totp_code && (
                    <p className="text-sm text-destructive">{errors.totp_code.message}</p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    Enter the 6-digit code from your authenticator app
                  </p>
                </div>
              )}
            </CardContent>

            <CardFooter>
              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Sign In
              </Button>
            </CardFooter>
          </form>
        </Card>

        <div className="text-center">
          <p className="text-sm text-gray-600">
            Intelligent Vehicle Arbitrage Platform
          </p>
        </div>
      </div>
    </div>
  )
}