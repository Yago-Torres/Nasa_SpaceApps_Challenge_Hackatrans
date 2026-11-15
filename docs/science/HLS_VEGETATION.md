# HLS vegetation observations (ABB-12)

`GET /api/vegetation/hls?latitude&longitude&start&end` returns, for one location and at most 92 days, **every** NASA HLS v2.0 overpass with its cloud/QA result and, when the view is clear, the NDVI of a small pixel window. Code: `backend/agroblackbox/services/hls.py`, `services/geotiff.py`, `vegetation.py`; web: `frontend/src/features/vegetation/`.

## Source

| Item | Value |
|---|---|
| Products | `HLSL30` v2.0 (Landsat 8/9 OLI) and `HLSS30` v2.0 (Sentinel-2A/B/C MSI), NASA LP DAAC |
| Discovery | NASA CMR `granules.json`, `point=lon,lat`, `temporal=start,end` (public metadata, no credentials) |
| Data access | Cloud-Optimized GeoTIFFs on `data.lpdaac.earthdatacloud.nasa.gov`, HTTP range requests, `Authorization: Bearer $EARTHDATA_TOKEN` (Earthdata Login). LP DAAC redirects to a signed CloudFront URL; the token is not forwarded there. |
| Grid | MGRS tiles, 109.8 km, UTM/WGS 84, 30 m pixels (3660 × 3660), 256 × 256 Deflate tiles with horizontal predictor (observed in live files 2026-11-15) |
| Bands used | red `B04`; NIR `B05` (L30) / `B8A` (S30, narrow NIR matching OLI B05); QA `Fmask` |
| Scale | reflectance = DN × 0.0001; fill −9999; valid DN −100…16000 (HLS v2.0 User Guide) |
| Documentation | https://lpdaac.usgs.gov/products/hlsl30v002/, https://lpdaac.usgs.gov/products/hlss30v002/, HLS v2.0 User Guide |
| Licence | NASA EOSDIS data: open, no restriction on reuse; cite the product DOI pages above |

## Method

1. The location is projected to the tile's UTM zone (Krüger series; checked against pyproj to < 0.1 mm over 3000 random points) and the pixel that contains it is found from the GeoTIFF tie point and pixel size.
2. **Window:** the 3 × 3 pixels around it (about 90 m × 90 m), clipped to the raster. A field narrower than 90 m will be mixed with its surroundings.
3. **Fmask classes** (HLS v2.0 bits, in this priority): fill (255), cloud (bit 1), cloud shadow (bit 3), adjacent to cloud/shadow (bit 2), cirrus (bit 0), snow/ice (bit 4), water (bit 5), high aerosol (bits 6–7 = 3), otherwise clear.
4. Red and NIR are read only if more than half of the in-footprint window pixels are clear. A clear pixel whose red or NIR is fill or outside the valid range becomes `invalid_reflectance`.
5. **NDVI** = (NIR − red) / (NIR + red) per clear pixel. The acquisition is **VALID** when more than half of the in-footprint pixels have a valid NDVI; the median is reported with the window minimum and maximum and the median red and NIR reflectance.
6. **One result per overpass:** overlapping MGRS tiles of the same product, date and time are grouped; the first tile (by granule id) with data at the location is used.
7. **Statuses:** `VALID`, `OBSCURED` (clouds, shadow, snow, water, high aerosol or not enough clear pixels; also whole scenes whose CMR metadata says 100 % cloud, which are not read), `NO_DATA` (location outside every tile footprint) and `NOT_READ` (retrieval failed for that scene; others are still returned).
8. **Gaps:** every maximal date interval in the range without a VALID observation is returned with its length. Nothing is interpolated, smoothed or filled, and the chart does not join points.

Provenance per observation: granule id, MGRS tile, product/sensor, EPSG, pixel size, Fmask class counts and the SHA-256 over the SHA-256 of each compressed tile read. The response carries a `SourceManifest` whose checksum covers all observations.

## Interpretation and limitations

- NDVI is canopy greenness at 30 m. It is **not** soil health, yield, biomass or crop damage, and it cannot explain why vegetation changed. Low NDVI also happens on bare soil after harvest, in fallow fields and in early growth.
- Fmask misses some thin clouds and shadows and flags some clear pixels. A VALID observation can still be contaminated; a sudden drop on one date should be checked against neighbouring overpasses.
- HLS harmonises Landsat and Sentinel-2, but small differences remain. When the difference matters, compare dates from one product (the chart marks them differently).
- Scene cloud cover from CMR describes the whole scene, not the location.
- Recent dates: scenes appear a few days after acquisition.

## Verification

- **Offline (CI):** `backend/tests/test_hls.py`, 64 tests on synthetic GeoTIFFs and a fake NASA (reader layouts, predictor and byte order, malformed files, UTM, Fmask bits, NDVI ranges, window clipping, overlapping tiles, cloudy scenes, one failed scene, all failed, 401/403, no token, range request ignored, cache, token only sent to LP DAAC, API status codes and payload).
- **Reader cross-check (2026-11-15, GitHub Actions):** for four real HLSL30 scenes of tile 30TXM (two clear, one high-aerosol, one cloudy), the Fmask classes and the NDVI median computed by `geotiff.py` matched those computed with rasterio/GDAL from the full downloaded files exactly (4 decimals).
- **Real smoke (`earthdata-smoke` workflow, `RUN_REAL_SOURCES=1`):** public Ebro-valley point (41.65, −0.88), 2023-04-01 → 2023-06-30: 57 overpasses (HLSL30 + HLSS30, tile 30TXM), 30 VALID, 27 OBSCURED, 0 NOT_READ, 65 days without a valid observation (longest 12), NDVI medians 0.15–0.23, 237 upstream requests, about 30 s. Log in `docs/operations/E2E_AND_CONTRACTS.md`.

The point is a public grid location, not a farm, and the values have not been interpreted agronomically; scientific review of the clear rule (majority of a 3 × 3 window, high aerosol excluded) is pending (role B).
