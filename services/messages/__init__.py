from pathlib import Path

from jinja2 import Environment, FileSystemLoader


template_folder = Path(__file__).absolute().parents[0]

loader = FileSystemLoader(template_folder)
environment = Environment(loader=loader, lstrip_blocks=True, trim_blocks=True)


def render_template(rel_path, **context):
    return environment.get_template(rel_path).render(context)
