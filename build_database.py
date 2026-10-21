"""
Cleans the two raw CMS files in data/raw/ and loads them into a SQLite
database (hospitals.db) for analysis.

Raw sources (data.cms.gov, Provider Data Catalog):
  - Hospital General Information          -> data/raw/hospital_general_info.csv
  - Hospital Readmissions Reduction        -> data/raw/hrrp_fy2026.csv
    Program (FY 2026, performance period 07/01/2021 - 06/30/2024)

Cleaning steps:
  1. Rename columns to snake_case.
  2. Convert CMS placeholder text ("Not Available", "Too Few to Report")
     to NULL so numbers can be stored as real numbers.
  3. Cast numeric columns to INTEGER / REAL.
  4. Map measure codes (e.g. READM-30-HF-HRRP) to readable condition names.
  5. Add a lookup table for the CMS footnote codes used in the data.
"""
import os
import sqlite3

import pandas as pd

RAW_DIR = os.path.join("data", "raw")
CLEAN_DIR = os.path.join("data", "clean")
DB_PATH = "hospitals.db"

MISSING = ["Not Available", "Too Few to Report", "N/A", ""]

CONDITIONS = {
    "READM-30-AMI-HRRP": "Heart attack (AMI)",
    "READM-30-HF-HRRP": "Heart failure",
    "READM-30-PN-HRRP": "Pneumonia",
    "READM-30-COPD-HRRP": "COPD",
    "READM-30-CABG-HRRP": "Bypass surgery (CABG)",
    "READM-30-HIP-KNEE-HRRP": "Hip/knee replacement",
}

# Text from the CMS "Footnote Crosswalk" dataset, for the codes present in these files.
FOOTNOTES = {
    "1": "The number of cases/patients is too few to report.",
    "5": "Results are not available for this reporting period.",
    "7": "No cases met the criteria for this measure.",
    "11": "There were discrepancies in the data collection process.",
    "16": "There are too few measures or measure groups reported to calculate a star rating or measure group score.",
    "19": "Data are shown only for hospitals that participate in the Inpatient Quality Reporting (IQR) and Outpatient Quality Reporting (OQR) programs.",
    "22": "Overall star ratings are not calculated for Department of Defense (DoD) hospitals.",
    "23": "The data are based on claims that the hospital or facility submitted to CMS; the facility reported discrepancies in its claims data.",
    "29": "This measure was calculated using partial performance period data due to a CMS-approved exception.",
}

SCHEMA = """
DROP TABLE IF EXISTS readmissions;
DROP TABLE IF EXISTS hospitals;
DROP TABLE IF EXISTS footnotes;

CREATE TABLE hospitals (
    facility_id        TEXT PRIMARY KEY,
    facility_name      TEXT NOT NULL,
    city               TEXT,
    state              TEXT NOT NULL,
    county             TEXT,
    hospital_type      TEXT,
    ownership          TEXT,
    emergency_services TEXT,
    star_rating        INTEGER CHECK (star_rating BETWEEN 1 AND 5),
    star_rating_footnote TEXT,
    readm_measures_better INTEGER,
    readm_measures_no_different INTEGER,
    readm_measures_worse INTEGER
);

CREATE TABLE readmissions (
    facility_id               TEXT NOT NULL,
    facility_name             TEXT NOT NULL,
    state                     TEXT NOT NULL,
    measure_code              TEXT NOT NULL,
    condition                 TEXT NOT NULL,
    discharges                INTEGER,
    excess_readmission_ratio  REAL,
    predicted_readmission_rate REAL,
    expected_readmission_rate REAL,
    readmissions              INTEGER,
    footnote                  TEXT,
    start_date                TEXT,
    end_date                  TEXT,
    PRIMARY KEY (facility_id, measure_code)
);

CREATE TABLE footnotes (
    footnote    TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE INDEX idx_readmissions_condition ON readmissions(condition);
CREATE INDEX idx_readmissions_state ON readmissions(state);
"""


