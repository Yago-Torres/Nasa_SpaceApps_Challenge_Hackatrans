from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from .schemas import contract_openapi_schemas
from .crop_catalog import CropCatalog, catalog
from .farm_profile import FarmProfile, FarmProfileAssessment, assess_profile
from .climate import router as climate_router
from .services import literature as literature_service
from .services.literature import LiteratureSearchResult, LiteratureSourceError
from .services.rotations import rotation_examples
from .services.report import build_report
from .rotation_api import router as rotation_router
from .api import include_api_v1
from . import observability, upstream_monitoring  # noqa: F401  (installs external-source monitoring)

observability.configure_logging()

app=FastAPI(title='CropStory API',version='0.1.0')
app.middleware('http')(observability.request_middleware)  # ABB-30: request id, JSON logs, counters
app.include_router(rotation_router)
include_api_v1(app)  # ABB-05/ABB-06: auth + cases; 503 when DATABASE_URL is not configured


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
def health():
    """Liveness: the process answers. Does not touch the database (see /api/ready)."""
    return {'status':'ok','version':observability.app_version()}


@app.get('/api/ready', tags=['operations (ABB-30)'])
def ready():
    """Readiness: PostgreSQL reachable and migrated to this build's head. 503 otherwise; never returns
    connection details."""
    ok, checks = observability.readiness()
    body = {'status': 'ready' if ok else 'not_ready', 'version': observability.app_version(), 'checks': checks}
    return JSONResponse(status_code=200 if ok else 503, content=body)


@app.get('/api/metrics', tags=['operations (ABB-30)'], include_in_schema=False)
def metrics(request: Request):
    """Prometheus metrics, only with METRICS_TOKEN set (16+ characters) and `Authorization: Bearer <token>`."""
    allowed = observability.metrics_allowed(request)
    if allowed is None:
        raise HTTPException(status_code=404, detail='Not Found')
    if not allowed:
        raise HTTPException(status_code=401, detail='Metrics token required.')
    return PlainTextResponse(observability.metrics_text(), media_type='text/plain; version=0.0.4')

# GET /api/climate (NASA POWER provenance + anomaly QC, ABB-07/ABB-08)
app.include_router(climate_router)

@app.get('/api/literature', response_model=LiteratureSearchResult)
async def literature(query:str=Query(min_length=3,max_length=180)):
    try:
        return await literature_service.search_literature(query)  # module lookup: monitored (ABB-30)
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
