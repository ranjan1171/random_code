"""
config.py — Central configuration for the Auto Job Apply System
All profile data, portal settings, and scoring parameters live here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# ──────────────────────────────────────────────────────────────
# CANDIDATE PROFILE — Ranjan Kumar
# ──────────────────────────────────────────────────────────────

PROFILE = {
    "name": "Ranjan Kumar",
    "email": "ranjankumar684118@gmail.com",
    "phone": "7992272611",
    "location": "Pune, India",
    "linkedin": "https://www.linkedin.com/in/ranjan-kumar-910449182/",
    "github": "https://github.com/ranjan1171",

    # Skills provided by user
    "skills": [
        # Languages
        "C++", "Rust", "Python", "JavaScript", "TypeScript", "SQL",
        # Backend & APIs
        "Node.js", "Express.js", "REST APIs", "Distributed Systems", "Microservices",
        # Data Engineering
        "Apache Kafka", "Confluent Kafka", "Kafka Connect", "Change Data Capture", "CDC",
        "JDBC Source/Sink Connectors", "Schema Registry", "Avro", "ETL Pipelines", "SingleStore Pipelines",
        # Databases
        "Oracle", "SingleStore", "PostgreSQL", "MySQL", "MongoDB", "Redis", "RocksDB",
        # Systems & Networking
        "Linux", "Systemd", "Cron", "Shell Scripting", "WebSockets", "TCP/IP", "POSIX Sockets", "Boost.Asio",
        # Observability
        "Grafana", "Jaeger", "OpenTelemetry",
        # Rust Ecosystem
        "Tokio", "Tokio-Tungstenite", "Flume", "SeaORM",
        # Tools
        "Git", "GitHub", "Docker", "Postman", "VS Code", "Confluent Control Center",
        # CS Fundamentals
        "Data Structures", "Algorithms", "Object-Oriented Programming", "OOP", "DBMS", "Operating Systems", "Computer Networks",
    ],

    # Keywords that STRONGLY boost score
    "primary_skills": [
        "python", "c++", "rust", "javascript", "typescript", "sql", "node.js", "express.js",
        "rest api", "distributed systems", "microservices", "kafka", "confluent kafka",
        "kafka connect", "cdc", "postgresql", "mysql", "mongodb", "redis", "rocksdb",
        "singlestore", "linux", "websockets", "docker", "git", "tokio", "seaorm",
    ],

    # Experience level: 1-3 years target
    "total_experience_years": 3,

    # Target job titles: SDE 1 / Junior / Software Engineer (NO SENIOR)
    "target_titles": [
        "Software Engineer", "Software Developer", "Backend Engineer",
        "Backend Developer", "Systems Engineer", "Software Development Engineer",
        "SDE", "SDE-1", "SDE 1", "SDE I", "Junior Software Engineer",
        "Junior Developer", "Associate Software Engineer", "Graduate Software Engineer",
        "Entry Level Software Engineer", "Python Developer", "Backend Software Engineer",
    ],

    # Target companies — bonus score if matched
    "target_companies": [
        "zerodha", "groww", "smallcase", "kite", "razorpay", "phonePe",
        "juspay", "meesho", "zomato", "swiggy", "cred", "atlassian",
        "confluent", "cloudflare", "hashicorp", "coinbase", "binance",
        "upstox", "angel one", "sharekhan", "edelweiss", "kotak",
    ],

    # Deal-breakers — MUST REJECT Senior / Lead / Staff / Principal / PhD / Manager / >3 YOE / Non-Tech roles
    "dealbreakers": [
        "senior", "sr.", "sr ", "staff", "principal", "lead", "director", "vp ", "vice president",
        "manager", "head of", "architect", "phd", "executive", "tech lead", "engineering manager",
        "4+ years", "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
        "4 years", "5 years", "6 years", "7 years", "8 years", "10 years",
        "accountant", "customer support", "tax ", "tax specialist", "screening analyst",
        "treasury operations", "audit analytics", "risk analyst", "finance & strategy",
        "frontend only", "react only", "angular", "vue.js developer",
        "ios developer", "android developer", "mobile developer",
        "sales", "business development", "account manager", "hr",
        "marketing", "content writer", "seo specialist",
        "mandatory relocation abroad", "us only", "uk only", "europe only",
    ],

    # Acceptable locations
    "acceptable_locations": [
        "pune", "bangalore", "bengaluru", "hyderabad", "mumbai",
        "remote", "work from home", "wfh", "hybrid", "india",
    ],

    # CV file path (PDF for uploading) — use whichever exists
    "cv_pdf_path": str(next(
        (p for p in [
            Path(r"C:\Users\HP\Downloads\ranjan_resume_2026.pdf"),
            Path(r"C:\Users\HP\OneDrive\Desktop\RanjankumarResumehr.pdf"),
            BASE_DIR.parent / "linkedin_automation" / "Ranjankumar_resume_comany.pdf",
            Path(r"C:\Users\HP\OneDrive\Desktop\linkedin_automation\Ranjankumar_resume_comany.pdf"),
        ] if p.exists()),
        BASE_DIR / "cv.pdf"   # fallback (won't exist — upload skipped)
    )),

    # Cover letter template text (used when no tailored CL is needed)
    "default_cover_letter": (
        "I am a Software Developer with 1.5+ years of experience in backend engineering, "
        "distributed systems, and high-performance computing. Currently at WhiteKlay, I build "
        "Python/Kafka-based data pipelines and Kafka CDC recovery systems. Previously at "
        "Teesta Investment (HFT firm), I developed low-latency market data infrastructure, "
        "reduced arbitrage misses by 30%, and cut latency by 70% with a centralized TCP server. "
        "I'm passionate about building high-throughput, fault-tolerant backend systems and "
        "would love to contribute to your engineering team."
    ),
}

# ──────────────────────────────────────────────────────────────
# JOB PORTALS CONFIGURATION
# ──────────────────────────────────────────────────────────────

PORTALS = {
    "linkedin": {
        "enabled": True,
        "name": "LinkedIn",
        "login_required": True,
        "easy_apply": True,        # supports Easy Apply
        "scrape_url": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
        "email": os.getenv("LINKEDIN_EMAIL", ""),
        "password": os.getenv("LINKEDIN_PASSWORD", ""),
    },
    "naukri": {
        "enabled": True,
        "name": "Naukri",
        "login_required": True,
        "easy_apply": True,        # supports Quick Apply
        "scrape_url": "https://www.naukri.com/jobapi/v3/search",
        "email": os.getenv("NAUKRI_EMAIL", ""),
        "password": os.getenv("NAUKRI_PASSWORD", ""),
    },
    "indeed": {
        "enabled": True,
        "name": "Indeed",
        "login_required": False,   # many jobs allow guest apply
        "easy_apply": False,
        "scrape_url": "https://in.indeed.com/jobs",
        "email": os.getenv("INDEED_EMAIL", ""),
        "password": os.getenv("INDEED_PASSWORD", ""),
    },
    "wellfound": {
        "enabled": True,
        "name": "Wellfound",
        "login_required": True,
        "easy_apply": True,
        "scrape_url": "https://wellfound.com/role/l/software-engineer/india",
        "email": os.getenv("WELLFOUND_EMAIL", ""),
        "password": os.getenv("WELLFOUND_PASSWORD", ""),
    },
    "internshala": {
        "enabled": True,
        "name": "Internshala",
        "login_required": False,
        "easy_apply": False,
        "scrape_url": "https://internshala.com/jobs/",
        "email": "",
        "password": "",
    },
    "freehire": {
        "enabled": True,
        "name": "Freehire.dev",
        "login_required": False,
        "easy_apply": False,         # just scrapes — links to original
        "scrape_url": "https://freehire.dev/api/v1/jobs",
        "email": "",
        "password": "",
    },
}

# ──────────────────────────────────────────────────────────────
# MATCHING SETTINGS
# ──────────────────────────────────────────────────────────────

MATCHING = {
    # Minimum score (0-100) to be considered a match
    "min_score": float(os.getenv("MIN_MATCH_SCORE", "60")),

    # Score weights
    "weights": {
        "skill_overlap": 0.40,      # TF-IDF skill matching
        "title_match": 0.25,        # Title keyword match
        "location_match": 0.20,     # Location acceptability
        "company_bonus": 0.10,      # Target company bonus
        "experience_fit": 0.05,     # Experience level fit
    },

    # Bonus score for primary skills match
    "primary_skill_bonus": 10,

    # Penalty for dealbreaker keywords found
    "dealbreaker_penalty": 100,
}

# ──────────────────────────────────────────────────────────────
# SEARCH QUERIES — What to search for
# ──────────────────────────────────────────────────────────────

SEARCH_QUERIES = [
    # Primary targets
    {"q": "backend engineer python kafka", "location": "Pune"},
    {"q": "backend engineer python kafka", "location": "Bangalore"},
    {"q": "software developer distributed systems", "location": "India"},
    {"q": "SDE python backend", "location": "Hyderabad"},
    {"q": "python developer kafka distributed", "location": "Remote"},
    {"q": "backend software engineer rust", "location": "India"},
    {"q": "systems engineer python backend", "location": "Mumbai"},
    {"q": "fintech backend developer python", "location": "India"},
    {"q": "platform engineer kafka python", "location": "India"},
    {"q": "software engineer backend node.js", "location": "Pune"},
    # HFT / Trading specific
    {"q": "quantitative developer python", "location": "India"},
    {"q": "HFT software engineer", "location": "India"},
    {"q": "trading systems developer python", "location": "India"},
    {"q": "low latency software developer", "location": "India"},
]

# ──────────────────────────────────────────────────────────────
# APPLICATION SETTINGS
# ──────────────────────────────────────────────────────────────

APPLICATION = {
    "max_daily": int(os.getenv("MAX_DAILY_APPLICATIONS", "20")),
    "apply_delay_seconds": float(os.getenv("APPLY_DELAY_SECONDS", "30")),
    "headless": os.getenv("HEADLESS_BROWSER", "false").lower() == "true",

    # Browser viewport (looks like a real user)
    "viewport": {"width": 1366, "height": 768},

    # Typical user-agent
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
}

# ──────────────────────────────────────────────────────────────
# CAPTCHA SETTINGS
# ──────────────────────────────────────────────────────────────

CAPTCHA = {
    "capsolver_api_key": os.getenv("CAPSOLVER_API_KEY", ""),
    "two_captcha_api_key": os.getenv("TWO_CAPTCHA_API_KEY", ""),
    "timeout_seconds": 120,
    "max_retries": 3,
}

# ──────────────────────────────────────────────────────────────
# EMAIL MONITOR SETTINGS
# ──────────────────────────────────────────────────────────────

EMAIL = {
    "gmail_address": os.getenv("GMAIL_ADDRESS", ""),
    "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD", ""),
    "imap_server": "imap.gmail.com",
    "imap_port": 993,
    "check_interval_seconds": 60,

    # Keywords to identify job-related emails
    "application_keywords": [
        "application received", "thank you for applying", "we received your application",
        "application confirmation", "successfully applied", "your application",
        "job application", "application status",
    ],
    "otp_keywords": ["otp", "one time password", "verification code", "your code is"],
    "rejection_keywords": ["unfortunately", "not moving forward", "not selected", "rejected"],
    "interview_keywords": ["interview", "schedule a call", "speak with you", "next steps"],
}

# ──────────────────────────────────────────────────────────────
# DATABASE & PATHS
# ──────────────────────────────────────────────────────────────

DB_PATH = BASE_DIR / "db" / "jobs.db"
LOG_DIR = BASE_DIR / "logs"
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
