# Claude AI Integration for PoolAIssistant - Full Plan

This document contains the complete architecture plan. See README.md for quick start and INTEGRATION.md for deployment steps.

---

[The full plan document from the initial specification is preserved here for reference]

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Claude API Location | Server-only | Simpler, cheaper, more secure. Pi displays results only. |
| Admin Oversight | Post-hoc review | Suggestions delivered immediately, admin can review/retract. |
| Backend Stack | Existing PHP (Hostinger) | Leverage current infrastructure. MySQL database. |
| Phase 1 Priority | Admin dashboard first | Build oversight tools before user-facing features. |

## Implementation Phases

### Phase 1: Admin Dashboard & Backend Foundation
- Database schema with all AI tables
- Question library manager
- Response viewer with filtering and export
- Suggestion management with retraction
- Overview dashboard with stats

### Phase 2: Claude Integration
- Claude API wrapper class
- Response analysis
- Suggestion generation
- Anomaly detection
- Conversation logging

### Phase 3: Pi User Interface
- Flask blueprint for AI assistant
- Question answering interface
- Suggestion display and feedback
- Local SQLite caching for offline
- Heartbeat sync integration

### Phase 4: Cross-Pool Learning
- Norm calculation across pools
- Anomaly detection by comparison
- Analytics dashboard

### Phase 5: Advanced Features
- Event-driven triggers
- Follow-up chains
- Effectiveness tracking

## Database Tables

See `database/schema_ai.sql` for full schema.

- `ai_questions` - Question library
- `ai_question_queue` - Per-device queue
- `ai_responses` - User answers
- `ai_pool_profiles` - Knowledge profiles
- `ai_suggestions` - AI recommendations
- `ai_pool_norms` - Cross-pool stats
- `ai_conversation_log` - Claude API audit

## API Endpoints

### Device (API Key Auth)
- POST `/api/ai/response.php` - Submit answer
- POST `/api/ai/ask_me.php` - Request question
- POST `/api/ai/suggestion_feedback.php` - Report action

### Admin (Session Auth)
- `/api/ai/questions.php` - Question CRUD
- `/api/ai/responses.php` - Response management
- `/api/ai/suggestions.php` - Suggestion management
- `/api/ai/profiles.php` - Pool profiles
- `/api/ai/queue.php` - Question queue
- `/api/ai/generate.php` - Trigger Claude
- `/api/ai/norms.php` - Analytics
