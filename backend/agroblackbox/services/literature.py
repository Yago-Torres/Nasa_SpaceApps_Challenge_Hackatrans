"""OpenAlex scholarly metadata lookup; no automatic interpretation of full papers."""
import os
import httpx
from fastapi import HTTPException

async def query_literature(query:str):
    params={'search':query,'per_page':6}
    if os.getenv('OPENALEX_API_KEY'):
        params['api_key']=os.environ['OPENALEX_API_KEY']
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r=await client.get('https://api.openalex.org/works', params=params)
            r.raise_for_status()
            works=r.json().get('results',[])
    except (httpx.HTTPError,ValueError) as e:
        raise HTTPException(status_code=502,detail=f'OpenAlex source unavailable: {e}') from e
    return [{'title':w.get('title'),'year':w.get('publication_year'),'doi':w.get('doi'),
             'openalex_id':w.get('id'),'kind':'literature','source':'OpenAlex metadata',
             'caveat':'Bibliographic match only; paper findings need human verification.'}
            for w in works if w.get('title')]
