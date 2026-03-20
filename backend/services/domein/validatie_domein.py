"""
Domeinlaag: HR validatie — dataclasses, helpers en de 7 validators.
Geen SQLAlchemy, geen database-toegang.

Alle validators ontvangen een 'ctx' dict met:
    maand_start, maand_eind, context_start  : date-grenzen
    gebruikers   : dict[int, Gebruiker-achtig object]
    shifts_per_user : dict[int, dict[date, str|None]]
    shifts_per_dag  : dict[date, list[str|None]]
    sc_lut       : dict[str, Shiftcode-achtig object]  (met .shift_type, .start_uur, .eind_uur)
    sp_lut       : dict[str, SpecialCode-achtig object] (met .telt_als_werkdag)
    regels       : dict[str, HRRegel-achtig object]     (met .waarde, .ernst_niveau)
    rode_lijn    : RodeLijn-achtig object | None        (met .start_datum, .interval_dagen)
    overrides    : set[tuple[int, date, str]]
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

# ------------------------------------------------------------------ #
# Domeinobject                                                         #
# ------------------------------------------------------------------ #

@dataclass
class ValidatieFout:
    gebruiker_id: int        # 0 = groepsniveau (bijv. kritieke shift)
    gebruiker_naam: str
    datum: date
    validator_code: str
    ernst: str               # "INFO", "WARNING", "CRITICAL"
    bericht: str
    heeft_override: bool = False
    gebruiker_uuid: str = ""  # ingevuld door ValidatieService na lookup


# ------------------------------------------------------------------ #
# Sortering                                                            #
# ------------------------------------------------------------------ #

ERNST_VOLGORDE: dict[str, int] = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


def sorteer_fouten(fouten: list[ValidatieFout]) -> list[ValidatieFout]:
    """Sorteert fouten: CRITICAL eerst, daarna oplopend op datum."""
    fouten.sort(key=lambda f: (ERNST_VOLGORDE.get(f.ernst, 3), f.datum))
    return fouten


# ------------------------------------------------------------------ #
# Hulpfuncties                                                         #
# ------------------------------------------------------------------ #

def is_werkdag(code: str | None, sc_lut: dict, sp_lut: dict) -> bool:
    """True als de shiftcode telt als gewerkte dag."""
    if not code:
        return False
    if code in sc_lut:
        return sc_lut[code].shift_type in ("vroeg", "laat", "nacht", "dag")
    if code in sp_lut:
        return sp_lut[code].telt_als_werkdag
    return True  # onbekende code: voorzichtigheidshalve als werkdag tellen


def is_nachtshift(code: str | None, sc_lut: dict) -> bool:
    if not code:
        return False
    return sc_lut.get(code) is not None and sc_lut[code].shift_type == "nacht"


def is_vroeg_of_dag(code: str | None, sc_lut: dict) -> bool:
    if not code:
        return False
    sc = sc_lut.get(code)
    return sc is not None and sc.shift_type in ("vroeg", "dag")


def dag_type_voor_datum(d: date) -> str:
    """Geeft 'weekend' of 'werkdag' (feestdagen niet apart behandeld in v0.8)."""
    return "weekend" if d.weekday() >= 5 else "werkdag"


def shift_minuten(code: str | None, sc_lut: dict) -> tuple[int | None, int | None]:
    """Geeft (start_min, eind_min) van een shiftcode. None als niet beschikbaar."""
    if not code or code not in sc_lut:
        return None, None
    sc = sc_lut[code]
    if not sc.start_uur or not sc.eind_uur:
        return None, None

    def parse(t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    return parse(sc.start_uur), parse(sc.eind_uur)


def uren_per_shift(code: str | None, sc_lut: dict) -> float:
    """Schat het aantal werkuren van een shift."""
    start, eind = shift_minuten(code, sc_lut)
    if start is None or eind is None:
        return 8.0  # standaard aanname
    if eind > start:
        return (eind - start) / 60
    # Shift loopt over middernacht (nacht)
    return (24 * 60 - start + eind) / 60


# ------------------------------------------------------------------ #
# Validators                                                           #
# ------------------------------------------------------------------ #

def valideer_kritieke_shifts(ctx: dict[str, Any]) -> list[ValidatieFout]:
    """KRITIEKE_SHIFT: controleer of alle kritieke shift codes bezet zijn."""
    fouten = []
    sc_lut: dict = ctx["sc_lut"]
    shifts_per_dag: dict = ctx["shifts_per_dag"]
    maand_start: date = ctx["maand_start"]
    maand_eind: date = ctx["maand_eind"]

    kritieke_codes = [sc for sc in sc_lut.values() if sc.is_kritisch]
    if not kritieke_codes:
        return []

    dag = maand_start
    while dag <= maand_eind:
        dt = dag_type_voor_datum(dag)
        bezet_codes = {c for c in shifts_per_dag.get(dag, []) if c}

        for sc in kritieke_codes:
            if sc.dag_type and sc.dag_type != dt:
                continue
            if sc.code not in bezet_codes:
                fouten.append(ValidatieFout(
                    gebruiker_id=0,
                    gebruiker_naam="(groep)",
                    datum=dag,
                    validator_code="KRITIEKE_SHIFT",
                    ernst="CRITICAL",
                    bericht=f"Kritieke shift '{sc.code}' is niet bezet op {dag.strftime('%d/%m')}.",
                ))
        dag = dag + timedelta(days=1)
    return fouten


def valideer_max_dagen_op_rij(ctx: dict[str, Any]) -> list[ValidatieFout]:
    """MAX_DAGEN_OP_RIJ: max N aaneengesloten werkdagen."""
    regel = ctx["regels"].get("MAX_DAGEN_OP_RIJ")
    if not regel:
        return []
    max_dagen = regel.waarde or 7
    ernst = regel.ernst_niveau

    fouten = []
    sc_lut = ctx["sc_lut"]
    sp_lut = ctx["sp_lut"]
    maand_start: date = ctx["maand_start"]
    maand_eind: date = ctx["maand_eind"]
    context_start: date = ctx["context_start"]

    for uid, gebruiker in ctx["gebruikers"].items():
        naam = gebruiker.volledige_naam or gebruiker.gebruikersnaam
        shiften = ctx["shifts_per_user"].get(uid, {})

        dag = context_start
        reeks = 0
        while dag <= maand_eind:
            code = shiften.get(dag)
            if is_werkdag(code, sc_lut, sp_lut):
                reeks += 1
                if reeks > max_dagen and maand_start <= dag <= maand_eind:
                    heeft_ovr = (uid, dag, "MAX_DAGEN_OP_RIJ") in ctx["overrides"]
                    fouten.append(ValidatieFout(
                        gebruiker_id=uid,
                        gebruiker_naam=naam,
                        datum=dag,
                        validator_code="MAX_DAGEN_OP_RIJ",
                        ernst=ernst,
                        bericht=f"{naam} werkt {reeks} werkdagen op rij (max {max_dagen}).",
                        heeft_override=heeft_ovr,
                    ))
            else:
                reeks = 0
            dag = dag + timedelta(days=1)
    return fouten


def valideer_nachtshift_opvolging(ctx: dict[str, Any]) -> list[ValidatieFout]:
    """NACHT_OPVOLGING: na een nachtshift geen vroege/dag shift."""
    regel = ctx["regels"].get("NACHT_OPVOLGING")
    if not regel:
        return []
    ernst = regel.ernst_niveau

    fouten = []
    sc_lut = ctx["sc_lut"]
    maand_start: date = ctx["maand_start"]
    maand_eind: date = ctx["maand_eind"]
    context_start: date = ctx["context_start"]

    for uid, gebruiker in ctx["gebruikers"].items():
        naam = gebruiker.volledige_naam or gebruiker.gebruikersnaam
        shiften = ctx["shifts_per_user"].get(uid, {})

        dag = context_start + timedelta(days=1)
        while dag <= maand_eind:
            vorige = dag - timedelta(days=1)
            code_vorige = shiften.get(vorige)
            code_huidig = shiften.get(dag)

            if (
                is_nachtshift(code_vorige, sc_lut)
                and is_vroeg_of_dag(code_huidig, sc_lut)
                and maand_start <= dag <= maand_eind
            ):
                heeft_ovr = (uid, dag, "NACHT_OPVOLGING") in ctx["overrides"]
                fouten.append(ValidatieFout(
                    gebruiker_id=uid,
                    gebruiker_naam=naam,
                    datum=dag,
                    validator_code="NACHT_OPVOLGING",
                    ernst=ernst,
                    bericht=(
                        f"{naam}: vroege/dag shift ({code_huidig}) direct na "
                        f"nachtshift ({code_vorige}) op {dag.strftime('%d/%m')}."
                    ),
                    heeft_override=heeft_ovr,
                ))
            dag = dag + timedelta(days=1)
    return fouten


def valideer_max_weekends_op_rij(ctx: dict[str, Any]) -> list[ValidatieFout]:
    """MAX_WEEKENDS_OP_RIJ: max N aaneengesloten weekenden gewerkt."""
    regel = ctx["regels"].get("MAX_WEEKENDS_OP_RIJ")
    if not regel:
        return []
    max_weekends = regel.waarde or 6
    ernst = regel.ernst_niveau

    fouten = []
    sc_lut = ctx["sc_lut"]
    sp_lut = ctx["sp_lut"]
    maand_start: date = ctx["maand_start"]
    maand_eind: date = ctx["maand_eind"]
    context_start: date = ctx["context_start"]

    for uid, gebruiker in ctx["gebruikers"].items():
        naam = gebruiker.volledige_naam or gebruiker.gebruikersnaam
        shiften = ctx["shifts_per_user"].get(uid, {})

        # Zoek eerste zaterdag in het context window
        dag = context_start
        while dag.weekday() != 5:
            dag = dag + timedelta(days=1)

        weekenden_op_rij = 0
        while dag <= maand_eind:
            zo = dag + timedelta(days=1)
            za_werk = is_werkdag(shiften.get(dag), sc_lut, sp_lut)
            zo_werk = is_werkdag(shiften.get(zo), sc_lut, sp_lut)

            if za_werk or zo_werk:
                weekenden_op_rij += 1
                if weekenden_op_rij > max_weekends and maand_start <= dag <= maand_eind:
                    heeft_ovr = (uid, dag, "MAX_WEEKENDS_OP_RIJ") in ctx["overrides"]
                    fouten.append(ValidatieFout(
                        gebruiker_id=uid,
                        gebruiker_naam=naam,
                        datum=dag,
                        validator_code="MAX_WEEKENDS_OP_RIJ",
                        ernst=ernst,
                        bericht=(
                            f"{naam} werkt {weekenden_op_rij} weekenden op rij "
                            f"(max {max_weekends})."
                        ),
                        heeft_override=heeft_ovr,
                    ))
            else:
                weekenden_op_rij = 0

            dag = dag + timedelta(days=7)
    return fouten


def valideer_rode_lijn(ctx: dict[str, Any]) -> list[ValidatieFout]:
    """RODE_LIJN_MAX_WERK: max N werkdagen per rode lijn cyclus."""
    regel = ctx["regels"].get("RODE_LIJN_MAX_WERK")
    rode_lijn = ctx.get("rode_lijn") or ctx.get("rode_lijn_config")
    if not regel or not rode_lijn:
        return []
    max_werkdagen = regel.waarde or 19
    interval = rode_lijn.interval_dagen
    ernst = regel.ernst_niveau

    fouten = []
    sc_lut = ctx["sc_lut"]
    sp_lut = ctx["sp_lut"]
    maand_start: date = ctx["maand_start"]
    maand_eind: date = ctx["maand_eind"]

    # Bepaal alle rode lijn periodes die overlappen met de doelmaand
    rl_start = rode_lijn.start_datum
    periodes: list[tuple[date, date]] = []
    periode_s = rl_start
    while periode_s <= maand_eind + timedelta(days=interval):
        periode_e = periode_s + timedelta(days=interval - 1)
        if periode_e >= maand_start:
            periodes.append((periode_s, periode_e))
        if periode_s > maand_eind:
            break
        periode_s = periode_s + timedelta(days=interval)

    for uid, gebruiker in ctx["gebruikers"].items():
        naam = gebruiker.volledige_naam or gebruiker.gebruikersnaam
        shiften = ctx["shifts_per_user"].get(uid, {})

        for periode_start, periode_eind in periodes:
            werkdagen = 0
            d = periode_start
            while d <= periode_eind:
                if is_werkdag(shiften.get(d), sc_lut, sp_lut):
                    werkdagen += 1
                d = d + timedelta(days=1)

            if werkdagen > max_werkdagen:
                rapportage_datum = min(periode_eind, maand_eind)
                if rapportage_datum >= maand_start:
                    heeft_ovr = (uid, rapportage_datum, "RODE_LIJN_MAX_WERK") in ctx["overrides"]
                    fouten.append(ValidatieFout(
                        gebruiker_id=uid,
                        gebruiker_naam=naam,
                        datum=rapportage_datum,
                        validator_code="RODE_LIJN_MAX_WERK",
                        ernst=ernst,
                        bericht=(
                            f"{naam}: {werkdagen} werkdagen in rode lijn periode "
                            f"{periode_start.strftime('%d/%m')}–{periode_eind.strftime('%d/%m')} "
                            f"(max {max_werkdagen})."
                        ),
                        heeft_override=heeft_ovr,
                    ))
    return fouten


def valideer_max_uren_week(ctx: dict[str, Any]) -> list[ValidatieFout]:
    """MAX_UREN_PER_WEEK: max N werkuren per kalenderweek."""
    regel = ctx["regels"].get("MAX_UREN_PER_WEEK")
    if not regel:
        return []
    max_uren = regel.waarde or 50
    ernst = regel.ernst_niveau

    fouten = []
    sc_lut = ctx["sc_lut"]
    sp_lut = ctx["sp_lut"]
    maand_start: date = ctx["maand_start"]
    maand_eind: date = ctx["maand_eind"]

    for uid, gebruiker in ctx["gebruikers"].items():
        naam = gebruiker.volledige_naam or gebruiker.gebruikersnaam
        shiften = ctx["shifts_per_user"].get(uid, {})

        # Groepeer per week (maandag = begin)
        weken: dict[date, list[tuple[date, str | None]]] = {}
        d = maand_start
        while d <= maand_eind:
            maandag = d - timedelta(days=d.weekday())
            weken.setdefault(maandag, []).append((d, shiften.get(d)))
            d = d + timedelta(days=1)

        for week_maandag, dagen in weken.items():
            totaal_uren = sum(
                uren_per_shift(code, sc_lut)
                for _, code in dagen
                if is_werkdag(code, sc_lut, sp_lut)
            )
            if totaal_uren > max_uren:
                rapportage_datum = max(dag for dag, _ in dagen if maand_start <= dag <= maand_eind)
                heeft_ovr = (uid, rapportage_datum, "MAX_UREN_PER_WEEK") in ctx["overrides"]
                fouten.append(ValidatieFout(
                    gebruiker_id=uid,
                    gebruiker_naam=naam,
                    datum=rapportage_datum,
                    validator_code="MAX_UREN_PER_WEEK",
                    ernst=ernst,
                    bericht=(
                        f"{naam}: {totaal_uren:.0f} uur in week van "
                        f"{week_maandag.strftime('%d/%m')} (max {max_uren} uur)."
                    ),
                    heeft_override=heeft_ovr,
                ))
    return fouten


def valideer_min_rusttijd(ctx: dict[str, Any]) -> list[ValidatieFout]:
    """MIN_RUSTTIJD: minimaal N uur rust tussen twee shifts."""
    regel = ctx["regels"].get("MIN_RUSTTIJD")
    if not regel:
        return []
    min_uren = regel.waarde or 11
    ernst = regel.ernst_niveau

    fouten = []
    sc_lut = ctx["sc_lut"]
    sp_lut = ctx["sp_lut"]
    maand_start: date = ctx["maand_start"]
    maand_eind: date = ctx["maand_eind"]
    context_start: date = ctx["context_start"]

    for uid, gebruiker in ctx["gebruikers"].items():
        naam = gebruiker.volledige_naam or gebruiker.gebruikersnaam
        shiften = ctx["shifts_per_user"].get(uid, {})

        dag = context_start + timedelta(days=1)
        while dag <= maand_eind:
            vorige = dag - timedelta(days=1)
            code_vorige = shiften.get(vorige)
            code_huidig = shiften.get(dag)

            if not is_werkdag(code_vorige, sc_lut, sp_lut) or not is_werkdag(code_huidig, sc_lut, sp_lut):
                dag = dag + timedelta(days=1)
                continue

            start_v, eind_v = shift_minuten(code_vorige, sc_lut)
            start_h, _ = shift_minuten(code_huidig, sc_lut)

            if start_v is None or eind_v is None or start_h is None:
                dag = dag + timedelta(days=1)
                continue

            # Bereken rustminuten tussen einde vorige shift en begin huidige shift
            if eind_v <= start_v:
                # Nachtshift: eindigt op eind_v (volgend dag-context)
                rust_min = start_h - eind_v
                if rust_min < 0:
                    rust_min += 24 * 60
            else:
                # Normale shift: eindigt dezelfde dag
                rust_min = (24 * 60 + start_h) - eind_v

            if rust_min < min_uren * 60 and maand_start <= dag <= maand_eind:
                heeft_ovr = (uid, dag, "MIN_RUSTTIJD") in ctx["overrides"]
                fouten.append(ValidatieFout(
                    gebruiker_id=uid,
                    gebruiker_naam=naam,
                    datum=dag,
                    validator_code="MIN_RUSTTIJD",
                    ernst=ernst,
                    bericht=(
                        f"{naam}: slechts {rust_min // 60}u {rust_min % 60}min rust "
                        f"tussen {code_vorige} en {code_huidig} op {dag.strftime('%d/%m')} "
                        f"(min {min_uren} uur)."
                    ),
                    heeft_override=heeft_ovr,
                ))
            dag = dag + timedelta(days=1)
    return fouten


def valideer_dubbele_shift(ctx: dict[str, Any]) -> list[ValidatieFout]:
    """DUBBELE_SHIFT: kritieke shift toegewezen aan meer dan één medewerker op dezelfde dag."""
    regel = ctx["regels"].get("DUBBELE_SHIFT")
    if not regel:
        return []
    ernst = regel.ernst_niveau

    sc_lut: dict = ctx["sc_lut"]
    shifts_per_user: dict = ctx["shifts_per_user"]
    maand_start: date = ctx["maand_start"]
    maand_eind: date = ctx["maand_eind"]

    kritieke_codes = {code for code, sc in sc_lut.items() if sc.is_kritisch}
    if not kritieke_codes:
        return []

    fouten = []
    dag = maand_start
    while dag <= maand_eind:
        # Tel per kritieke code hoeveel gebruikers die code hebben op deze dag
        tellers: dict[str, int] = {}
        for uid_shifts in shifts_per_user.values():
            code = uid_shifts.get(dag)
            if code and code in kritieke_codes:
                tellers[code] = tellers.get(code, 0) + 1

        for code, aantal in tellers.items():
            if aantal > 1:
                fouten.append(ValidatieFout(
                    gebruiker_id=0,
                    gebruiker_naam="(team)",
                    datum=dag,
                    validator_code="DUBBELE_SHIFT",
                    ernst=ernst,
                    bericht=(
                        f"Kritieke shift '{code}' is {aantal}× toegewezen op "
                        f"{dag.strftime('%d/%m')} (mag slechts 1×)."
                    ),
                ))
        dag = dag + timedelta(days=1)
    return fouten


def valideer_rx_gap(ctx: dict[str, Any]) -> list[ValidatieFout]:
    """RX_MAX_GAP: max N dagen tussen twee RX-rustdagen (RXW of RXF) per medewerker.

    Een 'lege cel' (geen shift op een dag) doorbreekt het segment — dan wordt de gap
    niet gemeld, want de planning is niet volledig voor die periode.
    """
    regel = ctx["regels"].get("RX_MAX_GAP")
    if not regel:
        return []
    max_gap: int = regel.waarde or 7
    ernst = regel.ernst_niveau

    fouten = []
    maand_start: date = ctx["maand_start"]
    maand_eind: date = ctx["maand_eind"]
    context_start: date = ctx["context_start"]

    RX_CODES = {"RXW", "RXF"}

    for uid, gebruiker in ctx["gebruikers"].items():
        naam = gebruiker.volledige_naam or gebruiker.gebruikersnaam
        shiften: dict[date, str | None] = ctx["shifts_per_user"].get(uid, {})

        # Verzamel alle RX-datums in het context window, op volgorde
        rx_datums: list[date] = []
        dag = context_start
        while dag <= maand_eind:
            code = shiften.get(dag)
            if code and code.upper() in RX_CODES:
                rx_datums.append(dag)
            dag = dag + timedelta(days=1)

        # Controleer gap tussen opeenvolgende RX-datums
        for i in range(len(rx_datums) - 1):
            rx1 = rx_datums[i]
            rx2 = rx_datums[i + 1]

            # Check of het segment gebroken is door een lege cel (geen shift entry)
            segment_gebroken = any(
                shiften.get(rx1 + timedelta(days=d)) is None
                for d in range(1, (rx2 - rx1).days)
            )
            if segment_gebroken:
                continue

            gap_dagen = (rx2 - rx1).days - 1  # dagen tússen de twee RX-datums

            if gap_dagen > max_gap:
                # Rapporteer op de datum van de tweede RX als die in de maand valt,
                # anders op maand_eind als rx1 in de context maar buiten de maand ligt
                rapportage_datum = rx2 if maand_start <= rx2 <= maand_eind else None
                if rapportage_datum is None and rx1 < maand_start:
                    rapportage_datum = min(rx2, maand_eind)
                if rapportage_datum is None:
                    continue

                heeft_ovr = (uid, rapportage_datum, "RX_MAX_GAP") in ctx["overrides"]
                fouten.append(ValidatieFout(
                    gebruiker_id=uid,
                    gebruiker_naam=naam,
                    datum=rapportage_datum,
                    validator_code="RX_MAX_GAP",
                    ernst=ernst,
                    bericht=(
                        f"{naam}: {gap_dagen} dagen tussen RX-rustdag op "
                        f"{rx1.strftime('%d/%m')} en {rx2.strftime('%d/%m')} "
                        f"(max {max_gap})."
                    ),
                    heeft_override=heeft_ovr,
                ))
    return fouten


# ------------------------------------------------------------------ #
# Validator register                                                   #
# ------------------------------------------------------------------ #

VALIDATORS = [
    valideer_kritieke_shifts,
    valideer_max_dagen_op_rij,
    valideer_nachtshift_opvolging,
    valideer_max_weekends_op_rij,
    valideer_rode_lijn,
    valideer_max_uren_week,
    valideer_min_rusttijd,
    valideer_dubbele_shift,
    valideer_rx_gap,
]
