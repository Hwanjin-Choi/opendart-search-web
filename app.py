from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from flask import Flask, jsonify, redirect, request

from server import (
    DEFAULT_CORPCODE_XML,
    DEFAULT_IDX_CODES,
    MAX_MULTI_COMPANIES,
    REPORT_CODE_NAME,
    DartService,
    load_companies,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CORPCODE_JSON = BASE_DIR / "data" / "corp_codes.json"

app = Flask(__name__)


@app.get("/")
def home():
    return redirect("/index.html", code=307)


@lru_cache(maxsize=1)
def get_dart_service() -> DartService:
    api_key = os.environ.get("DART_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DART_API_KEY environment variable is required.")

    data_path = os.environ.get("CORPCODE_JSON", str(DEFAULT_CORPCODE_JSON)).strip()
    if not Path(data_path).exists():
        data_path = os.environ.get("CORPCODE_XML", DEFAULT_CORPCODE_XML).strip()

    companies = load_companies(data_path)
    return DartService(api_key=api_key, companies=companies)


def json_error(message: str, status: int = 400, **extra):
    payload = {"error": message, **extra}
    return jsonify(payload), status


@app.get("/api/health")
def health():
    service = get_dart_service()
    return jsonify(
        {
            "status": "ok",
            "companies_loaded": len(service.companies),
            "default_idx_codes": list(DEFAULT_IDX_CODES),
            "report_codes": REPORT_CODE_NAME,
        }
    )


@app.get("/api/companies")
def companies():
    service = get_dart_service()
    query = (request.args.get("q", "") or "").strip()
    limit = int((request.args.get("limit", "10") or "10").strip())

    if not query:
        return jsonify({"query": "", "matches": []})

    matches = service.search_companies(query, limit=max(1, min(limit, 20)))
    return jsonify({"query": query, "matches": matches})


@app.get("/api/company-data")
def company_data():
    service = get_dart_service()
    query = (request.args.get("query", "") or "").strip()
    corp_code = (request.args.get("corp_code", "") or "").strip()
    bsns_year = (request.args.get("bsns_year", "2025") or "2025").strip()
    reprt_code = (request.args.get("reprt_code", "11011") or "11011").strip()
    idx_param = (request.args.get("idx_cl_codes", ",".join(DEFAULT_IDX_CODES)) or "").strip()
    idx_cl_codes = tuple(code for code in [item.strip() for item in idx_param.split(",")] if code) or DEFAULT_IDX_CODES

    companies, resolutions, unresolved_inputs = service.resolve_companies(
        query=query or None,
        corp_codes=corp_code or None,
    )

    if len(companies) > MAX_MULTI_COMPANIES:
        return json_error(
            f"한 번에 조회할 수 있는 회사 수는 최대 {MAX_MULTI_COMPANIES}개입니다.",
            status=400,
            selected_count=len(companies),
            max_multi_companies=MAX_MULTI_COMPANIES,
        )

    if not companies:
        return json_error(
            "기업을 찾지 못했습니다. 기업명, 종목코드, 고유번호를 다시 확인해주세요.",
            status=404,
            query=query,
            corp_code=corp_code,
            resolutions=resolutions,
            unresolved_inputs=unresolved_inputs,
        )

    if unresolved_inputs:
        return json_error(
            f"일부 입력을 찾지 못했습니다: {', '.join(unresolved_inputs)}",
            status=404,
            query=query,
            corp_code=corp_code,
            selected_companies=[DartService._public_company(company) for company in companies],
            resolutions=resolutions,
            unresolved_inputs=unresolved_inputs,
        )

    try:
        responses = service.fetch_company_bundle(
            companies=companies,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
            idx_cl_codes=idx_cl_codes,
        )
    except RuntimeError as error:
        return json_error(str(error), status=502)

    payload = {
        "query": query,
        "request": {
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "report_name": REPORT_CODE_NAME.get(reprt_code, ""),
            "idx_cl_codes": list(idx_cl_codes),
        },
        "selected_company": DartService._public_company(companies[0]),
        "selected_companies": [DartService._public_company(company) for company in companies],
        "resolutions": resolutions,
        "responses": responses,
    }
    return jsonify(payload)
