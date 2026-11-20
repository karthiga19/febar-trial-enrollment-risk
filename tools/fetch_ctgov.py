"""Pull trials from the public ClinicalTrials.gov API v2 into NDJSON landing files.

Each API page -> one file in data/raw/<cohort>/ (mimics files landing for Auto Loader).
Usage: python3 tools/fetch_ctgov.py <cohort> <status-filter> [date-range] [max_pages]
"""
import json, sys, time, urllib.parse, urllib.request, pathlib

API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ",".join([
    "protocolSection.identificationModule", "protocolSection.statusModule",
    "protocolSection.sponsorCollaboratorsModule", "protocolSection.conditionsModule",
    "protocolSection.designModule", "protocolSection.armsInterventionsModule",
    "protocolSection.eligibilityModule", "protocolSection.contactsLocationsModule",
    "protocolSection.outcomesModule",
])

def main(cohort, status, date_range=None, max_pages=1000):
    out = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw" / cohort
    out.mkdir(parents=True, exist_ok=True)
    adv = "AREA[StudyType]INTERVENTIONAL AND (AREA[Phase]PHASE2 OR AREA[Phase]PHASE3)"
    if date_range:
        adv += f" AND AREA[StartDate]RANGE[{date_range}]"
    params = {"filter.overallStatus": status, "filter.advanced": adv,
              "pageSize": 1000, "fields": FIELDS, "format": "json"}
    token, page, total = None, 0, 0
    while page < int(max_pages):
        if token:
            params["pageToken"] = token
        url = API + "?" + urllib.parse.urlencode(params)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    body = json.load(r)
                break
            except Exception as e:  # transient API errors
                print("retry", attempt, e); time.sleep(5 * (attempt + 1))
        studies = body.get("studies", [])
        with open(out / f"ctgov_{cohort}_{page:04d}.json", "w") as f:
            for s in studies:
                f.write(json.dumps(s) + "\n")
        total += len(studies); page += 1
        print(f"{cohort} page {page}: {len(studies)} (total {total})", flush=True)
        token = body.get("nextPageToken")
        if not token:
            break
    print(f"DONE {cohort}: {total} studies in {page} files")

if __name__ == "__main__":
    main(*sys.argv[1:])
