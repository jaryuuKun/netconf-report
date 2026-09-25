# CLAUDE.md: India data centre GTM report

Read this whole file before doing anything. It is the single source of instructions for this repo.

## 1. What you are building

An internal go-to-market report for Connectify. The company is preparing to sell network configuration (NETCONF) tooling to data centres in India. NETCONF is a standard protocol for configuring routers and switches automatically instead of by hand, so the buyers are organisations that run a lot of network equipment.

The output is **one self-contained HTML file** (`dist/india-dc-report.html`) that opens by double-clicking, with no server. It shows every record in `data/` and has filters, charts, a map, search, and a detail panel for every record, including contact details.

The audience is Krish (GTM, Connectify) and his manager. The file contains personal phone numbers and email addresses, so it is internal only. Never add hosting, analytics, sharing links or any code that sends data anywhere.

## 2. Ground rules

1. Every number, label and list shown on the page is computed from the CSVs in `data/` by the build script. Never type a data value into the HTML or the template.
2. Do not invent anything: no extra data, categories, benchmarks, market sizes, estimates, scores, rankings, or rules beyond those written in this file.
3. Do not write conclusions, recommendations or sales advice. The only text allowed is: the page copy given in section 8, explanations of what a chart shows, and the definitions in section 7. The single exception is the Overview headline, which states a computed fact (section 8).
4. Never edit files in `data/`. All tidying happens in the build script, using only the rules in section 6, and the original value always stays visible in the record's detail panel.
5. `reference/prototype.html` is a design and behaviour reference only. Do not read data out of it: its embedded data is an older copy and uses some rules that this file changes (section 10). Where this file and the prototype disagree, this file wins.
6. If anything is unclear, a verification number does not match, or a rule does not cover a case you find, stop and ask Krish. Do not guess.
7. Write in plain English. Explain every technical term (exchange, ASN, NOC, port, peering and so on) the first time it appears on a page, in the page text or an info tooltip.
8. No emojis anywhere.

## 3. Repo layout

```
CLAUDE.md                     this file
data/                         source data, one CSV per workbook sheet (read-only)
reference/prototype.html      approved look and behaviour (reference only)
reference/india_states.json   India state outlines, already projected to SVG paths
build/                        you create: build script and HTML template
dist/india-dc-report.html     you create: the final report
```

## 4. The data files

Read every CSV with every column as text, and empty cells as empty strings, never NaN (pandas: `dtype=str, keep_default_na=False`). Trim whitespace on every join key before joining. IDs must never be converted to numbers.

