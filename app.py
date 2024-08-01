import os
import uuid
import re
import datetime
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g,Response
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import generate_csrf, CSRFProtect
from flask_cors import CORS
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import csv
from io import StringIO

app = Flask(__name__)
CORS(app)
CSRFProtect(app)

# Load configuration from environment variables or default values
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///new_events.db')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallbacksecret')
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'uploads/')
app.config['WTF_CSRF_ENABLED'] = True

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class Organization(db.Model):
    """Model for organization."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    type = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    web_portal = db.Column(db.String(200), nullable=False)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    organization = db.relationship('Organization', backref='users')
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

class Event(db.Model):
    """Model for event."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.String(10), nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    end_date = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    venue = db.Column(db.String(200), nullable=True)
    description = db.Column(db.String(1000), nullable=False)
    image_url = db.Column(db.String(200), nullable=True)
    archive_date = db.Column(db.String(10), nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    organization = db.relationship('Organization', backref='events')

    @property
    def serialize(self) -> dict:
        """Serialize event data."""
        return {
            'id': self.id,
            'title': self.title,
            'language': self.language,
            'category': self.category,
            'start_date': self.start_date,
            'start_time': self.start_time,
            'end_date': self.end_date,
            'end_time': self.end_time,
            'state': self.state,
            'city': self.city,
            'venue': self.venue,
            'description': self.description,
            'image_url': self.image_url,
            'archive_date': self.archive_date,
            'organization_name': self.organization.name if self.organization else 'N/A'
        }

@login_manager.user_loader
def load_user(user_id: int) -> User:
    """Load user by ID."""
    return User.query.get(int(user_id))

@app.before_request
def load_logged_in_user() -> None:
    """Load the logged-in user into Flask global variable."""
    user_id = session.get('user_id')
    g.user = User.query.get(user_id) if user_id else None

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Handle admin login."""
    organizations = Organization.query.all()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = request.form.get('is_admin', 'false') == 'true'
        
        user_query = User.query.filter_by(username=username)
        if is_admin:
            user_query = user_query.filter_by(is_admin=True)
        
        user = user_query.first()
        
        if user and user.check_password(password):
            login_user(user)
            if is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        flash('Login Unsuccessful. Please check username and password', 'danger')
    
    return render_template('login.html', organizations=organizations)


@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Render admin dashboard with all organizations and events."""
    if not current_user.is_admin:
        flash('Access denied: Admins only.')
        return redirect(url_for('login'))

    # Query to get the number of events for each organization
    org_event_count = db.session.query(
        Organization.name, db.func.count(Event.id)
    ).join(Event).group_by(Organization.name).all()

    # Prepare data for Chart.js
    labels = [org for org, _ in org_event_count]
    values = [count for _, count in org_event_count]

    # Query to get event timelines by month
    current_year = datetime.datetime.now().year
    monthly_events = db.session.query(
        db.func.strftime('%Y-%m', Event.start_date).label('month'), db.func.count(Event.id)
    ).filter(db.func.strftime('%Y', Event.start_date) == str(current_year)).group_by('month').all()
    
    months = [event[0] for event in monthly_events]
    event_counts = [event[1] for event in monthly_events]

    # Query to get event categories and their counts
    category_count = db.session.query(
        Event.category, db.func.count(Event.id)
    ).group_by(Event.category).all()

    category_labels = [category for category, _ in category_count]
    category_values = [count for _, count in category_count]

    # Calculate percentages for categories
    total_events = sum(category_values)
    category_percentages = [(category, (count / total_events) * 100) for category, count in category_count] if total_events > 0 else []

    max_category = max(category_percentages, key=lambda x: x[1]) if category_percentages else ("N/A", 0)
    min_category = min(category_percentages, key=lambda x: x[1]) if category_percentages else ("N/A", 0)

    return render_template('admin_dashboard.html', 
                           labels=labels, 
                           values=values, 
                           months=months, 
                           event_counts=event_counts, 
                           category_labels=category_labels, 
                           category_values=category_values, 
                           max_category=max_category, 
                           min_category=min_category)


@app.route('/admin/download_report', methods=['GET', 'POST'])
@login_required
def download_report():
    """Download comprehensive report of events created by each organization."""
    if not current_user.is_admin:
        flash('Access denied: Admins only.')
        return redirect(url_for('login'))

    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    query = db.session.query(
        Organization.name, Event.title, Event.start_date, Event.end_date, Event.category
    ).join(Event).order_by(Organization.name, Event.start_date)

    if start_date and end_date:
        query = query.filter(Event.start_date >= start_date, Event.end_date <= end_date)

    events = query.all()

    def generate():
        data = StringIO()
        writer = csv.writer(data)
        writer.writerow(('Organization Name', 'Event Title', 'Start Date', 'End Date', 'Category'))
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)

        for row in events:
            writer.writerow(row)
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    response = Response(generate(), mimetype='text/csv')
    response.headers.set('Content-Disposition', 'attachment', filename='event_report.csv')
    return response

