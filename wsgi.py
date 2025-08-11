"""
WSGI Configuration untuk Vercel Deployment
Multi-Branch Sales Analytics
"""
from app import app

# Vercel requires the app to be in a variable called 'app'
if __name__ == "__main__":
    app.run()