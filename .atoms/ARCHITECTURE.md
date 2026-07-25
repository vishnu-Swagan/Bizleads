# Architecture Design

## System Overview
BizLeads is a subscription SaaS for web designers and agencies — "Website Opportunity Intelligence and Proof-to-Pitch OS." It discovers businesses likely to buy a better website using a 6-score intelligence system (Need, Buyability, Timing, Reachability, Agency Fit, Evidence Confidence), manages them through a CRM pipeline, and provides Stripe-based subscription billing with credit metering. Built on Atoms Cloud backend for auth, database, and custom APIs.

## Tech Stack
- Frontend: React + TypeScript + Vite + Tailwind CSS + Shadcn/ui
- Backend: Atoms Cloud (FastAPI-based) with PostgreSQL
- Auth: Atoms Cloud built-in authentication (OIDC)
- Payments: Stripe Checkout + Billing (subscription + credit model)
- State: React Query for server state, React Context for auth
- Scoring: Custom 6-score weighted priority system with confidence multiplier

## Module Design
| Module | Responsibility | Key Files |
|--------|---------------|-----------|
| Landing Page | Marketing page with features overview | src/pages/Index.tsx |
| Dashboard | CRM metrics, pipeline overview, recent leads | src/pages/Dashboard.tsx |
| Business Search | Search engine with filters for finding businesses | src/pages/Search.tsx |
| Lead Detail | Individual lead management with notes | src/pages/LeadDetail.tsx |
| App Layout | Shared navigation and header | src/components/AppLayout.tsx |
| Search API | Backend business search service | backend/routers/search.py, backend/services/business_search.py |
| Leads API | Auto-generated CRUD for leads entity | backend/routers/leads.py |
| Notes API | Auto-generated CRUD for lead_notes entity | backend/routers/lead_notes.py |

## Tech Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database schema | leads + lead_notes tables | Separate concerns for lead data and interaction history |
| Search simulation | Server-side random generation | MVP approach; can be replaced with real API integration |
| Pipeline stages | 5 stages (new_lead, contacted, in_progress, won, lost) | Standard CRM pipeline |
| Scoring system | 0-100 for both website and social | Simple numeric scoring for easy comparison |

## File Tree Plan
```
app/
├── frontend/src/
│   ├── pages/Index.tsx (landing)
│   ├── pages/Dashboard.tsx (CRM dashboard)
│   ├── pages/Search.tsx (business search)
│   ├── pages/LeadDetail.tsx (lead management)
│   ├── components/AppLayout.tsx (shared layout)
│   ├── contexts/AuthContext.tsx (auth state)
│   └── lib/api.ts (web SDK client)
├── backend/
│   ├── routers/search.py (search API)
│   ├── routers/leads.py (auto-generated)
│   ├── routers/lead_notes.py (auto-generated)
│   └── services/business_search.py (search logic)
```

## Implementation Guide
1. User lands on Index page, signs in via Atoms Cloud auth
2. Dashboard shows pipeline metrics and recent leads
3. Search page allows filtering by country, category, web presence
4. Search results can be saved as leads with one click
5. Lead detail page allows pipeline stage changes, priority updates, and note-taking