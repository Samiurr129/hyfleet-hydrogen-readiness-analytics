"""
generate_data.py
----------------
Builds the simulated HyFleet dataset for a fictional SME haulier,
"Pennine Haulage Ltd", which runs 60 HGVs from three Yorkshire depots.

The company and its data are invented. The numbers are calibrated to
published UK figures so the analysis behaves like the real thing:

* Diesel use: DfT road freight statistics give about 7.9 mpg for
  articulated HGVs and 9.1 mpg for rigids. That is about 35.8 and
  31.0 litres per 100 km.
* Diesel price: weekly UK pump prices moved between about 141p and
  200p per litre in the 52 weeks to mid November 2026 (UK Government
  weekly fuel price statistics). The series here is simulated but
  shaped to those anchor points.

Some mess is added on purpose (inconsistent text, mixed units, mixed
date formats, duplicates, missing values, typos). Cleaning it is part
of the learning.

Run from the project root:  python src/generate_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_VEHICLES = 60
START = pd.Timestamp("2025-11-24")  # a Monday
N_WEEKS = 52

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


def make_depots() -> pd.DataFrame:
    # km_to_hrs = road distance to the nearest HGV-capable hydrogen
    # refuelling station. Fictional values for the case study.
    return pd.DataFrame(
        {
            "depot_id": ["D01", "D02", "D03"],
            "depot_name": ["Bradford", "Wakefield", "Hull"],
            "region": ["West Yorkshire", "West Yorkshire", "East Riding"],
            "km_to_hrs": [18, 42, 95],
        }
    )


def make_vehicles(rng: np.random.Generator) -> pd.DataFrame:
    ids = np.array([f"V{n:03d}" for n in range(1, N_VEHICLES + 1)])
    vtype = rng.choice(["artic", "rigid"], size=N_VEHICLES, p=[0.6, 0.4])
    is_artic = vtype == "artic"

    year = rng.integers(2016, 2025, size=N_VEHICLES)

    # Rated diesel use (l/100km): DfT averages, newer trucks a bit better.
    base = np.where(is_artic, 35.8, 31.0)
    l_per_100 = base + rng.normal(0, 1.5, N_VEHICLES) - 0.25 * (year - 2020)

    gvw = np.where(is_artic, 44, rng.choice([18, 26], size=N_VEHICLES))
    payload_cap = np.where(is_artic, 26.0, np.where(gvw == 26, 15.0, 9.0))
    duty = np.where(
        is_artic,
        rng.choice(["trunking", "regional"], size=N_VEHICLES, p=[0.7, 0.3]),
        rng.choice(["regional", "multi-drop"], size=N_VEHICLES, p=[0.4, 0.6]),
    )

    depot = rng.choice(["D01", "D02", "D03"], size=N_VEHICLES, p=[0.45, 0.35, 0.2])
    # Messy text: the fleet system lets staff type the depot by hand.
    names = {"D01": "Bradford", "D02": "Wakefield", "D03": "Hull"}
    variants = lambda s: [s, s.lower(), s.upper() + " ", f" {s} Depot", s]
    home_depot = [rng.choice(variants(names[d])) for d in depot]

    return pd.DataFrame(
        {
            "vehicle_id": ids,
            "home_depot": home_depot,
            "vehicle_type": vtype,
            "gvw_t": gvw,
            "payload_capacity_t": payload_cap,
            "duty_cycle": duty,
            "year_registered": year,
            "rated_l_per_100km": l_per_100.round(1),
        }
    )


def make_diesel_prices(rng: np.random.Generator) -> pd.DataFrame:
    weeks = pd.date_range(START, periods=N_WEEKS, freq="W-MON")
    # Anchor points (pence per litre, pump price incl. VAT).
    anchor_days = np.array([0, 50, 95, 135, 200, 280, 322, 357])
    anchor_ppl = np.array([146, 141, 143, 190, 183, 184, 200, 197])
    day_index = (weeks - START).days.to_numpy()
    ppl = np.interp(day_index, anchor_days, anchor_ppl)  # NumPy interpolation
    ppl = ppl + rng.normal(0, 0.8, len(ppl))
    return pd.DataFrame({"week_start": weeks, "pump_ppl": ppl.round(2)})


def make_duties(rng: np.random.Generator, veh: pd.DataFrame) -> pd.DataFrame:
    days = pd.date_range(START, periods=N_WEEKS * 7, freq="D")
    days = days[days.dayofweek < 6]  # Monday to Saturday

    rows = []
    for v in veh.itertuples(index=False):
        # Each vehicle works on about 85% of operating days.
        works = rng.random(len(days)) < 0.85
        d = days[works]
        n = len(d)

        median_km = {"trunking": 420, "regional": 230, "multi-drop": 140}[v.duty_cycle]
        km = rng.lognormal(np.log(median_km), 0.22, n)
        # Drivers' hours cap a day at roughly 700 km, so redraw any longer days.
        too_long = km > 720
        km[too_long] = rng.uniform(550, 720, too_long.sum())

        load = np.clip(rng.normal(0.62, 0.18, n), 0.05, 1.0)
        payload = load * v.payload_capacity_t
        empty_share = np.clip(rng.normal(0.30, 0.10, n), 0, 0.8)  # DfT ~30%

        winter = np.isin(d.month, [12, 1, 2]).astype(float)
        fuel = (
            km / 100 * v.rated_l_per_100km
            * (1 + 0.15 * (load - 0.62))
            * (1 + 0.05 * winter)
            * rng.normal(1, 0.04, n)
        )
        hours = np.clip(km / rng.normal(62, 6, n) + rng.uniform(1.0, 2.5, n), 1, 15)
        rtb = rng.random(n) < (0.95 if v.duty_cycle != "trunking" else 0.75)

        rows.append(
            pd.DataFrame(
                {
                    "vehicle_id": v.vehicle_id,
                    "duty_date": d,
                    "distance": km,
                    "payload_t": payload,
                    "empty_km_share": empty_share,
                    "fuel_litres": fuel,
                    "duty_hours": hours,
                    "returned_to_base": rtb,
                }
            )
        )

    duties = pd.concat(rows, ignore_index=True)
    duties = duties.sort_values(["duty_date", "vehicle_id"]).reset_index(drop=True)
    duties.insert(0, "duty_id", [f"T{n:06d}" for n in range(1, len(duties) + 1)])
    return duties


def add_mess(rng: np.random.Generator, duties: pd.DataFrame) -> pd.DataFrame:
    df = duties.copy()
    n = len(df)

    # Two telematics providers. Provider B reports miles and UK dates.
    provider_b_vehicles = rng.choice(df["vehicle_id"].unique(), size=9, replace=False)
    is_b = df["vehicle_id"].isin(provider_b_vehicles).to_numpy()
    df["telematics_source"] = np.where(is_b, "B", "A")
    df["distance_unit"] = np.where(is_b, "mi", "km")
    df.loc[is_b, "distance"] = df.loc[is_b, "distance"] / 1.609344

    date_str = df["duty_date"].dt.strftime("%Y-%m-%d")
    date_str[is_b] = df.loc[is_b, "duty_date"].dt.strftime("%d/%m/%Y")
    df["duty_date"] = date_str

    # Rounding as the devices would report.
    df["distance"] = df["distance"].round(1)
    df["fuel_litres"] = df["fuel_litres"].round(1)
    df["payload_t"] = df["payload_t"].round(2)
    df["empty_km_share"] = df["empty_km_share"].round(3)
    df["duty_hours"] = df["duty_hours"].round(2)

    # Missing fuel readings (about 3%) and payloads (about 2%).
    df.loc[rng.random(n) < 0.03, "fuel_litres"] = np.nan
    df.loc[rng.random(n) < 0.02, "payload_t"] = np.nan

    # Decimal slips: fuel keyed in ten times too high (about 0.3%).
    slip = rng.random(n) < 0.003
    df.loc[slip, "fuel_litres"] = df.loc[slip, "fuel_litres"] * 10

    # Bad distance readings: zero or negative (about 0.2%).
    bad = rng.random(n) < 0.002
    df.loc[bad, "distance"] = rng.choice([0.0, -1.0], size=bad.sum()) * df.loc[bad, "distance"]

    # Duplicate uploads (about 1.2%).
    dupes = df.sample(frac=0.012, random_state=SEED)
    df = pd.concat([df, dupes]).sort_values("duty_id").reset_index(drop=True)
    return df


def main() -> None:
    rng = np.random.default_rng(SEED)
    RAW.mkdir(parents=True, exist_ok=True)

    depots = make_depots()
    vehicles = make_vehicles(rng)
    prices = make_diesel_prices(rng)
    duties = add_mess(rng, make_duties(rng, vehicles))

    depots.to_csv(RAW / "depots.csv", index=False)
    vehicles.to_csv(RAW / "vehicles.csv", index=False)
    prices.to_csv(RAW / "diesel_prices.csv", index=False)
    duties.to_csv(RAW / "duties.csv", index=False)

    print(f"depots: {len(depots)}, vehicles: {len(vehicles)}, "
          f"price weeks: {len(prices)}, duty rows: {len(duties):,}")


if __name__ == "__main__":
    main()
