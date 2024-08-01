from app import db
from sqlalchemy import text

# Check if the 'is_admin' column exists
result = db.engine.execute("PRAGMA table_info(user)")
columns = [col[1] for col in result]
print(columns)

# If 'is_admin' is not in columns, add it
if 'is_admin' not in columns:
    db.engine.execute(text("ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
    print("Column 'is_admin' added successfully.")

# Verify the column has been added
result = db.engine.execute("PRAGMA table_info(user)")
columns = [col[1] for col in result]
print(columns)  # This should now include 'is_admin'
