# DealerScope AI Evaluation Suite

A comprehensive testing framework that evaluates the completeness and functionality of the DealerScope application against multiple AI models and performance criteria.

## 🚀 Quick Start

```bash
# Make the script executable
chmod +x scripts/run-evaluation.sh

# Run the evaluation suite
./scripts/run-evaluation.sh

# Or run with verbose output
./scripts/run-evaluation.sh --verbose
```

## 📋 What It Tests

### Frontend Functionality
- ✅ Page loading and rendering
- ✅ React component functionality
- ✅ PWA features (manifest, service worker)
- ✅ User interface responsiveness
- ✅ Navigation and routing

### Backend API
- ✅ Health endpoint availability
- ✅ API response times
- ✅ Data processing endpoints
- ✅ Error handling
- ✅ Database connectivity

### Security Compliance
- ✅ Content Security Policy (CSP) headers
- ✅ Input validation and sanitization
- ✅ XSS protection
- ✅ CSRF protection
- ✅ Authentication mechanisms

### Performance Metrics
- ✅ Page load times
- ✅ API response times
- ✅ Bundle size optimization
- ✅ Memory usage
- ✅ Network efficiency

### Data Processing
- ✅ CSV upload and parsing
- ✅ Data validation
- ✅ Arbitrage calculations
- ✅ Market analysis
- ✅ Report generation

### Error Handling
- ✅ Error boundaries
- ✅ Graceful degradation
- ✅ Recovery mechanisms
- ✅ User feedback
- ✅ Logging and monitoring

## 🤖 AI Model Integration

The suite can evaluate your application against multiple AI models:

### OpenAI Models
- GPT-5 (flagship model with superior reasoning)
- GPT-5 Mini (fast and efficient)
- GPT-4.1 (reliable results)
- O3 (powerful reasoning model)

### Anthropic Models
- Claude Opus 4 (most capable)
- Claude Sonnet 4 (high performance)
- Claude Haiku 3.5 (fastest responses)

### Perplexity Models
- Llama 3.1 Sonar (with online search)

## 📊 Scoring System

The evaluation uses a weighted scoring system:

- **Functionality (30%)** - Core features and user interactions
- **Reliability (25%)** - Error handling and stability
- **Performance (20%)** - Speed and efficiency
- **Security (15%)** - Protection and compliance
- **Completeness (10%)** - Feature coverage and documentation

### Completeness Levels

| Score | Level | Description |
|-------|-------|-------------|
| 90%+ | Production Ready | Fully complete and production-ready |
| 75-89% | Near Complete | Minor issues, mostly ready |
| 60-74% | Functional | Core functionality works |
| 40-59% | Basic Implementation | Basic features present |
| <40% | Incomplete | Significant work needed |

## 📁 Report Output

The evaluation generates comprehensive reports in `./evaluation-reports/`:

```
evaluation-reports/
├── YYYY-MM-DD/
│   ├── frontend-functionality-report.json
│   ├── backend-api-report.json
│   ├── security-compliance-report.json
│   ├── performance-metrics-report.json
│   ├── data-processing-report.json
│   ├── error-handling-report.json
│   ├── final-report.json
│   └── final-report.html
```

### HTML Report Features
- 📊 Visual scoring dashboard
- 🧪 Detailed test results
- 🔧 Actionable recommendations
- 📈 Performance benchmarks
- 🔒 Security audit results

## ⚙️ Configuration

Edit `scripts/evaluation-config.json` to customize:

- AI models to test against
- Test criteria and weights
- Performance benchmarks
- Security requirements
- API endpoints to validate

## 🔧 Prerequisites

- Node.js (v16 or higher)
- npm or yarn
- DealerScope application running
- Network access for AI model APIs (optional)

## 🚦 Running Individual Test Suites

```bash
# Test only frontend functionality
node scripts/ai-evaluation-suite.js --suite frontend-functionality

# Test only security compliance
node scripts/ai-evaluation-suite.js --suite security-compliance

# Test with specific AI model
node scripts/ai-evaluation-suite.js --model gpt-5-2025-08-07
```

## 📝 Example Output

```
🚀 Initializing DealerScope AI Evaluation Suite...
🔧 Starting DealerScope services...
⏳ Waiting for services to be ready...
✅ Services ready!

🧪 Running comprehensive evaluation suite...

📋 Running frontend-functionality tests...
✅ Page Load: PASS (10/10)
✅ Component Rendering: PASS (15/15)
✅ PWA Features: PASS (10/10)

📋 Running backend-api tests...
❌ Health Endpoint: FAIL (0/15) - Backend not available
✅ Dashboard Endpoint: PASS (10/10)

📊 Generating final evaluation report...
📋 Final report generated: ./evaluation-reports/2025-08-20/final-report.html

🎉 Evaluation Complete!
Overall Score: 85%
Completeness: Near Complete
```

## 🔍 Troubleshooting

### Common Issues

**"Services failed to start"**
- Ensure all dependencies are installed: `npm install`
- Check if ports 3000/8000 are available
- Verify backend script exists and is executable

**"Backend not available"**
- Backend script may not be present (frontend-only evaluation will continue)
- Check if Python dependencies are installed for backend
- Verify database connectivity

**"Permission denied"**
- Make script executable: `chmod +x scripts/run-evaluation.sh`
- Check file permissions on evaluation suite

### Debug Mode

```bash
# Enable verbose logging
./scripts/run-evaluation.sh --verbose

# Check individual components
curl http://localhost:3000  # Frontend
curl http://localhost:8000/health  # Backend
```

## 🤝 Contributing

To add new test suites or AI model integrations:

1. Edit `scripts/ai-evaluation-suite.js`
2. Add new test methods to the `AIEvaluationSuite` class
3. Update `evaluation-config.json` with new criteria
4. Run the suite to verify changes

## 📄 License

Part of the DealerScope project. See main project license for details.