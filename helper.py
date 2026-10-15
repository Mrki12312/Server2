import re

def izvuci_univerzalni_sku(ime_artikla):
    if not ime_artikla:
        return "NEPOZNAT_MODEL"
        
    tekst = ime_artikla.upper()
    
    # Tražimo kombinacije slova i brojeva (šifre modela kao što je 50X120CM)
    skovi_sablon = re.findall(r'\b[A-Z0-9]{3,12}\b', tekst)
    if skovi_sablon:
        for stavka in skovi_sablon:
            # Ako šifra sadrži bar jedan broj, to je sigurno model (npr. 50X120CM)
            if any(c.isdigit() for c in stavka):
                return stavka
                
    # Rezervni plan ako nema fabričke šifre
    stop_reci = {"SET", "SLIKA", "DELA", "PODNA", "LAMPA", "CRNA", "MODERNA"}
    reci = [rec for rec in tekst.split() if rec not in stop_reci and len(rec) > 2]
    if reci:
        return str(reci[0])  # POPRAVLJENO: Uzimamo prvi tekstualni element iz niza
        
    return "NEPOZNAT_MODEL"

def izracunaj_vortex_cenu(cena_trenutna, cena_najniza_baza):
    """Računa srednju cenu za kupca i osigurava tvoju maržu od minimalno 10%"""
    srednja_cena = round((cena_trenutna + cena_najniza_baza) / 2, 2)
    minimalna_tvoja_cena = cena_najniza_baza * 1.10
    
    if srednja_cena < minimalna_tvoja_cena:
        srednja_cena = round(minimalna_tvoja_cena, 2)
        
    usteda = round(cena_trenutna - srednja_cena, 2)
    return {
        "vortex_cena": srednja_cena,
        "usteda": usteda,
        "validno": usteda > 0
    }
