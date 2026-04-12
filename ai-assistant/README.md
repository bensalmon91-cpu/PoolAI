# AI Assistant for PoolAIssistant

An intelligent AI assistant that helps pool operators with water quality, maintenance, and equipment management through contextual questions and personalized suggestions.

## Overview

The AI Assistant integrates with the existing PoolAIssistant infrastructure to:

1. **Ask Contextual Questions** - Build knowledge profiles for each pool
2. **Generate Suggestions** - Provide actionable recommendations based on data
3. **Learn Across Pools** - Aggregate insights for pattern recognition
4. **Admin Oversight** - Post-hoc review and steering capabilities

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ADMIN BACKEND                         │
│   Question Manager │ Response Viewer │ Analytics        │
│                          │                               │
│                    ┌─────┴─────┐                        │
│                    │  MySQL DB  │                        │
│                    └─────┬─────┘                        │
└──────────────────────────┼──────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │ Claude API  │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    ┌─────────┐       ┌─────────┐       ┌─────────┐
    │ Pi Unit │       │ Pi Unit │       │ Pi Unit │
    │ AI Chat │       │ AI Chat │       │ AI Chat │
    └─────────┘       └─────────┘       └─────────┘
```

## Quick Start

### 1. Database Setup

Run the migration on your MySQL server:

```bash
mysql -u username -p database_name < database/schema_ai.sql
```

### 2. Configure Claude API

Add to your `.env` file on Hostinger:

```
CLAUDE_API_KEY=sk-ant-api03-xxxxx
```

### 3. Deploy PHP Files

Copy the contents of `php/` to your existing `php_deploy/` directory:

```
php/api/ai/*       → php_deploy/api/ai/
php/admin/*        → php_deploy/admin/
php/includes/*     → php_deploy/includes/
```

### 4. Deploy Pi Files (Phase 3)

Copy to your Pi software:

```
pi/blueprints/ai_assistant.py → PoolDash_v6/pooldash_app/blueprints/
pi/templates/ai_assistant.html → PoolDash_v6/pooldash_app/templates/
```

## Directory Structure

```
ai-assistant/
├── README.md                 # This file
├── docs/
│   ├── PROGRESS.md          # Implementation progress tracker
│   └── PLAN.md              # Full architecture plan
├── database/
│   └── schema_ai.sql        # MySQL migration
├── php/                      # Server-side code
│   ├── api/ai/              # API endpoints
│   │   ├── questions.php    # Question CRUD
│   │   ├── responses.php    # Response management
│   │   ├── suggestions.php  # Suggestion management
│   │   ├── profiles.php     # Pool profiles
│   │   ├── queue.php        # Question queue
│   │   ├── response.php     # Device answer endpoint
│   │   ├── ask_me.php       # On-demand question
│   │   ├── suggestion_feedback.php
│   │   ├── generate.php     # Trigger Claude
│   │   └── norms.php        # Cross-pool analytics
│   ├── admin/               # Admin dashboard pages
│   │   ├── ai_dashboard.php
│   │   ├── ai_questions.php
│   │   ├── ai_responses.php
│   │   └── ai_suggestions.php
│   └── includes/
│       └── claude_api.php   # Claude API wrapper
├── pi/                       # Pi-side code
│   ├── blueprints/
│   │   └── ai_assistant.py  # Flask blueprint
│   └── templates/
│       └── ai_assistant.html
└── prompts/                  # Claude prompt templates
    ├── analyze_response.txt
    ├── generate_suggestion.txt
    └── detect_anomaly.txt
```

## API Endpoints

### Device Endpoints (API Key Auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ai/response.php` | Submit answer to question |
| POST | `/api/ai/ask_me.php` | Request a new question |
| POST | `/api/ai/suggestion_feedback.php` | Report action on suggestion |

### Admin Endpoints (Session Auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST/PUT/DELETE | `/api/ai/questions.php` | Question CRUD |
| GET/PUT | `/api/ai/responses.php` | View/flag responses |
| GET/POST/PUT | `/api/ai/suggestions.php` | Manage suggestions |
| GET/PUT | `/api/ai/profiles.php` | View pool profiles |
| GET/POST/DELETE | `/api/ai/queue.php` | Manage question queue |
| POST | `/api/ai/generate.php` | Trigger Claude analysis |
| GET/POST | `/api/ai/norms.php` | Cross-pool analytics |

## Database Tables

| Table | Purpose |
|-------|---------|
| `ai_questions` | Question library templates |
| `ai_question_queue` | Per-device question queue |
| `ai_responses` | User answers to questions |
| `ai_pool_profiles` | Per-pool knowledge profiles |
| `ai_suggestions` | AI-generated suggestions |
| `ai_pool_norms` | Cross-pool statistics |
| `ai_conversation_log` | Claude API audit log |

## Implementation Phases

- [x] **Phase 1A**: Database schema
- [x] **Phase 1B-E**: Admin dashboard & APIs
- [ ] **Phase 2**: Claude API integration
- [ ] **Phase 3**: Pi user interface
- [ ] **Phase 4**: Cross-pool learning
- [ ] **Phase 5**: Advanced features

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `CLAUDE_API_KEY` | Anthropic API key | Yes |
| `DB_*` | Database credentials | Yes (existing) |

### Claude API Costs

Estimated costs per operation:
- Response analysis: ~$0.01
- Suggestion generation: ~$0.02
- Anomaly detection: ~$0.01

## Security Notes

- Claude API key stored in `.env` (not in git)
- Device authentication via existing API key system
- Admin authentication via existing session system
- Pool data anonymized before sending to Claude
