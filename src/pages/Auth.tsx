import React, { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/contexts/ModernAuthContext';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, Eye, EyeOff } from 'lucide-react';

export default function Auth() {
  const { user, signIn, signUp, loading } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    displayName: '',
  });

  // Redirect if already authenticated
  if (user && !loading) {
    return <Navigate to="/" replace />;
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }));
    setError(null);
  };

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    
    console.log('🔐 Attempting sign in for:', formData.email);
    
    const { error } = await signIn(formData.email, formData.password);
    
    if (error) {
      console.error('❌ Sign in failed:', error);
      setError(error.message || 'Failed to sign in. Please check your credentials.');
    } else {
      console.log('✅ Sign in successful');
    }
    
    setIsLoading(false);
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    
    const { error } = await signUp(formData.email, formData.password);
    
    if (error) {
      setError(error.message);
    } else {
      setError('Check your email for the confirmation link!');
    }
    
    setIsLoading(false);
  };

  const testSupabaseConnection = async () => {
    try {
      console.log('🧪 Testing Supabase connection...');
      console.log('🔗 Supabase URL:', 'https://lgpugcflvrqhslfnsjfh.supabase.co');
      console.log('🔗 Current window location:', window.location.origin);
      
      // Test the new auth debugging function
      const { data: authTest, error: authError } = await supabase.rpc('test_auth');
      
      if (authError) {
        console.error('🧪 Auth test error:', authError);
        setError(`Auth test failed: ${authError.message}`);
      } else {
        console.log('🧪 Auth test result:', authTest);
        setError(`✅ Connection working! Current auth state: ${JSON.stringify(authTest, null, 2)}`);
      }
      
    } catch (error) {
      console.error('🧪 Supabase connection test failed:', error);
      setError(`Connection test failed: ${error}`);
    }
  };

  const createTestAccount = async () => {
    const testEmail = 'test@dealerscope.com';
    const testPassword = 'testpass123';
    
    console.log('🔨 Creating test account...');
    setError('Creating test account...');
    
    const { error } = await signUp(testEmail, testPassword);
    
    if (error) {
      setError(`Test account creation failed: ${error.message}`);
    } else {
      setError('✅ Test account created! You can now sign in with test@dealerscope.com / testpass123');
      setFormData({ ...formData, email: testEmail, password: testPassword });
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background via-background to-primary/5 p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">DealerScope</h1>
          <p className="text-muted-foreground">Professional vehicle arbitrage analysis platform</p>
        </div>
        
        <Card className="shadow-lg border-0 bg-card/95 backdrop-blur-sm">
          <CardHeader className="space-y-1">
            <CardTitle className="text-2xl text-center text-foreground">Welcome</CardTitle>
            <CardDescription className="text-center text-muted-foreground">
              Sign in to access your deal opportunities
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="signin" className="w-full">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="signin">Sign In</TabsTrigger>
                <TabsTrigger value="signup">Sign Up</TabsTrigger>
              </TabsList>
              
              <TabsContent value="signin" className="space-y-4">
                <form onSubmit={handleSignIn} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="signin-email">Email</Label>
                    <Input
                      id="signin-email"
                      name="email"
                      type="email"
                      placeholder="Enter your email"
                      value={formData.email}
                      onChange={handleInputChange}
                      required
                      disabled={isLoading}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="signin-password">Password</Label>
                    <div className="relative">
                      <Input
                        id="signin-password"
                        name="password"
                        type={showPassword ? "text" : "password"}
                        placeholder="Enter your password"
                        value={formData.password}
                        onChange={handleInputChange}
                        required
                        disabled={isLoading}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-0 top-0 h-full px-3 py-2"
                        onClick={() => setShowPassword(!showPassword)}
                        disabled={isLoading}
                      >
                        {showPassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                  <Button type="submit" className="w-full" disabled={isLoading}>
                    {isLoading ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Signing in...
                      </>
                    ) : (
                      'Sign In'
                    )}
                  </Button>
                </form>
              </TabsContent>
              
              <TabsContent value="signup" className="space-y-4">
                <form onSubmit={handleSignUp} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="signup-displayname">Display Name (Optional)</Label>
                    <Input
                      id="signup-displayname"
                      name="displayName"
                      type="text"
                      placeholder="Enter your display name"
                      value={formData.displayName}
                      onChange={handleInputChange}
                      disabled={isLoading}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="signup-email">Email</Label>
                    <Input
                      id="signup-email"
                      name="email"
                      type="email"
                      placeholder="Enter your email"
                      value={formData.email}
                      onChange={handleInputChange}
                      required
                      disabled={isLoading}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="signup-password">Password</Label>
                    <div className="relative">
                      <Input
                        id="signup-password"
                        name="password"
                        type={showPassword ? "text" : "password"}
                        placeholder="Enter your password"
                        value={formData.password}
                        onChange={handleInputChange}
                        required
                        disabled={isLoading}
                        minLength={6}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-0 top-0 h-full px-3 py-2"
                        onClick={() => setShowPassword(!showPassword)}
                        disabled={isLoading}
                      >
                        {showPassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                  <Button type="submit" className="w-full" disabled={isLoading}>
                    {isLoading ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Creating account...
                      </>
                    ) : (
                      'Create Account'
                    )}
                  </Button>
                </form>
              </TabsContent>
            </Tabs>
            
            {error && (
              <Alert className="mt-4">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            
            {/* Debug/Test Connection Buttons */}
            <div className="mt-4 pt-4 border-t border-border space-y-2">
              <Button 
                onClick={testSupabaseConnection} 
                variant="outline" 
                size="sm" 
                className="w-full text-xs"
                disabled={isLoading}
              >
                Test Connection
              </Button>
              <Button 
                onClick={createTestAccount} 
                variant="outline" 
                size="sm" 
                className="w-full text-xs"
                disabled={isLoading}
              >
                Create Test Account
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}