| File | Original workbook sheet | Source | One row is |
|---|---|---|---|
| `facilities.csv` | Datacentres - PeeringDB ( india | PeeringDB `fac` | one data centre building in India |
| `facility_networks.csv` | occupiers NET_ID - peeringdb( i | PeeringDB `netfac` | one network installed in one facility |
| `networks.csv` | Occupiers name - peeringdb( ind | PeeringDB `net` | one network, worldwide (see note) |
| `exchange_facilities.csv` | peeringdb_ixfac | PeeringDB `ixfac` | one exchange present in one facility |
| `exchanges.csv` | peeringdb_ix | PeeringDB `ix` | one internet exchange in India |
| `exchange_ports.csv` | peeringdb_netixlan_india | PeeringDB `netixlan` | one port a network has on an Indian exchange |
| `nixi_locations.csv` | nixi_noc_locations | NIXI website | one NIXI location (NOC), with phone and address |
| `nixi_isps.csv` | nixi_noc_complete | NIXI website | one ISP connected at one NIXI location |

**Column notes**

- `facilities.csv`: `fac_id` is the key. Contacts are `sales_email`, `sales_phone`, `tech_email`, `tech_phone`, `fac_website`. `fac_net_count`, `fac_ix_count` and `fac_carrier_count` are PeeringDB's own summary counts (see rule 6.4). `state` is inconsistent (for example MH, Maharashtra, Maharastra); show it in the detail panel only and never use it for filters or charts.
- `facility_networks.csv`: keys `fac_id` and `net_id`. Its `name`, `city` and `country` columns repeat facility details; always take facility details from `facilities.csv`.
- `networks.csv`: key `net_id`. This is the full PeeringDB network table (worldwide). The report shows only networks linked to India, meaning any `net_id` found in `facility_networks.csv` or `exchange_ports.csv`. The full table is used for one thing only: checking whether a NIXI ISP's ASN exists anywhere on PeeringDB (section 7). `net_fac_count` and `net_ix_count` are worldwide counts; label them "worldwide".
- `exchange_facilities.csv`: keys `ix_id` and `fac_id`. Its `name` and `city` repeat facility details.
- `exchanges.csv`: key `ix_id`. `ix_org_id` identifies the company running the exchange. Contacts are the `ix_tech_*`, `ix_policy_*` and `ix_sales_*` columns.
- `exchange_ports.csv`: keys `net_id` and `ix_id`. `port_speed_mbps` is the port speed in megabits per second. A network can have several ports on the same exchange, so count unique `net_id` when counting networks. `Column 1` and `Column 2` are empty; ignore them.
- `nixi_isps.csv`: `noc_location` matches `Location` in `nixi_locations.csv` exactly. `asNumber` is the ISP's ASN. The location contact columns (`contact_name`, `mobileNo`, `contact_email`, `address`) repeat on every ISP row for that location. `noc_id` and `noc_location` match one to one, but `nixi_locations.csv` has no `noc_id`, so join the two NIXI files on the location name.
- `nixi_locations.csv`: `Location`, `Phone No`, `Address`. 19 locations have no rows in `nixi_isps.csv`; show them with zero ISPs and their phone and address.

## 5. How the files connect

```
facilities.fac_id  --<  facility_networks.fac_id    facility_networks.net_id  >--  networks.net_id
facilities.fac_id  --<  exchange_facilities.fac_id  exchange_facilities.ix_id >--  exchanges.ix_id
networks.net_id    --<  exchange_ports.net_id       exchange_ports.ix_id      >--  exchanges.ix_id
nixi_isps.asNumber  ==  networks.asn  (and exchange_ports.asn)
nixi_isps.noc_location  ==  nixi_locations.Location
facilities.org_name  groups facilities into operators
```

Every join key in the data has been checked: no orphan IDs exist in any link file.

## 6. Tidying rules (the only ones allowed)

1. **City names** (facilities and exchanges). Replace exactly these values, then strip leading and trailing spaces and commas, then convert values written entirely in capitals to title case (AMRITSAR to Amritsar):
   `Mumbai,` to Mumbai; `Navi Mumbai,` to Navi Mumbai; `Panvel, Raigad,` to Panvel; `Egmore ,Chennai` to Chennai; `Serilingampally,Hyderabad` to Hyderabad; `Gurgaon` to Gurugram; `Vijaywada` to Vijayawada; `Vishakhapatam` and `Viskhapatnam` to Visakhapatnam; `YamunaNagar` to Yamuna Nagar; `Bengaluru` to Bangalore.
   Do not merge any other names. Delhi and New Delhi stay separate unless section 11 says otherwise.
2. **NIXI ISP names.** Trim spaces and line breaks. When one ASN appears with several names, display the name that occurs most often (ties: the first one in file order) and list the other spellings under "Also listed as" in the detail panel.
3. **NIXI location and zone names.** Display values written entirely in capitals in title case (DELHI to Delhi); `zoneName` has one location written in two cases (Chennai-STT and CHENNAI-STT), which this rule merges. Do not correct spellings.
4. **Counts come from linked rows.** Wherever the page shows how many networks are in a facility, how many exchanges a facility hosts, or how many networks are on an exchange, count the linked rows (`facility_networks`, `exchange_facilities`, unique `net_id` in `exchange_ports`). This makes every number open to exactly that many records. Show PeeringDB's own summary count in the detail panel as "PeeringDB count" when it differs.
5. **Port speed 0.** 17 ports have speed 0. Count them as ports; leave them out of speed charts and capacity totals.
6. **Ports not operational.** 11 ports have `operational` = False. Count them like any other port and show the status in the detail panels.
7. **Map positions.** A city's bubble sits at the average latitude and longitude of that city's facilities that have coordinates. Facilities in a city with no coordinates at all stay in every chart, table and count, and are listed under the map as "Not on the map: Cochin (2), Mohali (2), Siliguri (1), Amritsar (1), Salem (1), Tuticorin (1), Jetpur (1), Yamuna Nagar (1)".
8. **Contact details** are shown exactly as in the data. Do not correct email addresses or phone numbers.

## 7. Definitions

- **Facility size**, from linked network count: Major hub is 50 or more; Mid-size is 10 to 49; Small is fewer than 10. Always show the rule next to the name.
- **Networks installed**: the sum of linked network counts across facilities. A network in three facilities counts three times. Say this in an info tooltip wherever the figure appears.
- **Operator**: all facilities sharing an `org_name`.
- **Exchange operator**: all exchanges sharing an `ix_org_id`. The data has no operator name column, so label each group with the first word of its exchanges' `ix_name` (for example NIXI, DE-CIX, Extreme). This labelling has been checked: first word and `ix_org_id` match one to one across all 20 operators.
- **Tenant network**: a network with at least one row in `facility_networks.csv`.
- **Network seen only at exchanges**: a network with rows in `exchange_ports.csv` but none in `facility_networks.csv`.
- **NIXI match groups.** Test each unique NIXI ASN in this order and assign the first group that fits:
  1. Already in facility data: the ASN belongs to a tenant network.
  2. Seen only at exchanges: the ASN appears in `exchange_ports.asn`.
  3. In PeeringDB, not linked to India: the ASN appears anywhere in `networks.asn`.
  4. Only known through NIXI: none of the above.

## 8. Pages

Follow the prototype's layout and behaviour: sticky header with the title and a global search, tabs below it, and on every page a filter panel, then summary cards, then charts, then the full table. The sections below give what each page must contain.

**Behaviour on every page**

- Filter panel: multi-select dropdowns with a search box, "Select all" and "Select none"; chips; on/off toggles; "Reset filters". Filters are per page.
- Charts, summary cards, map and table all use the same filter state. Clicking a bar, bubble or chart group sets that filter; clicking it again clears it. Table header filter buttons open the same multi-select as the panel.
- Every chart that lists items has its own Top N control: Top 10, 15, 25, 50, Show all.
- Every table has: a search box; a Top N control (Top 10, 25, 50, 100, All rows) labelled "by current sort"; sortable columns; horizontal scrolling; a count ("Showing X of Y"); and a row click that opens the detail panel. All rows are available when set to All rows.
- Empty results show a sentence saying nothing matches and how to widen the filters.
- Global search covers facilities, operators, networks linked to India, exchanges, NIXI locations and NIXI ISPs. It matches names, cities, ASNs (with or without "AS"), and NIXI contact names, with results grouped by type.
- Detail panel: opens on the right. Contacts first, then every non-empty column for the record in plain-English labels, then linked records as clickable lists. Emails open the mail app, websites open in a new tab.

**Overview**
- Headline, computed: "{major hub count} of India's {facility count} data centre facilities hold {share} of all installed networks."
- One-paragraph plain-English explanation of a facility and why network count matters (use the prototype's paragraph).
- Full-width bar split by facility size (share of networks installed), and three cards, one per size, each showing: the rule, facilities, networks installed, share, and facilities hosting an exchange.
- "How the data fits together": four cards (Facilities, Tenant networks, Internet exchanges, NIXI locations) with counts and a one-line description, each opening its tab.
- "Where the facilities are": map with city bubbles, with a "Facilities by city" bar chart beside it, split by facility size. Filter: facility size chips. Clicking a city opens the Facilities tab filtered to that city.
- "Largest operators": bars of networks installed per operator, split by facility size, with Top N. Click opens the operator panel.

**Facilities**
- Filters: city, operator, facility size, "Hosts an internet exchange", "Has contact details".
- Cards: facilities, operators, networks installed, hosting an exchange, with contact details.
- Map and "Facilities by city" bars side by side.
- Table: facility, operator, city, networks inside, exchanges, carriers, size, sales email, tech email, phone.
- Panel: contacts, all details, operator, exchanges hosted here, networks inside.

**Operators**
- Filters: city (counts only the operator's facilities in those cities), operator, facility size, "Runs more than one facility".
- Cards: operators, running more than one facility, running at least one major hub, networks installed.
- Bubble chart: across is facilities run, up is networks installed, bubble size is cities, colour is the largest facility size the operator runs. Label the top points with full names, and avoid overlapping labels.
- Bars: networks installed per operator, split by facility size, with Top N.
- Table: operator, facilities, networks installed, in major hubs, cities, facilities with an exchange, facilities with contacts.
- Panel: summary, a button "Show these facilities" that opens the Facilities tab filtered to this operator, and the facility list.

**Tenant networks**
- Filters: network type (`info_type`, empty shown as "Not stated"), installed in city, scope, peering policy, "Also connects at an Indian exchange", and "Include networks seen only at exchanges" (off by default; when on, those networks join the table, cards and type chart, but not the map or facility charts because they have no facility).
- Cards: networks, installed in 5 or more facilities, also connect at an exchange, facilities hosting them.
- Charts: "What kind of networks are they?" (type bars, click to filter), and "Which networks are in the most facilities?" (Top N, with an info tooltip explaining that more facilities means more locations with equipment to configure).
- "Where these networks are installed": map and "Facilities hosting them" bars. Table rows have tick boxes; with rows ticked, the map and bars show only the ticked networks. Provide "Clear ticks".
- Table: network, ASN, type, scope, Indian facilities, Indian exchange ports, peering policy, traffic.
- Panel: all details, Indian facilities, Indian exchange ports with speed and status.

**Internet exchanges**
- Filters: city, exchange operator, "Has ports listed".
- Cards: exchanges, networks connected (unique), ports, total capacity in Tbps.
- Charts: bubble chart of networks connected (across) against total port capacity in Gbps (up), coloured by exchange operator; port speed bars; exchanges by city (click to filter).
- Table: exchange, operator, city, networks connected, facilities, ports, capacity (Gbps), tech email.
- Panel: contacts, details (including the PeeringDB member count), facilities hosting it, networks with ports here.

**NIXI**
- Plain-English introduction: what NIXI is, what a NOC is, and why it matters here (one organisation with many sites; its ISP lists include regional ISPs not in the facility data).
- Filters: match group, NIXI location, "Connected at more than one location".
- Cards: NIXI locations, locations with an ISP list, unique ISPs, ISPs not in the facility data.
- "How many of NIXI's ISPs are new to us?": a bar split into the four match groups, plus four cards explaining each group. Clicking a group filters.
- "Which NIXI locations have the most ISPs?" and "Which ISPs connect at several locations?" bars, with Top N.
- Tables: ISPs (name, ASN, match group, number of locations, locations) and NIXI locations (location, contact, mobile, email, phone, address, ISPs listed).
- ISP panel: match group, ASN, locations, other name spellings, and a link to the PeeringDB network record when one exists. Location panel: contacts and the ISP list.

**Sources and method**
- Table of the eight datasets: plain name, source, workbook sheet name, row count (computed).
- Table of shared IDs and what they connect (section 5, in plain English).
- Definitions (section 7) and tidying rules (section 6) in plain English.
- A note that map boundaries are simplified public data for visual reference, not survey-grade.

## 9. Design

Match the prototype's look. Tokens:

- Background white `#FFFFFF`; tinted panels `#F4F6FB`; lines `#E2E6EF`; text `#131A35`; secondary text `#5B6480`; faint text `#8C93AA`.
- One colour per dataset, used on its tab underline, cards and charts: facilities `#2F4BDB`, networks `#0C9A8C`, exchanges `#7050D6`, NIXI `#B3307C`.
- Facility sizes: Major hub `#E4502F`, Mid-size `#F1A532`, Small `#AAB6CB`.
- Fonts: Bricolage Grotesque for headings and large numbers, IBM Plex Sans for everything else, loaded from Google Fonts with system fallbacks, so the file still works offline.
- Rounded cards (radius about 14px), info icons with tooltips, and sentence-case labels.
- Responsive down to phone width; visible keyboard focus.
- Charts are hand-built SVG or HTML. Use no chart libraries and no scripts from external hosts, so the file works offline.
- The map uses `reference/india_states.json` (state outlines already projected to SVG paths). To place a point: x = (longitude − minx) × k × s, y = (maxy − latitude) × s, using the values stored in the file.

## 10. Known problems in the prototype (fix these)

1. Network counts per facility used PeeringDB's summary count, so a facility showed 86 networks but listed 85. Use linked rows (rule 6.4).
2. Networks seen only at exchanges (382) could not be listed anywhere except through search. Add the toggle on the Tenant networks page.
3. Exchange cities showed Bangalore and Bengaluru separately. Apply rule 6.1 to exchanges too.
4. Map labels overlapped (Mumbai was hidden under Navi Mumbai, and Bangalore under Chennai). Place labels so they do not collide, and leave a small city unlabelled rather than overlap.
5. Facilities without coordinates in their city silently disappeared from the map. List them under the map (rule 6.7).
6. Scatter labels crowded together at the bottom left, and operator names were cut short by a pattern. Use full names and avoid collisions.
7. NIXI ISP names with trailing line breaks and several spellings per ASN. Apply rule 6.2.
8. Table Top N did not say it follows the current sort.

## 11. Decisions confirmed by Krish

Krish edits this section. If it is empty, use the defaults stated in the rules above.

**2026-09-25. Networks are listed on evidence, not from the occupiers table alone.**
Every network the data shows has equipment or membership in India gets a row, whether
the evidence is a facility row, an operational exchange port or a NIXI listing. Counts
are real, including zeros, and every row shows which kinds of evidence it rests on. A
network listed only by a port that is not operational keeps a searchable row with every
count at zero, so nothing in the data becomes unfindable. This widens the tab beyond
facility tenants, so it is named "Networks".

**2026-09-25. A port marked not operational counts nowhere. This replaces rule 6.6.**
Such a port is left out of every count, total, average and chart, including port counts,
networks-connected counts, capacity and the match groups. The detail panels still show
it, labelled as not counted, so nothing is hidden. Rule 6.5 stands and is extended: a
port with speed 0 has no recorded speed, so it is a real port and is counted as one, but
it adds nothing to any capacity total or any average.

**2026-09-25. Exchange infrastructure is marked and never ranked.** A network PeeringDB
types as Route Server or Route Collector is an exchange's own equipment rather than an
independent organisation. It keeps its row and its counts, is marked on every row, and
is left out of every ranking and largest list. Separately, a network whose `org_id` is
also an exchange's `ix_org_id` is marked as run by that exchange operator; those are
ordinary networks and are still ranked.

**2026-09-25. Where two tabs report different network totals, the page shows the
breakdown that reconciles them**, so the difference reads as a definition rather than a
contradiction.

**2026-09-25. Search matches any name a record goes by.** Name, also-known-as, long
name and ASN with or without "AS" in front, plus acronyms and punctuation-free forms,
so "AWS" finds Amazon.com and "decix" finds DE-CIX.

These decisions change the following section 13 numbers. The build prints both values.

| Check | Section 13 | Under these decisions | Why |
|---|---|---|---|
| Networks linked to India | 1215 | 1215 | unchanged; a non-operational port still earns a row |
| Networks seen only at exchanges | 382 | 380 | two rested only on a non-operational port |
| Total port capacity, Tbps | 59.4 | 59.3 | non-operational ports no longer add capacity |
| Rows on the Networks tab | not stated | 1237 | 1215, plus 22 whose only evidence is NIXI |

## 12. How to work

1. **Data layer first.** Write `build/build.py`. It reads the CSVs, applies section 6, builds all joins and derived fields, and prints every number in section 13 in the same order and wording. Run it and show Krish the output. Do not start on the page until every number matches.
2. **Then the template.** Write `build/template.html`. The build script injects the prepared data as JSON and writes `dist/india-dc-report.html`. Build the pages in tab order, and render and check each page before moving on.
3. **Checks before finishing.** Open the file in a headless browser. There must be no console errors, and every tab must render with and without filters. Select none on a filter to confirm the empty state appears, and open a detail panel of each type. Confirm the section 13 numbers appear on the page where they are shown.
4. **Data integrity.** At the start of every session and again before you finish, compute the SHA-256 hash of every file in `data/` and compare it with section 14. If any hash differs, stop and tell Krish; do not continue and do not try to repair the file.
5. Keep the build rerunnable: running `python build/build.py` from the repo root must regenerate the report from `data/` with no manual steps.

## 13. Verification numbers

Computed from `data/` with the rules above. The build script must reproduce these exactly.

| Check | Expected |
|---|---|
| Rows in facilities.csv | 246 |
| Rows in facility_networks.csv | 2521 |
| Rows in networks.csv | 35285 |
| Rows in exchange_facilities.csv | 202 |
| Rows in exchanges.csv | 42 |
| Rows in exchange_ports.csv | 2197 |
| Rows in nixi_locations.csv | 79 |
| Rows in nixi_isps.csv | 345 |
| Operators (unique org_name) | 64 |
| Operators running more than one facility | 24 |
| Cities after the city rules | 80 |
| Facilities with coordinates | 203 |
| Facilities that cannot be placed on the map | 10 |
| Facilities with at least one linked network | 204 |
| Unique networks inside facilities (tenants) | 833 |
| Networks installed (sum of linked counts) | 2521 |
| Major hub facilities | 13 |
| Mid-size facilities | 34 |
| Small facilities | 199 |
| Networks installed in major hubs | 1259 |
| Major hub share of networks installed | 49.9% |
| Facilities hosting at least one exchange (linked) | 107 |
| Exchange operators (unique ix_org_id) | 20 |
| Networks linked to India (facility or exchange port) | 1215 |
| Networks seen only at exchanges | 382 |
| Exchange ports with speed 0 | 17 |
| Exchange ports marked not operational | 11 |
| Total port capacity, Tbps (speed > 0) | 59.4 |
| NIXI locations with at least one ISP row | 60 |
| Unique NIXI ISPs (by ASN) | 273 |
| NIXI ISPs: Already in facility data | 175 |
| NIXI ISPs: Seen only at exchanges | 76 |
| NIXI ISPs: In PeeringDB, not linked to India | 13 |
| NIXI ISPs: Only known through NIXI | 9 |
| Linked networks at Equinix MB1 - Mumbai (GPX Mumbai 1) | 255 |
| Facilities run by Sify Technologies Limited | 30 |


## 14. Data file fingerprints

SHA-256 hashes of the files in `data/` as delivered. If a file changes in any way, even a single character, its hash changes. Check with `sha256sum data/*.csv` (Mac/Linux) or `Get-FileHash data\*.csv` (Windows PowerShell).

| File | SHA-256 |
|---|---|
| `exchange_facilities.csv` | `4fc4024ca6266294f8453a03a0f513749fe003c0846d068334fb397edcf78d52` |
| `exchange_ports.csv` | `da75c1745e0d92d1ef037231f8a27c2d6e4f0ee4f142fbbca53b2a2755d6d55e` |
| `exchanges.csv` | `289f6ae4153e247c3123677247839dc40233395bc09af6ee147b044ae382dc94` |
| `facilities.csv` | `ee4a85418f104ff654c49f117c1f07ed24a618bc59e4d031a1e7c4b883224540` |
| `facility_networks.csv` | `ac174877704f7437453e3ebec1f8c4beb1adad09e6176d7188785ede4cd80922` |
| `networks.csv` | `0eb05b06a5ed829576f66174400f8f61cebdb04ca38971a466e3ba0944c3239a` |
| `nixi_isps.csv` | `529e28ea7e2c0e8e9c75262f2306cd4fe7ec15cf5f02608333656b8646f25bf7` |
| `nixi_locations.csv` | `6cb493d6a4605c5221c85138be3caeafea89d27bc32321ff06d38a4c27d221a2` |
