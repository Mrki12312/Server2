from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import datetime
import os

app = Flask(__name__)
# Otvaramo CORS maksimalno kako bi obe ekstenzije i tvoj robot mogli da komuniciraju sa serverom
CORS(app, resources={r"/*": {"origins": "*"}})

BAZA_NAME = "vortex_network_v4.db"

def inicijalizuj_globalnu_bazu():
    conn = sqlite3.connect(BAZA_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skenirano_trziste (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artikal_id TEXT,
            ime TEXT,
            nadjena_cena REAL,
            sajt_izvora TEXT,
            link_proizvoda TEXT,
            vreme_skena DATETIME
        )
    """)
    # Globalna tabela u kojoj robot ostavlja poruke šta treba pretražiti
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS robot_zadaci (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            termin_pretrage TEXT,
            status TEXT,
            vreme_kreiranja DATETIME
        )
    """)
    conn.commit()
    conn.close()

# ================= RUTE ZA EKSTENZIJU KUPCA (EKSTENZIJA 2) =================

# 1. Kupac otvara skup sajt -> Ova ruta prima signal, upisuje u bazu i kreira zadatak za kućnog robota
@app.route("/api/vortex-pokreni-pretragu", methods=["POST"])
def pokreni_vortex_robotiku():
    podaci = request.json
    if not podaci: 
        return jsonify({"status": "greska", "poruka": "Nema podataka"})
        
    ime_artikla = podaci.get("ime_proizvoda", "")
    trenutna_cena = float(podaci.get("cena", 0))
    sajt_izvora = podaci.get("sajt", "Skupi Sajt")
    link = podaci.get("link", "")
    
    # Izvlačenje SKU formata iz naslova
    from helper import izvuci_univerzalni_sku
    artikal_id = izvuci_univerzalni_sku(ime_artikla)

    conn = sqlite3.connect(BAZA_NAME)
    cursor = conn.cursor()
    
    # Upiši skupu cenu konkurencije
    cursor.execute("""
        INSERT INTO skenirano_trziste (artikal_id, ime, nadjena_cena, sajt_izvora, link_proizvoda, vreme_skena)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (artikal_id, ime_artikla, trenutna_cena, sajt_izvora, link, datetime.datetime.now()))
    
    # Dodaj zadatak u red za kućnog robota
    cursor.execute("""
        INSERT INTO robot_zadaci (termin_pretrage, status, vreme_kreiranja)
        VALUES (?, 'CEKA', ?)
    """, (ime_artikla, datetime.datetime.now()))
    
    conn.commit()
    conn.close()

    return jsonify({"status": "uspeh", "sku": artikal_id})

# 2. Ekstenzija kupca konstantno pita ovu rutu da li su stigle jeftinije cene sa ePonude/Shoppstera
@app.route("/api/vortex-provera-ponude", methods=["GET"])
def provera_ponude_za_kupca():
    sku = request.args.get("sku")
    if not sku:
        return jsonify({"status": "greska", "poruka": "Fali SKU"})
        
    conn = sqlite3.connect(BAZA_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Tražimo sve zabeležene cene za taj SKU, sortirane od najniže
    cursor.execute("""
        SELECT * FROM skenirano_trziste 
        WHERE artikal_id = ? AND sajt_izvora LIKE '%Ponuda%' OR sajt_izvora LIKE '%Opcija%'
        ORDER BY nadjena_cena ASC LIMIT 1
    """, (sku,))
    
    najbolja_opcija = cursor.fetchone()
    conn.close()
    
    if najbolja_opcija:
        # Generišemo tvoju Shopify adresu gde će kupac kupiti proizvod sa tvojom ugrađenom maržom
        # (Za testiranje vraćamo link originalnog jeftinog sajta)
        from helper import izracunaj_vortex_cenu
        
        return jsonify({
            "status": "pronadjeno",
            "bolja_cena": najbolja_opcija["nadjena_cena"],
            "link": najbolja_opcija["link_proizvoda"]
        })
        
    return jsonify({"status": "cekanje"})


# ================= RUTE ZA LOKALNOG ROBOTA (TVOJ KOMPJUTER) =================

# 3. Tvoj robot kući konstantno poziva ovu rutu (Long-Polling) da vidi da li ima novih poslova
@app.route("/api/robot-sledeci-zadatak", methods=["GET"])
def sledeci_zadatak_za_robota():
    conn = sqlite3.connect(BAZA_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM robot_zadaci WHERE status = 'CEKA' ORDER BY vreme_kreiranja ASC LIMIT 1")
    zadatak = cursor.fetchone()
    
    if zadatak:
        # Prebaci status u 'U_OBRADI' da se posao ne bi duplirao
        cursor.execute("UPDATE robot_zadaci SET status = 'U_OBRADI' WHERE id = ?", (zadatak["id"],))
        conn.commit()
        conn.close()
        return jsonify({"status": "ima_posla", "id": zadatak["id"], "termin": zadatak["termin_pretrage"]})
        
    conn.close()
    return jsonify({"status": "nema_posla"})


# ================= RUTA ZA TVOJU SKRAPER EKSTENZIJU (EKSTENZIJA 1) =================

# 4. Tvoja skraper ekstenzija šalje 5-6 cena koje je našla na ePonudi/Shoppsteru
@app.route("/api/vortex-upis-cena", methods=["POST"])
def upis_cena_iz_ekstenzije():
    podaci = request.json
    if not podaci: 
        return jsonify({"status": "greska"})
        
    artikal_id = podaci.get("artikal_id", "SKU_NEPOZNAT")
    ime_artikla = podaci.get("ime_proizvoda", "Nepoznat naziv")
    cena = float(podaci.get("cena", 0))
    sajt = podaci.get("sajt", "Nepoznat sajt")
    link = podaci.get("link", "")
    
    conn = sqlite3.connect(BAZA_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO skenirano_trziste (artikal_id, ime, nadjena_cena, sajt_izvora, link_proizvoda, vreme_skena)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (artikal_id, ime_artikla, cena, sajt, link, datetime.datetime.now()))
    conn.commit()
    conn.close()
    return jsonify({"status": "uspeh"})


# ================= DASHBOARD PANEL =================
@app.route("/")
def administrativni_panel():
    conn = sqlite3.connect(BAZA_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM skenirano_trziste ORDER BY vreme_skena DESC LIMIT 40")
    skenovi = cursor.fetchall()
    conn.close()
    
    skenovi_html = "".join([
        f"<li>📡 <b>SKU: {s['artikal_id']}</b> | "
        f"<a href='{s['link_proizvoda']}' target='_blank' style='color:#aaa;text-decoration:none;'>{s['ime'][:50]}...</a> | "
        f"<b style='color:#2ecc71;'>{s['nadjena_cena']} RSD</b> ({s['sajt_izvora']})</li>" 
        for s in skenovi
    ]) if skenovi else "<li>Čeka se prvi signal sa mreže...</li>"
    
    return f"""
    <html>
    <head><title>Vortex Kontrolni Centar</title></head>
    <body style="font-family: Arial, sans-serif; padding: 30px; background: #111; color: #eee;">
        <h1>⚡ Vortex Centralni Cloud Server</h1>
        <hr style="border-color: #333; margin-bottom: 25px;">
        <div style="background: #222; padding: 20px; border-radius: 8px; border: 1px solid #333;">
            <h2>📡 Skeniranje i upoređivanje tržišta uživo</h2>
            <ul>{skenovi_html}</ul>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    inicijalizuj_globalnu_bazu()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