@app.route('/admin/logout')
@login_required
def admin_logout():
    if not current_user.is_admin:
        flash('Access denied: Admins only.')
        return redirect(url_for('login'))
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('login'))


def allowed_file(filename: str) -> bool:
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}

def validate_string_no_special_chars(input_string: str) -> bool:
    """Validate string to ensure it has no special characters."""
    return bool(re.match("^[A-Za-z0-9 _]*$", input_string))

def validate_event_data(name: str, start_date: str, end_date: str, state: str, city: str, description: str, event_image) -> bool:
    """Validate event data."""
    if not name or len(name) > 100 or not validate_string_no_special_chars(name):
        flash('Event name is required, must be under 100 characters, and cannot contain special characters.')
        return False
    
    try:
        event_start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        event_end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        if event_start_date < datetime.datetime.now():
            flash('Event start date cannot be in the past.')
            return False
        if event_end_date < event_start_date:
            flash('Event end date cannot be before the event start date.')
            return False
    except ValueError:
        flash('Invalid date format. Expected YYYY-MM-DD.')
        return False
    
    if not state or len(state) > 100 or not validate_string_no_special_chars(state):
        flash('Event state is required, must be under 100 characters, and cannot contain special characters.')
        return False

    if not city or len(city) > 100 or not validate_string_no_special_chars(city):
        flash('Event city is required, must be under 100 characters, and cannot contain special characters.')
        return False
    
    if not description or len(description) > 500:
        flash('Event description is required and must be under 500 characters.')
        return False
    
    if event_image:
        if not allowed_file(event_image.filename):
            flash('Invalid image format. Allowed formats are PNG, JPG, JPEG.')
            return False
        if event_image.content_length > 5 * 1024 * 1024:  # 5 MB
            flash('Image file size must be under 5 MB.')
            return False

    return True

def save_uploaded_file(event_image) -> str:
    """Save the uploaded file and return its path."""
    if event_image:
        ext = secure_filename(event_image.filename).rsplit('.', 1)[1].lower()
        filename = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.{ext}")
        event_image.save(filename)
        return filename
    return None

