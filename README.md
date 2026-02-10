# Interview Platform Backend

A Django-based role-based interview platform that separates authentication, authorization, and role-based workflows.

## 🎯 Problem Solved

This platform fixes the common issues in interview systems:
- **Authentication ≠ Authorization ≠ Role**: Three separate stages
- **No redirect loops**: Clean flow from login → role selection → dashboard
- **No duplicate profiles**: Single profile creation via signals
- **Flexible role switching**: Users can switch between attender and taker roles anytime

## 🚀 Quick Start

### 1. Setup Environment

```bash
cd Interview-System-Backend/interview_platform

# Create virtual environment (if not already done)
python -m venv venv
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

The `.env` file is already created. Make sure to update the OAuth credentials:

```env
# Django Settings
DEBUG=True
SECRET_KEY=your-super-secret-key-here-change-this-in-production

# Database settings
DATABASE_URL=postgresql://user:password@localhost:5432/interview_platform

# Google OAuth Credentials (from Google Cloud Console)
GOOGLE_OAUTH_CLIENT_ID=your-google-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-google-client-secret

# LinkedIn OAuth Credentials (from LinkedIn Developer Portal)
LINKEDIN_OAUTH_CLIENT_ID=your-linkedin-client-id
LINKEDIN_OAUTH_CLIENT_SECRET=your-linkedin-client-secret
```

### 3. Run the Application

```bash
# Option 1: Use the run script (recommended)
python run_server.py

# Option 2: Manual setup
python manage.py migrate
python manage.py clear_sessions  # Clear any old sessions
python manage.py runserver
```

## 🔐 Authentication Flow

### 1. **Unauthenticated User**
- Visit `http://127.0.0.1:8000/` → Redirects to login

### 2. **Login Process**
- Go to `http://127.0.0.1:8000/accounts/login/`
- Login with email/password or OAuth (Google/LinkedIn)
- After login → Redirects to role selection (if no role set)

### 3. **Role Selection (Changeable anytime)**
- Choose: `attender` (interview candidate) or `taker` (interviewer)
- Role can be changed anytime via `/api/select-role/`

### 4. **Interview Workflow**
- **Attender**: Sends interview requests with preferred time slots
- **Taker**: Receives requests in dashboard, can accept/reject
- **Accepted interviews**: Appear in calendar for both parties
- Users can switch roles anytime to participate as both attender and taker

### 5. **Dashboard Access**
- Role-based dashboard showing relevant interview information
- `attender`: Sent requests, accepted interviews, scheduling
- `taker`: Received requests (pending/accepted/rejected), management tools

## 📁 Project Structure

```
interview_platform/
├── config/
│   ├── settings.py      # Django settings
│   ├── urls.py         # Main URL configuration
│   └── wsgi.py
├── apps/
│   ├── accounts/       # Authentication & user management
│   │   ├── models.py
│   │   ├── signals.py  # Profile creation signals
│   │   └── middleware.py # Role enforcement middleware
│   ├── profiles/       # User profiles & role management
│   │   ├── models.py
│   │   ├── api.py      # Role selection endpoint
│   │   └── serializers.py
│   └── interviews/     # Interview management
│       ├── models.py
│       ├── api.py      # Interview APIs
│       └── permissions.py # Role-based permissions
├── manage.py
├── run_server.py      # Quick start script
├── test_auth_flow.py   # Authentication tests
└── requirements.txt
```

## 🔧 Key Features Fixed

### ✅ **No More Redirect Loops**
- Middleware properly exempts auth routes (`/accounts/*`)
- Login redirect goes to `/` (root) for proper flow control
- Role selection happens exactly once

### ✅ **Clean Profile Management**
- Single signal creates profile on user creation
- No duplicate profile creation
- Role validation prevents changes after setting

### ✅ **Role-Based Access**
- `attender`: Can attend interviews, view schedule
- `taker`: Can create/manage interviews, evaluate candidates
- Middleware enforces role requirements

### ✅ **OAuth Support**
- Google and LinkedIn login
- Automatic profile creation with OAuth data
- No duplicate users/profiles

## 🧪 Testing

Run the authentication flow test:

```bash
python test_auth_flow.py
```

This tests:
- Unauthenticated redirects
- Login process
- Role selection (changeable)
- Dashboard access
- Role switching capability

## 🌐 API Endpoints

### Authentication (Allauth)
- `GET/POST /accounts/login/` - Login
- `GET/POST /accounts/signup/` - Registration
- `POST /accounts/logout/` - Logout

### Profile Management
- `GET /api/select-role/` - Get available roles
- `POST /api/select-role/` - Set role (one-time only)
- `GET/PUT /api/profile/` - Profile management

### Interview Management
- `POST /api/interviews/create/` - Create interview request (attenders only)
- `GET /api/interviews/sent/` - Sent requests (attenders only)
- `GET /api/interviews/received/` - Received requests (takers only)
- `POST /api/interviews/{id}/accept/` - Accept request (takers only)
- `POST /api/interviews/{id}/reject/` - Reject request (takers only)

### Dashboard
- `GET /dashboard/` - Role-based dashboard (requires role)

## 🛠️ Development Commands

```bash
# Run migrations
python manage.py migrate

# Clear sessions (useful for testing auth)
python manage.py clear_sessions

# Create superuser
python manage.py createsuperuser

# Run tests
python test_auth_flow.py

# Run development server
python manage.py runserver
```

## 🔒 Security Notes

- Role selection can only happen once
- Middleware prevents unauthorized access to role-specific endpoints
- Session management for proper authentication state
- CSRF protection on all forms

## 🚨 Troubleshooting

### **Still seeing dashboard instead of login?**
```bash
# Clear browser sessions and run:
python manage.py clear_sessions
# Restart server
```

### **Role selection not working?**
- Check that user profile exists: `UserProfile.objects.get(user=user)`
- Verify role is None: `profile.role is None`
- Check middleware exempt paths

### **OAuth not working?**
- Verify `.env` has correct OAuth credentials
- Check Django admin social applications configuration
- Ensure callback URLs are configured in OAuth providers

---

## 🎯 Summary

This backend provides a **stable, loop-free authentication and role-based workflow** that properly separates:

1. **Authentication** (login/signup)
2. **Authorization** (role assignment)
3. **Role-based experience** (dashboard & APIs)

No more redirect loops, duplicate profiles, or confused role logic!