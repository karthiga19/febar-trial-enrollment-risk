"""Synthesize the Meridian Therapeutics (fictional sponsor) clinical-ops feeds.

Study designs + eligibility text are templated from REAL currently-recruiting industry
Phase 2/3 trials on ClinicalTrials.gov (public data; source_nct_id kept for lineage).
Sponsor, study codes, managers, sites and weekly enrollment actuals are synthetic.

Outputs (landing-zone layout that Auto Loader watches):
  data/meridian/portfolio/ctms_study_master_<date>.csv
  data/meridian/enrollment/edc_enrollment_week_<yyyy-mm-dd>.csv   (one file per week)
  data/meridian_holdback/...  (latest week, dropped live during the demo)
"""
import csv, json, glob, math, random, re, pathlib, datetime as dt
import numpy as np

random.seed(42); rng = np.random.default_rng(42)
ROOT = pathlib.Path(__file__).resolve().parents[1]
AS_OF = dt.date(2026, 11, 13)        # last week loaded before the demo
HOLDBACK = dt.date(2026, 11, 20)     # week dropped live
N_STUDIES = 24

TA_RULES = [  # (therapeutic area, abbrev, keyword regex on conditions)
  ("Oncology", "ONC", r"cancer|carcinoma|tumou?r|lymphoma|leukemia|myeloma|melanoma|neoplasm|sarcoma|glioma"),
  ("Cardiometabolic", "CVM", r"heart|cardi|diabet|obes|hypertension|lipid|kidney|renal"),
  ("Neuroscience", "NEU", r"alzheimer|parkinson|sclerosis|epilep|migraine|neuro|depress|schizo|als\b"),
  ("Immunology", "IMM", r"arthritis|psoria|lupus|crohn|colitis|dermatitis|asthma|copd|urticaria"),
  ("Infectious Disease", "INF", r"hiv|hepatitis|influenza|covid|infection|vaccine|rsv"),
]
MANAGERS = ["Dana Whitfield", "Priya Raman", "Marcus Oyelaran", "Elena Sorensen", "Tomás Herrera", "Grace Liu"]
COUNTRIES = ["United States", "United States", "United States", "Canada", "Germany", "Spain", "Poland", "Japan", "Australia", "Brazil"]

def ta_of(cond):
    for ta, ab, rx in TA_RULES:
        if re.search(rx, cond, re.I): return ta, ab
    return None, None

def n_exclusions(text):
    ex = re.split(r"exclusion criteria", text, flags=re.I)
    return len(re.findall(r"^\s*(?:[-*•]|\d+\.)\s", ex[1], flags=re.M)) if len(ex) > 1 else 0

def friday(d): return d + dt.timedelta(days=(4 - d.weekday()) % 7)

# ---- pick real recruiting trials as design templates -------------------------
cands = []
for f in sorted(glob.glob(str(ROOT / "data/raw/recruiting/*.json"))):
    for line in open(f):
        p = json.loads(line)["protocolSection"]
        if p["sponsorCollaboratorsModule"]["leadSponsor"].get("class") != "INDUSTRY": continue
        phases = p["designModule"].get("phases", [])
        elig = p.get("eligibilityModule", {}).get("eligibilityCriteria", "")
        cond = "; ".join(p.get("conditionsModule", {}).get("conditions", [])[:3])
        ta, ab = ta_of(cond)
        if not ta or len(elig) < 800 or not phases: continue
        cands.append(dict(nct=p["identificationModule"]["nctId"], cond=cond, ta=ta, ab=ab,
             phase="PHASE3" if "PHASE3" in phases else "PHASE2",
             enroll=p["designModule"].get("enrollmentInfo", {}).get("count") or 200,
             sites=len(p.get("contactsLocationsModule", {}).get("locations", [])), excl=n_exclusions(elig)))
random.shuffle(cands)
quota = {"Oncology": 8, "Cardiometabolic": 4, "Neuroscience": 4, "Immunology": 5, "Infectious Disease": 3}
picked = []
for c in cands:
    if quota.get(c["ta"], 0) > 0:
        picked.append(c); quota[c["ta"]] -= 1
assert len(picked) == N_STUDIES, len(picked)

