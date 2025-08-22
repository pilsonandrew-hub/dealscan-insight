import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'

// Initialize production logger to override console methods
import '@/utils/productionLogger';

// Initialize secure configuration
import '@/config/secureConfig';

createRoot(document.getElementById("root")!).render(<App />);
