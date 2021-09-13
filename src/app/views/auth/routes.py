# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone

from flask import current_app, flash, redirect, render_template, request, \
    url_for
from flask_login import current_user, login_user, logout_user
import jwt
from werkzeug.urls import url_parse

from src.app import db
from src.app.views.auth import bp
from src.app.views.auth.forms import LoginForm, RegistrationForm, InvitationForm
from src.app.models import User, Role


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid username or password")
            return redirect(url_for("auth.login", **request.args))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get("next")
        flash(f"You are now logged in {current_user.username}")
        if not next_page or url_parse(next_page).netloc != "":
            next_page = url_for("main.home")
        return redirect(next_page)
    return render_template("auth/login.html", title="Sign In", form=form)


@bp.route("/logout")
def logout():
    logout_user()
    flash(f"You are now logged out")
    return redirect(url_for("main.home"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    token = request.args.get("token")
    if token is None:
        form = InvitationForm()
        if form.validate_on_submit():
            token = form.token.data.strip()
            return redirect(url_for("auth.register", token=token))
        return render_template('auth/invitation.html', title='Register',
                               form=form)

    try:
        decoded = jwt.decode(token, current_app.config["JWT_SECRET_KEY"],
                             algorithms="HS256",
                             leeway=timedelta(days=1))
        user = User.query.filter(User.token == decoded["utk"]).first()
    except jwt.ExpiredSignatureError:
        flash("This invitation token has expired")
        return redirect(url_for("auth.register"))
    except jwt.InvalidSignatureError:
        flash("This invitation token is invalid")
        return redirect(url_for("auth.register"))
    except KeyError:
        flash("This invitation token is invalid")
        return redirect(url_for("auth.register"))
    except jwt.InvalidTokenError:
        flash("This invitation token is invalid")
        return redirect(url_for("auth.register"))
    if user:
        flash("This invitation token has already been used for registration")
        return redirect(url_for("auth.login"))

    role = Role.query.filter_by(name=decoded.get("rle")).first()
    if not role:
        role = Role.query.filter_by(default=True).first()

    firstname = decoded.get("fnm")
    lastname = decoded.get("lnm")
    email = decoded.get("eml")
    form = RegistrationForm()

    if request.method == "GET":
        form.firstname.data = firstname
        form.lastname.data = lastname
        form.email.data = email

    if form.validate_on_submit():
        # Make sure Operators and Admin keep their invitation name
        if not role.default and firstname:
            form.firstname.data = firstname
        if not role.default and lastname:
            form.lastname.data = lastname
        if email:
            form.email.data = email
        user = User(
            firstname=form.firstname.data,
            lastname=form.lastname.data,
            username=form.username.data,
            email=form.email.data,
            registration_datetime=datetime.now(timezone.utc),
            token=decoded["utk"],
            role=role,
            telegram_chat_id=decoded.get("tgm")
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(f"You are now registered {form.username.data}!")
        login_user(user)
        return redirect(url_for("main.home"))
    return render_template("auth/register.html", title="Register", form=form,
                           role=role)
