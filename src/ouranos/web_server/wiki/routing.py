import pathlib

from flask import abort, Blueprint, current_app, render_template, \
    send_from_directory
from flask_login import current_user

from ouranos.web_server import app_path
from ouranos.web_server.wiki import ArticleNotAvailable, WIKI_STATIC_URL


TEMPLATE_PATH = "main/wiki.html"
PROTECTED_CATEGORIES = ("plants_care", )

rel_path = pathlib.Path(__file__).parent.absolute().relative_to(app_path)

# wiki_engine = get_wiki()
bp = Blueprint("wiki", __name__)


@bp.route(f"/{WIKI_STATIC_URL}/<path:filename>")
def wiki_static(filename):
    return send_from_directory(f"{rel_path}", filename)


@bp.route("/wiki/<category>/<article>")
def index(category: str, article: str):
    if not current_user.is_authenticated and category in PROTECTED_CATEGORIES:
        return current_app.login_manager.unauthorized()
    try:
        article = wiki_engine.get_article(category, article)
        title = article.metadata["title"][0]
        return render_template(f"{TEMPLATE_PATH}", title=title, article=article)
    except ArticleNotAvailable:
        abort(404)
