#!/usr/bin/env python3
"""PokéAlerte : surveille sorties, actus et stocks, et vous envoie une notification.

Notifications :
  - NTFY_TOPIC  (recommandé) : notification push sur votre téléphone via l'app ntfy
  - SMTP_*      (optionnel)  : envoi d'un email
"""
import json, os, re, smtplib, ssl, sys, datetime as dt
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) PokeAlerte/1.0"}


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def notify(title, message, url=None):
    print(f"[NOTIF] {title} – {message}")
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        headers = {"Title": title.encode("utf-8").decode("latin-1", "ignore") or "PokeAlerte"}
        if url:
            headers["Click"] = url
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{topic}", data=message.encode("utf-8"),
                headers={**headers, "Tags": "zap"}, method="POST")
            urllib.request.urlopen(req, timeout=20)
        except Exception as e:
            print("ntfy erreur:", e)
    host, user, pwd, to = (os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "EMAIL_TO"))
    if host and user and pwd and to:
        try:
            msg = EmailMessage()
            msg["Subject"], msg["From"], msg["To"] = f"PokéAlerte – {title}", user, to
            msg.set_content(message + (f"\n\n{url}" if url else ""))
            with smtplib.SMTP_SSL(host, int(os.environ.get("SMTP_PORT", 465)),
                                  context=ssl.create_default_context()) as s:
                s.login(user, pwd)
                s.send_message(msg)
        except Exception as e:
            print("email erreur:", e)


def check_releases(cfg, state, feed):
    today = dt.date.today()
    out = []
    for r in cfg.get("releases", []):
        try:
            d = dt.date.fromisoformat(r["date"])
        except Exception:
            continue
        days = (d - today).days
        out.append({"name": r["name"], "date": r["date"], "days": days})
        for step in (7, 1, 0):
            key = f"rel|{r['name']}|{r['date']}|{step}"
            if days == step and not state.get(key):
                when = "aujourd'hui" if step == 0 else f"dans {step} jour(s)"
                notify("Sortie Pokémon", f"{r['name']} sort {when} ({r['date']}).")
                state[key] = True
    feed["releases"] = sorted(out, key=lambda x: x["date"])


def check_news(cfg, state, feed):
    kws = [k.lower() for k in cfg.get("news_keywords", [])]
    items, first_run, any_ok = [], not state.get("_news_init"), False
    for src in cfg.get("news_feeds", []):
        try:
            root = ET.fromstring(fetch(src["url"]))
            any_ok = True
        except Exception as e:
            print("flux KO:", src["name"], e)
            continue
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            date = (it.findtext("pubDate") or "").strip()
            if kws and not any(k in title.lower() for k in kws):
                continue
            items.append({"title": title, "link": link, "date": date, "source": src["name"]})
            key = "news|" + link
            if not state.get(key):
                state[key] = True
                if not first_run:
                    notify("Actu Pokémon", title, link)
    if any_ok:
        state["_news_init"] = True
    feed["news"] = items[:30]


BUYABLE = ("en stock", "précommande")
DEFAULT_IN = ["ajouter au panier", "ajouter au caddie", "add to cart"]
DEFAULT_OUT = ["rupture de stock", "en rupture", "indisponible", "épuisé", "out of stock",
               "sold out", "prévenez-moi lorsque", "bientôt disponible"]

# Données structurées (schema.org / balises meta) : plus fiables que le texte de la page.
_AVAIL = re.compile(
    r'availability["\']?\s*[:=]?\s*["\']?[^<>]{0,80}?'
    r'(InStock|OutOfStock|SoldOut|PreOrder|PreSale|BackOrder|LimitedAvailability|'
    r'Discontinued|InStoreOnly|OnlineOnly)', re.I)
_META = re.compile(r'(?:product|og):availability["\']?\s+content=["\']([^"\']+)', re.I)
_MAP = {"instock": "en stock", "limitedavailability": "en stock", "onlineonly": "en stock",
        "instoreonly": "en stock", "preorder": "précommande", "presale": "précommande",
        "backorder": "précommande", "outofstock": "rupture", "soldout": "rupture",
        "discontinued": "rupture", "oos": "rupture"}


def structured_status(raw):
    m = _AVAIL.search(raw)
    if m:
        return _MAP.get(m.group(1).lower())
    m = _META.search(raw)
    if m:
        return _MAP.get(re.sub(r"[^a-z]", "", m.group(1).lower()))
    return None


def detect_status(p, raw):
    """detect: "auto" (défaut) = données structurées puis phrases ; "structured" ; "phrases"."""
    mode = p.get("detect", "auto")
    if mode in ("auto", "structured"):
        s = structured_status(raw)
        if s:
            return s
        if mode == "structured":
            return "inconnu"
    html = re.sub(r"\s+", " ", raw.lower())
    if any(x.lower() in html for x in p.get("out_of_stock_phrases", DEFAULT_OUT)):
        return "rupture"
    if any(x.lower() in html for x in p.get("in_stock_phrases", DEFAULT_IN)):
        return "en stock"
    return "inconnu"


def check_products(cfg, state, feed):
    res = []
    first_run = not state.get("_stock_init")
    seen = False
    for p in cfg.get("products", []):
        try:
            status = detect_status(p, fetch(p["url"]))
        except Exception as e:
            print("produit KO:", p["name"], e)
            status = "erreur"
        key = "stock|" + p["url"]
        prev = state.get(key)
        if status in BUYABLE and status != prev and not first_run:
            label = "PRÉCOMMANDE" if status == "précommande" else "RESTOCK"
            notify(f"{label} Pokémon", f"{p['name']} : {status} !", p["url"])
        if status in BUYABLE or status == "rupture":
            state[key] = status
            seen = True
        res.append({"name": p["name"], "url": p["url"], "status": status})
    if seen:
        state["_stock_init"] = True  # 1er passage silencieux : on enregistre l'état de départ
    feed["products"] = res


def main():
    cfg = load(ROOT / "config.json", {})
    state = load(DATA / "state.json", {})
    feed = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    check_releases(cfg, state, feed)
    check_news(cfg, state, feed)
    check_products(cfg, state, feed)
    (DATA / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
