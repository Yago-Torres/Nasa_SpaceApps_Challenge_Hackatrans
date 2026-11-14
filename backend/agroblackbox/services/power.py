"""NASA POWER daily point adapter with on-disk TTL cache and traceability."""
import hashlib
import json
import time
from pathlib import Path
import httpx
from fastapi import HTTPException

BASE='https://power.larc.nasa.gov/api/temporal/daily/point'
CACHE=Path(__file__).resolve().parents[2]/'.cache'/'power'

async def fetch_power(latitude:float, longitude:float, event_year:int, ref_start:int, ref_end:int):
    params={
      'latitude': latitude, 'longitude':longitude,
      'parameters':'PRECTOTCORR,T2M_MAX', 'community':'AG',
      'start': f'{min(event_year,ref_start):04d}0101',
      'end': f'{max(event_year,ref_end):04d}1231',
      'time-standard':'UTC', 'format':'JSON'
    }
    key=hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
    path=CACHE/f'{key}.json'
    if path.exists() and time.time()-path.stat().st_mtime < 86400:
        raw=path.read_bytes()
    else:
        try:
            async with httpx.AsyncClient(timeout=55,follow_redirects=True) as client:
                response=await client.get(BASE,params=params)
                response.raise_for_status()
                raw=response.content
            record=json.loads(raw)
            if 'properties' not in record or 'parameter' not in record['properties']:
                raise ValueError('Unexpected NASA POWER response')
            CACHE.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=502,detail=f'NASA POWER source unavailable/invalid: {e}') from e
    try:
        record=json.loads(raw)
        parameter=record['properties']['parameter']
    except (KeyError,ValueError) as e:
        raise HTTPException(status_code=502,detail=f'Invalid cached POWER data: {e}') from e
    return parameter, hashlib.sha256(raw).hexdigest(), params
