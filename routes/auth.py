from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user

from extensions import db
from models import User, get_user_by_id

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter(
            (User.email == identifier) | (User.username == identifier)
        ).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user)
            next_param = request.args.get("next")
            if next_param:
                next_url = next_param
            elif user.is_admin:
                next_url = url_for("streaming_admin.dashboard")
            else:
                next_url = url_for("streaming.index")
            return redirect(next_url)
        flash("Credenciales inválidas / Invalid credentials", "error")
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if User.query.filter((User.email == email) | (User.username == username)).first():
            flash("Usuario o email ya existe / User or email already exists", "error")
        else:
            user = User(email=email, username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("streaming.index"))
    return render_template("auth/register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("streaming.index"))
