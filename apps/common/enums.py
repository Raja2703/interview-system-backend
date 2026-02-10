# apps/common/enums.py
"""
Centralized constants/enums for the Interview Platform.
Single source of truth for frontend and backend.

These values are exposed via GET /api/enums/ endpoint.
"""

# ========== PHONE PREFIXES ==========
PHONE_PREFIXES = [
    {"code": "+91", "country": "India"},
    {"code": "+1", "country": "United States"},
    {"code": "+44", "country": "United Kingdom"},
    {"code": "+61", "country": "Australia"},
    {"code": "+81", "country": "Japan"},
    {"code": "+49", "country": "Germany"},
    {"code": "+33", "country": "France"},
    {"code": "+86", "country": "China"},
    {"code": "+971", "country": "United Arab Emirates"},
    {"code": "+65", "country": "Singapore"},
    {"code": "+852", "country": "Hong Kong"},
    {"code": "+60", "country": "Malaysia"},
    {"code": "+63", "country": "Philippines"},
    {"code": "+966", "country": "Saudi Arabia"},
    {"code": "+27", "country": "South Africa"},
    {"code": "+55", "country": "Brazil"},
    {"code": "+52", "country": "Mexico"},
    {"code": "+7", "country": "Russia"},
    {"code": "+82", "country": "South Korea"},
    {"code": "+39", "country": "Italy"},
]

# ========== DESIGNATION OPTIONS ==========
DESIGNATION_OPTIONS = [
    "Software Developer",
    "Frontend Developer",
    "Backend Developer",
    "Full Stack Developer",
    "DevOps Engineer",
    "Cloud Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "Data Engineer",
    "QA Engineer",
    "Testing Engineer",
    "Mobile Developer",
    "iOS Developer",
    "Android Developer",
    "Site Reliability Engineer",
    "Security Engineer",
    "Product Manager",
    "Technical Lead",
    "Engineering Manager",
    "Architect",
    "Solution Architect",
    "Principal Engineer",
    "Staff Engineer",
    "UI/UX Designer",
    "Database Administrator",
    "Network Engineer",
    "Systems Administrator",
    "Blockchain Developer",
    "Game Developer",
    "Embedded Systems Engineer",
]

# ========== SKILLS ==========
SKILLS = [
    # Programming Languages
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "C++",
    "C#",
    "Go",
    "Rust",
    "Ruby",
    "PHP",
    "Swift",
    "Kotlin",
    "Scala",
    "R",
    # Frontend
    "React",
    "Vue.js",
    "Angular",
    "Next.js",
    "HTML/CSS",
    "Tailwind CSS",
    "Redux",
    # Backend
    "Node.js",
    "Django",
    "Flask",
    "Spring Boot",
    "FastAPI",
    "Express.js",
    ".NET",
    "Ruby on Rails",
    "Laravel",
    # Databases
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Elasticsearch",
    "Cassandra",
    "DynamoDB",
    "Oracle",
    "SQL Server",
    # Cloud & DevOps
    "AWS",
    "Azure",
    "Google Cloud Platform",
    "Docker",
    "Kubernetes",
    "Terraform",
    "Jenkins",
    "CI/CD",
    "Ansible",
    "Linux",
    # Data & ML
    "Machine Learning",
    "Deep Learning",
    "TensorFlow",
    "PyTorch",
    "Pandas",
    "NumPy",
    "Data Analysis",
    "Computer Vision",
    "NLP",
    "Apache Spark",
    # Other
    "System Design",
    "Microservices",
    "REST APIs",
    "GraphQL",
    "gRPC",
    "Message Queues",
    "Kafka",
    "RabbitMQ",
    "Git",
    "Agile/Scrum",
    "Testing",
]

# ========== LANGUAGES ==========
LANGUAGES = [
    "English",
    "Hindi",
    "Spanish",
    "Mandarin",
    "French",
    "German",
    "Japanese",
    "Portuguese",
    "Russian",
    "Arabic",
    "Korean",
    "Italian",
    "Dutch",
    "Turkish",
    "Polish",
    "Vietnamese",
    "Thai",
    "Indonesian",
    "Malay",
    "Tamil",
    "Telugu",
    "Bengali",
    "Punjabi",
    "Marathi",
    "Gujarati",
    "Kannada",
    "Malayalam",
]

# ========== TARGET ROLES ==========
TARGET_ROLES = [
    "Junior Software Engineer",
    "Software Engineer",
    "Senior Software Engineer",
    "Staff Software Engineer",
    "Principal Engineer",
    "Technical Lead",
    "Engineering Manager",
    "Director of Engineering",
    "VP of Engineering",
    "CTO",
    "Frontend Engineer",
    "Backend Engineer",
    "Full Stack Engineer",
    "DevOps Engineer",
    "Site Reliability Engineer",
    "Cloud Engineer",
    "Data Scientist",
    "Senior Data Scientist",
    "Machine Learning Engineer",
    "Senior ML Engineer",
    "Data Engineer",
    "Senior Data Engineer",
    "Product Manager",
    "Senior Product Manager",
    "Technical Program Manager",
    "Solutions Architect",
    "Cloud Architect",
    "Security Engineer",
    "QA Engineer",
    "Mobile Developer",
]

# ========== CAREER GOALS ==========
CAREER_GOALS = [
    {"value": "finding_jobs", "label": "Finding Jobs", "description": "Looking for new job opportunities"},
    {"value": "switching_jobs", "label": "Switching Jobs", "description": "Looking to switch from current job"},
]

# ========== EXPERTISE LEVELS ==========
EXPERTISE_LEVELS = [
    {"value": "beginner", "label": "Beginner", "description": "0-2 years of experience"},
    {"value": "intermediate", "label": "Intermediate", "description": "2-5 years of experience"},
    {"value": "expert", "label": "Expert", "description": "5+ years of experience"},
]

# ========== ROLES ==========
USER_ROLES = [
    {"value": "attender", "label": "Interview Attender", "description": "Can attend interviews and send interview requests"},
    {"value": "taker", "label": "Interview Taker", "description": "Can conduct interviews and receive interview requests"},
]

# ========== EXPERIENCE YEARS RANGE ==========
EXPERIENCE_YEARS = {
    "min": 0,
    "max": 50,
    "default": 0,
}

# ========== DAYS OF WEEK ==========
DAYS_OF_WEEK = [
    {"value": "monday", "label": "Monday"},
    {"value": "tuesday", "label": "Tuesday"},
    {"value": "wednesday", "label": "Wednesday"},
    {"value": "thursday", "label": "Thursday"},
    {"value": "friday", "label": "Friday"},
    {"value": "saturday", "label": "Saturday"},
    {"value": "sunday", "label": "Sunday"},
]


def get_all_enums():
    """
    Returns all enums as a single dictionary.
    This is what the /api/enums/ endpoint returns.
    """
    return {
        "phone_prefixes": PHONE_PREFIXES,
        "designation_options": DESIGNATION_OPTIONS,
        "skills": SKILLS,
        "languages": LANGUAGES,
        "target_roles": TARGET_ROLES,
        "career_goals": CAREER_GOALS,
        "expertise_levels": EXPERTISE_LEVELS,
        "user_roles": USER_ROLES,
        "experience_years": EXPERIENCE_YEARS,
        "days_of_week": DAYS_OF_WEEK,
    }
