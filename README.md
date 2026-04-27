# OpenDART Company Explorer

기업명을 자유롭게 입력해서 OpenDART의 아래 API를 한 번에 조회하는 로컬 웹앱입니다.

- `fnlttSinglAcnt.json`
- `fnlttMultiAcnt.json`
- `fnlttSinglIndx.json`

## 특징

- 기업명, 종목코드, 고유번호로 자유 검색
- `CORPCODE.xml` 기반 기업 매칭
- API 키는 브라우저가 아니라 서버에서만 사용
- `사업연도`, `보고서 코드`, `지표 분류` 선택 가능
- 결과를 탭별 표와 원본 JSON으로 확인 가능

## 실행 방법

```bash
cd /Users/hwanjinchoi/Documents/opendart-search-web
DART_API_KEY="YOUR_KEY" ./run_local.sh
```

브라우저에서 아래 주소를 열면 됩니다.

```text
http://127.0.0.1:8765
```

## 환경 변수

- `DART_API_KEY`: 필수
- `CORPCODE_XML`: 선택, 기본값 `/Users/hwanjinchoi/Downloads/CORPCODE.xml`
- `PORT`: 선택, 기본값 `8765`

## 엔드포인트

- `GET /api/health`
- `GET /api/companies?q=현대로템`
- `GET /api/company-data?query=현대로템&bsns_year=2025&reprt_code=11011`

## 메모

- 서버는 파이썬 표준 라이브러리만 사용합니다.
- 같은 요청은 서버 내부 캐시로 재사용합니다.

## Vercel 배포

이 프로젝트는 GitHub와 Vercel에서 아래 구조로 배포할 수 있게 준비되어 있습니다.

- `public/`: 정적 프론트엔드
- `app.py`: Flask 기반 서버리스 API
- `data/corp_codes.json`: 배포용 회사코드 데이터

### 1. 프로젝트 루트

이 폴더 자체를 GitHub 저장소 루트로 올리는 기준입니다.

```text
/Users/hwanjinchoi/Documents/opendart-search-web
```

이 기준으로 저장소를 만들면 Vercel의 `Root Directory`는 기본값(`/`) 그대로 두면 됩니다.
만약 더 큰 모노레포 안에 `opendart-search-web`을 하위 폴더로 넣는 경우에만 `Root Directory`를 `opendart-search-web`로 설정하면 됩니다.

### 2. 환경 변수

버셀 프로젝트 설정에서 아래 환경 변수를 추가합니다.

- `DART_API_KEY` = 발급받은 OpenDART 키

선택:

- `CORPCODE_JSON` = `/var/task/data/corp_codes.json`

기본값으로도 배포 번들 안의 `data/corp_codes.json`을 사용하므로 보통 추가 설정은 필요 없습니다.

### 3. 배포 방법

Vercel CLI:

```bash
cd /Users/hwanjinchoi/Documents/opendart-search-web
vercel
vercel --prod
```

또는 GitHub 저장소를 연결한 뒤 Import 하면 됩니다.

### 3-1. GitHub에 올리기

GitHub 웹에서 빈 저장소를 먼저 만든 뒤 아래 순서로 올리면 됩니다.

```bash
cd /Users/hwanjinchoi/Documents/opendart-search-web
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_ID/YOUR_REPO.git
git push -u origin main
```

`.env` 파일은 커밋하지 말고, API 키는 반드시 GitHub가 아니라 Vercel 환경 변수에만 넣어야 합니다.

### 3-2. GitHub에서 Vercel로 배포

1. Vercel Dashboard에서 `Add New Project`
2. 방금 올린 GitHub 저장소 선택
3. Root Directory는 기본값(`/`) 유지
4. Environment Variables에 `DART_API_KEY` 추가
5. Deploy 실행

### 4. 주의사항

- OpenDART API 키는 반드시 Vercel 환경 변수로 넣어야 합니다.
- `CORPCODE.xml`은 버셀 서버에 없으므로, 배포 시에는 포함된 `data/corp_codes.json`을 사용합니다.
- 복수 회사 조회는 회사 수가 많아질수록 응답 시간이 늘어날 수 있습니다.
