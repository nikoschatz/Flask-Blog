# Below are our imports. Different instances using tools from the various flask and  native python libraries
import os
import secrets
from PIL import Image
from datetime import datetime
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from flask import Flask,render_template,url_for,flash,redirect, request, abort
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager,UserMixin, login_user, logout_user, current_user, login_required
from flask_mail import Mail, Message

# initialisation of Flask
app = Flask(__name__)
app.config['SECRET_KEY']='36785952d33f5473bf968c6bcfd20679'  # creating a secret key which we will use later
app.config['SQLALCHEMY_DATABASE_URI']= 'sqlite:///site.db'  # connecting to our database
db = SQLAlchemy(app)  # creating an instance of the database in our app
bcrypt = Bcrypt(app)  # creating an instance of the Bcrypt module for hashing our passwords

# creating an instance of the LoginManager module which will help us with our Login Forms
login_manager = LoginManager(app)
# additional LoginManager initialisation code lines
login_manager.login_view='login'
login_manager.login_message_category='info'

# initialisation of our MAIL SERVER which of course is not completed because we have to insert real mail credentials
app.config['MAIL_SERVER']= 'smtp.googlemail.com'
app.config['MAIL_PORT']= 587
app.config['MAIL_USE_TLS']= True
app.config['MAIL_USERNAME']= os.environ.get('EMAIL_USER')
app.config['MAIL_PASSWORD']= os.environ.get('EMAIL_PASS')
mail = Mail(app)


# also a crucial part for our Login Manager to work it has to corellate to a user each time
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# database models declaration with each column of our tables creating them as classes thanks to SQLALCHEMY
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default=('default.jpg'))
    password = db.Column(db.String(60), nullable=False)
    posts = db.relationship('Post', backref='author',lazy=True)

    def get_reset_token(self,expires_sec=1800):
        s = Serializer(app.config['SECRET_KEY'], expires_sec)
        return s.dumps({'user_id':self.id}).decode('utf-8')

# also accompanied with some functions such as the create a token(for the email password reset)
    @staticmethod
    def verify_reset_token(token):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token)['user_id']
        except:
            return None
        return User.query.get(user_id)

    def __repr__(self):
        return f"User('{self.username}','{self.email}','{self.image_file}')"


# another database model, now for our posts
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default= datetime.utcnow)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"Post('{self.title}','{self.date_posted}')"


# the route for our home page we are also using a type of pagination
@app.route("/")
@app.route("/home")
def home():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page,per_page=5)
    return render_template('home.html', posts=posts)


# this is a mock about page which we can fill with the information of the owner
@app.route("/about")
def about():
        return render_template('about.html', title='About')


# the route for our register page/form, inside we are committing data to our User table
@app.route("/register", methods=['GET', 'POST'])
def register():
        if current_user.is_authenticated:
            return redirect(url_for('home'))
        form = RegistrationForm()
        if form.validate_on_submit():
            hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            user = User(username=form.username.data, email=form.email.data, password= hashed_pw)
            db.session.add(user)
            db.session.commit()
            flash('Your account has been created! You are now able to log in', 'success')
            return redirect(url_for('login'))
        return render_template('register.html', title='Register', form=form)


# the route for our login form, where we are also hasing the user's password
@app.route("/login", methods=['GET', 'POST'])
def login():
        if current_user.is_authenticated:
            return redirect(url_for('home'))
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()
            if user and bcrypt.check_password_hash(user.password, form.password.data):
                login_user(user, remember=form.remember.data)
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('home'))
            else:
                flash('Login Unsuccessful. Please check email and password', 'danger')
        return render_template('login.html', title='Login', form=form)


# the logout user route
@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))


# this is a function for saving the user profile picture and formatting the image file
def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path,'static/profile_pics', picture_fn)
    output_size = (125,125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)
    return picture_fn


# this the route for the user's account and there is also a login required parameter, inside we add all the user's info
@app.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    form= UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file= url_for('static',filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title='Account', image_file=image_file, form=form)


# the route for a new post by the user, who also has to be logged in
@app.route("/post/new",methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content= form.content.data, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash('Your post has been created','success')
        return redirect(url_for('home'))
    return render_template('create_post.html', title='New Post', form=form, legend='New Post')


# the post route, we are displaying an error if the post doesn't currently exist
@app.route("/post/<int:post_id>")
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html',title= post.title, post=post)


# the update post route updating an old post, also a login is required
@app.route("/post/<int:post_id>/update",methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        db.session.commit()
        flash('Your post has been updated!','success')
        return redirect(url_for('post', post_id= post.id))
    elif request.method == 'GET':
        form.title.data = post.title
        form.content.data = post.content
    return render_template('create_post.html', title='Update Post', form=form, legend='Update Post')


# the delete post route, showing a message window for the user to be sure about deletion
@app.route("/post/<int:post_id>/delete", methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Your post has been deleted','success')
    return redirect(url_for('home'))


# the route where you can see all the posts by date for a single user
@app.route("/user/<string:username>")
def user_posts(username):
    page = request.args.get('page', 1, type=int)
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(author=user)\
        .order_by(Post.date_posted.desc())\
        .paginate(page=page,per_page=5)
    return render_template('user_posts.html', posts=posts, user=user)


# here we create the function which will send the email to the user wanting to change password, having mock mail o.f.c.
def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request', sender='noreply@demo.com', recipients=[user.email])
    msg.body = f''' To reset your password, visit the following link:
    {url_for('reset_token', token =token, external= True)}

    If you did not make this request then simply ignore this email and no changes will be made
    '''
    mail.send(msg)


# reset request rout
@app.route("/reset_password",methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password', 'info')
        return render_template(url_for('login'))
    return render_template('reset_request.html', title='Reset Password',form=form)


# reset password route using the token we've created
@app.route("/reset_password/<token>",methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm
    if form.validate_on_submit():
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_pw
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title= 'Reset Password', form=form)


# we are importing the forms from the file forms.py here due to circular import errors
from forms import RegistrationForm, LoginForm, UpdateAccountForm, PostForm, RequestResetForm, ResetPasswordForm

if __name__ == '__main__':
    app.run()
