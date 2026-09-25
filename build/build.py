#!/usr/bin/env python3
"""Build the India data centre NETCONF go-to-market report.

Reads the CSVs in data/, applies the tidying rules in CLAUDE.md section 6,
builds every join and derived field, prints the section 13 verification
numbers, and writes dist/index.html from build/template.html.

Run from the repo root:  python build/build.py
"""

import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BUILD = ROOT / "build"
DIST = ROOT / "dist"

# ---------------------------------------------------------------------------
# Data integrity (CLAUDE.md section 14)
# ---------------------------------------------------------------------------

FINGERPRINTS = {
    "exchange_facilities.csv": "4fc4024ca6266294f8453a03a0f513749fe003c0846d068334fb397edcf78d52",
    "exchange_ports.csv": "da75c1745e0d92d1ef037231f8a27c2d6e4f0ee4f142fbbca53b2a2755d6d55e",
    "exchanges.csv": "289f6ae4153e247c3123677247839dc40233395bc09af6ee147b044ae382dc94",
    "facilities.csv": "ee4a85418f104ff654c49f117c1f07ed24a618bc59e4d031a1e7c4b883224540",
    "facility_networks.csv": "ac174877704f7437453e3ebec1f8c4beb1adad09e6176d7188785ede4cd80922",
    "networks.csv": "0eb05b06a5ed829576f66174400f8f61cebdb04ca38971a466e3ba0944c3239a",
    "nixi_isps.csv": "529e28ea7e2c0e8e9c75262f2306cd4fe7ec15cf5f02608333656b8646f25bf7",
    "nixi_locations.csv": "6cb493d6a4605c5221c85138be3caeafea89d27bc32321ff06d38a4c27d221a2",
}


def check_fingerprints():
    bad = []
    for name, expected in sorted(FINGERPRINTS.items()):
        path = DATA / name
        if not path.exists():
            bad.append(f"{name}: missing")
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != expected:
            bad.append(f"{name}:\n    expected {expected}\n    found    {got}")
    if bad:
        print("STOP. A file in data/ does not match its fingerprint in CLAUDE.md section 14.")
        print("Tell Krish before going any further. Do not try to repair the file.\n")
        for b in bad:
            print("  " + b)
        sys.exit(1)
    print("Data fingerprints: all 8 files match CLAUDE.md section 14.\n")


# ---------------------------------------------------------------------------
# Reading (every column as text, empty cells as empty strings)
# ---------------------------------------------------------------------------

def read_csv(name):
    with open(DATA / name, newline="", encoding="utf-8-sig") as fh:
        rows = []
        for row in csv.DictReader(fh):
            rows.append({k: ("" if v is None else v) for k, v in row.items() if k is not None})
        return rows


def key(v):
    """Trim whitespace on a join key. IDs stay text."""
    return str(v).strip()


def as_int(v):
    v = str(v).strip()
    if not v:
        return 0
    try:
        return int(float(v))
    except ValueError:
        return 0


def as_float(v):
    v = str(v).strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Section 6 tidying rules
# ---------------------------------------------------------------------------

CITY_REPLACEMENTS = {
    "Mumbai,": "Mumbai",
    "Navi Mumbai,": "Navi Mumbai",
    "Panvel, Raigad,": "Panvel",
    "Egmore ,Chennai": "Chennai",
    "Serilingampally,Hyderabad": "Hyderabad",
    "Gurgaon": "Gurugram",
    "Vijaywada": "Vijayawada",
    "Vishakhapatam": "Visakhapatnam",
    "Viskhapatnam": "Visakhapatnam",
    "YamunaNagar": "Yamuna Nagar",
    "Bengaluru": "Bangalore",
}


def title_case(value):
    """Rules 6.1 and 6.3: a value written entirely in capitals becomes title case.

    Only the leading word is recased, so the spellings the data already uses for
    the trailing site codes are kept: CHENNAI-STT becomes Chennai-STT, which is
    how rule 6.3 merges it with the row already written Chennai-STT, and
    COCHIN NOC becomes Cochin NOC, the spelling used in zoneName. A value that
    is not entirely in capitals is left exactly as it is.
    """
    if not value or not value.isupper():
        return value
    m = re.match(r"[A-Za-z]+", value)
    if not m:
        return value
    word = m.group(0)
    return word[0].upper() + word[1:].lower() + value[m.end():]


def clean_city(raw):
    """Rule 6.1. Replace the listed values, strip spaces and commas, then title case."""
    v = CITY_REPLACEMENTS.get(raw, raw)
    v = v.strip(" ,\t\r\n")
    v = CITY_REPLACEMENTS.get(v, v)
    return title_case(v)


def clean_nixi_name(raw):
    """Rule 6.2, first half: trim spaces and line breaks."""
    return re.sub(r"\s+", " ", str(raw).replace("\r", " ").replace("\n", " ")).strip()


# ---------------------------------------------------------------------------
# Section 7 definitions
# ---------------------------------------------------------------------------

TIERS = {
    1: {"name": "Major hub", "rule": "50 or more networks inside"},
    2: {"name": "Mid-size", "rule": "10 to 49 networks inside"},
    3: {"name": "Small", "rule": "Fewer than 10 networks inside"},
}


