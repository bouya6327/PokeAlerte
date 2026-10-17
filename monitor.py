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


def check_products(cfg, state, feed):
    res = []
    for p in cfg.get("products", []):
        status = "inconnu"
        try:
            html = re.sub(r"\s+", " ", fetch(p["url"]).lower())
            if any(x in html for x in p.get("out_of_stock_phrases", [])):
                status = "rupture"
            elif any(x in html for x in p.get("in_stock_phrases", [])):
                status = "en stock"
        except Exception as e:
            print("produit KO:", p["name"], e)
            status = "erreur"
        key = "stock|" + p["url"]
        prev = state.get(key)
        if status == "en stock" and prev != "en stock":
            notify("RESTOCK Pokémon", f"{p['name']} semble de nouveau disponible !", p["url"])
        if status in ("en stock", "rupture"):
            state[key] = status
        res.append({"name": p["name"], "url": p["url"], "status": status})
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
