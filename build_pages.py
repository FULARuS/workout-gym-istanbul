"""Build the static, shareable GitHub Pages preview."""

import argparse
import re
import shutil
from pathlib import Path

from server import ASSETS, ROOT

PAGES = {"": "home", "uyelik": "membership", "salon": "club"}
LOCAL_URL = re.compile(r'\b(href|src|poster)="(/(?!/)[^"]*)"')


def render(template, route, page):
    prefix = "../" if route else "./"

    def relative_url(match):
        attribute, url = match.groups()
        for directory in ("uyelik", "salon"):
            if url == f"/{directory}" or url.startswith(f"/{directory}#"):
                url = url.replace(f"/{directory}", f"/{directory}/", 1)
                break
        return f'{attribute}="{prefix}{url[1:]}"'

    document = LOCAL_URL.sub(relative_url, template)
    document = document.replace('<html lang="tr" dir="ltr">',
        f'<html lang="tr" dir="ltr" data-page="{page}" data-form-mode="whatsapp">', 1)
    document = document.replace('<head>', '<head>\n  <meta name="robots" content="noindex">', 1)
    return document.replace(' action="/api/leads"', "")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=ROOT / "dist")
    output = parser.parse_args().output.resolve()
    template = (ROOT / "index.html").read_text(encoding="utf-8")

    for route, page in PAGES.items():
        folder = output / route
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(render(template, route, page), encoding="utf-8")
    for asset in sorted(ASSETS | {"/style.css", "/site.js", "/translations.js"}):
        destination = output / asset[1:]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / asset[1:], destination)
    (output / ".nojekyll").touch()


if __name__ == "__main__":
    main()
