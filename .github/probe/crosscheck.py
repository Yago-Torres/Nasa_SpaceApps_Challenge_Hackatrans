"""TEMPORARY (ABB-12 verification): compare CropStory's pure-Python HLS reader with rasterio/GDAL."""
import asyncio, os, statistics, subprocess, sys
import numpy as np, rasterio
from rasterio.warp import transform
from agroblackbox.services import hls

LAT, LON = 41.65, -0.88
TOKEN = os.environ['EARTHDATA_TOKEN']

async def main():
    import httpx
    from datetime import date
    async with hls._make_client() as client:
        http = hls._Http(client, TOKEN)
        granules = []
        for product in hls.PRODUCTS:
            granules += [hls._granule_from_dict(g) for g in
                         await hls._search(http, product, LAT, LON, date(2023, 5, 15), date(2023, 6, 15))]
        checked = 0
        for g in granules:
            ours = await hls._read_scene(http, g, LAT, LON)
            if ours.status not in ('VALID', 'OBSCURED') or ours.window_pixels == 0:
                continue
            spec = hls.PRODUCTS[g.product]
            files = {}
            for band in ('Fmask', spec['red'], spec['nir']):
                path = f'/tmp/{g.granule_id}.{band}.tif'
                if not os.path.exists(path):
                    subprocess.run(['curl', '-s', '-L', '-o', path, '-H', f'Authorization: Bearer {TOKEN}',
                                    g.assets[band]], check=True)
                files[band] = path
            with rasterio.open(files['Fmask']) as ds:
                xs, ys = transform('EPSG:4326', ds.crs, [LON], [LAT])
                row, col = ds.index(xs[0], ys[0])
                win = ((row - 1, row + 2), (col - 1, col + 2))
                fm = ds.read(1, window=win)
                print(g.granule_id, 'crs', ds.crs, 'pixel', col, row, 'gdal nodata', ds.nodata)
            with rasterio.open(files[spec['red']]) as ds:
                red = ds.read(1, window=win).astype(int)
            with rasterio.open(files[spec['nir']]) as ds:
                nir = ds.read(1, window=win).astype(int)
            counts = {k: 0 for k in hls.CLASSES}
            ndvis = []
            for f, r, n in zip(fm.ravel(), red.ravel(), nir.ravel()):
                c = hls.classify_fmask(int(f))
                if c == 'clear':
                    v = hls.ndvi_of(int(r), int(n))
                    if v is None:
                        c = 'invalid_reflectance'
                    else:
                        ndvis.append(v)
                counts[c] += 1
            ref_ndvi = round(statistics.median(ndvis), 4) if ndvis else None
            print('  ours  :', ours.status, ours.ndvi, {k: v for k, v in ours.pixels.items() if v})
            print('  gdal  :', ref_ndvi, {k: v for k, v in counts.items() if v}, 'fmask', fm.ravel().tolist())
            assert counts == ours.pixels, 'Fmask classes differ'
            if ours.status == 'VALID':
                assert ref_ndvi == ours.ndvi, 'NDVI differs'
            checked += 1
            if checked >= 4:
                break
        assert checked >= 2
        print('CROSSCHECK OK on', checked, 'scenes')

asyncio.run(main())
