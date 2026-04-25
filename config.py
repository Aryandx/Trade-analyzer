import os

INVESTMENT_AMOUNT = 5000          # INR
ANALYSIS_LOOKBACK = "3y"          # 3 years of history for robust analysis
STOP_LOSS_PCT = 0.07              # legacy fallback — stock_scorer uses ATR-based stops
REWARD_RISK_RATIO = 3             # 3:1 reward:risk
MAX_PRICE = 4800                  # Filter: must be able to buy at least 1 share
MIN_PRICE = 50                    # Filter: avoid penny stocks
MIN_HISTORY_DAYS = 200            # Need enough data for indicators

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
REPORT_JSON = os.path.join(RESULTS_DIR, "latest_analysis.json")
REPORT_HTML = os.path.join(RESULTS_DIR, "market_report.html")
DATA_CACHE_DIR = os.path.join(RESULTS_DIR, "cache")

# Nifty 100 + quality midcap universe — large/liquid = hard to manipulate
STOCK_UNIVERSE = [
    # ── Large-cap / Nifty 50 core ───────────────────────────────────────────
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "HINDUNILVR.NS",
    "ICICIBANK.NS", "KOTAKBANK.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS",
    "SBIN.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "AXISBANK.NS", "MARUTI.NS",
    "WIPRO.NS", "NESTLEIND.NS", "TITAN.NS", "HCLTECH.NS", "SUNPHARMA.NS",
    "ONGC.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "NTPC.NS", "BAJAJFINSV.NS",
    "M&M.NS", "TATAMOTORS.NS", "INDUSINDBK.NS", "JSWSTEEL.NS",
    "TATASTEEL.NS", "COALINDIA.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS",
    "CIPLA.NS", "BPCL.NS", "BRITANNIA.NS", "DRREDDY.NS", "DIVISLAB.NS",
    "EICHERMOT.NS", "APOLLOHOSP.NS", "TECHM.NS", "HINDALCO.NS", "TATACONSUM.NS",
    "SBILIFE.NS", "ADANIPORTS.NS", "HDFCLIFE.NS", "PIDILITIND.NS", "DABUR.NS",

    # ── Financials / Banks / NBFC ────────────────────────────────────────────
    "HAVELLS.NS", "MUTHOOTFIN.NS", "CHOLAFIN.NS",
    "BANKBARODA.NS", "IDFCFIRSTB.NS", "FEDERALBNK.NS",
    "AUBANK.NS", "BANDHANBNK.NS",
    "HDFCAMC.NS", "ICICIGI.NS", "ICICIPRULI.NS",

    # ── IT / Technology ──────────────────────────────────────────────────────
    "PERSISTENT.NS", "MPHASIS.NS", "LTIM.NS", "LTTS.NS", "OFSS.NS",
    "COFORGE.NS", "KPITTECH.NS", "MASTEK.NS",

    # ── Pharma / Healthcare ──────────────────────────────────────────────────
    "TORNTPHARM.NS", "LUPIN.NS", "ZYDUSLIFE.NS", "MANKIND.NS",
    "LAURUSLABS.NS", "GLENMARK.NS", "ALKEM.NS", "BIOCON.NS", "AUROPHARMA.NS",
    "APLLTD.NS", "SYNGENE.NS", "IPCA.NS", "GRANULES.NS",

    # ── Consumer / FMCG ─────────────────────────────────────────────────────
    "TRENT.NS", "JUBLFOOD.NS", "DMART.NS", "GODREJCP.NS",
    "MARICO.NS", "COLPAL.NS", "EMAMILTD.NS", "RADICO.NS",

    # ── Auto / Auto ancillaries ──────────────────────────────────────────────
    "TVSMOTOR.NS", "MOTHERSON.NS", "BOSCHLTD.NS",
    "ASHOKLEY.NS", "MRF.NS", "BALKRISIND.NS",
    "BHARATFORG.NS", "TIINDIA.NS",

    # ── Metals / Mining ──────────────────────────────────────────────────────
    "NMDC.NS", "SAIL.NS", "VEDL.NS", "NATIONALUM.NS", "HINDALCO.NS",

    # ── Energy / Oil & Gas ───────────────────────────────────────────────────
    "IOC.NS", "GAIL.NS", "PETRONET.NS", "TATAPOWER.NS", "TORNTPOWER.NS",
    "HINDPETRO.NS", "MGL.NS",

    # ── Infrastructure / Capital Goods ───────────────────────────────────────
    "SIEMENS.NS", "ABB.NS", "BHEL.NS", "CONCOR.NS", "CUMMINSIND.NS",
    "POLYCAB.NS", "AIAENG.NS", "THERMAX.NS", "KEI.NS",

    # ── Defense / PSU ────────────────────────────────────────────────────────
    "BEL.NS", "HAL.NS", "IRCTC.NS",
    "NHPC.NS", "SJVN.NS", "RVNL.NS", "IRFC.NS",
    "MAZAGON.NS", "COCHINSHIP.NS", "GRSE.NS",

    # ── Chemicals / Specialty ────────────────────────────────────────────────
    "DEEPAKNTR.NS", "PIIND.NS", "TATACHEM.NS", "FINEORG.NS",

    # ── Cement / Building materials ──────────────────────────────────────────
    "SHREECEM.NS", "KAJARIACER.NS", "ASTRAL.NS", "SUPREMEIND.NS",

    # ── Realty ───────────────────────────────────────────────────────────────
    "GODREJPROP.NS", "PRESTIGE.NS", "OBEROIRLTY.NS", "DLF.NS", "SOBHA.NS",

    # ── Consumer Durables / Electronics ─────────────────────────────────────
    "DIXON.NS", "VOLTAS.NS",
    "SCHAEFFLER.NS", "SKFINDIA.NS",

    # ── Paints ───────────────────────────────────────────────────────────────
    "BERGEPAINT.NS", "KANSAINER.NS",

    # ── Hospitality / Aviation / Logistics ───────────────────────────────────
    "INDHOTEL.NS", "INTERGLOBE.NS", "BLUEDART.NS",

    # ── Telecom / Media ──────────────────────────────────────────────────────
    "PVRINOX.NS",
]