def to_date(series):
    """Convert MM/DD/YYYY to ISO YYYY-MM-DD so SQLite can sort and compare dates."""
    return pd.to_datetime(series, format="%m/%d/%Y").dt.strftime("%Y-%m-%d")


def clean_hospitals():
    df = pd.read_csv(os.path.join(RAW_DIR, "hospital_general_info.csv"),
                     dtype=str, na_values=MISSING, keep_default_na=True)
    df = df.rename(columns={
        "Facility ID": "facility_id",
        "Facility Name": "facility_name",
        "City/Town": "city",
        "State": "state",
        "County/Parish": "county",
        "Hospital Type": "hospital_type",
        "Hospital Ownership": "ownership",
        "Emergency Services": "emergency_services",
        "Hospital overall rating": "star_rating",
        "Hospital overall rating footnote": "star_rating_footnote",
        "Count of READM Measures Better": "readm_measures_better",
        "Count of READM Measures No Different": "readm_measures_no_different",
        "Count of READM Measures Worse": "readm_measures_worse",
    })
    keep = ["facility_id", "facility_name", "city", "state", "county",
            "hospital_type", "ownership", "emergency_services", "star_rating",
            "star_rating_footnote", "readm_measures_better",
            "readm_measures_no_different", "readm_measures_worse"]
    df = df[keep]
    for col in ["star_rating", "readm_measures_better",
                "readm_measures_no_different", "readm_measures_worse"]:
        df[col] = pd.to_numeric(df[col]).astype("Int64")
    return df


def clean_readmissions():
    df = pd.read_csv(os.path.join(RAW_DIR, "hrrp_fy2026.csv"),
                     dtype=str, na_values=MISSING, keep_default_na=True)
    df = df.rename(columns={
        "Facility Name": "facility_name",
        "Facility ID": "facility_id",
        "State": "state",
        "Measure Name": "measure_code",
        "Number of Discharges": "discharges",
        "Footnote": "footnote",
        "Excess Readmission Ratio": "excess_readmission_ratio",
        "Predicted Readmission Rate": "predicted_readmission_rate",
        "Expected Readmission Rate": "expected_readmission_rate",
        "Number of Readmissions": "readmissions",
        "Start Date": "start_date",
        "End Date": "end_date",
    })
    df["condition"] = df["measure_code"].map(CONDITIONS)
    if df["condition"].isna().any():
        raise ValueError("Unknown measure code found: update CONDITIONS")
    for col in ["discharges", "readmissions"]:
        df[col] = pd.to_numeric(df[col]).astype("Int64")
    for col in ["excess_readmission_ratio", "predicted_readmission_rate",
                "expected_readmission_rate"]:
        df[col] = pd.to_numeric(df[col])
    df["start_date"] = to_date(df["start_date"])
    df["end_date"] = to_date(df["end_date"])
    cols = ["facility_id", "facility_name", "state", "measure_code", "condition",
            "discharges", "excess_readmission_ratio", "predicted_readmission_rate",
            "expected_readmission_rate", "readmissions", "footnote",
            "start_date", "end_date"]
    return df[cols]


def main():
    hospitals = clean_hospitals()
    readmissions = clean_readmissions()
    footnotes = pd.DataFrame(list(FOOTNOTES.items()), columns=["footnote", "description"])

    os.makedirs(CLEAN_DIR, exist_ok=True)
    hospitals.to_csv(os.path.join(CLEAN_DIR, "hospitals.csv"), index=False)
    readmissions.to_csv(os.path.join(CLEAN_DIR, "readmissions.csv"), index=False)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    hospitals.to_sql("hospitals", conn, if_exists="append", index=False)
    readmissions.to_sql("readmissions", conn, if_exists="append", index=False)
    footnotes.to_sql("footnotes", conn, if_exists="append", index=False)
    conn.commit()

    for table in ["hospitals", "readmissions", "footnotes"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:<13} {n:>6,} rows")
    conn.close()
    print(f"Database written to {DB_PATH}")


if __name__ == "__main__":
    main()
