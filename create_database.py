from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
from datetime import datetime

# ✅ Step 1: Initialize Flask App
app = Flask(__name__)

# ✅ Step 2: Configure Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://employee_time_tracking_db_user:etuFbKaxgzHj7upU33pXTSJJisKz61d9@dpg-cvd99tggph6c739jrt3g-a:5432/employee_time_tracking_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ✅ Step 3: Define Database Models

# 🔹 Employee Model
class Employee(db.Model):
    __tablename__ = 'employee'  # Lowercase table name
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    monthly_overtime = db.Column(db.Integer, default=0)  # Stores overtime hours

# 🔹 Work Session Model
class WorkSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    clock_in = db.Column(db.DateTime, nullable=False, default=datetime.now)
    clock_out = db.Column(db.DateTime, nullable=True)
    employee = db.relationship('Employee', backref=db.backref('sessions', lazy=True))

# 🔹 Vehicle Key Monitor User Model (For Vehicle Key Page Login)
class VehicleKeyUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# 🔹 Vehicle Key Model
class VehicleKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    key_checkout_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
    key_number = db.Column(db.String(5), nullable=False)
    key_return_time = db.Column(db.DateTime, nullable=True)
    employee = db.relationship('Employee', backref=db.backref('vehicle_keys', lazy=True))

# ✅ Step 4: Create the Database
with app.app_context():
    print("🔄 Creating database tables...")
    db.create_all()

    # ✅ Step 5: Add Default Admin Employee
    print("👤 Adding default admin user...")
    admin_user = Employee(name="Admin User")
    db.session.add(admin_user)

    # ✅ Step 6: Add Default Vehicle Key Monitor User
    print("🔑 Adding a Vehicle Key Monitor user...")
    vehicle_key_user = VehicleKeyUser(username="employee1", password=generate_password_hash("password123"))
    db.session.add(vehicle_key_user)

    # ✅ Step 7: Save changes
    db.session.commit()
    print("✅ Database has been created successfully!")
