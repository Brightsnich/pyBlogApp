from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor, CKEditorField
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy import Integer, String, Text, ForeignKey, create_engine
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
# Import your forms from the forms.py
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
import psycopg2, os
from dotenv import load_dotenv
import yagmail

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("FLASK_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)

# Configuration for your email
YAGMAIL_USER = os.getenv("USER_EMAIL")  # Your Gmail address
YAGMAIL_PASSWORD = os.getenv("PASSWORD")  # Your Gmail password (or app password)
TO_EMAIL = os.getenv("TO_EMAIL") # The email where you want to receive contact form submissions

# TODO: Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Specify the login view function
login_manager.login_message = "Please log in to access this page."

# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DB_URI")
engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI']) #create engine
Session = sessionmaker(bind=engine) #create session
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    author: Mapped["User"] = relationship(back_populates="posts")
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    comments: Mapped[list["Comment"]] = relationship(back_populates="parent_post")


# TODO: Create a User table for all your registered users. 
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(1000), nullable=False)
    email:  Mapped[str] = mapped_column(String(250), nullable= False)
    password: Mapped[str] = mapped_column(String(250), nullable=False)
    posts: Mapped[list["BlogPost"]] = relationship(back_populates="author")
    comments: Mapped[list["Comment"]] = relationship(back_populates="comment_author")

    def __init__(self, email, password, name):
        self.email = email
        self.password = password
        self.name = name

    def __repr__(self):
        return f"<User {self.name}>"

class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    comment_author: Mapped["User"] = relationship(back_populates="comments")
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("blog_posts.id"), nullable=False)
    parent_post: Mapped["BlogPost"] = relationship(back_populates="comments")


with app.app_context():
    db.create_all()

# Flask-Login user loader function
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# TODO: Use a decorator so only an admin user can create a new post
def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Assuming the first user in the database is the admin.  This is NOT ideal for production.
        if not current_user.is_authenticated or current_user.id != 1:  # Replace 1 with the actual admin user's ID.  Hardcoding is bad.
            return abort(403)  # Return a 403 Forbidden error
        return f(*args, **kwargs)
    return decorated_function

# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if request.method == "POST":
        if form.validate_on_submit():
            name = form.name.data
            email = form.email.data
            user_password = form.password.data
            print(name, email, user_password)
            try:

                existing_user = User.query.filter_by(email=email).first()
                if existing_user:
                    flash("You have already registered. Please log in", "error")
                    return redirect(url_for("login"))
                hashed_password = generate_password_hash(password=user_password, method="scrypt", salt_length=10)
                print(hashed_password)
                new_user = User(email=email, name=name, password=hashed_password)
                db.session.add(new_user)
                db.session.commit()
                login_user(new_user)
                return redirect(url_for("get_all_posts"))
            except Exception as e:
                flash(f"Error adding user: {e}", 'error')  # flash the error
                return redirect(url_for('register'))  # redirect to register
    return render_template("register.html", form=form)


# TODO: Retrieve a user from the database based on their email. 
@app.route('/login', methods = ["GET", "POST"])
def login():
    form = LoginForm()
    if request.method == "POST":
        if form.validate_on_submit():
            email = form.email.data
            password = form.password.data
            try:
                user = User.query.filter_by(email=email).first()
                if not user:
                    flash("This email does not exist in our database.", "error")
                    return redirect(url_for("login"))
                elif not check_password_hash(user.password, password):
                    flash(message="Wrong email or password, please try again.", category="error")
                    return redirect(url_for('login'))
                else:
                    login_user(user)
                    return redirect(url_for("get_all_posts"))
            except Exception as e:
                flash(f"Wrong email or password, please try again.", 'error')  # flash the error
                return redirect(url_for('register'))
    return render_template("login.html", form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
@login_required
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    form = CommentForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("Please log in to comment.", "warning")
            return redirect(url_for("login"))
        new_comment = Comment(
            text=form.comment.data,
            comment_author=current_user,
            parent_post=requested_post,
        )
        db.session.add(new_comment)
        db.session.commit()
        return redirect(url_for("show_post", post_id=post_id))
    # Get existing comments for the post
    comments = db.session.query(Comment).filter_by(post_id=post_id).all()
    return render_template("post.html", post=requested_post, form=form, comments=comments)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@login_required
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@login_required
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@login_required
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods = ["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        message = request.form["message"]
        try:
            # Initialize yagmail and send the email.
            yag = yagmail.SMTP(user=YAGMAIL_USER, password=YAGMAIL_PASSWORD)
            contents = [
                f"Name: {name}",
                f"Email: {email}",
                f"Message: {message}",
            ]
            yag.send(
                to=TO_EMAIL,
                subject=f"New Contact Form Submission from {name}",
                contents=contents,
            )
            yag.close()  # explicitly close the connection

            flash('Your message has been sent successfully!', 'success')  # use flash
            return redirect(url_for('contact', msg_sent = "Succesful"))  # Redirect to the contact page to clear the form
        except Exception as e:
            # Handle errors during email sending.  Important!
            flash(f'An error occurred while sending your message: {e}', 'error')
            return render_template('contact.html')  # Render the template again, so the user doesn't lose their input
        # If the form is not submitted or the data is invalid, render the contact page.
    return render_template("contact.html")


if __name__ == "__main__":
    app.run(debug=False, port=5002)
