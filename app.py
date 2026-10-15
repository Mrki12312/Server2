from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import datetime
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BAZA_NAME = "vortex_network_v4.db"

def inicijalizuj_globalnu_bazu():
    conn = sqlite3.connect(BAZA_NAME, timeout=30)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skenirano_trziste (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artikal_id TEXT,
            ime TEXT,
            nadjena_cena REAL,
            sajt_izvora TEXT,
            link_proizvoda TEXT,
            vreme_skena TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS robot_zadaci (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            termin_pretrage TEXT,
            status TEXT,
            vreme_kreiranja TEXT
        )
    """)
    conn.commit()
    conn.close()

# Inicijalizujemo bazu odmah
inicijalizuj_globalnu_bazu()

# ================= RUTE ZA EKSTENZIJE =================

# POPRAVLJENO: Tvoja stara ekstenzija šalje podatke ovde.
# Sada ova ruta NE SAMO da upisuje cenu, već ODMAH pravi i zadatak za robota!
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
    
    # Ako tvoja stara ekstenzija ne šalje artikal_id (SKU), generišemo ga automatski iz naslova
    if artikal_id == "SKU_NEPOZNAT" and ime_artikla != "Nepoznat naziv":
        from helper import izvuci_univerzalni_sku
        artikal_id = izvuci_univerzalni_sku(ime_artikla)
    
    conn = sqlite3.connect(BAZA_NAME, timeout=30)
    cursor = conn.cursor()
    
    vreme_sada = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Upisujemo proizvod u skladište tržišta
    cursor.execute("""
        INSERT INTO skenirano_trziste (artikal_id, ime, nadjena_cena, sajt_izvora, link_proizvoda, vreme_skena)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (artikal_id, ime_artikla, cena, sajt, link, vreme_sada))
    
    # 2. AUTOMATSKI DOSTAVLJAMO ZADATAK ROBOTU (Most za staru ekstenziju!)
    # Proveravamo da li ovaj zadatak već čeka u redu da ne bismo zatrpali robota duplikatima
    cursor.execute("SELECT id FROM robot_zadaci WHERE termin_pretrage = ? AND status = 'CEKA'", (ime_artikla,))
    postoji = cursor.fetchone()
    
    if not postoji:
        cursor.execute("""
            INSERT INTO robot_zadaci (termin_pretrage, status, vreme_kreiranja)
            VALUES (?, 'CEKA', ?)
        """, (ime_artikla, vreme_sada))
        print(f"🤖 [Server] Kreiran automatski zadatak za kućnog robota: {ime_artikla}")
    
    conn.commit()
    conn.close()
    return jsonify({"status": "uspeh", "sku": artikal_id})


# Pomoćna ruta (ako neka nova ekstenzija bude koristila ovaj naziv)
@app.route("/api/vortex-pokreni-pretragu", methods=["POST"])
def pokreni_vortex_robotiku():
    return upis_cena_iz_ekstenzije()


# ================= KORAK ZA KUPCA (PROVERA NAJJEFTINIJE CENE) =================

@app.route("/api/vortex-provera-ponude", methods=["GET"])
def provera_ponude_za_kupca():
    sku = request.args.get("sku")
    if not sku:
        return jsonify({"status": "greska", "poruka": "Fali SKU"})
        
    conn = sqlite3.connect(BAZA_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Tražimo najjeftiniju opciju koju je robot skrapovao (izvori koji sadrže 'Ponuda' ili 'Opcija')
    cursor.execute("""
        SELECT * FROM skenirano_trziste 
        WHERE artikal_id = ? AND (sajt_izvora LIKE '%Ponuda%' OR sajt_izvora LIKE '%Opcija%')
        ORDER BY nadjena_cena ASC LIMIT 1
    """, (sku,))
    
    najbolja_opcija = cursor.fetchone()
    conn.close()
    
    if najbolja_opcija:
        return jsonify({
            "status": "pronadjeno",
            "bolja_cena": najbolja_opcija["nadjena_cena"],
            "link": najbolja_opcija["link_proizvoda"]
        })
        
    return jsonify({"status": "cekanje"})


# ================= RUTA ZA TVOG KUĆNOG ROBOTA (`robot_polling.py`) =================

@app.route("/api/robot-sledeci-zadatak", methods=["GET"])
def sledeci_zadatak_za_robota():
    conn = sqlite3.connect(BAZA_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM robot_zadaci WHERE status = 'CEKA' ORDER BY vreme_kreiranja ASC LIMIT 1")
    zadatak = cursor.fetchone()
    
    if zadatak:
        # Menjamo status u 'U_OBRADI' da drugi procesi ne bi preuzeli isti posao
        cursor.execute("UPDATE robot_zadaci SET status = 'U_OBRADI' WHERE id = ?", (zadatak["id"],))
        conn.commit()
        conn.close()
        return jsonify({"status": "ima_posla", "id": zadatak["id"], "termin": zadatak["termin_pretrage"]})
        
    conn.close()
    return jsonify({"status": "nema_posla"})


# ================= KONTROLNA TABLA =================
@app.route("/")
def administrativni_panel():
    conn = sqlite3.connect(BAZA_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM skenirano_trziste ORDER BY vreme_skena DESC LIMIT 40")
    skenovi = cursor.fetchall()
    conn.close()
    
    skenovi_html = ""
    if skenovi:
        for s in skenovi:
            artikal_id = s["artikal_id"] if "artikal_id" in s.keys() else "N/A"
            link = s["link_proizvoda"] if "link_proizvoda" in s.keys() else "#"
            ime = s["ime"] if "ime" in s.keys() else "Nepoznato"
            cena = s["nadjena_cena"] if "nadjena_cena" in s.keys() else 0
            izvor = s["sajt_izvora"] if "sajt_izvora" in s.keys() else "N/A"
            
            skenovi_html += f"<li>📡 <b>SKU: {artikal_id}</b> | <a href='{link}' target='_blank' style='color:#aaa;text-decoration:none;'>{ime[:50]}...</a> | <b style='color:#2ecc71;'>{cena} RSD</b> ({izvor})</li>"
    else:
        skenovi_html = "<li>Čeka se prvi signal sa mreže...</li>"
    
    return f"""
    <html>
    <head><title>Vortex Kontrolni Centar</title></head>
    <body style="font-family: Arial, sans-serif; padding: 30px; background: #111; color: #eee;">
        <h1>⚡ Vortex Centralni Cloud Server (Uvezan sa starom ekstenzijom)</h1>
        <hr style="border-color: #333; margin-bottom: 25px;">
        <div style="background: #222; padding: 20px; border-radius: 8px; border: 1px solid #333;">
            <h2>📡 Skeniranje i upoređivanje tržišta uživo</h2>
            <ul>{skenovi_html}</ul>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