# Load state and city data
with open('indian_state_city_list.json', 'r') as f:
    data = json.load(f)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration."""
    organizations = Organization.query.all()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        organization_id = request.form['organization_id']
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists.')
            return redirect(url_for('register'))

        new_user = User(username=username, organization_id=organization_id)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful, please login.')
        return redirect(url_for('login'))
    return render_template('register.html', organizations=organizations)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    organizations = Organization.query.all()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        organization_id = request.form['organization_id']
        user = User.query.filter_by(username=username, organization_id=organization_id).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Login Unsuccessful. Please check username, password, and organization', 'danger')
    return render_template('login.html', organizations=organizations)

@app.route('/logout')
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def dashboard():
    """Render dashboard with all events posted by the same type of organization as the logged-in user."""
    if request.method == 'POST':
        title = request.form.get('title')
        language = request.form.get('language', 'English')
        category = request.form.get('category', 'General')
        start_date = request.form['start_date']
        start_time = request.form['start_time']
        end_date = request.form['end_date']
        end_time = request.form['end_time']
        state = request.form['state']
        city = request.form['city']
        venue = request.form.get('venue')
        description = request.form['description']
        archive_date = request.form.get('archive_date')
        event_image = request.files.get('image_url')

        if Event.query.filter_by(title=title, start_date=start_date, end_date=end_date).first():
            flash('An event with the same title, start date, and end date already exists.')
            return redirect(request.url)

        if not validate_event_data(title, start_date, end_date, state, city, description, event_image):
            return redirect(request.url)

        filename = save_uploaded_file(event_image) if event_image else None

        new_event = Event(
            title=title,
            language=language,
            category=category,
            start_date=start_date,
            start_time=start_time,
            end_date=end_date,
            end_time=end_time,
            state=state,
            city=city,
            venue=venue,
            description=description,
            image_url=filename,
            archive_date=archive_date,
            organization_id=current_user.organization_id
        )
        db.session.add(new_event)
        db.session.commit()
        flash('Event Added Successfully!')

    organization_type = current_user.organization.type
    all_events = Event.query.join(Organization).filter(Organization.type == organization_type).all()
    csrf_token = generate_csrf()
    organization = Organization.query.get(current_user.organization_id)
    states = list(set([entry['State'] for entry in data]))
    return render_template('dashboard.html', events=all_events, csrf_token=csrf_token, organization=organization, states=states, data=data)


@app.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    """Edit an existing event."""
    event = Event.query.get_or_404(event_id)
    csrf_token = generate_csrf()
    organization = Organization.query.get(current_user.organization_id)
    
    if request.method == 'POST':
        title = request.form['title']
        language = request.form.get('language')
        category = request.form.get('category')
        start_date = request.form['start_date']
        start_time = request.form['start_time']
        end_date = request.form['end_date']
        end_time = request.form['end_time']
        state = request.form['state']
        city = request.form['city']
        venue = request.form.get('venue')
        description = request.form['description']
        archive_date = request.form['archive_date']
        event_image = request.files.get('image_url')

        if not validate_event_data(title, start_date, end_date, state, city, description, event_image):
            flash('Event data is not valid')
            return redirect(request.url)

        if event_image and allowed_file(event_image.filename):
            filename = save_uploaded_file(event_image)
            if filename:
                old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], event.image_url) if event.image_url else None
                if old_image_path and os.path.isfile(old_image_path):
                    try:
                        os.remove(old_image_path)
                    except OSError as e:
                        flash(f'Error deleting old image file: {e.strerror}', 'warning')
                event.image_url = filename

        event.title = title
        event.language = language if language else event.language
        event.category = category if category else event.category
        event.start_date = start_date
        event.start_time = start_time
        event.end_date = end_date
        event.end_time = end_time
        event.state = state
        event.city = city
        event.venue = venue if venue else event.venue
        event.description = description
        event.archive_date = archive_date if archive_date else event.archive_date

        db.session.commit()
        flash('Event updated successfully!')
        return redirect(url_for('dashboard'))

    return render_template('edit_event.html', event=event, csrf_token=csrf_token, organization=organization)

@app.route('/view_event/<int:event_id>')
def view_event(event_id):
    """View details of an event."""
    event = Event.query.get_or_404(event_id)
    return render_template('view_event.html', event=event)

@app.route('/delete_event/<int:event_id>')
@login_required
def delete_event(event_id):
    """Delete an event."""
    event = Event.query.get_or_404(event_id)
    try:
        db.session.delete(event)
        db.session.commit()
        flash('Event deleted successfully!')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the event.')
    return redirect(url_for('dashboard'))

@app.route('/delete_all_events')
@login_required
def delete_all_events():
    """Delete all events."""
    try:
        num_deleted = Event.query.delete()
        db.session.commit()
        flash(f'All events deleted successfully! Total: {num_deleted}')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting all events.')
    return redirect(url_for('dashboard'))

@app.route('/api/events', methods=['GET'])
def get_events():
    """Get all events."""
    all_events = Event.query.all()
    return jsonify([e.serialize for e in all_events]), 200

@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event_details(event_id):
    """Get event details by ID."""
    event = Event.query.get_or_404(event_id)
    return jsonify(event.serialize), 200

@app.route('/api/today-events', methods=['GET'])
def today_events():
    """Get today's events."""
    today = datetime.date.today()
    events = Event.query.filter(Event.start_date <= today, Event.end_date >= today).all()
    return jsonify([event.serialize for event in events]), 200

