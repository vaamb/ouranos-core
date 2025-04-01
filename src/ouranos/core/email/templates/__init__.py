from html.parser import HTMLParser
from pathlib import Path
import re

from jinja2 import Environment, FileSystemLoader


# Template rendering
template_folder = Path(__file__).absolute().parent

loader = FileSystemLoader(template_folder)
environment = Environment(
    loader=loader, lstrip_blocks=True, trim_blocks=True, autoescape=True, enable_async=True)


async def render_template(rel_path, **context) -> str:
    template = await environment.get_template(f"{rel_path}.html").render_async(context)
    return template


# Template body linearization
body_pattern = re.compile(r'<body>((.|\n)*?)</body>', re.RegexFlag.MULTILINE)

class HTMLFilter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.links = []

    def add_space_if_needed(self):
        if self.text and self.text[-1] != " ":
            self.text += " "

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            for attr in attrs:
                if attr[0] == "data-replace":
                    self.add_space_if_needed()
                    self.text += attr[1]
                elif attr[0] == "alt":
                    self.add_space_if_needed()
                    self.text += f"[picture of {attr[1]}] "
        elif tag == "a":
            self.add_space_if_needed()
            for attr in attrs:
                if attr[0] == "href":
                    self.links.append(attr[1])
                else:
                    self.links.append(None)

    def handle_endtag(self, tag):
        if tag == "a":
            link = self.links.pop()
            if link:
                self.add_space_if_needed()
                self.text += f"[{link}] "
        elif tag.startswith("h") or tag in {"p", "ul", "ol", "li"}:
            if self.text and self.text[-1] != "\n":
                self.text += "\n"
        elif tag in {"br", "tr"}:
            self.text += "\n"

    def handle_data(self, data):
        data = data.strip()
        self.text += data


def get_body_text(template: str) -> str:
    body = body_pattern.search(template)
    if not body:
        return ""
    filter = HTMLFilter()
    filter.feed(body.group(1))
    return filter.text.strip()
