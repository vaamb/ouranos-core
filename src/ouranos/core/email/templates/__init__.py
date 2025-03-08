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
    text = ""
    def handle_data(self, data):
        self.text += data


def get_body_text(template: str) -> str:
    body = body_pattern.search(template)
    if not body:
        return ""
    filter = HTMLFilter()
    filter.feed(body.group(1))
    return filter.text.strip()