# News is now fetched via yfinance per-stock (see news_fetcher.py).
# EVENT_RSS_FEEDS kept as empty dict for backward compatibility with event_analyzer imports.
EVENT_RSS_FEEDS: dict = {}

# Sector → stock mapping for event analysis
SECTOR_STOCKS = {
    "Energy_Upstream":      ["ONGC.NS", "COALINDIA.NS", "NMDC.NS", "VEDL.NS"],
    "Energy_Downstream":    ["BPCL.NS", "IOC.NS", "HINDPETRO.NS", "GAIL.NS", "PETRONET.NS", "MGL.NS", "RELIANCE.NS"],
    "Energy_Renewables":    ["TATAPOWER.NS", "NTPC.NS", "TORNTPOWER.NS", "POWERGRID.NS"],
    "Chemicals":            ["DEEPAKNTR.NS", "PIIND.NS"],
    "Paints":               ["ASIANPAINT.NS", "BERGEPAINT.NS", "PIDILITIND.NS"],
    "Metals":               ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "SAIL.NS", "NATIONALUM.NS"],
    "Ports_Logistics":      ["ADANIPORTS.NS", "CONCOR.NS"],
    "Defense":              ["HAL.NS", "BEL.NS", "BHEL.NS", "MAZAGON.NS", "COCHINSHIP.NS", "GRSE.NS"],
    "Infrastructure":       ["LT.NS", "SIEMENS.NS", "ABB.NS", "CUMMINSIND.NS", "BHEL.NS",
                             "POLYCAB.NS", "AIAENG.NS", "THERMAX.NS", "KEI.NS",
                             "RVNL.NS", "IRFC.NS", "NHPC.NS", "SJVN.NS"],
    "IT":                   ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS",
                             "PERSISTENT.NS", "MPHASIS.NS", "LTIM.NS", "LTTS.NS", "OFSS.NS",
                             "COFORGE.NS", "KPITTECH.NS", "MASTEK.NS"],
    "Banks":                ["HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "SBIN.NS",
                             "AXISBANK.NS", "BANKBARODA.NS", "IDFCFIRSTB.NS", "FEDERALBNK.NS",
                             "INDUSINDBK.NS", "AUBANK.NS", "BANDHANBNK.NS"],
    "NBFC":                 ["BAJFINANCE.NS", "BAJAJFINSV.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS"],
    "Insurance":            ["SBILIFE.NS", "HDFCLIFE.NS", "ICICIGI.NS", "ICICIPRULI.NS", "HDFCAMC.NS"],
    "Pharma":               ["SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS",
                             "TORNTPHARM.NS", "LUPIN.NS", "ZYDUSLIFE.NS", "MANKIND.NS",
                             "LAURUSLABS.NS", "GLENMARK.NS", "ALKEM.NS", "BIOCON.NS",
                             "AUROPHARMA.NS", "APLLTD.NS", "SYNGENE.NS", "IPCA.NS", "GRANULES.NS"],
    "FMCG":                 ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS",
                             "DABUR.NS", "TATACONSUM.NS", "GODREJCP.NS",
                             "MARICO.NS", "COLPAL.NS", "EMAMILTD.NS", "RADICO.NS"],
    "Auto":                 ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "HEROMOTOCO.NS",
                             "BAJAJ-AUTO.NS", "EICHERMOT.NS", "TVSMOTOR.NS", "MOTHERSON.NS",
                             "BOSCHLTD.NS", "ASHOKLEY.NS", "MRF.NS", "BALKRISIND.NS",
                             "BHARATFORG.NS", "TIINDIA.NS"],
    "Cement":               ["ULTRACEMCO.NS", "SHREECEM.NS"],
    "Realty":               ["GODREJPROP.NS", "PRESTIGE.NS", "OBEROIRLTY.NS", "DLF.NS", "SOBHA.NS"],
    "Consumer_Durables":    ["TITAN.NS", "HAVELLS.NS", "VOLTAS.NS", "DIXON.NS", "POLYCAB.NS"],
    "Telecom":              ["BHARTIARTL.NS"],
    "Travel_Tourism":       ["IRCTC.NS", "INDHOTEL.NS", "INTERGLOBE.NS"],
    "Agriculture":          ["ITC.NS", "DABUR.NS", "TATACONSUM.NS"],
    "Manufacturing_PLI":    ["DIXON.NS", "POLYCAB.NS", "HAVELLS.NS", "SIEMENS.NS", "ABB.NS"],
}

