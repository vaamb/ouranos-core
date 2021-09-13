from collections import namedtuple
from datetime import datetime, timezone
import pathlib

import cachetools.func
import markdown
import markdown.extensions.extra


WIKI_STATIC_URL = "wiki_static"


class ArticleNotAvailable(Exception):
    """The article doesn't exist"""


article_tuple = namedtuple("article_tuple", ["metadata", "html"])


class simpleWiki:
    def __init__(self) -> None:
        self.wiki_path = pathlib.Path(__file__).parent.absolute()
        self.md_parser = markdown.Markdown(
            # TODO: bake a custom image size selector instead of attr_list
            extensions=["extra", "meta", "attr_list"])

    @property
    def categories_available(self) -> dict:
        categories = {i.name: i for i in self.wiki_path.iterdir()
                      if i.is_dir() and "__" not in i.name}
        categories.pop("template")
        return categories

    @cachetools.func.ttl_cache(maxsize=1, ttl=60)
    def articles_available(self, categories=()) -> dict:
        if not categories:
            categories = [key for key in self.categories_available]
        articles = {}
        for category in categories:
            path = self.wiki_path/category
            if path.exists():
                articles[category] = {
                    d.name: d for d in path.iterdir()
                    if d.is_dir()
                    and "main.md" in [f.name for f in d.iterdir()]
                }
        return articles

    def get_article(self, category: str, article: str) -> article_tuple:
        path = self.wiki_path/category/article/"main.md"
        if path.exists():
            with path.open() as article_file:
                html = self.md_parser.convert(article_file.read())
                # TODO: improve this ugly replace
                html = html.replace("|!IMG|",
                                    f"/{WIKI_STATIC_URL}/{category}/{article}/")
            # change path to image
            return article_tuple(self.md_parser.Meta, html)
        raise ArticleNotAvailable

    def create_template(self):
        pass

    def create_article(self,
                       body_text,
                       category,
                       subject,
                       title,
                       author="The Author",
                       date=datetime.now(timezone.utc),
                       summary="Summary"):
        pass
        # TODO: think about the metadata

    def modify_article(self):
        pass


_wiki = None


def get_wiki():
    global _wiki
    if not _wiki:
        _wiki = simpleWiki()
    return _wiki
