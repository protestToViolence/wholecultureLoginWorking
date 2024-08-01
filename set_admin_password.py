import os
from werkzeug.security import generate_password_hash
from app import app, db
from models import User

# Make sure to replace 'your_application' with the actual name of your application module

with app.app_context():
    # Generate a hashed password
    hashed_password = generate_password_hash('adminpassword')

    # Query for the admin user
    admin_user = User.query.filter_by(username='admin').first()

    if admin_user:
        # Set the new password hash
        admin_user.password_hash = hashed_password
        db.session.commit()
        print("Password updated successfully")
    else:
        print("Admin user not found")
