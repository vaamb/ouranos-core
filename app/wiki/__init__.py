#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pathlib
import markdown
import markdown.extensions.extra
from datetime import datetime

class simpleWiki():
    def __init__(self):
        self.script_path = pathlib.Path(__file__).parent.absolute()
        self.wiki_path = pathlib.Path(__file__).parent.absolute()

    def categories_available(self):
        categories = os.listdir(self.wiki_path)
        categories.remove("template")
        return categories

    def articles_available(self, category = ""):
        path = os.path.join(self.wiki_path, category)
        articles = []
        for dirpath, dirnames, filenames in os.walk(path):
            for file in filenames:        
                if 'main.md' in file:
                    articles.append(os.path.relpath(dirpath, path))
        articles = [a.replace('\\', '/') for a in articles] #needed for windows path
        if articles != []:
            return articles
        else:
            return "It looks like this category is either empty or does not exist. Check the existing categories by using 'categories_available()'"

    def get_article(self, *args, data = "html"):
        path = self.wiki_path
        for subcaterory in args:
            path = os.path.join(path, subcaterory)
        article_path = os.path.join(path, "main.md")
        try:
            md = markdown.Markdown(extensions = ["extra", "meta"])
            f = open(article_path, "r", encoding = 'utf-8')
            html = md.convert(f.read())
            f.close()
            if data == "html":
                return html
            elif data == "metadata":
                return md.Meta
        except IOError:
            return("It looks like this article does not exist. Check the existing categories by using 'articles_available()")
                
    def create_template(self):
        pass
    
    def create_article(self, category = "", article = "article", title = "Title", author = "The Author", date = datetime.now(), summary = "Summary"):
        pass
        #think about the metadata
    
    def modify_article(self, *args, author = "The Author"):
        pass
        #add the author in meta data