@app.route('/api/past-events', methods=['GET'])
def past_events():
    """Get past events."""
    today = datetime.date.today()
    events = Event.query.filter(Event.end_date < today).all()
    return jsonify([event.serialize for event in events]), 200

@app.route('/api/upcoming-events', methods=['GET'])
def upcoming_events():
    """Get upcoming events."""
    today = datetime.date.today()
    events = Event.query.filter(Event.start_date > today).all()
    return jsonify([event.serialize for event in events]), 200

@app.route('/api/all-events', methods=['GET'])
def all_events_api():
    """Get all events with optional filters."""
    query = Event.query
    state = request.args.get('state')
    city = request.args.get('city')
    category = request.args.get('category')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if state:
        query = query.filter(Event.state == state)
    if city:
        query = query.filter(Event.city == city)
    if category:
        query = query.filter(Event.category == category)
    if start_date:
        query = query.filter(Event.start_date >= datetime.datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(Event.end_date <= datetime.datetime.strptime(end_date, '%Y-%m-%d'))

    events = query.all()
    return jsonify([event.serialize for event in events]), 200

@app.route('/api/events', methods=['POST'])
def create_event():
    """Create a new event."""
    data = request.form
    title = data.get('title')
    language = data.get('language')
    category = data.get('category')
    start_date = data.get('start_date')
    start_time = data.get('start_time')
    end_date = data.get('end_date')
    end_time = data.get('end_time')
    state = data.get('state')
    city = data.get('city')
    venue = data.get('venue')
    description = data.get('description')
    archive_date = data.get('archive_date')
    event_image = request.files.get('image_url')

    if not validate_event_data(title, start_date, end_date, state, city, description, event_image):
        return jsonify({'error': 'Invalid event data'}), 400

    filename = save_uploaded_file(event_image) if event_image else None

    new_event = Event(
        title=title,
        language=language,
        category=category,
        start_date=start_date,
        start_time=start_time,
        end_date=end_date,
        end_time=end_time,
        state=state,
        city=city,
        venue=venue,
        description=description,
        image_url=filename,
        archive_date=archive_date,
        organization_id=current_user.organization_id
    )
    db.session.add(new_event)
    db.session.commit()

    return jsonify(new_event.serialize), 201

@app.route('/api/events/<int:event_id>', methods=['PUT'])
def update_event(event_id):
    """Update an existing event."""
    event = Event.query.get_or_404(event_id)
    data = request.form
    title = data.get('title')
    language = data.get('language')
    category = data.get('category')
    start_date = data.get('start_date')
    start_time = data.get('start_time')
    end_date = data.get('end_date')
    end_time = data.get('end_time')
    state = data.get('state')
    city = data.get('city')
    venue = data.get('venue')
    description = data.get('description')
    archive_date = data.get('archive_date')
    event_image = request.files.get('image_url')

    if not validate_event_data(title, start_date, end_date, state, city, description, event_image):
        return jsonify({'error': 'Invalid event data'}), 400

    if event_image and allowed_file(event_image.filename):
        filename = save_uploaded_file(event_image)
        if filename:
            old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], event.image_url) if event.image_url else None
            if old_image_path and os.path.isfile(old_image_path):
                try:
                    os.remove(old_image_path)
                except OSError as e:
                    flash(f'Error deleting old image file: {e.strerror}', 'warning')
            event.image_url = filename

    event.title = title
    event.language = language if language else event.language
    event.category = category if category else event.category
    event.start_date = start_date
    event.start_time = start_time
    event.end_date = end_date
    event.end_time = end_time
    event.state = state
    event.city = city
    event.venue = venue if venue else event.venue
    event.description = description
    event.archive_date = archive_date if archive_date else event.archive_date

    db.session.commit()

    return jsonify(event.serialize), 200

