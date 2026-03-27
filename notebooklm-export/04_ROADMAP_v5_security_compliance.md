# Something Later

This document contains a comprehensive plan for upgrading DealerScope to version 5.0 with a focus on SECURITY & COMPLIANCE features, including:

## Goals
1. **Production-grade file upload hardening**: Streaming uploads, AV scanning, EXIF stripping, and quotas.
2. **CCPA right-to-delete workflow**: Structured processes for user data deletion, including attestation and idempotent job considerations.
3. **Robots compliance layer**: Implementing checks for robots.txt and associated compliance measures.
4. **Full CI + metrics**: Monitoring and enforcing quality standards without external notifications.

## Key Components
- **File Upload Hardening**: Implements secure storage practices, MIME detection, and audit logging.
- **Privacy Deletion Workflow**: Structured deletion requests with dynamic target discovery to ensure compliance with privacy laws.
- **Robots Compliance**: Ensures ethical web scraping and adherence to site policies with caching mechanisms.

### Actions Required:
- Wire up the upload process and CCPA workflow.
- Ensure robust compliance measures are integrated.
- Conduct testing to confirm functionality and security.

The plan outlines both **high-impact immediate actions** and **long-term strategies**, ensuring DealerScope is positioned for both growth and security compliance. 

---
This document will serve as a reference as development progresses and acts as a guide for implementing these critical features.