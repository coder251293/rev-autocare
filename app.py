from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from fpdf import FPDF
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger  # ✅ Ensure correct cron trigger import
import atexit


app = Flask(__name__)
app.secret_key = "7654321jJ"


# Set up the database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///employees.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)


# Employee model
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    monthly_overtime = db.Column(db.Integer, default=0)  # Ensure this line is in the model

class TimeTrackerUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)  # Store hashed passwords

class VehicleKeyUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)  # Store hashed passwords

class WorkSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    clock_in = db.Column(db.DateTime, nullable=False, default=datetime.now)
    clock_out = db.Column(db.DateTime, nullable=True)

    employee = db.relationship('Employee', backref=db.backref('sessions', lazy=True))

    def total_hours(self):
        if self.clock_in and self.clock_out:
            total_seconds = (self.clock_out - self.clock_in).total_seconds()
            return int(total_seconds // 60)  # Return total minutes as an integer
        return 0  # Return 0 minutes if no clock-out
    
class VehicleKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    key_checkout_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
    key_number = db.Column(db.String(5), nullable=False)  # Stores the last 5 digits of the key
    key_return_time = db.Column(db.DateTime, nullable=True)

    employee = db.relationship('Employee', backref=db.backref('vehicle_keys', lazy=True))

@app.route('/')
def home():
    return render_template('home.html')

# Vehicle Key model
@app.route('/add_vehicle_key', methods=['POST'])
def add_vehicle_key():
    employee_id = request.form.get('employee_id')  # Get selected employee
    key_number = request.form.get('key_number')  # Get entered key number

    if employee_id and key_number:
        new_key = VehicleKey(
            employee_id=employee_id,
            key_number=key_number,
            key_checkout_time=datetime.now()
        )
        db.session.add(new_key)
        db.session.commit()

    return redirect(url_for('vehicle_key_monitor'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == "rev180325":  # ✅ Set a secure password
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Incorrect password, try again!", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

# Route for homepage (empty for now)
@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'admin_logged_in' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            new_employee = Employee(name=name)
            db.session.add(new_employee)
            db.session.commit()

    employees = Employee.query.all()
    time_tracker_users = TimeTrackerUser.query.all()  # Fetch all Time Tracker users
    vehicle_key_users = VehicleKeyUser.query.all()  # Fetch all Vehicle Key Monitor users


    for emp in employees:
        # Calculate total worked hours (in minutes)
        total_minutes = sum(session.total_hours() for session in emp.sessions)
        total_hours = total_minutes // 60  # Convert minutes to hours
        total_remaining_minutes = total_minutes % 60  # Get remaining minutes
        emp.total_worked_hours = f"{total_hours}:{total_remaining_minutes:02d}"

        # Calculate overtime (assuming 6 days a week, 8 hours per day)
        workdays = sum(1 for i in range((datetime.now() - datetime(datetime.now().year, datetime.now().month, 1)).days)
                       if (datetime(datetime.now().year, datetime.now().month, 1) + timedelta(days=i)).weekday() < 6)

        # Total expected hours in a month (6 days a week, 8 hours per day)
        expected_hours = workdays * 8  # 8 hours per workday
        overtime_hours = max(total_hours - expected_hours, 0)  # Overtime can't be negative

        # Store the calculated overtime hours in the employee
        emp.monthly_overtime = overtime_hours

    db.session.commit()  # Commit the overtime changes to the database

    return render_template('admin_dashboard.html', employees=employees, 
                       time_tracker_users=time_tracker_users, vehicle_key_users=vehicle_key_users)

from werkzeug.security import generate_password_hash, check_password_hash

@app.route('/register_time_tracker_user', methods=['POST'])
def register_time_tracker_user():
    if 'admin_logged_in' not in session:
        flash("You must be logged in as admin to register users.", "danger")
        return redirect(url_for('login'))

    username = request.form.get('username')
    password = request.form.get('password')

    existing_user = TimeTrackerUser.query.filter_by(username=username).first()
    if existing_user:
        flash("Username already exists! Choose another.", "danger")
        return redirect(url_for('admin_dashboard'))

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    new_user = TimeTrackerUser(username=username, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    flash(f"User {username} registered successfully for Employee Time Tracker!", "success")
    return redirect(url_for('admin_dashboard'))

from werkzeug.security import generate_password_hash, check_password_hash

@app.route('/reset_vehicle_key_user_password', methods=['POST'])
def reset_vehicle_key_user_password():
    if 'admin_logged_in' not in session:
        return redirect(url_for('login'))

    user_id = request.form.get('user_id')
    new_password = request.form.get('new_password')

    user = VehicleKeyUser.query.get(user_id)
    if user:
        hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
        user.password = hashed_password
        db.session.commit()
        flash(f"Password reset successfully for {user.username}", "success")
    
    return redirect(url_for('admin_dashboard'))

@app.route('/remove_vehicle_key_user/<int:id>', methods=['GET'])
def remove_vehicle_key_user(id):
    if 'admin_logged_in' not in session:
        return redirect(url_for('login'))

    user = VehicleKeyUser.query.get(id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.username} has been removed.", "success")
    
    return redirect(url_for('admin_dashboard'))

@app.route('/remove_time_tracker_user/<int:id>', methods=['GET'])
def remove_time_tracker_user(id):
    if 'admin_logged_in' not in session:
        flash("You must be logged in as admin to remove users.", "danger")
        return redirect(url_for('login'))

    user = TimeTrackerUser.query.get(id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.username} has been removed.", "success")
    else:
        flash("User not found.", "danger")

    return redirect(url_for('admin_dashboard'))

# After employee removal, redirect back to Employee Time Tracker page
@app.route('/remove_employee/<int:id>', methods=['GET'])
def remove_employee(id):
    employee = Employee.query.get(id)
    
    if employee:
        # ✅ Delete all work sessions related to this employee first
        WorkSession.query.filter_by(employee_id=employee.id).delete()

        # ✅ Delete all vehicle key records related to this employee
        VehicleKey.query.filter_by(employee_id=employee.id).delete()

        # ✅ Now delete the employee
        db.session.delete(employee)
        db.session.commit()

    return redirect(url_for('admin_dashboard'))

# Route for Employee Time Tracker page
@app.route('/employee_time_tracker')
def employee_time_tracker():
    if 'time_tracker_logged_in' not in session:
        flash("You must be logged in to access this page.", "danger")
        return redirect(url_for('time_tracker_login'))

    employees = Employee.query.all()

    for emp in employees:
        total_minutes = sum(session.total_hours() for session in emp.sessions)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        emp.total_worked_hours = f"{hours}:{minutes:02d}"

    return render_template('index.html', employees=employees)

# Route for clocking in
@app.route('/clock_in/<int:id>')
def clock_in(id):
    employee = Employee.query.get(id)
    if employee:
        new_session = WorkSession(employee_id=employee.id, clock_in=datetime.now())  # ✅ Create new session
        db.session.add(new_session)
        db.session.commit()
    return redirect(url_for('employee_time_tracker'))

# Route for clocking out
@app.route('/clock_out/<int:id>')
def clock_out(id):
    employee = Employee.query.get(id)
    if employee:
        session = WorkSession.query.filter_by(employee_id=employee.id, clock_out=None).first()
        if session:
            session.clock_out = datetime.now()
            db.session.commit()
    return redirect(url_for('employee_time_tracker'))

@app.route('/manual_clock_out', methods=['POST'])
def manual_clock_out():
    employee_id = request.form.get('employee_id')
    clock_out_time = request.form.get('clock_out_time')

    if employee_id and clock_out_time:
        employee = Employee.query.get(employee_id)
        
        if employee:
            # Find the most recent clock-in session that has not been clocked out
            session = WorkSession.query.filter_by(employee_id=employee.id, clock_out=None).order_by(WorkSession.clock_in.desc()).first()
            
            if session:
                session.clock_out = datetime.strptime(clock_out_time, '%Y-%m-%dT%H:%M')  # Convert to datetime format
                db.session.commit()
                flash(f"Clock-out time manually set for {employee.name}", "success")

    return redirect(url_for('admin_dashboard'))

# Route for returning vehicle key (update the key return time)
@app.route('/return_vehicle_key/<int:id>')
def return_vehicle_key(id):
    vehicle_key = VehicleKey.query.get(id)
    if vehicle_key:
        vehicle_key.key_return_time = datetime.now()
        db.session.commit()
    return redirect(url_for('vehicle_key_monitor'))

@app.route('/vehicle_key_monitor')
def vehicle_key_monitor():
    if 'vehicle_key_logged_in' not in session:  # 🔒 Check if user is logged in
        flash("You must be logged in to access this page.", "danger")
        return redirect(url_for('vehicle_key_login'))

    employees = Employee.query.all()
    vehicle_keys = VehicleKey.query.filter_by(key_return_time=None).all()

    return render_template('vehicle_key_monitor.html', employees=employees, vehicle_keys=vehicle_keys)

from werkzeug.security import generate_password_hash, check_password_hash

# Route to register new vehicle key users
@app.route('/register_vehicle_key_user', methods=['POST'])
def register_vehicle_key_user():
    if 'admin_logged_in' not in session:
        flash("You must be logged in as admin to register users.", "danger")
        return redirect(url_for('login'))

    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for('admin_dashboard'))

    existing_user = VehicleKeyUser.query.filter_by(username=username).first()
    if existing_user:
        flash("Username already exists! Choose another.", "danger")
        return redirect(url_for('admin_dashboard'))

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    new_user = VehicleKeyUser(username=username, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    flash(f"User {username} registered successfully for Vehicle Key Monitor!", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/vehicle_key_login', methods=['GET', 'POST'])
def vehicle_key_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = VehicleKeyUser.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session.clear()  # 🚀 Ensure previous sessions are removed
            session['vehicle_key_logged_in'] = user.id  # Store specific user ID
            flash("Login successful!", "success")
            return redirect(url_for('vehicle_key_monitor'))
        else:
            flash("Incorrect username or password!", "danger")

    return render_template('vehicle_key_login.html')

@app.route('/time_tracker_login', methods=['GET', 'POST'])
def time_tracker_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = TimeTrackerUser.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session.clear()  # 🚀 Ensure previous sessions are removed
            session['time_tracker_logged_in'] = user.id  # Store specific user ID
            flash("Login successful!", "success")
            return redirect(url_for('employee_time_tracker'))
        else:
            flash("Incorrect username or password!", "danger")

    return render_template('time_tracker_login.html')

@app.route('/time_tracker_logout')
def time_tracker_logout():
    session.pop('time_tracker_logged_in', None)
    flash("You have been logged out.", "success")
    return redirect(url_for('time_tracker_login'))

@app.route('/vehicle_key_logout')
def vehicle_key_logout():
    session.pop('vehicle_key_logged_in', None)
    flash("You have been logged out.", "success")
    return redirect(url_for('vehicle_key_login'))

@app.route('/previous_key_logs')
def previous_key_logs():
    vehicle_keys = VehicleKey.query.filter(VehicleKey.key_return_time.isnot(None)).all()  # ✅ Show only returned keys

    return render_template('previous_key_logs.html', vehicle_keys=vehicle_keys)

@app.route('/test')
def test():
    return "Flask is working!"

@app.route('/delete_employee_logs/<int:employee_id>', methods=['GET'])
def delete_employee_logs(employee_id):
    employee = Employee.query.get(employee_id)
    
    if employee:
        # Delete all work sessions related to this employee
        WorkSession.query.filter_by(employee_id=employee.id).delete()

        # Commit the changes to the database
        db.session.commit()
        flash(f"Employee logs for {employee.name} have been successfully deleted.", "success")
    else:
        flash("Employee not found.", "danger")

    # Redirect back to the admin dashboard
    return redirect(url_for('admin_dashboard'))

@app.route('/download_employee_pdf/<int:employee_id>')
def download_employee_pdf(employee_id):
    employee = Employee.query.get(employee_id)
    if not employee:
        flash("Employee not found!", "danger")
        return redirect(url_for('admin_dashboard'))

    # Calculate total worked hours from work sessions
    total_minutes = sum(session.total_hours() for session in employee.sessions)  # Total minutes worked
    total_hours = total_minutes // 60  # Convert minutes to hours
    total_remaining_minutes = total_minutes % 60  # Get remaining minutes
    total_worked_hours = f"{total_hours}:{total_remaining_minutes:02d}"  # Format as HH:MM

    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(200, 10, txt=f"Employee Report: {employee.name}", ln=True, align='C')

    pdf.ln(10)

    # Total Hours & Overtime
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(200, 10, txt=f"Total Hours Worked: {total_worked_hours}", ln=True, align='L')
    pdf.cell(200, 10, txt=f"Overtime Hours: {employee.monthly_overtime} hrs", ln=True, align='L')

    pdf.ln(10)

    # Table Header
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(65, 10, txt="Clock In Time", border=1, align='C')
    pdf.cell(65, 10, txt="Clock Out Time", border=1, align='C')
    pdf.cell(60, 10, txt="Hours Worked", border=1, align='C')
    pdf.ln()

    # Work Sessions
    pdf.set_font('Arial', '', 10)
    if employee.sessions:
        for session in employee.sessions:
            # Include weekday in the Clock In and Clock Out times
            clock_in = session.clock_in.strftime('%A, %d/%m/%Y %H:%M:%S')  # Added %A for full weekday name
            clock_out = session.clock_out.strftime('%A, %d/%m/%Y %H:%M:%S') if session.clock_out else "Still Working"  # Added %A for full weekday name
            hours_worked = session.total_hours() // 60  # Convert minutes to hours

            pdf.cell(65, 10, txt=clock_in, border=1, align='C')
            pdf.cell(65, 10, txt=clock_out, border=1, align='C')
            pdf.cell(60, 10, txt=f"{hours_worked} hrs", border=1, align='C')
            pdf.ln()
    else:
        pdf.cell(190, 10, txt="No work sessions available", border=1, align='C')
        pdf.ln()

    pdf_path = f"employee_report_{employee.id}.pdf"
    pdf.output(pdf_path)

    return send_file(pdf_path, as_attachment=True)

import pandas as pd

@app.route('/export_vehicle_keys')
def export_vehicle_keys():
    vehicle_keys = VehicleKey.query.all()

    # Convert Data to Pandas DataFrame
    data = []
    for vk in vehicle_keys:
        data.append({
            "Employee Name": vk.employee.name,
            "Key Number": vk.key_number,
            "Key Checkout Time": vk.key_checkout_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Key Return Time": vk.key_return_time.strftime("%Y-%m-%d %H:%M:%S") if vk.key_return_time else "Not Returned"
        })
    
    df = pd.DataFrame(data)
    file_path = "vehicle_keys_report.xlsx"
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True)
#Generate pdf
from fpdf import FPDF
from datetime import datetime, timedelta

def generate_employee_pdf(employee):
    """Generate PDF for each employee and save it"""
    now = datetime.now()
    first_day_of_this_month = datetime(now.year, now.month, 1)
    first_day_of_last_month = first_day_of_this_month - timedelta(days=1)
    first_day_of_last_month = datetime(first_day_of_last_month.year, first_day_of_last_month.month, 1)

    # Calculate total worked hours from work sessions for the previous month
    sessions = WorkSession.query.filter(
        WorkSession.employee_id == employee.id,
        WorkSession.clock_in >= first_day_of_last_month,
        WorkSession.clock_out < first_day_of_this_month
    ).all()

    total_minutes = sum(session.total_hours() for session in sessions)  # Total minutes worked
    total_hours = total_minutes // 60  # Convert minutes to hours
    total_remaining_minutes = total_minutes % 60  # Get remaining minutes
    total_worked_hours = f"{total_hours}:{total_remaining_minutes:02d}"  # Format as HH:MM

    # Calculate overtime hours (assuming 8 hours work per day)
    workdays = sum(1 for i in range((first_day_of_this_month - first_day_of_last_month).days)
                   if (first_day_of_last_month + timedelta(days=i)).weekday() < 6)
    expected_hours = workdays * 8
    overtime_hours = max(total_hours - expected_hours, 0)

    # Create PDF for employee
    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(200, 10, txt=f"Employee Report: {employee.name}", ln=True, align='C')

    pdf.ln(10)

    # Total Hours & Overtime
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(200, 10, txt=f"Total Hours Worked: {total_worked_hours}", ln=True, align='L')
    pdf.cell(200, 10, txt=f"Overtime Hours: {overtime_hours} hrs", ln=True, align='L')

    pdf.ln(10)

    # Table Header
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(65, 10, txt="Clock In Time", border=1, align='C')
    pdf.cell(65, 10, txt="Clock Out Time", border=1, align='C')
    pdf.cell(60, 10, txt="Hours Worked", border=1, align='C')
    pdf.ln()

    # Work Sessions
    pdf.set_font('Arial', '', 10)
    if sessions:
        for session in sessions:
            clock_in = session.clock_in.strftime('%d/%m/%Y %H:%M:%S')
            clock_out = session.clock_out.strftime('%d/%m/%Y %H:%M:%S') if session.clock_out else "Still Working"
            hours_worked = session.total_hours() // 60  # Convert minutes to hours

            pdf.cell(65, 10, txt=clock_in, border=1, align='C')
            pdf.cell(65, 10, txt=clock_out, border=1, align='C')
            pdf.cell(60, 10, txt=f"{hours_worked} hrs", border=1, align='C')
            pdf.ln()
    else:
        pdf.cell(190, 10, txt="No work sessions available", border=1, align='C')
        pdf.ln()

    # Save the PDF
    pdf_output_path = f"employee_report_{employee.id}_month_{datetime.now().strftime('%Y_%m')}.pdf"
    pdf.output(pdf_output_path)
    print(f"Generated PDF for {employee.name}: {pdf_output_path}")

# Function to reset Employee Time Tracker logs at 00:00 every night
from fpdf import FPDF
from datetime import datetime, timedelta

def generate_employee_pdf(employee):
    """Generate PDF for each employee and save it"""
    now = datetime.now()
    first_day_of_this_month = datetime(now.year, now.month, 1)
    first_day_of_last_month = first_day_of_this_month - timedelta(days=1)
    first_day_of_last_month = datetime(first_day_of_last_month.year, first_day_of_last_month.month, 1)

    # Get all work sessions for the previous month
    sessions = WorkSession.query.filter(
        WorkSession.employee_id == employee.id,
        WorkSession.clock_in >= first_day_of_last_month,
        WorkSession.clock_out < first_day_of_this_month
    ).all()

    # Calculate total worked hours in minutes
    total_minutes = sum(session.total_hours() for session in sessions)  # Total minutes worked
    total_hours = total_minutes // 60  # Convert minutes to hours
    total_remaining_minutes = total_minutes % 60  # Get remaining minutes
    total_worked_hours = f"{total_hours}:{total_remaining_minutes:02d}"

    # Calculate workdays (Monday-Saturday)
    workdays = sum(1 for i in range((first_day_of_this_month - first_day_of_last_month).days)
                   if (first_day_of_last_month + timedelta(days=i)).weekday() < 6)

    # Calculate expected hours (6 days a week, 8 hours per day)
    expected_hours = workdays * 8
    expected_minutes = expected_hours * 60  # Convert expected hours to minutes

    # Calculate overtime (in minutes) and convert to hours
    overtime_minutes = max(total_minutes - expected_minutes, 0)  # Overtime in minutes
    overtime_hours = overtime_minutes // 60  # Convert overtime minutes to hours
    overtime_remaining_minutes = overtime_minutes % 60  # Remaining minutes after overtime hours

    # Create PDF for employee
    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(200, 10, txt=f"Employee Report: {employee.name}", ln=True, align='C')

    pdf.ln(10)

    # Total Hours & Overtime
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(200, 10, txt=f"Total Hours Worked: {total_worked_hours}", ln=True, align='L')
    pdf.cell(200, 10, txt=f"Overtime: {overtime_hours} hrs {overtime_remaining_minutes} mins", ln=True, align='L')

    pdf.ln(10)

    # Table Header
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(65, 10, txt="Clock In Time", border=1, align='C')
    pdf.cell(65, 10, txt="Clock Out Time", border=1, align='C')
    pdf.cell(60, 10, txt="Hours Worked", border=1, align='C')
    pdf.ln()

    # Work Sessions
    pdf.set_font('Arial', '', 10)
    if sessions:
        for session in sessions:
            clock_in = session.clock_in.strftime('%d/%m/%Y %H:%M:%S')
            clock_out = session.clock_out.strftime('%d/%m/%Y %H:%M:%S') if session.clock_out else "Still Working"
            hours_worked = session.total_hours() // 60  # Convert minutes to hours

            pdf.cell(65, 10, txt=clock_in, border=1, align='C')
            pdf.cell(65, 10, txt=clock_out, border=1, align='C')
            pdf.cell(60, 10, txt=f"{hours_worked} hrs", border=1, align='C')
            pdf.ln()
    else:
        pdf.cell(190, 10, txt="No work sessions available", border=1, align='C')
        pdf.ln()

    # Save the PDF
    pdf_output_path = f"employee_report_{employee.id}_month_{datetime.now().strftime('%Y_%m')}.pdf"
    pdf.output(pdf_output_path)
    print(f"Generated PDF for {employee.name}: {pdf_output_path}")

def reset_employee_time_tracker():
    with app.app_context():
        # Get current and previous month
        now = datetime.now()
        first_day_of_this_month = datetime(now.year, now.month, 1)
        first_day_of_last_month = first_day_of_this_month - timedelta(days=1)
        first_day_of_last_month = datetime(first_day_of_last_month.year, first_day_of_last_month.month, 1)

        # Generate PDF and calculate overtime for each employee
        employees = Employee.query.all()
        for emp in employees:
            # Generate and save the PDF for the employee
            generate_employee_pdf(emp)

            # Calculate and save overtime for the employee
            total_minutes = sum(session.total_hours() for session in emp.sessions)
            total_hours_worked = total_minutes // 60
            workdays = sum(1 for i in range((first_day_of_this_month - first_day_of_last_month).days)
                           if (first_day_of_last_month + timedelta(days=i)).weekday() < 6)
            expected_hours = workdays * 8
            overtime_hours = max(total_hours_worked - expected_hours, 0)  # Overtime can't be negative
            emp.monthly_overtime = overtime_hours

        # Commit the overtime changes
        db.session.commit()

        # Delete all work session logs after saving overtime
        db.session.query(WorkSession).delete()
        db.session.commit()

        print("✅ Employee Time Tracker reset at midnight with overtime saved and PDFs generated!")

# Set up the scheduler to run at 00:00 on the 1st of each month
scheduler = BackgroundScheduler()
scheduler.add_job(func=reset_employee_time_tracker, trigger=CronTrigger(day=1, hour=0, minute=0))  # Runs on the 1st of every month at midnight
scheduler.start()

# Ensure the scheduler shuts down when the app exits
atexit.register(lambda: scheduler.shutdown())


if __name__ == '__main__':
    # Create the database tables
    with app.app_context():
        db.create_all()
    app.run(debug=True)
