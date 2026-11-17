#!/usr/bin/env python
"""
Flask-Migrate Setup Script for AZUL
Initializes database migrations for production deployment
"""
import os

PROJECT_DIR = r"C:\Users\abdo oubir\apology-website"

# Create instance/backups directory
os.makedirs(os.path.join(PROJECT_DIR, "instance", "backups"), exist_ok=True)
print("Created: instance/backups/")

# Create .env.example
env_example = """# AZUL - Environment Configuration
# Copy this file to .env and fill in your values

# REQUIRED in production
SECRET_KEY=your-secret-key-here-change-this

# OPTIONAL - Database
# DATABASE_URL=sqlite:///instance/azul.db
# Default: SQLite in instance/azul.db

# OPTIONAL - Environment
FLASK_ENV=production
FLASK_DEBUG=0
"""

with open(os.path.join(PROJECT_DIR, ".env.example"), "w") as f:
    f.write(env_example)
print("Created: .env.example")

# Create .gitignore entry for .env
gitignore_path = os.path.join(PROJECT_DIR, ".gitignore")
gitignore_entries = "\n# Environment\n.env\n\n# Database backups\ninstance/backups/\n"

if os.path.exists(gitignore_path):
    with open(gitignore_path, "a") as f:
        f.write(gitignore_entries)
else:
    with open(gitignore_path, "w") as f:
        f.write(gitignore_entries)
print("Updated: .gitignore")

print("\nFlask-Migrate setup complete.")
print("Next steps:")
print("  1. Create .env file from .env.example")
print("  2. Run: flask db init")
print("  3. Run: flask db migrate -m 'Initial migration'")
print("  4. Run: flask db upgrade")