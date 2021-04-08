from collections import namedtuple
from datetime import datetime, timezone
import pathlib

import cachetools.func
import markdown
import markdown.extensions.extra


article_tuple = namedtuple("article_tuple", ["metadata", "html"])


class simpleWiki:
    def __init__(self):
        self.script_path = pathlib.Path(__file__).parent.absolute()
        self.wiki_path = pathlib.Path(__file__).parent.absolute()
        self.md_parser = markdown.Markdown(extensions=["extra", "meta"])

    @property
    def categories_available(self):
        categories = {i.name: i for i in self.wiki_path.iterdir()
                      if i.is_dir() and "__" not in i.name}
        categories.pop("template")
        return categories

    @property
    @cachetools.func.ttl_cache(maxsize=1, ttl=60)
    def articles_available(self):
        categories = [key for key in self.categories_available]
        articles = {}
        for category in categories:
            path = self.wiki_path/category
            articles[category] = {
                d.name: d/"main.md" for d in path.iterdir()
                if d.is_dir()
                and "main.md" in [f.name for f in d.iterdir()]
            }
        return articles

    def get_article(self, category, article):
        try:
            article_path = self.articles_available[
                category.lower()][article.lower()]
        except KeyError:
            print("This article doesn't exists")
            return
        with open(article_path) as article_file:
            html = self.md_parser.convert(article_file.read())
        return article_tuple(self.md_parser.Meta, html)

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
