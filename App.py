import smtplib
from datetime import datetime, timedelta
import secrets
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os
import werkzeug
from flask import Flask, render_template, redirect, url_for, request, send_from_directory, flash, get_flashed_messages
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Float
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import IntegrityError
from flask import flash, redirect, url_for, request, render_template
import re 
from flask import Flask, render_template, request
from flask import Flask, render_template, request


load_dotenv()


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.config['SECRET_KEY'] = '3f8c2e7a9b4d12f7c6a8e9f1b2d3c4e5f6a7b8c9d0e1f2a3b4c5d6e7f8g9h0i1'
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)


# user_loader callback
@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


class User(UserMixin, db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True, nullable=False)
    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    password: Mapped[str] = mapped_column(unique=False, nullable=False)


class RecoveryCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    code = db.Column(db.String(50), nullable=False, unique=True)
    expiry_time = db.Column(db.DateTime, nullable=False)

    user = db.relationship('User', back_populates='recovery_codes')


User.recovery_codes = db.relationship('RecoveryCode', back_populates='user', lazy=True)

with app.app_context():
    db.create_all()


@app.route('/')
def index():
    return render_template("index.html")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        existing_username = User.query.filter_by(username=username).first()
        existing_email = User.query.filter_by(email=email).first()

        if existing_username:
            flash("Username already exists. Please choose a different one.", "error")
            return render_template("register.html", username=username, email=email)

        if existing_email:
            flash("Email already exists. Please use a different email.", "error")
            return render_template("register.html", username=username, email=email)

        if len(password) < 8 or not re.search(r"\d", password) or not re.search(r"[A-Z]", password):
            flash("Password must be at least 8 characters long, contain one uppercase letter, and one number.", "error")
            return render_template("register.html", username=username, email=email)

        hash_password = generate_password_hash(password, method='pbkdf2:sha256:600000', salt_length=8)

        try:
            user = User(username=username, email=email, password=hash_password)
            db.session.add(user)
            db.session.commit()
            flash("Registration successful! You can now log in.", "success")
            return redirect(url_for("login"))

        except IntegrityError:
            db.session.rollback()
            flash("An error occurred. Please try again.", "error")
            return render_template("register.html", username=username, email=email)

    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if not user:
            user = User.query.filter_by(username=email).first()

        if user:
            if werkzeug.security.check_password_hash(user.password, password):
                login_user(user)
                flash("Login successful!", "success")  # Store the success message
                return redirect(url_for("secretz"))  # Redirect to the next page
            else:
                flash("Password is incorrect!", "error")
        else:
            flash("Username or email is incorrect!", "error")

    return render_template("login.html")

def send_recovery_email(to_email, code):
    from_email = "your mail id"
    from_password = "your app password"
    subject = 'Password Recovery Code-MediFetch'
    body = (f'Your recovery code is {code}.'
            f'It will expire in 15 minutes.'
            f'If Code expired kindly press resend code')

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(from_email, from_password)
            server.sendmail(from_email, to_email, msg.as_string())
            print(f"Recovery email sent successfully! to {to_email}")
    except Exception as e:
        print(f"Error sending email: {e}")


@app.route('/forgetpassword', methods=['GET', 'POST'])
def forgetpassword():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate a 4-byte hex recovery code
            code = secrets.token_hex(4)
            expiry_time = datetime.utcnow() + timedelta(minutes=15)

            # Store recovery code in the database
            recovery_code = RecoveryCode(user_id=user.id, code=code, expiry_time=expiry_time)
            db.session.add(recovery_code)
            db.session.commit()

            # Send recovery email
            send_recovery_email(user.email, code)

            flash(f"A recovery code has been sent to your email! {email}","success")
            return redirect(url_for('reset_password'))  # Redirect to reset password page

        else:
            flash("Invalid email. Please enter a registered email.", "error")

    return render_template("forget.html")
    

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get("email")
        code = request.form.get("code")
        new_password = request.form.get("password")

        print(email, code, new_password)

        # Check if the email exists
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Invalid email. Please enter a registered email.", "error")
            return redirect(url_for('reset_password'))

        # Check if recovery code exists and is still valid
        recovery_code = RecoveryCode.query.filter_by(user_id=user.id, code=code).first()
        if not recovery_code or recovery_code.expiry_time < datetime.utcnow():
            flash("Invalid or expired recovery code. Request a new one.", "error")
            return redirect(url_for('reset_password'))

        # Validate password strength
        if len(new_password) < 8 or not any(char.isdigit() for char in new_password) or not any(char.isupper() for char in new_password):
            flash("Password must be at least 8 characters long, contain an uppercase letter and a number.", "error")
            return redirect(url_for('reset_password'))

        # Update user password
        hash_password = generate_password_hash(new_password, method='pbkdf2:sha256:600000', salt_length=8)
        user.password = hash_password
        db.session.delete(recovery_code)  # Delete used recovery code
        db.session.commit()

        flash("Your password has been updated successfully!", "success")
        return redirect(url_for('login'))

    return render_template("reset_password.html")


@app.route('/secret', methods=['GET', 'POST'])
@login_required
def secretz():
    messages = get_flashed_messages(with_categories=True)
    return render_template("secret.html", username=current_user.username)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route('/download', methods=['GET'])
@login_required
def download():
    if request.method == "GET":
        return send_from_directory('static', 'Drug report.pdf')


@app.route("/", methods=["GET", "POST"])
def home():
    reviews = []
    drug_name = ""

    if request.method == "POST":
        drug_name = request.form["drug_name"].strip()
        reviews = analyze_reviews(drug_name)

    return render_template("screte.html", drug=drug_name, reviews=reviews)


@app.route('/', methods=['GET'])
def secret():
    """Display the input form"""
    return render_template('secret.html')



if __name__ == '__main__':
    app.run(debug=True, port=5001)
