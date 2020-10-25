# -*- coding: utf-8 -*-
import datetime

from flask import render_template
from flask_login import login_required

from app.models import Permission
from app.admin import bp
from app.common.decorators import permission_required
from app.main import layout


import tracemalloc
tracemalloc.start()
s1 = None
s2 = None
outfile = "mem_leak.debug"

@bp.route('/admin/mem_snapshot')
@login_required
@permission_required(Permission.ADMIN)
def mem_snapshot():
     global s1, s2
     if s1 == None:
         s1 = tracemalloc.take_snapshot()
         return render_template("admin/snapshot.html",
                                diff = ["First snapshot taken"])
     else:
         s2 = tracemalloc.take_snapshot()
         diff = []
         with open(outfile, "a+") as file:
             now = datetime.datetime.now()
             file.write(f"{now} \r")
             for i in s2.compare_to(s1,'lineno')[:10]:
                 file.write(f"{i} \r")
                 diff.append(i)
#                 print(i)
             file.write("\r")
         return render_template("admin/snapshot.html",
                                diff = diff)

@bp.route("/admin/system")
@login_required
@permission_required(Permission.ADMIN)
def system():
   return render_template("admin/system.html", title="Server monitoring",
                           data = [],
                           parameters = layout.parameters,
                           )

@bp.route("/admin/logs")
@login_required
@permission_required(Permission.ADMIN)
def log_home():
    title = "Logs"
    return render_template("admin/log_home.html", title=title,
                           )

@bp.route("/admin/logs/<log_type>")
@login_required
@permission_required(Permission.ADMIN)
def log(log_type):
    title = "{} logs".format(log_type.capitalize())
    return render_template("admin/log.html", title=title)

@bp.route("/admin/db_management")
@login_required
@permission_required(Permission.ADMIN)
def db_management_home():
    return render_template("admin/db_home.html")

@bp.route("/admin/db_management/<db>")
@login_required
@permission_required(Permission.ADMIN)
def db_management(db):
    return render_template("admin/db_management.html")