# ---- generate study master + weekly site enrollment -------------------------
excl = np.array([c["excl"] for c in picked], float)
z = (excl - excl.mean()) / (excl.std() + 1e-9)
studies, weekly = [], []
for i, c in enumerate(picked):
    code = f"MRD-{c['ab']}-{'3' if c['phase']=='PHASE3' else '2'}{i+1:02d}"
    target = int(np.clip(c["enroll"], 80, 900))
    plan_rate = rng.uniform(0.4, 1.1)                                 # pts / site / month assumed in plan
    months = float(rng.uniform(12, 26))                               # planned enrollment duration
    planned_sites = int(np.clip(round(target / (plan_rate * (months - 3))), 8, 80))
    lpi = friday(dt.date(2026, 12, 1) + dt.timedelta(days=int(rng.integers(0, 540))))
    fpi = friday(lpi - dt.timedelta(days=int(months * 30.4)))
    if fpi > AS_OF - dt.timedelta(days=120):                          # every study has >=4 months of history
        fpi = friday(AS_OF - dt.timedelta(days=int(rng.integers(120, 300)))); lpi = friday(fpi + dt.timedelta(days=int(months * 30.4)))
    plan_rate = target / (planned_sites * (months - 3))
    # hidden truth: restrictive eligibility -> lower real productivity, slower site activation
    productivity = float(np.exp(rng.normal(-0.25 * z[i] + 0.12, 0.2)))
    ramp_weeks = int(np.clip(rng.normal(14 + 4 * z[i], 3), 6, 30))
    studies.append(dict(study_code=code, source_nct_id=c["nct"], study_title=f"{c['phase'].title().replace('Phase','Phase ')} study in {c['cond'].split(';')[0]}",
        therapeutic_area=c["ta"], phase=c["phase"], indication=c["cond"].split(";")[0], study_manager=MANAGERS[i % len(MANAGERS)],
        target_enrollment=target, planned_sites=planned_sites, planned_fpi_date=fpi.isoformat(), planned_lpi_date=lpi.isoformat(),
        planned_rate_pts_site_month=round(plan_rate, 2)))
    sites = [dict(site_id=f"{code}-S{s+1:03d}", country=random.choice(COUNTRIES),
                  activate_week=int(rng.integers(0, ramp_weeks + 1)) if s < planned_sites * rng.uniform(0.7, 1.0) else 10**6,
                  site_prod=float(rng.gamma(1.5, 1/1.5))) for s in range(planned_sites)]
    wk, cum = fpi, 0
    w_i = 0
    while wk <= HOLDBACK and cum < target:
        for s in sites:
            active = w_i >= s["activate_week"]
            lam = plan_rate / 4.33 * productivity * s["site_prod"] if active else 0
            rand = int(rng.poisson(lam)) if active else 0
            rand = min(rand, target - cum); cum += rand
            scr = rand + int(rng.poisson(rand * 1.3 + (0.3 if active else 0)))
            weekly.append(dict(study_code=code, site_id=s["site_id"], country=s["country"], week_ending=wk.isoformat(),
                               site_active=str(active).lower(), patients_screened=scr, patients_randomized=rand))
        wk += dt.timedelta(days=7); w_i += 1

# ---- write landing files -----------------------------------------------------
out = ROOT / "data/meridian"; hb = ROOT / "data/meridian_holdback"
for d in [out / "portfolio", out / "enrollment", hb / "enrollment"]: d.mkdir(parents=True, exist_ok=True)
with open(out / "portfolio" / f"ctms_study_master_{AS_OF}.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=[k for k in studies[0] if not k.startswith("_")], extrasaction="ignore"); w.writeheader(); w.writerows(studies)
by_week = {}
for r in weekly: by_week.setdefault(r["week_ending"], []).append(r)
for wkend, rows in by_week.items():
    target_dir = (hb if wkend == HOLDBACK.isoformat() else out) / "enrollment"
    with open(target_dir / f"edc_enrollment_week_{wkend}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
import collections
cum = collections.Counter(); 
for r in weekly:
    if r["week_ending"] <= AS_OF.isoformat(): cum[r["study_code"]] += r["patients_randomized"]
for st in studies:
    f, l = dt.date.fromisoformat(st["planned_fpi_date"]), dt.date.fromisoformat(st["planned_lpi_date"])
    st["_pct"] = round(cum[st["study_code"]] / max(1, st["target_enrollment"] * min(1, (AS_OF - f).days / (l - f).days)), 2)
print(f"studies={len(studies)} weekly_rows={len(weekly)} weeks={len(by_week)}")
for s in studies: print(s["study_code"], s["therapeutic_area"], s["target_enrollment"], s["planned_sites"], s["planned_fpi_date"], s["planned_lpi_date"], s["source_nct_id"], "pct_of_plan", s["_pct"])