def tier_of(linked_network_count):
    if linked_network_count >= 50:
        return 1
    if linked_network_count >= 10:
        return 2
    return 3


MATCH_GROUPS = [
    ("fac", "Already in facility data",
     "The ASN belongs to a network installed in at least one Indian facility, so we already have it."),
    ("port", "Seen only at exchanges",
     "The ASN has a port on an Indian internet exchange, but no facility listing."),
    ("pdb", "In PeeringDB, not linked to India",
     "The ASN is on PeeringDB, but with no Indian facility and no Indian exchange port."),
    ("none", "Only known through NIXI",
     "The ASN is not on PeeringDB at all. NIXI's list is the only place it appears."),
]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main():
    check_fingerprints()

    facilities_raw = read_csv("facilities.csv")
    facnets_raw = read_csv("facility_networks.csv")
    networks_raw = read_csv("networks.csv")
    ixfac_raw = read_csv("exchange_facilities.csv")
    exchanges_raw = read_csv("exchanges.csv")
    ports_raw = read_csv("exchange_ports.csv")
    nixi_locs_raw = read_csv("nixi_locations.csv")
    nixi_isps_raw = read_csv("nixi_isps.csv")

    sheets = [
        ("Facilities", "facilities.csv", "PeeringDB fac", "Datacentres - PeeringDB ( india",
         "One data centre building in India.", len(facilities_raw)),
        ("Networks in facilities", "facility_networks.csv", "PeeringDB netfac", "occupiers NET_ID - peeringdb( i",
         "One network installed in one facility.", len(facnets_raw)),
        ("Networks", "networks.csv", "PeeringDB net", "Occupiers name - peeringdb( ind",
         "One network anywhere in the world. The report shows the ones linked to India.", len(networks_raw)),
        ("Exchanges in facilities", "exchange_facilities.csv", "PeeringDB ixfac", "peeringdb_ixfac",
         "One internet exchange present in one facility.", len(ixfac_raw)),
        ("Internet exchanges", "exchanges.csv", "PeeringDB ix", "peeringdb_ix",
         "One internet exchange in India.", len(exchanges_raw)),
        ("Exchange ports", "exchange_ports.csv", "PeeringDB netixlan", "peeringdb_netixlan_india",
         "One port a network has on an Indian exchange.", len(ports_raw)),
        ("NIXI locations", "nixi_locations.csv", "NIXI website", "nixi_noc_locations",
         "One NIXI location (NOC), with its phone number and address.", len(nixi_locs_raw)),
        ("NIXI ISPs", "nixi_isps.csv", "NIXI website", "nixi_noc_complete",
         "One ISP connected at one NIXI location.", len(nixi_isps_raw)),
    ]

    # ---- links -----------------------------------------------------------
    fac_nets = defaultdict(list)   # fac_id -> [net_id]
    net_facs = defaultdict(list)   # net_id -> [fac_id]
    for r in facnets_raw:
        f, n = key(r["fac_id"]), key(r["net_id"])
        fac_nets[f].append(n)
        net_facs[n].append(f)

    fac_ixs = defaultdict(list)    # fac_id -> [ix_id]
    ix_facs = defaultdict(list)    # ix_id  -> [fac_id]
    for r in ixfac_raw:
        f, i = key(r["fac_id"]), key(r["ix_id"])
        fac_ixs[f].append(i)
        ix_facs[i].append(f)

    # Port rules (Krish, 2026-09-25):
    #   - a port marked not operational counts nowhere at all;
    #   - a port with speed 0 has no recorded speed, so it is a real port but
    #     contributes to no capacity total and no average.
    # "countable" means operational. "rated" means operational and speed > 0.
    ports = []
    for r in ports_raw:
        op = key(r["operational"]) != "False"
        mbps = as_int(r["port_speed_mbps"])
        ports.append({
            "net_id": key(r["net_id"]),
            "ix_id": key(r["ix_id"]),
            "mbps": mbps,
            "asn": key(r["asn"]),
            "operational": key(r["operational"]),
            "op": op,
            "countable": op,
            "rated": op and mbps > 0,
            "id": key(r["netixlan_id"]),
        })
    # every port, used only by the detail panels, which show a port and say it does not count
    all_ports_by_net = defaultdict(list)
    all_ports_by_ix = defaultdict(list)
    for p in ports:
        all_ports_by_net[p["net_id"]].append(p)
        all_ports_by_ix[p["ix_id"]].append(p)
    # countable ports, used by every count, total and average on the site
    ports_by_net = defaultdict(list)
    ports_by_ix = defaultdict(list)
    for p in ports:
        if p["countable"]:
            ports_by_net[p["net_id"]].append(p)
            ports_by_ix[p["ix_id"]].append(p)

    # ---- facilities ------------------------------------------------------
    facilities = []
    for r in facilities_raw:
        fid = key(r["fac_id"])
        linked_nets = fac_nets.get(fid, [])
        linked_ixs = fac_ixs.get(fid, [])
        n = len(linked_nets)
        lat, lon = as_float(r["latitude"]), as_float(r["longitude"])
        contacts = [r["sales_email"], r["sales_phone"], r["tech_email"], r["tech_phone"]]
        facilities.append({
            "id": fid,
            "name": r["facility_name"],
            "org": r["org_name"],
            "aka": r["fac_aka"],
            "address1": r["address1"],
            "address2": r["address2"],
            "city": clean_city(r["city"]),
            "city_raw": r["city"],
            "state": r["state"],
            "zip": r["zipcode"],
            "lat": lat,
            "lon": lon,
            "web": r["fac_website"],
            "sales_email": r["sales_email"],
            "sales_phone": r["sales_phone"],
            "tech_email": r["tech_email"],
            "tech_phone": r["tech_phone"],
            "property": r["property"],
            "voltage": r["voltage_services"],
            "updated": r["last_updated"],
            "notes": r["fac_notes"],
            "carriers": as_int(r["fac_carrier_count"]),
            "n": n,                                   # rule 6.4: linked rows
            "nix": len(linked_ixs),                   # rule 6.4: linked rows
            "pdb_n": as_int(r["fac_net_count"]),      # PeeringDB's own count
            "pdb_nix": as_int(r["fac_ix_count"]),
            "tier": tier_of(n),
            "contact": any(c.strip() for c in contacts),
        })
    fac_by_id = {f["id"]: f for f in facilities}

    # ---- map positions (rule 6.7) ---------------------------------------
    city_points = {}
    coords = defaultdict(list)
    for f in facilities:
        if f["lat"] is not None and f["lon"] is not None:
            coords[f["city"]].append((f["lon"], f["lat"]))
    for city, pts in coords.items():
        city_points[city] = [
            round(sum(p[0] for p in pts) / len(pts), 5),
            round(sum(p[1] for p in pts) / len(pts), 5),
        ]
    off_map = Counter(f["city"] for f in facilities if f["city"] not in city_points)
    # most facilities first, then in the order the city first appears in facilities.csv
    first_seen = {}
    for i, f in enumerate(facilities):
        first_seen.setdefault(f["city"], i)
    off_map_list = sorted(off_map.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))

    # ---- networks --------------------------------------------------------
    # Krish, 2026-09-25: every network with evidence of equipment in India gets a
    # row, whether the evidence is a facility, an operational exchange port or
    # NIXI membership. Counts are real, including zeros, and each row says which
    # kinds of evidence it rests on.
    nixi_asns_raw = {key(r["asNumber"]) for r in nixi_isps_raw if key(r["asNumber"])}

    all_asns = set()
    net_rows_by_asn = defaultdict(list)
    net_raw_by_id = {}
    for r in networks_raw:
        nid = key(r["net_id"])
        net_raw_by_id[nid] = r
        asn = key(r["asn"])
        if asn:
            all_asns.add(asn)
            net_rows_by_asn[asn].append(nid)

    # NIXI locations per ASN, and the net_ids those ASNs resolve to
    nixi_locs_by_asn = defaultdict(list)
    for r in nixi_isps_raw:
        a, loc = key(r["asNumber"]), key(r["noc_location"])
        if a and loc not in nixi_locs_by_asn[a]:
            nixi_locs_by_asn[a].append(loc)
    nixi_net_ids = set()
    nixi_only_asns = []
    for a in nixi_locs_by_asn:
        ids = net_rows_by_asn.get(a, [])
        if ids:
            nixi_net_ids.update(ids)
        else:
            nixi_only_asns.append(a)

    fac_evidence = set(net_facs)
    port_evidence = set(ports_by_net)          # operational ports only: this is what counts
    listed_evidence = set(all_ports_by_net)    # any port listing: this is what earns a row
    universe = fac_evidence | listed_evidence | nixi_net_ids

    # Exchange infrastructure (rather than an independent organisation), from the data:
    #   infra  - PeeringDB types the network as a Route Server or Route Collector
    #   ix_run - the network's org_id is the org_id of an exchange in exchanges.csv
    INFRA_TYPES = {"Route Server", "Route Collector"}
    ix_org_ids = {key(r["ix_org_id"]) for r in exchanges_raw}
    ix_org_label = {}
    for r in exchanges_raw:
        ix_org_label.setdefault(key(r["ix_org_id"]), r["ix_name"].strip().split(" ")[0])

    def search_extra(*names):
        """Acronyms and punctuation-free forms, so AWS finds Amazon Web Services."""
        out = set()
        for nm in names:
            nm = (nm or "").strip()
            if not nm:
                continue
            words = [w for w in re.split(r"[^A-Za-z0-9]+", nm) if w]
            if len(words) > 1:
                ac = "".join(w[0] for w in words)
                if len(ac) >= 2:
                    out.add(ac.lower())
            squashed = re.sub(r"[^A-Za-z0-9]+", "", nm).lower()
            if squashed and squashed != nm.lower():
                out.add(squashed)
        return " ".join(sorted(out))

    networks = []
    for nid in sorted(universe, key=lambda x: int(x) if x.isdigit() else 0):
        r = net_raw_by_id.get(nid)
        if r is None:
            continue
        asn = key(r["asn"])
        facs = net_facs.get(nid, [])
        cports = ports_by_net.get(nid, [])
        aports = all_ports_by_net.get(nid, [])
        locs = nixi_locs_by_asn.get(asn, []) if asn else []
        org = key(r["org_id"])
        ev = ("F" if facs else "") + ("X" if cports else "") + ("N" if locs else "")
        networks.append({
            "id": nid,
            "name": r["network_name"],
            "aka": r["network_aka"],
            "long": r["name_long"],
            "web": r["network_website"],
            "asn": asn,
            "type": r["info_type"],
            "p4": r["info_prefixes4"],
            "p6": r["info_prefixes6"],
            "traffic": r["info_traffic"],
            "ratio": r["info_ratio"],
            "scope": r["info_scope"],
            "ipv6": r["info_ipv6"],
            "ww_ix": as_int(r["net_ix_count"]),
            "ww_fac": as_int(r["net_fac_count"]),
            "notes": r["network_notes"],
            "policy": r["policy_general"],
            "updated": r["net_updated"],
            "org_id": org,
            "facs": facs,
            "nports": len(cports),
            "nports_all": len(aports),
            "locs": locs,
            "ev": ev,
            # listed on an exchange, but every one of its ports is not operational,
            # so it earns a row and is searchable while counting towards nothing
            "stale": bool(aports) and not cports and not facs and not locs,
            "pdb": True,
            "infra": r["info_type"] in INFRA_TYPES,
            "ixrun": org in ix_org_ids,
            "ixrun_label": ix_org_label.get(org, ""),
            "sx": search_extra(r["network_name"], r["network_aka"], r["name_long"]),
        })

    # ISPs NIXI lists whose ASN has no PeeringDB network record at all: NIXI is the
    # only evidence they exist, so they get a row built from the NIXI data.
    isp_name_by_asn = {}
    isp_first_row = {}
    for r in nixi_isps_raw:
        a = key(r["asNumber"])
        if a:
            isp_first_row.setdefault(a, r)
    for a in sorted(nixi_only_asns, key=lambda x: int(x) if x.isdigit() else 0):
        nm = clean_nixi_name(isp_first_row[a]["companyName"])
        networks.append({
            "id": "nixi-" + a, "name": nm, "aka": "", "long": "", "web": "", "asn": a,
            "type": "", "p4": "", "p6": "", "traffic": "", "ratio": "", "scope": "",
            "ipv6": "", "ww_ix": 0, "ww_fac": 0, "notes": "", "policy": "", "updated": "",
            "org_id": "", "facs": [], "nports": 0, "nports_all": 0,
            "locs": nixi_locs_by_asn.get(a, []), "ev": "N", "stale": False, "pdb": False,
            "infra": False, "ixrun": False, "ixrun_label": "",
            "sx": search_extra(nm),
        })

    net_by_id = {n["id"]: n for n in networks}
    tenant_ids = {n["id"] for n in networks if n["facs"]}
    exchange_only_ids = {n["id"] for n in networks if n["nports"] and not n["facs"]}
    evidence_mix = Counter(n["ev"] for n in networks)
    stale_nets = [n for n in networks if n["stale"]]
    infra_nets = [n for n in networks if n["infra"]]
    ixrun_nets = [n for n in networks if n["ixrun"]]

    # ---- exchanges -------------------------------------------------------
    org_first_word = defaultdict(set)
    for r in exchanges_raw:
        org_first_word[key(r["ix_org_id"])].add(r["ix_name"].strip().split(" ")[0])
    for org, words in org_first_word.items():
        if len(words) != 1:
            print(f"STOP. Exchange operator {org} has more than one first word: {sorted(words)}")
            print("CLAUDE.md section 7 says first word and ix_org_id match one to one. Ask Krish.")
            sys.exit(1)

    exchanges = []
    for r in exchanges_raw:
        xid = key(r["ix_id"])
        xp = ports_by_ix.get(xid, [])          # countable: operational only
        xa = all_ports_by_ix.get(xid, [])      # every listed port
        rated = [p for p in xp if p["mbps"] > 0]
        rated_mbps = sum(p["mbps"] for p in rated)
        exchanges.append({
            "id": xid,
            "org_id": key(r["ix_org_id"]),
            "operator": r["ix_name"].strip().split(" ")[0],
            "name": r["ix_name"],
            "aka": r["ix_aka"],
            "long": r["ix_name_long"],
            "city": clean_city(r["ix_city"]),
            "city_raw": r["ix_city"],
            "notes": r["ix_notes"],
            "web": r["ix_website"],
            "stats": r["ix_url_stats"],
            "tech_email": r["ix_tech_email"],
            "tech_phone": r["ix_tech_phone"],
            "policy_email": r["ix_policy_email"],
            "policy_phone": r["ix_policy_phone"],
            "sales_email": r["ix_sales_email"],
            "sales_phone": r["ix_sales_phone"],
            "service": r["service_level"],
            "terms": r["terms"],
            "updated": r["ix_updated"],
            "pdb_nets": as_int(r["ix_net_count"]),
            "pdb_facs": as_int(r["ix_fac_count"]),
            "nets": len({p["net_id"] for p in xp}),   # rule 6.4: unique net_id, countable ports
            "ports": len(xp),                         # countable ports only
            "ports_all": len(xa),
            "ports_nonop": sum(1 for p in xa if not p["op"]),
            "ports_zero": sum(1 for p in xp if p["mbps"] == 0),
            "mbps": rated_mbps,                       # operational and speed > 0
            "rated": len(rated),
            "avg_mbps": round(rated_mbps / len(rated)) if rated else 0,
            "facs": ix_facs.get(xid, []),
        })

    # ---- NIXI ------------------------------------------------------------
    # Rule 6.2: one row per ASN, displaying the most common spelling.
    isp_rows = defaultdict(list)
    isp_order = []
    for r in nixi_isps_raw:
        asn = key(r["asNumber"])
        if asn not in isp_rows:
            isp_order.append(asn)
        isp_rows[asn].append(r)

    tenant_asns = {net_by_id[i]["asn"] for i in tenant_ids if net_by_id[i]["asn"]}
    # countable ports only: a non-operational port is not evidence of anything
    port_asns = {p["asn"] for p in ports if p["asn"] and p["countable"]}

    isps = []
    for asn in isp_order:
        rows = isp_rows[asn]
        names = [clean_nixi_name(r["companyName"]) for r in rows]
        counts = Counter(names)
        top = max(counts.values())
        # most common spelling; ties go to the first one in file order
        best = next(nm for nm in names if counts[nm] == top)
        others = [nm for nm in dict.fromkeys(names) if nm != best]
        locs = list(dict.fromkeys(key(r["noc_location"]) for r in rows))
        nixi_ids = sorted({key(r["networkMasterId"]) for r in rows if key(r["networkMasterId"])})
        created = sorted(r["createdAt"].strip() for r in rows if r["createdAt"].strip())
        updated = sorted(r["updatedAt"].strip() for r in rows if r["updatedAt"].strip())
        zones = sorted({title_case(clean_nixi_name(r["zoneName"])) for r in rows if r["zoneName"].strip()})
        if asn in tenant_asns:
            group = "fac"
        elif asn in port_asns:
            group = "port"
        elif asn in all_asns:
            group = "pdb"
        else:
            group = "none"
        pdb_net = ""
        if group != "none":
            cand = net_rows_by_asn.get(asn, [])
            india_first = [c for c in cand if c in universe and c in net_by_id]
            pool = india_first or [c for c in cand if c in net_by_id]
            if pool:
                pdb_net = pool[0]
        isps.append({
            "id": asn,
            "asn": asn,
            "name": best,
            "also": others,
            "locs": locs,
            "nlocs": len(locs),
            "zones": zones,
            "group": group,
            "net": pdb_net,
            "nixi_ids": nixi_ids,
            "created": created[0] if created else "",
            "updated": updated[-1] if updated else "",
            "infra": bool(pdb_net) and net_by_id[pdb_net]["infra"],
            "sx": search_extra(best, *others),
        })

    isps_by_loc = defaultdict(list)
    for r in isps:
        for l in r["locs"]:
            isps_by_loc[l].append(r["id"])

    loc_contacts = {}
    for r in nixi_isps_raw:
        l = key(r["noc_location"])
        if l not in loc_contacts:
            loc_contacts[l] = {
                "contact": clean_nixi_name(r["contact_name"]),
                "mobile": clean_nixi_name(r["mobileNo"]),
                "email": clean_nixi_name(r["contact_email"]),
                "isp_address": clean_nixi_name(r["address"]),
                "noc_id": key(r["noc_id"]),
            }

    nixi_locs = []
    for r in nixi_locs_raw:
        raw = key(r["Location"])
        extra = loc_contacts.get(raw, {})
        nixi_locs.append({
            "id": raw,
            "name": title_case(raw),
            "name_raw": raw,
            "phone": r["Phone No"],
            "address": r["Address"],
            "contact": extra.get("contact", ""),
            "mobile": extra.get("mobile", ""),
            "email": extra.get("email", ""),
            "noc_id": extra.get("noc_id", ""),
            "isps": isps_by_loc.get(raw, []),
        })
    clash = [k for k, v in Counter(l["name"] for l in nixi_locs).items() if v > 1]
    if clash:
        print(f"STOP. Two NIXI locations display the same name after rule 6.3: {clash}. Ask Krish.")
        sys.exit(1)

    # ---- numbers ---------------------------------------------------------
    cities = sorted({f["city"] for f in facilities})
    tier_facs = {t: [f for f in facilities if f["tier"] == t] for t in (1, 2, 3)}
    total_installed = sum(f["n"] for f in facilities)
    hub_installed = sum(f["n"] for f in tier_facs[1])
    hub_share = f"{hub_installed / total_installed * 100:.1f}%"
    orgs = sorted({f["org"] for f in facilities})
    org_facs = Counter(f["org"] for f in facilities)
    group_counts = Counter(r["group"] for r in isps)

    countable = [p for p in ports if p["countable"]]
    rated = [p for p in countable if p["mbps"] > 0]
    nonop = [p for p in ports if not p["op"]]
    zero = [p for p in ports if p["mbps"] == 0]
    cap_tbps = sum(p["mbps"] for p in rated) / 1_000_000
    avg_mbps = round(sum(p["mbps"] for p in rated) / len(rated)) if rated else 0
    equinix = next((f for f in facilities if f["name"] == "Equinix MB1 - Mumbai (GPX Mumbai 1)"), None)

    # numbers straight from the CSVs, in the order Krish asked for them
    def line(label, value):
        return (label, value)

    ev_rows = [
        ("In a facility", sum(1 for n in networks if "F" in n["ev"])),
        ("On an exchange (operational port)", sum(1 for n in networks if "X" in n["ev"])),
        ("At NIXI", sum(1 for n in networks if "N" in n["ev"])),
    ]
    mix_labels = [
        ("F", "facility only"), ("X", "exchange only"), ("N", "NIXI only"),
        ("FX", "facility and exchange"), ("FN", "facility and NIXI"),
        ("XN", "exchange and NIXI"), ("FXN", "all three"),
        ("", "listed only by a port that is not operational"),
    ]

    print("COUNTS TAKEN STRAIGHT FROM THE CSVs")
    print("=" * 62)
    print("Facilities and operators")
    print(f"  facilities                                {len(facilities):>7}")
    print(f"  operators (unique org_name)               {len(orgs):>7}")
    print(f"  operators running more than one facility  {sum(1 for v in org_facs.values() if v > 1):>7}")
    print(f"  cities after the city rules               {len(cities):>7}")
    print(f"  facilities with at least one network       {sum(1 for f in facilities if f['n'] > 0):>6}")
    print(f"  networks installed (sum of linked rows)   {total_installed:>7}")
    print()
    print("Networks by evidence  (a network can rest on more than one)")
    for label, v in ev_rows:
        print(f"  {label:<41}{v:>7}")
    print("  " + "-" * 48)
    for k, label in mix_labels:
        print(f"  {label:<41}{evidence_mix.get(k, 0):>7}")
    print(f"  {'NIXI only, no PeeringDB record':<41}{sum(1 for n in networks if not n['pdb']):>7}")
    print("  " + "-" * 48)
    print(f"  {'TOTAL networks with evidence':<41}{len(networks):>7}")
    print(f"  {'of which exchange infrastructure':<41}{len(infra_nets):>7}")
    print(f"  {'of which run by an exchange operator':<41}{len(ixrun_nets):>7}")
    print()
    print("Exchanges and ports")
    print(f"  exchanges                                 {len(exchanges):>7}")
    print(f"  exchange operators (unique ix_org_id)     {len({x['org_id'] for x in exchanges}):>7}")
    print(f"  ports listed in the CSV                   {len(ports):>7}")
    print(f"    not operational (count nowhere)         {len(nonop):>7}")
    print(f"    speed 0 (real ports, no recorded speed) {len(zero):>7}")
    print(f"    both not operational and speed 0        {sum(1 for p in ports if not p['op'] and p['mbps'] == 0):>7}")
    print(f"  countable ports (operational)             {len(countable):>7}")
    print(f"  rated ports (operational and speed > 0)   {len(rated):>7}")
    print(f"  total capacity, Tbps                      {cap_tbps:>7.1f}")
    print(f"  average rated port speed, Mbps            {avg_mbps:>7}")
    print()
    print("NIXI")
    print(f"  NIXI locations                            {len(nixi_locs):>7}")
    print(f"  locations with at least one ISP row       {sum(1 for l in nixi_locs if l['isps']):>7}")
    print(f"  unique ISPs (by ASN)                      {len(isps):>7}")
    for k, name, _ in MATCH_GROUPS:
        print(f"    {name:<39}{group_counts[k]:>7}")
    print(f"  ISPs with no PeeringDB record             {sum(1 for n in networks if not n['pdb']):>7}")
    print("=" * 62)
    print()

    # ---- checks against CLAUDE.md section 13 ------------------------------
    # Krish's rules of 2026-09-25 change how some of these are counted. Those
    # entries are listed as "changed", with the old value and the reason.
    checks = [
        ("Rows in facilities.csv", len(facilities_raw), 246),
        ("Rows in facility_networks.csv", len(facnets_raw), 2521),
        ("Rows in networks.csv", len(networks_raw), 35285),
        ("Rows in exchange_facilities.csv", len(ixfac_raw), 202),
        ("Rows in exchanges.csv", len(exchanges_raw), 42),
        ("Rows in exchange_ports.csv", len(ports_raw), 2197),
        ("Rows in nixi_locations.csv", len(nixi_locs_raw), 79),
        ("Rows in nixi_isps.csv", len(nixi_isps_raw), 345),
        ("Operators (unique org_name)", len(orgs), 64),
        ("Operators running more than one facility", sum(1 for v in org_facs.values() if v > 1), 24),
        ("Cities after the city rules", len(cities), 80),
        ("Facilities with coordinates", sum(1 for f in facilities if f["lat"] is not None and f["lon"] is not None), 203),
        ("Facilities that cannot be placed on the map", sum(off_map.values()), 10),
        ("Facilities with at least one linked network", sum(1 for f in facilities if f["n"] > 0), 204),
        ("Unique networks inside facilities (tenants)", len(tenant_ids), 833),
        ("Networks installed (sum of linked counts)", total_installed, 2521),
        ("Major hub facilities", len(tier_facs[1]), 13),
        ("Mid-size facilities", len(tier_facs[2]), 34),
        ("Small facilities", len(tier_facs[3]), 199),
        ("Networks installed in major hubs", hub_installed, 1259),
        ("Major hub share of networks installed", hub_share, "49.9%"),
        ("Facilities hosting at least one exchange (linked)", sum(1 for f in facilities if f["nix"] > 0), 107),
        ("Exchange operators (unique ix_org_id)", len({x["org_id"] for x in exchanges}), 20),
        ("Exchange ports with speed 0", len(zero), 17),
        ("Exchange ports marked not operational", len(nonop), 11),
        ("NIXI locations with at least one ISP row", sum(1 for l in nixi_locs if l["isps"]), 60),
        ("Unique NIXI ISPs (by ASN)", len(isps), 273),
        ("Linked networks at Equinix MB1 - Mumbai (GPX Mumbai 1)", equinix["n"] if equinix else "facility not found", 255),
        ("Facilities run by Sify Technologies Limited", org_facs.get("Sify Technologies Limited", 0), 30),
    ]
    changed = [
        ("Networks linked to India (facility or exchange port)", len(fac_evidence | listed_evidence), 1215,
         "unchanged: a non-operational port still earns a searchable row, it just counts nowhere"),
        ("Networks seen only at exchanges", len(exchange_only_ids), 382,
         f"{len(stale_nets)} of these had only non-operational ports, which now count towards nothing"),
        ("Total port capacity, Tbps", f"{cap_tbps:.1f}", "59.4",
         "non-operational ports no longer add capacity"),
        ("NIXI ISPs: Already in facility data", group_counts["fac"], 175, "unchanged in value"),
        ("NIXI ISPs: Seen only at exchanges", group_counts["port"], 76, "countable ports only"),
        ("NIXI ISPs: In PeeringDB, not linked to India", group_counts["pdb"], 13, "countable ports only"),
        ("NIXI ISPs: Only known through NIXI", group_counts["none"], 9, "countable ports only"),
    ]

    width = max(len(c[0]) for c in checks + [(c[0],) for c in changed])
    failed = 0
    print("CLAUDE.md section 13 checks that the new rules do not touch")
    print("-" * (width + 30))
    for label, got, expected in checks:
        ok = str(got) == str(expected)
        if not ok:
            failed += 1
        print(f"{label.ljust(width)}  {str(got).rjust(7)}  expected {str(expected).rjust(7)}  {'ok' if ok else 'MISMATCH'}")
    print()
    print("Section 13 numbers the new rules change")
    print("-" * (width + 30))
    for label, got, was, why in changed:
        same = str(got) == str(was)
        print(f"{label.ljust(width)}  {str(got).rjust(7)}  was {str(was).rjust(7)}  {'(same)' if same else 'CHANGED'}  {why}")
    print("-" * (width + 30))

    expected_off_map = "Cochin (2), Mohali (2), Siliguri (1), Amritsar (1), Salem (1), Tuticorin (1), Jetpur (1), Yamuna Nagar (1)"
    got_off_map = ", ".join(f"{c} ({n})" for c, n in off_map_list)
    if got_off_map != expected_off_map:
        failed += 1
        print(f"MISMATCH on rule 6.7. Got: {got_off_map}")
    print()

    # ---- where the port rules were not holding before --------------------
    print("WHERE THE PORT RULES WERE NOT HOLDING BEFORE")
    print("-" * 62)
    only_nonop = sorted(
        {p["net_id"] for p in ports if not p["op"]} - {p["net_id"] for p in countable},
        key=lambda x: int(x) if x.isdigit() else 0)
    audit = [
        ("Exchange 'ports' column and the ports card",
         f"counted all {len(ports)} listed ports; now counts the {len(countable)} operational ones"),
        ("Exchange 'networks connected' and the bubble chart",
         f"counted networks reached only by a non-operational port; {len(only_nonop)} network(s) affected"),
        ("Network 'Indian exchange ports' column",
         "counted non-operational ports in each network's total"),
        ("Total port capacity",
         f"included non-operational ports, giving 59.4 Tbps; now {cap_tbps:.1f} Tbps"),
        ("Port speed chart",
         "already left out speed 0, but still counted non-operational ports"),
        ("'Networks linked to India'",
         f"{len(only_nonop)} network(s) have ports but every port is non-operational: "
         + "; ".join(
             f"{net_raw_by_id[i]['network_name']} (AS{net_raw_by_id[i]['asn']}), "
             + (f"kept, it has {len(net_facs[i])} facilities" if net_facs.get(i) else "dropped, it had no other evidence")
             for i in only_nonop if i in net_raw_by_id)),
        ("NIXI match groups",
         "'Seen only at exchanges' could rest on a non-operational port"),
        ("Averages",
         f"no average port speed was shown anywhere; the exchange panel now shows one, over rated ports only ({avg_mbps} Mbps overall)"),
    ]
    if stale_nets:
        audit.append(("Rows that exist but count towards nothing",
                      "; ".join(f"{n['name']} (AS{n['asn']}) keeps a searchable row with every count at zero" for n in stale_nets)))
    for where, what in audit:
        print(f"  {where}\n      {what}")
    print("-" * 62)
    print()

    # ---- what was flagged as exchange infrastructure ---------------------
    print(f"FLAGGED AS EXCHANGE INFRASTRUCTURE: {len(infra_nets)} networks")
    print("  (PeeringDB types them Route Server or Route Collector; kept in the")
    print("   data and on the page, marked, and left out of every ranking)")
    print("-" * 62)
    for n in sorted(infra_nets, key=lambda x: (-len(x["facs"]), -x["nports"], x["name"])):
        print(f"  AS{n['asn']:<9} {n['name'][:44]:<44} {n['type']:<16} facilities={len(n['facs'])} ports={n['nports']}")
    extra = [n for n in ixrun_nets if not n["infra"]]
    print()
    print(f"ALSO MARKED, run by an exchange operator but not typed as infrastructure: {len(extra)}")
    print("  (marked on the row only; still counted and still ranked)")
    print("-" * 62)
    for n in sorted(extra, key=lambda x: x["name"]):
        print(f"  AS{n['asn']:<9} {n['name'][:44]:<44} {n['type']:<22} operator={n['ixrun_label']}")
    print("-" * 62)
    print()

    if failed:
        print(f"STOP. {failed} check(s) do not match CLAUDE.md. Tell Krish before going further.")
        sys.exit(1)

    # ---- payload ---------------------------------------------------------
    geo = json.loads((ROOT / "reference" / "india_states.json").read_text(encoding="utf-8"))

    payload = {
        "meta": {
            "sheets": [
                {"name": n, "file": f, "source": s, "sheet": sh, "row": rw, "rows": rows}
                for n, f, s, sh, rw, rows in sheets
            ],
            "tiers": {str(t): dict(TIERS[t], facilities=len(tier_facs[t]),
                                   installed=sum(f["n"] for f in tier_facs[t]),
                                   share=f"{sum(f['n'] for f in tier_facs[t]) / total_installed * 100:.1f}%",
                                   with_ix=sum(1 for f in tier_facs[t] if f["nix"] > 0))
                      for t in (1, 2, 3)},
            "groups": [{"k": k, "name": n, "desc": d, "n": group_counts[k]} for k, n, d in MATCH_GROUPS],
            "headline": {
                "hubs": len(tier_facs[1]),
                "facilities": len(facilities),
                "share": hub_share,
                "installed": total_installed,
            },
            "totals": {
                "facilities": len(facilities),
                "operators": len(orgs),
                "cities": len(cities),
                "tenants": len(tenant_ids),
                "exchange_only": len(exchange_only_ids),
                "networks": len(networks),
                "ev_fac": sum(1 for n in networks if "F" in n["ev"]),
                "ev_ix": sum(1 for n in networks if "X" in n["ev"]),
                "ev_nixi": sum(1 for n in networks if "N" in n["ev"]),
                "no_pdb": sum(1 for n in networks if not n["pdb"]),
                "infra": len(infra_nets),
                "stale": len(stale_nets),
                "ixrun": len([n for n in ixrun_nets if not n["infra"]]),
                "exchanges": len(exchanges),
                "exchange_operators": len({x["org_id"] for x in exchanges}),
                "ports_listed": len(ports),
                "ports": len(countable),
                "ports_rated": len(rated),
                "capacity_tbps": f"{cap_tbps:.1f}",
                "avg_mbps": avg_mbps,
                "nixi_locs": len(nixi_locs),
                "nixi_locs_with_isps": sum(1 for l in nixi_locs if l["isps"]),
                "nixi_isps": len(isps),
                "nixi_new": len(isps) - group_counts["fac"],
                "installed": total_installed,
                "with_coords": sum(1 for f in facilities if f["lat"] is not None),
                "off_map": sum(off_map.values()),
                "ports_zero": len(zero),
                "ports_down": len(nonop),
            },
            "evidence_mix": [{"k": k, "label": lab, "n": evidence_mix.get(k, 0)} for k, lab in mix_labels],
            "off_map": [{"city": c, "n": n} for c, n in off_map_list],
            "city_replacements": [{"from": k, "to": v} for k, v in CITY_REPLACEMENTS.items()],
        },
        "facilities": facilities,
        "netfac": [[key(r["fac_id"]), key(r["net_id"])] for r in facnets_raw],
        "networks": networks,
        "exchanges": exchanges,
        "ixfac": [[key(r["ix_id"]), key(r["fac_id"])] for r in ixfac_raw],
        "ports": [[p["net_id"], p["ix_id"], p["mbps"], 1 if p["op"] else 0, p["asn"]] for p in ports],
        "nixi_locs": nixi_locs,
        "nixi_isps": isps,
        "cities": city_points,
        "geo": geo,
    }

    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")

    template = (BUILD / "template.html").read_text(encoding="utf-8")
    if "/*__DATA__*/" not in template:
        print("STOP. build/template.html has no /*__DATA__*/ placeholder.")
        sys.exit(1)
    out = template.replace("/*__DATA__*/", blob)
    DIST.mkdir(exist_ok=True)
    target = DIST / "index.html"
    target.write_text(out, encoding="utf-8")
    print(f"Wrote {target.relative_to(ROOT)}  ({len(out) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
