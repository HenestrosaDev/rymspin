#!/usr/bin/env python3
"""Elige un álbum al azar entre los puntuados por un usuario de RateYourMusic.

Uso:
    python rym_random.py USUARIO [--min 0.5] [--max 5.0]

RYM está detrás de Cloudflare, así que se usa un Chrome real controlado con
Playwright. El perfil se guarda en .rym_profile/ para reutilizar la cookie de
Cloudflare entre ejecuciones.
"""

import argparse
import random
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://rateyourmusic.com"
PER_PAGE = 25
PROFILE_DIR = Path(__file__).resolve().parent / ".rym_profile"


class Fetcher:
    def __init__(self):
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",
            headless=False,  # en modo headless Cloudflare bloquea el acceso
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def get(self, url):
        self._page.goto(url)
        # Esperar a que se resuelva el desafío de Cloudflare (hasta ~60 s, por
        # si hay que marcar la casilla a mano en la ventana).
        for _ in range(60):
            if "Just a moment" not in self._page.title():
                break
            self._page.wait_for_timeout(1000)
        else:
            sys.exit("No se pudo superar la protección de Cloudflare.")
        self._page.wait_for_load_state("networkidle")
        return BeautifulSoup(self._page.content(), "html.parser")

    def close(self):
        self._ctx.close()
        self._pw.stop()


def parse_rows(soup):
    table = soup.find("table", class_="mbgen")
    if table is None:
        return []
    albums = []
    for row in table.find_all("tr", id=re.compile(r"^page_catalog_item_\d+")):
        artists = row.select("a.artist")
        album = row.select_one("a.album")
        if album is None:
            continue
        rating = row.select_one("td.or_q_rating_date_s img")
        year = row.select_one("div.or_q_albumartist span.smallgray")
        albums.append({
            "artist": " & ".join(a.get_text(" ", strip=True) for a in artists) or "?",
            "title": album.get_text(" ", strip=True),
            "year": year.get_text(strip=True).strip("()") if year else "",
            "rating": rating["title"].replace(" stars", "") if rating else "?",
            "url": BASE + album["href"],
        })
    return albums


def last_page(soup):
    nums = [int(a.get_text()) for a in soup.select("a.navlinknum") if a.get_text().isdigit()]
    return max(nums, default=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("user", help="nombre de usuario de RYM")
    parser.add_argument("--min", type=float, default=0.5, help="nota mínima (por defecto 0.5)")
    parser.add_argument("--max", type=float, default=5.0, help="nota máxima (por defecto 5.0)")
    args = parser.parse_args()

    collection = f"{BASE}/collection/{args.user}/r{args.min:.1f}-{args.max:.1f}"
    fetcher = Fetcher()
    try:
        first = fetcher.get(collection)
        if first.find("table", class_="mbgen") is None:
            sys.exit(f"No se encontró la colección de '{args.user}' (¿usuario correcto o colección privada?).")
        pages = last_page(first)
        cache = {1: parse_rows(first)}

        # Muestreo uniforme: página y posición al azar; si la posición no existe
        # (solo puede pasar en la última página, que está incompleta), se repite.
        while True:
            page = random.randint(1, pages)
            slot = random.randrange(PER_PAGE)
            if page not in cache:
                cache[page] = parse_rows(fetcher.get(f"{collection}/{page}"))
            if not cache[page]:
                sys.exit("La colección está vacía para ese rango de notas.")
            if slot < len(cache[page]):
                choice = cache[page][slot]
                break
    finally:
        fetcher.close()

    year = f" ({choice['year']})" if choice["year"] else ""
    print(f"{choice['artist']} - {choice['title']}{year}")
    print(f"Nota: {choice['rating']}")
    print(choice["url"])


if __name__ == "__main__":
    main()