# Event keyword rules: (keyword_to_match, sector, impact_direction, reason)
# impact_direction: +1 = positive, -1 = negative
EVENT_SECTOR_IMPACTS = {
    # Strait of Hormuz open → oil supply normalizes → crude prices fall
    "strait_hormuz": [
        ("strait",          "Energy_Upstream",   -1, "Crude price fall hurts upstream E&P margins"),
        ("hormuz",          "Energy_Upstream",   -1, "Crude oversupply risks for oil producers"),
        ("iran",            "Energy_Upstream",   -1, "Iran oil return depresses global crude"),
        ("ceasefire",       "Energy_Upstream",   -1, "Geopolitical risk premium removed from oil"),
        ("hormuz",          "Energy_Downstream", +1, "Cheaper crude = lower refining input cost"),
        ("oil supply",      "Energy_Downstream", +1, "Excess supply lowers OMC procurement cost"),
        ("crude",           "Energy_Downstream", +1, "Lower crude benefits refiners"),
        ("crude",           "Paints",            +1, "Crude-derived TiO2 and resin costs drop"),
        ("crude",           "Chemicals",         +1, "Petrochemical feedstock cheaper"),
        ("oil",             "Auto",              +1, "Lower fuel prices boost vehicle demand"),
        ("oil",             "FMCG",              +1, "Lower logistics & packaging input costs"),
        ("shipping",        "Ports_Logistics",   +1, "Open strait boosts shipping throughput"),
        ("trade route",     "Ports_Logistics",   +1, "Resumption of Red Sea-adjacent trade"),
        ("ceasefire",       "Defense",           -1, "Reduced conflict lowers defense urgency"),
        ("peace",           "Defense",           -1, "Geopolitical de-escalation reduces defense orders"),
        ("iran",            "Energy_Downstream", +1, "Iranian oil adds supply, benefits importers"),
        ("oil prices fall", "FMCG",              +1, "Lower logistics cost supports FMCG margins"),
        ("oil prices fall", "Pharma",            +1, "Lower solvent and packaging costs"),
    ],
    # PM speech — infrastructure focus
    "pm_speech_infra": [
        ("infrastructure",  "Infrastructure",    +1, "Infrastructure push benefits capex stocks"),
        ("capex",           "Infrastructure",    +1, "Government capex announcement"),
        ("railways",        "Travel_Tourism",    +1, "Railway expansion benefits IRCTC"),
        ("railways",        "Infrastructure",    +1, "Rail infra investment"),
        ("highways",        "Infrastructure",    +1, "Highway projects boost construction"),
        ("metro",           "Infrastructure",    +1, "Urban transit investment"),
        ("ports",           "Ports_Logistics",   +1, "Port development investment"),
        ("power",           "Energy_Renewables", +1, "Power sector investment"),
    ],
    # PM speech — defense and manufacturing
    "pm_speech_defense": [
        ("defence",         "Defense",           +1, "Defense indigenization push"),
        ("defense",         "Defense",           +1, "Defense spending increase"),
        ("atmanirbhar",     "Defense",           +1, "Self-reliance in defense manufacturing"),
        ("atmanirbhar",     "Manufacturing_PLI", +1, "Domestic manufacturing push"),
        ("make in india",   "Defense",           +1, "Domestic defense procurement"),
        ("make in india",   "Manufacturing_PLI", +1, "PLI scheme benefits"),
        ("export",          "IT",                +1, "Export promotion boosts IT/services"),
        ("export",          "Pharma",            +1, "Pharma export incentives"),
    ],
    # PM speech — digital and technology
    "pm_speech_digital": [
        ("digital",         "IT",                +1, "Digital India spending boosts IT"),
        ("technology",      "IT",                +1, "Tech investment announcement"),
        ("artificial intelligence", "IT",        +1, "AI policy boosts IT sector"),
        ("ai",              "IT",                +1, "AI investment"),
        ("startup",         "IT",                +1, "Startup ecosystem support"),
        ("fintech",         "Banks",             +1, "Fintech push benefits digital banks"),
        ("fintech",         "NBFC",              +1, "Fintech opportunity for NBFCs"),
        ("5g",              "Telecom",           +1, "5G rollout boosts telecom"),
        ("telecom",         "Telecom",           +1, "Telecom policy reform"),
    ],
    # PM speech — energy and environment
    "pm_speech_energy": [
        ("solar",           "Energy_Renewables", +1, "Solar push boosts renewable stocks"),
        ("green energy",    "Energy_Renewables", +1, "Clean energy investment"),
        ("renewable",       "Energy_Renewables", +1, "Renewable capacity addition"),
        ("green hydrogen",  "Energy_Renewables", +1, "Hydrogen economy push"),
        ("coal",            "Energy_Upstream",   -1, "Coal phase-out concerns"),
        ("net zero",        "Energy_Renewables", +1, "Climate commitment boosts green"),
        ("electric vehicle","Auto",              +1, "EV policy push boosts auto sector"),
        ("ev",              "Auto",              +1, "Electric vehicle incentives"),
    ],
    # PM speech — health
    "pm_speech_health": [
        ("health",          "Pharma",            +1, "Healthcare spending increase"),
        ("ayushman",        "Pharma",            +1, "Ayushman Bharat expansion"),
        ("hospital",        "Pharma",            +1, "Healthcare infrastructure boost"),
        ("medicine",        "Pharma",            +1, "Medicine accessibility push"),
        ("insurance",       "Insurance",         +1, "Health insurance push"),
    ],
    # PM speech — agriculture
    "pm_speech_agri": [
        ("farmer",          "Agriculture",       +1, "Farmer welfare scheme boost"),
        ("agriculture",     "Agriculture",       +1, "Agri policy push"),
        ("kisan",           "Agriculture",       +1, "PM-Kisan related scheme"),
        ("fertilizer",      "Chemicals",         +1, "Fertilizer subsidy or policy"),
        ("food",            "FMCG",              +1, "Food security policy benefits FMCG"),
    ],
    # PM speech — manufacturing and PLI
    "pm_speech_manufacturing": [
        ("manufacturing",   "Manufacturing_PLI", +1, "Manufacturing push benefits PLI stocks"),
        ("pli",             "Manufacturing_PLI", +1, "PLI scheme expansion"),
        ("semiconductor",   "IT",                +1, "Chip fab push benefits tech"),
        ("semiconductor",   "Manufacturing_PLI", +1, "Semiconductor manufacturing PLI"),
        ("electronics",     "Consumer_Durables", +1, "Electronics manufacturing boost"),
        ("housing",         "Realty",            +1, "Affordable housing push"),
        ("cement",          "Cement",            +1, "Construction and housing demand"),
        ("steel",           "Metals",            +1, "Infrastructure demand for steel"),
    ],
}

