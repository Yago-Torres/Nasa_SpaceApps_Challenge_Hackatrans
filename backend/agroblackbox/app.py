from fastapi import FastAPI, HTTPException, Query
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from .schemas import contract_openapi_schemas
from .crop_catalog import CropCatalog, catalog
from .farm_profile import FarmProfile, FarmProfileAssessment, assess_profile
from .services.power import fetch_power
from .services.metrics import summarize_power
from .services.literature import LiteratureSearchResult, LiteratureSourceError, search_literature
from .services.rotations import rotation_examples
from .services.report import build_report

app=FastAPI(title='AGRO BLACK BOX API',version='0.1.0')


def versioned_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema.setdefault('components', {}).setdefault('schemas', {}).update(contract_openapi_schemas())
    schema['info']['x-agro-contract-version'] = '1.0'
    schema['info']['description'] = (
        'Existing /api routes are the development baseline. Components marked schema_version '
        '1.0 define the shared target contract; route migration is tracked separately.'
    )
    app.openapi_schema = schema
    return schema


app.openapi = versioned_openapi

@app.get('/api/health')
def health():return {'status':'ok','version':'0.1.0'}

@app.get('/api/climate')
async def climate(latitude:float=Query(ge=-90,le=90), longitude:float=Query(ge=-180,le=180),
                  event_year:int=Query(ge=1981,le=2025),
                  reference_start:int=Query(default=2010,ge=1981,le=2025),
                  reference_end:int=Query(default=2021,ge=1981,le=2025)):
    if reference_end < reference_start or reference_start <= event_year <= reference_end:
        raise HTTPException(422,detail='Reference years must be ordered and exclude event year.')
    if reference_end-reference_start+1<3:
        raise HTTPException(422,detail='At least 3 reference years required')
    parameter,sha,params=await fetch_power(latitude,longitude,event_year,reference_start,reference_end)
    try: monthly=summarize_power(parameter,event_year,reference_start,reference_end)
    except ValueError as e:raise HTTPException(502,detail=str(e)) from e
    return {'kind':'observation','dataset':'NASA POWER daily point',
            'source_url':'https://power.larc.nasa.gov/docs/services/api/temporal/daily/',
            'data_sha256':sha,'request_params':params,
            'event_year':event_year,'reference_start':reference_start,'reference_end':reference_end,
            'monthly':monthly,
            'disclaimer':'Gridded regional meteorology, not a field reading. Anomalies are descriptive and do not establish crop-failure causes. Short reference period.'}

@app.get('/api/literature', response_model=LiteratureSearchResult)
async def literature(query:str=Query(min_length=3,max_length=180)):
    try:
        return await search_literature(query)
    except LiteratureSourceError as e:
        # public_message never contains request URLs, API keys or contact data.
        raise HTTPException(status_code=502, detail=e.public_message) from e

@app.get('/api/rotations/demo')
def rotations():return {'rotations':rotation_examples()}

@app.get('/api/v1/crop-catalog', response_model=CropCatalog, tags=['farm profile (ABB-11)'])
def crop_catalog():
    """Crop identity catalogue (taxonomy only, pending review). Contains no agronomic parameters."""
    return catalog()

@app.post('/api/v1/farm-profiles/assess', response_model=FarmProfileAssessment, tags=['farm profile (ABB-11)'])
def assess_farm_profile(profile: FarmProfile):
    """Stateless consistency/completeness check of farmer-supplied soil, crops, calendar, constraints
    and priorities. Nothing is stored; no agronomic outcome is computed."""
    return assess_profile(profile)

class CaseReport(BaseModel):
    location_label:str=Field(max_length=160)
    climate:dict=Field(default_factory=dict)
    literature:list[dict]=Field(default_factory=list)
    rotations:list[dict]=Field(default_factory=list)

@app.post('/api/report')
def report(case:CaseReport):
    return {'filename':'agro-black-box-case-report.md','markdown':build_report(case.model_dump()),
            'status':'PRELIMINARY_NOT_PEER_REVIEWED'}
