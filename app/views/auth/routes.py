# -*- coding: utf-8 -*-
from datetime import datetime, timezone

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.urls import url_parse

from app import db
from app.views.auth import bp
from app.views.auth.forms import LoginForm, RegistrationForm, InvitationForm
from app.models import User


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
        if not next_page or url_parse(next_page).netloc != "":
            next_page = url_for("main.home")
        return redirect(next_page)
    return render_template("auth/login.html", title="Sign In", form=form)


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.home"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    token = request.args.get("token")
    if token is None:
        form = InvitationForm()
        if form.validate_on_submit():
            token = form.token.data
            return redirect(url_for("auth.register", **{"token": token}))
        return render_template('auth/invitation.html', title='Register',
                               form=form)

    user = User.query.filter(
        User.token == token).first()

    if user is None:
        flash("This invitation token is either invalid or expired")
        return redirect(url_for("auth.register"))

    if user.username:
        # If the user has a username, he is registered
        flash(f"This token has already been used for registration")
        return redirect(url_for('auth.login'))

    if user.registration_exp \
            and user.registration_exp <= datetime.now(timezone.utc):
        flash("This invitation token has expired")
        return redirect(url_for("auth.register"))

    form = RegistrationForm()
    form.token = token
    if request.method == "GET":
        form.firstname.data = user.firstname
        form.lastname.data = user.lastname
        form.email.data = user.email

    if form.validate_on_submit():
        user.firstname = form.firstname.data
        user.lastname = form.lastname.data
        user.username = form.username.data
        user.email = form.email.data
        user.set_password(form.password.data)
        user.registration_datetime = datetime.now(timezone.utc)
        db.session.merge(user)
        db.session.commit()
        flash(f"You are now registered {form.username.data}!")
        login_user(user)
        return redirect(url_for("main.home"))
    return render_template("auth/register.html", title="Register", form=form)
