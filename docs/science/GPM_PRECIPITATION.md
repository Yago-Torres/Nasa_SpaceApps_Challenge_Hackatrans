# GPM IMERG monthly precipitation (ABB-09)

`GET /api/precipitation/gpm?latitude&longitude&year[&compare_power=true]` returns twelve monthly precipitation totals from NASA GPM IMERG Final for the 0.1° cell that contains the point, side by side with the NASA POWER monthly totals for the same year. Code: `backend/agroblackbox/services/gpm.py`, `precipitation.py`; web: `frontend/src/features/precipitation/`.

## Source

| Item | Value |
|---|---|
| Product | `GPM_3IMERGM` v07: GPM IMERG Final Precipitation L3, 1 month, 0.1° × 0.1°, V07 (NASA GES DISC), DOI 10.5067/GPM/IMERG/3B-MONTH/07 |
| Why monthly Final | One granule per month (12 small requests per year), gauge-adjusted, and the same time step as the POWER anomaly analysis. Latency about 3.5 months; the record starts in 1998. |
| Discovery | NASA CMR `granules.json` (`short_name=GPM_3IMERGM`, `version=07`, `temporal`), public metadata. If two processing letters exist for a month (V07A, V07B), the later one is used. |
| Access | GES DISC OPeNDAP (`gpm1.gesdisc.eosdis.nasa.gov/opendap/…`), DAP2 ASCII subset of one cell, `Authorization: Bearer $EARTHDATA_TOKEN`. The Earthdata account must have accepted the GES DISC data terms (done 2026-11-15). |
| Variables | `precipitation` (mm/hr, monthly mean rate), `randomError` (mm/hr, RMS), `precipitationQualityIndex` (dimensionless), `gaugeRelativeWeighting` (%), plus the cell centre `lat`/`lon` |
| Fill | `-9999.9` (float) and `-9999` (int16) → missing |
| Grid | 3600 × 1800 cells, centres at −179.95…179.95 and −89.95…89.95 |
| Licence | NASA EOSDIS open data, no restriction on reuse; cite the DOI above |

## Method

1. Cell: `i = floor((lon + 180) / 0.1)`, `j = floor((lat + 90) / 0.1)`, clamped at the edges. The centre returned by OPeNDAP must equal the expected centre (±0.011°); otherwise the month is not accepted.
2. Units: before any new value is accepted (or cached), the dataset attributes (`.das`) of one granule must report `mm/hr` for `precipitation` and `randomError` and `percent` for the gauge weight. The check runs alongside the month reads; a passed check is cached for 30 days per product version (`cache.units_from_cache`).
3. Total: `precipitation_mm = rate × days in month × 24`, rounded to 0.1 mm. The random error is converted the same way and is IMERG's own estimate (RMS); it is shown as ±, not as a confidence interval.
4. Statuses: `OBSERVED`, `MISSING` (fill value), `NOT_AVAILABLE` (no granule published, for example recent months) and `NOT_READ` (retrieval failed for that month only, or it was not read within the request's time budget). A rejected token stops the whole request; if every month fails, the request fails (502).
6. **Slow GES DISC:** on 2026-11-15 GES DISC OPeNDAP took 23–50 s before the first byte of a `.das`, so the original 30 s read limit failed every request after ~90 s of retries. Reads now wait up to 75 s and a timed-out read is not retried (a slow connection, up to 20 s, still is); at most 4 requests run at once, because more made GES DISC answer 503; and the whole year has an 85 s budget, so the response arrives before the 100 s limit of the Cloudflare tunnel that serves the demo (HTTP 524 after that). Months still unread then are `NOT_READ` (months already read are cached, so retrying completes the year). If the units check itself does not finish, nothing is accepted and the request fails (502). The NASA POWER comparison is fetched at the same time as GPM with the same budget; if it does not finish, the comparison is `UNAVAILABLE` and the GPM months are still returned.
5. **Comparison with POWER:** POWER `PRECTOTCORR` daily values for the same year are summed per calendar month (UTC), and only months with every day present are used. Difference = GPM − POWER. There is no regridding, interpolation, bias correction or significance test. The two cells differ in size (IMERG 0.1°, POWER 0.5° × 0.625°) and in method, so a difference describes disagreement between products, not which is right. If POWER fails, GPM is still returned and the comparison says why it is unavailable.

Provenance: per month the granule id and the SHA-256 of the OPeNDAP answer; per response a `SourceManifest` whose checksum covers all months, the POWER payload checksum and the cell centre.

## Interpretation and limitations

- IMERG merges passive-microwave and infrared satellite estimates with GPCC monthly gauge analyses. It describes an 11 km cell, not a field, and smooths storms smaller than the cell.
- A low gauge weight means the cell relies mostly on satellites, which are weaker over snow, mountains and coasts.
- Neither IMERG nor POWER is a rain-gauge reading at the farm. A difference between them is a reason to look for a local measurement, not a finding about the crop.
- The comparison covers only the event year; anomalies against a reference period remain POWER-based (`CLIMATE_ANOMALIES.md`).

## Verification

- **Offline (CI):** `backend/tests/test_gpm.py`, 40 tests on synthetic answers in the observed CMR/DAS/ASCII shapes. They cover grid indices and the live-probe cell, hours per month, ASCII parsing, units, granule selection, rate→total, fill values, unpublished months, wrong cell, negative rate, one month failing, all months failing, 401/403, the redirect to the login page, the token sent only to GES DISC, read timeouts not retried and connection timeouts retried, the units check running in parallel and cached, the time budget, the cache, and the API with and without the POWER comparison.
- **Real smoke (`earthdata-smoke` workflow, 2026-11-15):** public Ebro point (41.65, −0.88), 2022. 12/12 months observed in cell (41.65, −0.85), 14 upstream requests, annual total 403.0 mm against POWER 320.1 mm over 12 compared months. Gauge weight 88–93 %.
- **Cross-check:** the June 2022 granule was downloaded whole (19 MB HDF5) and read with h5py. The rate (0.032 mm/hr), the cell centre and the units equal the OPeNDAP answer. Log in `docs/operations/E2E_AND_CONTRACTS.md`.

The values have not been interpreted agronomically. Scientific review (role B) of presenting the random error as ± and of the complete-month rule for POWER is pending.