NIFTY_SYMBOL = "^NSEI"
INDIA_VIX = "^INDIAVIX"

# ── Auto Theme Detection Rules ────────────────────────────────────────────────
# Each theme: { keywords, threshold (min hits to activate), impacts [(sector, dir, reason)] }
THEME_DETECTORS = {
    "rbi_rate_cut": {
        "keywords": ["rbi rate cut", "repo rate cut", "rate cut", "monetary easing",
                     "accommodative policy", "rbi reduces", "interest rate cut"],
        "threshold": 2,
        "impacts": [
            ("Banks",   +3, "Rate cut expands NIMs and credit demand"),
            ("NBFC",    +3, "Lower cost of funds benefits NBFCs"),
            ("Realty",  +3, "Cheaper mortgages boost housing demand"),
            ("Auto",    +2, "Cheaper vehicle financing lifts sales"),
            ("Consumer_Durables", +1, "EMI-driven purchases accelerate"),
        ],
    },
    "rbi_rate_hike": {
        "keywords": ["rbi rate hike", "repo rate hike", "rate hike", "hawkish",
                     "monetary tightening", "rbi raises", "interest rate hike"],
        "threshold": 2,
        "impacts": [
            ("Banks",   -2, "Rate hike compresses NIMs"),
            ("NBFC",    -2, "Higher cost of funds hurts NBFCs"),
            ("Realty",  -3, "Higher mortgage rates curb demand"),
            ("Auto",    -1, "Costlier financing slows sales"),
        ],
    },
    "fii_buying": {
        "keywords": ["fii buying", "foreign inflow", "fii net buy", "foreign buying",
                     "fpi inflow", "foreign portfolio investor buying"],
        "threshold": 2,
        "impacts": [
            ("Banks",   +2, "FII inflows surge into large-cap banks"),
            ("IT",      +1, "Foreign interest in IT/tech"),
            ("NBFC",    +1, "FII buying in financial sector"),
        ],
    },
    "fii_selling": {
        "keywords": ["fii selling", "foreign outflow", "fii net sell", "foreign selling",
                     "fpi outflow", "capital outflow"],
        "threshold": 2,
        "impacts": [
            ("Banks",   -2, "FII outflows pressure large-cap banks"),
            ("IT",      -1, "Selling pressure in tech"),
            ("NBFC",    -1, "Financial sector under selling"),
        ],
    },
    "rupee_weakness": {
        "keywords": ["rupee falls", "rupee weakens", "rupee low", "inr depreciation",
                     "rupee drops", "rupee hits low", "inr falls"],
        "threshold": 2,
        "impacts": [
            ("IT",              +2, "Weak rupee boosts IT export realization"),
            ("Pharma",          +2, "Pharma export revenues rise in INR terms"),
            ("Energy_Downstream", -1, "Crude import costs rise in INR"),
            ("FMCG",            -1, "Imported input costs rise"),
        ],
    },
    "rupee_strength": {
        "keywords": ["rupee rises", "rupee strengthens", "rupee gains", "inr appreciation",
                     "rupee high", "inr rises"],
        "threshold": 2,
        "impacts": [
            ("IT",     -2, "Strong rupee compresses IT export margins"),
            ("Pharma", -1, "Export margin compression"),
            ("Metals", +1, "Cheaper metal imports"),
        ],
    },
    "crude_rally": {
        "keywords": ["crude rises", "oil prices up", "brent rally", "oil surge",
                     "opec cut", "oil price hike", "crude oil high"],
        "threshold": 2,
        "impacts": [
            ("Energy_Upstream",   +3, "Higher crude directly boosts E&P margins"),
            ("Energy_Downstream", -3, "Higher crude input costs hurt OMCs"),
            ("Paints",            -2, "TiO2 and resin costs rise"),
            ("Chemicals",         -2, "Petrochemical feedstock expensive"),
            ("Auto",              -1, "Higher fuel prices dent vehicle demand"),
            ("FMCG",              -1, "Logistics and packaging costs rise"),
        ],
    },
    "crude_fall": {
        "keywords": ["crude falls", "oil prices drop", "brent falls", "oil slump",
                     "oil oversupply", "crude down", "oil price fall", "crude slide"],
        "threshold": 2,
        "impacts": [
            ("Energy_Upstream",   -3, "Lower crude hurts E&P margins directly"),
            ("Energy_Downstream", +3, "Cheaper input costs for OMC refiners"),
            ("Paints",            +2, "Crude-linked raw material costs fall"),
            ("Chemicals",         +2, "Petrochemical feedstock cheaper"),
            ("Auto",              +1, "Lower fuel boosts vehicle demand"),
            ("FMCG",              +1, "Lower logistics and packaging costs"),
        ],
    },
    "infrastructure_capex": {
        "keywords": ["infrastructure spending", "capex boost", "infra investment",
                     "highway project", "metro project", "government capex",
                     "infrastructure order", "national highway"],
        "threshold": 2,
        "impacts": [
            ("Infrastructure", +3, "Direct capex spending benefits EPC stocks"),
            ("Cement",         +2, "Construction activity rises"),
            ("Metals",         +2, "Steel demand for infrastructure"),
            ("Ports_Logistics", +1, "Logistics demand grows"),
        ],
    },
    "defense_orders": {
        "keywords": ["defense order", "defence contract", "military procurement",
                     "defense export", "hal order", "bel order", "defence deal",
                     "indigenous defense", "atmanirbhar defense"],
        "threshold": 2,
        "impacts": [
            ("Defense",        +4, "Defense order flow directly benefits sector"),
            ("Manufacturing_PLI", +1, "Defense indigenization push"),
        ],
    },
    "it_headwinds": {
        "keywords": ["it layoffs", "tech layoffs", "it slowdown", "software demand falls",
                     "it revenue miss", "tech spending cut", "visa restrictions h1b"],
        "threshold": 2,
        "impacts": [
            ("IT", -3, "IT sector faces demand or visa headwinds"),
        ],
    },
    "it_tailwinds": {
        "keywords": ["ai spending", "cloud spending", "digital transformation",
                     "it deal win", "large deal", "tech hiring", "ai contract"],
        "threshold": 2,
        "impacts": [
            ("IT", +3, "AI/cloud spending drives IT deal wins"),
        ],
    },
    "banking_stress": {
        "keywords": ["bank npa", "npa rises", "bad loans", "banking crisis", "credit stress",
                     "loan default", "bank fraud", "banking sector stress"],
        "threshold": 2,
        "impacts": [
            ("Banks", -3, "NPA concerns weigh on banking sector"),
            ("NBFC",  -2, "Credit quality concerns spread to NBFCs"),
        ],
    },
    "pharma_tailwinds": {
        "keywords": ["usfda approval", "usfda clearance", "drug approval",
                     "pharma export", "generic drug", "fda approved", "who prequalification"],
        "threshold": 2,
        "impacts": [
            ("Pharma", +3, "USFDA approvals unlock export revenues"),
        ],
    },
    "pharma_headwinds": {
        "keywords": ["usfda warning letter", "import alert", "drug recall",
                     "fda rejection", "gmp violation"],
        "threshold": 1,
        "impacts": [
            ("Pharma", -3, "USFDA regulatory action hurts sector"),
        ],
    },
    "ev_push": {
        "keywords": ["electric vehicle", "ev policy", "ev subsidy", "ev sales", "ev charging",
                     "electric car", "pm-ebus", "ev mandate"],
        "threshold": 2,
        "impacts": [
            ("Auto",              +2, "EV push boosts forward-looking auto names"),
            ("Energy_Renewables", +1, "EV charging needs green power"),
            ("Consumer_Durables", +1, "EV components and electronics"),
        ],
    },
    "renewable_push": {
        "keywords": ["solar energy", "renewable energy", "green energy", "wind power",
                     "green hydrogen", "net zero", "solar panel", "clean energy"],
        "threshold": 2,
        "impacts": [
            ("Energy_Renewables", +3, "Policy tailwind for renewable energy"),
            ("Infrastructure",    +1, "Grid infrastructure investment"),
        ],
    },
    "realty_boost": {
        "keywords": ["housing demand", "home sales", "property sales", "real estate boom",
                     "pmay", "affordable housing", "housing project"],
        "threshold": 2,
        "impacts": [
            ("Realty",  +3, "Housing demand surge benefits developers"),
            ("Cement",  +2, "Construction activity picks up"),
            ("Banks",   +1, "Home loan disbursements grow"),
        ],
    },
    "global_recession": {
        "keywords": ["global recession", "us recession", "gdp contraction", "economic downturn",
                     "global slowdown", "recession fears"],
        "threshold": 3,
        "impacts": [
            ("IT",     -2, "IT discretionary spending cuts globally"),
            ("Metals", -2, "Industrial demand slump"),
            ("Banks",  -1, "Credit quality and FII flow concerns"),
            ("Pharma", +1, "Defensive; healthcare demand resilient"),
        ],
    },
    "china_slowdown": {
        "keywords": ["china slowdown", "china gdp miss", "china demand falls",
                     "china weakness", "china manufacturing pmi"],
        "threshold": 2,
        "impacts": [
            ("Metals",    -2, "China is largest metals consumer"),
            ("Chemicals", -1, "Chemical demand from China falls"),
        ],
    },
    "india_pakistan_tension": {
        "keywords": ["india pakistan", "pakistan tension", "border tension", "surgical strike",
                     "line of control", "kashmir tension", "india military"],
        "threshold": 2,
        "impacts": [
            ("Defense",           +4, "Heightened border tension spurs defense orders"),
            ("Ports_Logistics",   -1, "Trade disruption risk"),
            ("Travel_Tourism",    -2, "Travel affected by tensions"),
            ("Banks",             -1, "Risk-off sentiment"),
        ],
    },
    "geopolitical_tension": {
        "keywords": ["war", "conflict", "missile", "sanction", "geopolitical", "nato",
                     "ukraine", "middle east war"],
        "threshold": 3,
        "impacts": [
            ("Defense",           +2, "Geopolitical tension favors defense"),
            ("Energy_Upstream",   +1, "Oil supply risk premium"),
            ("Gold",              +1, "Safe haven demand"),
            ("Banks",             -1, "Risk-off"),
        ],
    },
    "strong_earnings": {
        "keywords": ["profit jumps", "earnings beat", "revenue beat", "record profit",
                     "strong results", "quarterly profit rises", "net profit up"],
        "threshold": 3,
        "impacts": [
            ("Banks", +1, "Strong earnings season positive for financials"),
            ("IT",    +1, "Tech earnings beat expectations"),
        ],
    },
    "weak_earnings": {
        "keywords": ["profit falls", "earnings miss", "revenue miss", "weak results",
                     "quarterly loss", "net profit down", "margin squeeze"],
        "threshold": 3,
        "impacts": [
            ("Banks", -1, "Weak earnings season weighs on financials"),
            ("IT",    -1, "Tech earnings disappointment"),
        ],
    },
}

POSITIVE_KEYWORDS = [
    "beat", "beats", "strong", "record", "profit", "growth", "dividend",
    "buyback", "upgrade", "order", "win", "acquisition", "expand", "launch",
    "q3 results", "q4 results", "outlook", "guidance raise", "surplus"
]
NEGATIVE_KEYWORDS = [
    "fraud", "probe", "investigation", "loss", "miss", "downgrade", "resign",
    "penalty", "default", "delay", "weak", "concern", "slump", "crash",
    "scam", "fir", "raid", "sebi notice", "npa"
]
