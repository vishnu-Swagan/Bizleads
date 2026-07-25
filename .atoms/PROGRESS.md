# Requirements & Progress

## Requirements Overview
Build a Search options and CRM to find local businesses around the globe with weak websites and social media presence and no websites at all.

## User Stories
- As a user, I can search for businesses globally by location, category, and web presence status
- As a user, I can view business cards with digital presence scores
- As a user, I can save search results as leads to my CRM pipeline
- As a user, I can manage leads through pipeline stages (New, Contacted, In Progress, Won, Lost)
- As a user, I can add notes and track interactions with leads
- As a user, I can see dashboard metrics and pipeline overview

## Task Breakdown
- [x] Create database tables (leads, lead_notes)
- [x] Insert mock data for leads
- [x] Create backend search API for business discovery
- [x] Build landing page with feature overview
- [x] Build CRM dashboard with metrics, quick actions, and pipeline summary
- [x] Build business search page with filters (country, category, web presence)
- [x] Build lead detail page with notes and pipeline management
- [x] Build Pipeline/Kanban board view with stage progression
- [x] Build All Leads page with table view, search, filters, bulk actions, CSV export
- [x] Build Analytics page with pipeline distribution, digital presence breakdown, priority & category/country insights
- [x] Full navigation menu (Dashboard, Search, All Leads, Pipeline, Analytics)
- [x] Lint, build, and verify
- [x] Fix authentication to use Web SDK (client.auth.me/toLogin/logout)
- [x] Fix business discovery filter handling (null vs placeholder strings)
- [x] Add country/location filter to All Leads page
- [x] Add guided onboarding tutorial for new users on Dashboard
- [x] Add AI auto lead generation (backend + frontend)
- [x] Add AI follow-up email generator (backend + frontend)
- [x] Add AI daily activity report (backend + frontend)
- [x] Add Automation page with tabs and navigation link
- [x] Add AI interaction logging (track all AI feature usage with timing/status)
- [x] Add advanced lead targeting filters (business size, years, revenue, intent signals)
- [x] Add email service integration (send follow-up emails directly to leads)
- [x] Enhance AI prompts for more precise/accurate business discovery
- [x] Add Activity Log tab showing full interaction history
- [x] Replace mock/simulated data with AI-powered real business discovery
- [x] Update Search page to use real AI-powered global business intelligence
- [x] Phase A: Rebrand to BizLeads with new landing page and positioning
- [x] Phase A: Add /pricing page with subscription tiers (Solo/Pro/Agency)
- [x] Phase A: Restructure routes under /app/* with redirects from old paths
- [x] Phase A: Collapsible left sidebar navigation replacing top nav
- [x] Phase A: Multi-score system (Need, Buyability, Timing, Reachability, Fit, Confidence)
- [x] Phase A: Stripe subscription integration (checkout, verify, credit ledger)
- [x] Phase A: Workspace settings with offer profile and integrations page
- [x] Phase B: Enhanced discovery workflow with credit estimation and job states
- [x] Phase B: Score breakdown UI with "Why this score?" drawer per lead
- [x] Phase B: Lead detail redesign with tabbed view (Overview, Evidence, Contacts, Notes)
- [x] Phase B: Provider adapter architecture with demo/setup states
- [x] Phase B: Proper empty/loading/error/permission/quota states on all pages
- [x] Add guided tutorial for new users (7-step interactive tour with navigation)
- [x] Connect Google Places API for accurate business data (with AI fallback)
- [x] Fix Stripe billing checkout + verification flow

## Progress Log
- Created leads and lead_notes database tables with BackendManager
- Inserted 8 mock lead records
- Created business_search service with simulated global business data
- Created search API router with POST /businesses and GET /filters endpoints
- Built frontend: landing page, dashboard, search, lead detail pages
- Set up design system with Poppins/Open Sans fonts and professional blue theme
- Enhanced to production-ready: added Pipeline board, All Leads table, Analytics page
- Added full navigation with 5 menu items, bulk actions, CSV export, sorting/filtering
- All pages pass lint and build checks
- Added explicit Sign Up / Sign In buttons on landing page (both use Atoms Cloud OIDC auth)
- Added category filter to All Leads page alongside existing stage and priority filters
- Fixed auth: replaced axios-based auth with Web SDK (client.auth.me(), toLogin(), logout())
- Fixed business search: filter values now send null instead of "all_countries"/"all_categories"
- Added country/location filter to All Leads page for location-based lead filtering
- Added GuidedTutorial component on Dashboard with 4-step interactive onboarding walkthrough
- Removed unused lib/auth.ts file
- All changes pass lint and production build
- Added AI automation backend: services/ai_automation.py + routers/automation.py
  - POST /api/v1/automation/generate-leads: AI generates new business leads and saves to CRM
  - POST /api/v1/automation/follow-up-email: AI generates personalized follow-up emails per lead
  - GET /api/v1/automation/daily-report: AI generates daily activity report with action items
- Added Automation page (frontend) with 3 tabs: Generate Leads, Follow-Up Emails, Daily Report
- Added "AI Auto" nav item to AppLayout navigation
- All Python files pass py_compile, frontend passes lint and build
- Enhanced AI Automation with competitive features (based on market research):
  - AI Interaction Logs: new DB table + service to track all AI usage (action type, duration, status)
  - Advanced Targeting: business size, years in business, target revenue, intent signals (hiring, expanding, rebranding, new location)
  - Email Service: POST /api/v1/automation/send-email generates + sends emails, auto-updates lead stage to "contacted"
  - Enhanced AI prompts: more specific business details, opportunity scoring, concrete digital gap analysis
  - Activity Log tab: paginated history with filter by action type, duration display, status badges
  - 4-tab UI: Generate Leads, Follow-Up Emails, Daily Report, Activity Log
- Replaced ALL mock/simulated data with AI-powered real business discovery:
  - business_search.py now uses AI (deepseek-v4-pro) to discover real businesses worldwide
  - Removed random generators, hardcoded name prefixes, and fake data patterns
  - AI uses training knowledge of real businesses, locations, and market conditions
  - Search prompts emphasize real naming conventions, real neighborhoods, correct phone formats
  - Updated search router to async + 600s timeout for AI-powered discovery
  - Updated frontend Search page: renamed to "AI Business Discovery", added loading indicator
  - AI automation lead generation also uses real-data-focused prompts