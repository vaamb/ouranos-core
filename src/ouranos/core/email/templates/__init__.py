from pathlib import Path

from jinja2 import Environment, FileSystemLoader


template_folder = Path(__file__).absolute().parent

loader = FileSystemLoader(template_folder)
environment = Environment(
    loader=loader, lstrip_blocks=True, trim_blocks=True, autoescape=True, enable_async=True)


async def render_template(rel_path, **context) -> str:
    template = await environment.get_template(f"{rel_path}.html").render_async(context)
    return template