@app.route('/api/events/<int:event_id>', methods=['DELETE'])
def delete_event_api(event_id):
    """Delete an event via API."""
    event = Event.query.get_or_404(event_id)
    try:
        db.session.delete(event)
        db.session.commit()
        return jsonify({'message': 'Event deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'An error occurred while deleting the event'}), 500

@app.route('/api/search-events', methods=['GET'])
def search_events():
    """Search for events."""
    title = request.args.get('title')
    state = request.args.get('state')
    city = request.args.get('city')
    category = request.args.get('category')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = Event.query

    if title:
        query = query.filter(Event.title.ilike(f'%{title}%'))
    if state:
        query = query.filter(Event.state == state)
    if city:
        query = query.filter(Event.city == city)
    if category:
        query = query.filter(Event.category == category)
    if start_date:
        query = query.filter(Event.start_date >= datetime.datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(Event.end_date <= datetime.datetime.strptime(end_date, '%Y-%m-%d'))

    events = query.all()
    return jsonify([event.serialize for event in events]), 200

@app.route('/api/event-categories', methods=['GET'])
def event_categories():
    """Get distinct event categories."""
    categories = db.session.query(Event.category.distinct()).all()
    return jsonify([c[0] for c in categories]), 200

@app.route('/api/events/category/<string:category>', methods=['GET'])
def events_by_category(category: str):
    """Get events by category."""
    events = Event.query.filter_by(category=category).all()
    return jsonify([event.serialize for event in events]), 200

@app.route('/api/user-events/<int:user_id>', methods=['GET'])
def user_events(user_id: int):
    """Get events created by a specific user."""
    user = User.query.get_or_404(user_id)
    events = Event.query.filter_by(user_id=user.id).all()
    return jsonify([event.serialize for event in events]), 200

@app.route('/api/favorite-events', methods=['POST'])
def favorite_event():
    """Add an event to user favorites."""
    data = request.get_json()
    user_id = data.get('user_id')
    event_id = data.get('event_id')
    user = User.query.get_or_404(user_id)
    event = Event.query.get_or_404(event_id)
    user.favorites.append(event)
    db.session.commit()
    return jsonify({'message': 'Event added to favorites'}), 200

@app.route('/api/user-favorites/<int:user_id>', methods=['GET'])
def user_favorites(user_id: int):
    """Get user's favorite events."""
    user = User.query.get_or_404(user_id)
    return jsonify([event.serialize for event in user.favorites]), 200

@app.route('/api/events/archive/<int:event_id>', methods=['PUT'])
def archive_event(event_id: int):
    """Archive an event."""
    event = Event.query.get_or_404(event_id)
    event.archive_date = datetime.datetime.now().strftime("%Y-%m-%d")
    db.session.commit()
    return jsonify({'message': 'Event archived successfully'}), 200

@app.route('/searchevents')
def search_event():
    """Render the search events page."""
    return render_template('searchevents.html')

def create_or_update_admin_user():
    with app.app_context():
        username = 'admin'
        password = 'adminpassword'
        organization_id = 3  # Set this to the correct organization ID for the admin user

        # Check if the admin user already exists
        admin_user = User.query.filter_by(username=username).first()
        
        if admin_user:
            # Update the existing admin user's password
            admin_user.password_hash = generate_password_hash(password)
            print("Admin user password updated successfully")
        else:
            # Create a new admin user
            new_admin_user = User(
                username=username,
                password_hash=generate_password_hash(password),
                organization_id=organization_id,
                is_admin=True
            )
            db.session.add(new_admin_user)
            print("Admin user created successfully")
        
        db.session.commit()





    


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
  # Call the function
    create_or_update_admin_user()
    app.run(debug=True)
