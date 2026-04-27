from __future__ import annotations

import json
import os
import re
import sys
from functools import lru_cache
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen
from xml.etree import ElementTree as ET


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "public" if (BASE_DIR / "public").exists() else BASE_DIR / "static"
DEFAULT_CORPCODE_XML = "/Users/hwanjinchoi/Downloads/CORPCODE.xml"
DEFAULT_PORT = 8765
DEFAULT_IDX_CODES = ("M210000", "M220000", "M230000", "M240000")
MAX_MULTI_COMPANIES = 100
REPORT_CODE_NAME = {
    "11011": "사업보고서",
    "11012": "반기보고서",
    "11013": "1분기보고서",
    "11014": "3분기보고서",
}


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def split_multi_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,\n]+", value or "") if item.strip()]


def load_companies(xml_path: str) -> list[dict[str, str]]:
    path = Path(xml_path)
    if not path.exists():
        raise FileNotFoundError(f"CORPCODE.xml not found: {xml_path}")

    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as handle:
            companies = json.load(handle)
        for company in companies:
            company["normalized_name"] = normalize_text(company.get("corp_name", ""))
            company["normalized_eng_name"] = normalize_text(company.get("corp_eng_name", ""))
        return companies

    companies: list[dict[str, str]] = []
    tree = ET.parse(path)
    root = tree.getroot()

    for item in root.findall("./list"):
        corp_name = (item.findtext("corp_name") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_eng_name = (item.findtext("corp_eng_name") or "").strip()
        if not corp_name or not corp_code:
            continue

        companies.append(
            {
                "corp_name": corp_name,
                "corp_code": corp_code,
                "stock_code": stock_code,
                "corp_eng_name": corp_eng_name,
                "normalized_name": normalize_text(corp_name),
                "normalized_eng_name": normalize_text(corp_eng_name),
            }
        )

    return companies


def score_company(query: str, company: dict[str, str]) -> int:
    query_norm = normalize_text(query)
    if not query_norm:
        return 0

    corp_name = company["normalized_name"]
    eng_name = company["normalized_eng_name"]
    corp_code = company["corp_code"].lower()
    stock_code = company["stock_code"].lower()

    if query_norm == corp_name:
        return 100
    if query_norm == corp_code:
        return 99
    if query_norm == stock_code:
        return 98
    if corp_name.startswith(query_norm):
        return 92
    if query_norm in corp_name:
        return 85
    if stock_code.startswith(query_norm):
        return 83
    if eng_name.startswith(query_norm):
        return 75
    if query_norm in eng_name:
        return 70
    return 0


class DartService:
    def __init__(self, api_key: str, companies: list[dict[str, str]]):
        self.api_key = api_key
        self.companies = companies
        self.company_by_code = {company["corp_code"]: company for company in companies}

    def search_companies(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        scored = []
        for company in self.companies:
            score = score_company(query, company)
            if score <= 0:
                continue
            scored.append((score, company))

        scored.sort(
            key=lambda item: (
                -item[0],
                len(item[1]["corp_name"]),
                item[1]["corp_name"],
            )
        )

        return [self._public_company(company) for _, company in scored[:limit]]

    def resolve_company(self, corp_code: str | None, query: str | None) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
        if corp_code:
            company = self.company_by_code.get(corp_code)
            candidates = [self._public_company(company)] if company else []
            return company, candidates

        if not query:
            return None, []

        candidates = self.search_companies(query, limit=10)
        if not candidates:
            return None, []

        selected = self.company_by_code.get(candidates[0]["corp_code"])
        return selected, candidates

    def resolve_companies(
        self,
        query: str | None,
        corp_codes: str | None,
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[str]]:
        code_tokens = split_multi_values(corp_codes or "")
        query_tokens = split_multi_values(query or "")

        selected_companies: list[dict[str, str]] = []
        resolutions: list[dict[str, Any]] = []
        unresolved_inputs: list[str] = []
        seen_codes: set[str] = set()

        if code_tokens:
            for code in code_tokens:
                company = self.company_by_code.get(code)
                if company and company["corp_code"] not in seen_codes:
                    selected_companies.append(company)
                    seen_codes.add(company["corp_code"])
                elif not company:
                    unresolved_inputs.append(code)

        for token in query_tokens:
            candidates = self.search_companies(token, limit=5)
            selected = self.company_by_code.get(candidates[0]["corp_code"]) if candidates else None
            resolutions.append(
                {
                    "input": token,
                    "selected_company": self._public_company(selected),
                    "candidates": candidates,
                }
            )
            if not selected:
                unresolved_inputs.append(token)
                continue
            if selected["corp_code"] in seen_codes:
                continue
            selected_companies.append(selected)
            seen_codes.add(selected["corp_code"])

        return selected_companies, resolutions, unresolved_inputs

    def fetch_company_bundle(
        self,
        companies: list[dict[str, str]],
        bsns_year: str,
        reprt_code: str,
        idx_cl_codes: tuple[str, ...],
    ) -> dict[str, Any]:
        responses: dict[str, Any] = {
            "fnlttSinglAcnt": self.fetch_single_account_bundle(companies, bsns_year, reprt_code),
            "fnlttMultiAcnt": self.fetch_multi_account_bundle(companies, bsns_year, reprt_code),
            "fnlttSinglIndx": self.fetch_single_index_bundle(companies, bsns_year, reprt_code, idx_cl_codes),
        }
        return responses

    def fetch_single_account_bundle(
        self,
        companies: list[dict[str, str]],
        bsns_year: str,
        reprt_code: str,
    ) -> dict[str, Any]:
        company_results = []
        merged_rows = []
        statuses = []

        for company in companies:
            response = self.fetch_api(
                "fnlttSinglAcnt.json",
                {
                    "corp_code": company["corp_code"],
                    "bsns_year": bsns_year,
                    "reprt_code": reprt_code,
                },
            )
            company_results.append(
                {
                    "company": self._public_company(company),
                    "status": response.get("status", ""),
                    "message": response.get("message", ""),
                    "count": len(response.get("list", [])),
                }
            )
            merged_rows.extend(self._attach_company_metadata(response.get("list", []), company))
            statuses.append(response)

        status, message = self._merge_status(statuses)
        return {
            "status": status,
            "message": message,
            "company_count": len(companies),
            "companies": company_results,
            "list": merged_rows,
        }

    def fetch_multi_account_bundle(
        self,
        companies: list[dict[str, str]],
        bsns_year: str,
        reprt_code: str,
    ) -> dict[str, Any]:
        corp_codes = ",".join(company["corp_code"] for company in companies)
        response = self.fetch_api(
            "fnlttMultiAcnt.json",
            {
                "corp_code": corp_codes,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
            },
        )

        rows = []
        for item in response.get("list", []):
            company = self.company_by_code.get(item.get("corp_code", ""))
            rows.extend(self._attach_company_metadata([item], company))

        return {
            "status": response.get("status", ""),
            "message": response.get("message", ""),
            "company_count": len(companies),
            "companies": [self._public_company(company) for company in companies],
            "list": rows,
        }

    def fetch_single_index_bundle(
        self,
        companies: list[dict[str, str]],
        bsns_year: str,
        reprt_code: str,
        idx_cl_codes: tuple[str, ...],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}

        for idx_cl_code in idx_cl_codes:
            company_results = []
            merged_rows = []
            statuses = []
            for company in companies:
                response = self.fetch_api(
                    "fnlttSinglIndx.json",
                    {
                        "corp_code": company["corp_code"],
                        "bsns_year": bsns_year,
                        "reprt_code": reprt_code,
                        "idx_cl_code": idx_cl_code,
                    },
                )
                company_results.append(
                    {
                        "company": self._public_company(company),
                        "status": response.get("status", ""),
                        "message": response.get("message", ""),
                        "count": len(response.get("list", [])),
                    }
                )
                merged_rows.extend(self._attach_company_metadata(response.get("list", []), company))
                statuses.append(response)

            status, message = self._merge_status(statuses)
            result[idx_cl_code] = {
                "status": status,
                "message": message,
                "company_count": len(companies),
                "companies": company_results,
                "list": merged_rows,
            }

        return result

    @lru_cache(maxsize=256)
    def _cached_fetch(self, endpoint: str, params_key: tuple[tuple[str, str], ...]) -> dict[str, Any]:
        params = dict(params_key)
        params["crtfc_key"] = self.api_key
        query = urlencode(params)
        url = f"https://opendart.fss.or.kr/api/{endpoint}?{query}"

        try:
            with urlopen(url, timeout=20) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as error:
            raise RuntimeError(f"OpenDART HTTP error {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"OpenDART request failed: {error.reason}") from error

        try:
            return json.loads(payload)
        except json.JSONDecodeError as error:
            raise RuntimeError("OpenDART returned invalid JSON") from error

    def fetch_api(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        params_key = tuple(sorted(params.items()))
        return self._cached_fetch(endpoint, params_key)

    def _attach_company_metadata(
        self,
        rows: list[dict[str, Any]],
        fallback_company: dict[str, str] | None,
    ) -> list[dict[str, Any]]:
        attached = []
        for item in rows:
            company = self.company_by_code.get(item.get("corp_code", "")) or fallback_company
            enriched = dict(item)
            if company:
                enriched["corp_name"] = company["corp_name"]
                enriched["corp_eng_name"] = company["corp_eng_name"]
                enriched["stock_code"] = item.get("stock_code") or company["stock_code"]
            attached.append(enriched)
        return attached

    @staticmethod
    def _merge_status(responses: list[dict[str, Any]]) -> tuple[str, str]:
        statuses = [response.get("status", "") for response in responses]
        messages = [response.get("message", "") for response in responses]

        if not statuses:
            return "", ""
        if all(status == statuses[0] for status in statuses):
            return statuses[0], messages[0]
        return "MIXED", "복수 회사 조회 결과에 정상/오류 응답이 혼합되어 있습니다."

    @staticmethod
    def _public_company(company: dict[str, str] | None) -> dict[str, str]:
        if not company:
            return {}
        return {
            "corp_name": company["corp_name"],
            "corp_code": company["corp_code"],
            "stock_code": company["stock_code"],
            "corp_eng_name": company["corp_eng_name"],
        }


class DartRequestHandler(SimpleHTTPRequestHandler):
    dart_service: DartService

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.path = "/index.html"
            return super().do_GET()
        if parsed.path == "/api/health":
            return self.handle_health()
        if parsed.path == "/api/companies":
            return self.handle_company_search(parsed.query)
        if parsed.path == "/api/company-data":
            return self.handle_company_data(parsed.query)

        return super().do_GET()

    def handle_health(self) -> None:
        payload = {
            "status": "ok",
            "companies_loaded": len(self.dart_service.companies),
            "default_idx_codes": list(DEFAULT_IDX_CODES),
            "report_codes": REPORT_CODE_NAME,
        }
        self.send_json(payload)

    def handle_company_search(self, query_string: str) -> None:
        params = parse_qs(query_string)
        query = (params.get("q", [""])[0] or "").strip()
        limit = int((params.get("limit", ["10"])[0] or "10").strip())

        if not query:
            return self.send_json({"query": "", "matches": []})

        matches = self.dart_service.search_companies(query, limit=max(1, min(limit, 20)))
        self.send_json({"query": query, "matches": matches})

    def handle_company_data(self, query_string: str) -> None:
        params = parse_qs(query_string)
        query = (params.get("query", [""])[0] or "").strip()
        corp_code = (params.get("corp_code", [""])[0] or "").strip()
        bsns_year = (params.get("bsns_year", ["2025"])[0] or "2025").strip()
        reprt_code = (params.get("reprt_code", ["11011"])[0] or "11011").strip()
        idx_param = (params.get("idx_cl_codes", [",".join(DEFAULT_IDX_CODES)])[0] or "").strip()
        idx_cl_codes = tuple(code for code in [item.strip() for item in idx_param.split(",")] if code) or DEFAULT_IDX_CODES

        companies, resolutions, unresolved_inputs = self.dart_service.resolve_companies(
            query=query or None,
            corp_codes=corp_code or None,
        )

        if len(companies) > MAX_MULTI_COMPANIES:
            return self.send_json(
                {
                    "error": f"한 번에 조회할 수 있는 회사 수는 최대 {MAX_MULTI_COMPANIES}개입니다.",
                    "selected_count": len(companies),
                    "max_multi_companies": MAX_MULTI_COMPANIES,
                },
                status=HTTPStatus.BAD_REQUEST,
            )

        if not companies:
            return self.send_json(
                {
                    "error": "기업을 찾지 못했습니다. 기업명, 종목코드, 고유번호를 다시 확인해주세요.",
                    "query": query,
                    "corp_code": corp_code,
                    "resolutions": resolutions,
                    "unresolved_inputs": unresolved_inputs,
                },
                status=HTTPStatus.NOT_FOUND,
            )

        if unresolved_inputs:
            return self.send_json(
                {
                    "error": f"일부 입력을 찾지 못했습니다: {', '.join(unresolved_inputs)}",
                    "query": query,
                    "corp_code": corp_code,
                    "selected_companies": [DartService._public_company(company) for company in companies],
                    "resolutions": resolutions,
                    "unresolved_inputs": unresolved_inputs,
                },
                status=HTTPStatus.NOT_FOUND,
            )

        try:
            responses = self.dart_service.fetch_company_bundle(
                companies=companies,
                bsns_year=bsns_year,
                reprt_code=reprt_code,
                idx_cl_codes=idx_cl_codes,
            )
        except RuntimeError as error:
            return self.send_json({"error": str(error)}, status=HTTPStatus.BAD_GATEWAY)

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
        self.send_json(payload)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))


def main() -> None:
    api_key = os.environ.get("DART_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DART_API_KEY environment variable is required.")

    xml_path = os.environ.get("CORPCODE_XML", DEFAULT_CORPCODE_XML).strip()
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    companies = load_companies(xml_path)
    service = DartService(api_key=api_key, companies=companies)

    DartRequestHandler.dart_service = service
    server = ThreadingHTTPServer(("127.0.0.1", port), DartRequestHandler)

    print(f"OpenDART explorer running at http://127.0.0.1:{port}")
    print(f"Loaded {len(companies)} companies from {xml_path}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
