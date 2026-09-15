#Macro-Portfolio Cross-Analyzer

## 1. System Persona & Goal (작업 컨텍스트 문서)
- **에이전트 역할 및 목적:** 본 에이전트는 글로벌 매크로 경제 분석가이자 포트폴리오 관리자(TAA)의 역할을 수행합니다. 매일 수집되는 다양한 형태의 거시경제 리포트와 뉴스를 분석하고, 이를 사용자의 가족 자산 포트폴리오 DB(Supabase)와 교차 검증하여 4차원 정량 스코어(Direction, Horizon, Signal, Impact)를 산출한 뒤 최적의 투자 액션 플랜을 도출합니다.
- **배경 및 범위:** 파편화된 매크로 정보들을 사용자의 실제 자산 비중에 맞게 Re-aggregate(재집계)하여 개인화된 금융 인사이트를 자동화하는 것이 핵심입니다. 일일 분석 결과의 노션(Notion) 적재 및 시계열 리포팅을 위한 로컬 아카이빙까지 포함합니다.
- **주요 제약조건:** 
  - LLM의 환각(Hallucination)을 방지하기 위해 결정론적 데이터(DB조회, 파일 파싱, API 전송)는 반드시 커스텀 스크립트로 분리하여 실행합니다.
  - 임시 파일이나 중간 생성물은 반드시 `scratch/` 디렉토리 내에만 머물러야 하며, 프로젝트 루트를 오염시켜서는 안 됩니다.

## 2. Triggers & Data Flow (트리거 및 데이터 흐름)
- **Input (입력):** 
  - **트리거:** 사용자가 `input_staging/` 폴더에 당일 분석할 자료(`pdf`, `md`, `txt`)와 `links.txt`(URL 목록)를 넣은 후, 메인 에이전트에게 "오늘자 매크로 분석 시작해"라고 명령.
  - **포트폴리오 페이로드:** Supabase DB의 `holdings` 및 `asset_ratio` 테이블에서 조회된 최신 자산 스냅샷 (JSON).
- **Output (출력 및 임시 데이터):** 
  - **임시 데이터 (Temporary):** `scratch/parsed_report_YYYYMMDD.md`, `scratch/portfolio_snapshot_YYYYMMDD.json`
  - **최종 산출물 (Persistent):**
    1. 로컬 누적 데이터: `archive/YYYY-MM/YYYYMMDD_macro_analysis.md` 및 `.json`
    2. 노션 적재: Notion Master DB(3bcbad03-f76c-80c3-b81c-000b6bd3509a)의 당일 날짜 페이지 (Upsert)

## 3. Core Workflow (워크플로우 정의 및 로직 분리)

- **Step 1: Staging 데이터 일괄 파싱 및 정규화**
  - **역할 주체:** 커스텀 스크립트 (`parse_all_inputs.py/ts`) + 서브에이전트 (`browser_agent`)
  - **로직 설명:** `input_staging/`의 모든 파일을 스캔합니다. 로컬 파일(`pdf, md, txt`)은 텍스트로 추출하고, `links.txt`의 URL은 메인 에이전트가 `invoke_subagent`로 브라우저 에이전트를 호출하여 크롤링/파싱합니다. 추출된 모든 텍스트는 `scratch/parsed_report_YYYYMMDD.md`로 병합됩니다.
  - **성공 기준 및 예외 처리:** URL 접근 실패(크롤링 차단 등) 시 해당 건만 에러 로깅하고 파이프라인은 중단 없이(Skip & Continue) 다음 파일로 넘어갑니다.

- **Step 2: 포트폴리오 기준 데이터 스냅샷 조회**
  - **역할 주체:** 커스텀 스크립트 (`fetch_portfolio_supabase.py/ts`)
  - **로직 설명:** Supabase API를 호출하여 '자산군-세부자산군-세부자산군2' 체계로 분류된 현재 보유 현황 및 비중 데이터를 JSON 배열로 가져와 `scratch/portfolio_snapshot_YYYYMMDD.json`으로 저장합니다.
  - **성공 기준 및 예외 처리:** DB 연결 지연 및 타임아웃 발생 시 3회 재시도(Retry)하며, 최종 실패 시 Fallback 데이터(빈 배열 및 에러 상태코드)를 반환하여 에이전트가 매크로 단독 분석 모드로 전환되도록 유도합니다.

- **Step 3: 매크로 교차 분석 및 4차원 스코어링 (핵심 추론)**
  - **역할 주체:** 메인 에이전트 단독 수행
  - **로직 설명:** 메인 에이전트가 Step 1과 Step 2의 결과물(scratch 내 파일)을 읽고, 매크로 이슈를 3단계 자산분류에 매핑합니다. 이후 Direction, Horizon, Signal, Impact의 4차원 스코어를 산출하고, Weighted Impact 수식을 통해 당일 Re-aggregate 통합 재집계를 수행합니다. 또한 사용자의 실제 보유 ETF(`holdings`) 목록 및 평가손익/비중을 연계하여 구체적 매매 가이드, 신규 편입 추천 ETF(Part D), 취약 ETF 지목 및 시장 트리거 지표(Part E)를 도출합니다.
  - **성공 기준 및 예외 처리:** 반드시 정해진 4차원 스코어링 기준 내의 실수값(예: +1.0, -0.5)만 사용하도록 프롬프트로 강제하며, Part D/E는 유의미한 상위 3~5개 핵심 자산군 및 2~3개 핵심 리스크에 집중합니다.

- **Step 4: 로컬 아카이빙 (MD 및 JSON 생성)**
  - **역할 주체:** 메인 에이전트 (네이티브 파일 도구 활용)
  - **로직 설명:** Step 3의 분석 결과를 토대로 Part A ~ Part E 구조를 갖춘 마크다운 리포트와 정량적 수치 및 구조화된 액션/리스크 객체(JSON)를 생성하여 `archive/YYYY-MM/` 경로에 파일 쓰기(File Write)를 수행합니다.
  - **성공 기준 및 예외 처리:** 폴더가 없을 경우 에이전트가 직접 디렉토리를 생성한 후 파일을 저장합니다.

- **Step 5: 노션 Master DB 일일 갱신 (Upsert)**
  - **역할 주체:** 커스텀 스크립트 (`upsert_notion_daily.py/ts`)
  - **로직 설명:** 생성된 JSON/MD 데이터를 노션 API를 통해 전송합니다. Master DB에서 당일(YYYY-MM-DD) 날짜의 페이지가 존재하는지 쿼리하여, 존재하면 Update(내용 덮어쓰기), 없으면 Create(신규 생성)합니다.
  - **성공 기준 및 예외 처리:** Rate Limit(HTTP 429) 발생 시 지수 백오프(Exponential Backoff)로 대기 후 재시도하여 데이터 누락 및 중복 페이지 생성을 원천 차단합니다.

## 4. Implementation Spec (구조 및 역할 정의)

### 4.1. Directory Structure
    /project-root
      ├── AGENTS.md                          # 에이전트 글로벌 페르소나 및 핵심 룰 (4차원 스코어링 공식 등)
      ├── /.agents
      │   └── /skills/macro_portfolio_analysis
      │       ├── SKILL.md                   # 메인 워크플로우 (Step 1~5) 지침서
      │       └── /references                # 3단계 자산 체계 등 정적 참조 문서
      ├── src/
      │   └── scripts/
      │       ├── parse_all_inputs.ts        # 문서 통합 파싱 스크립트
      │       ├── fetch_portfolio.ts         # Supabase 조회 스크립트
      │       └── upsert_notion.ts           # Notion API Upsert 스크립트
      ├── input_staging/                     # [Dropzone] 일일 분석용 원본 파일 적재 폴더
      ├── scratch/                           # [Temp] 파싱 마크다운 및 DB 스냅샷 JSON 임시 저장
      └── archive/                           # [Persistent] 주간/월간 리포팅을 위한 시계열 산출물 누적 폴더

### 4.2. Agent Architecture
- **에이전트 오케스트레이션:** 메인 에이전트가 `macro_portfolio_analysis` 스킬을 장착하고 프로세스의 시작부터 끝까지 지휘(Orchestrate)합니다. 
- **서브에이전트 상세:**
  - **[browser_agent]:** 
    - 역할: `input_staging/links.txt`에 포함된 웹사이트 URL에 접근하여 방어 로직을 우회하고 순수 텍스트를 크롤링하여 반환.
    - 트리거 조건: `input_staging/` 내에 처리해야 할 URL이 존재할 때 메인 에이전트가 `invoke_subagent` 도구로 호출.

### 4.3. Skills & Scripts
- **[macro_portfolio_analysis]:** 사용자의 "분석 시작" 트리거 시 활성화되며, Step 1~5의 작업 순서를 에이전트에게 강제하는 핵심 스킬(프롬프트 템플릿)입니다. 출력 서식(Part a ~ Part e)이 정의되어 있습니다.

## 5. Tools, Integrations & DB (필요 도구 연동)
- **Supabase 연동:** PostgreSQL REST API 또는 Supabase 공식 클라이언트 라이브러리 사용. (`holdings`, `asset_ratio` 테이블 접근 권한 필요)
- **Notion API:** `@notionhq/client`를 활용한 DB Query 및 Page Create/Update 엔드포인트 연동.
- **문서 파싱 라이브러리:** `pdf-parse` (PDF 처리용), `mammoth` (DOCX 처리용), HWPX 처리를 위한 호환 라이브러리(또는 파이썬 기반 `pyhwpx` 래퍼) 구성 필요.

## 6. Edge Cases, State & Error Handling
- **상태 관리 (State/Memory):** 에이전트는 세션 중 `scratch/` 디렉토리에 저장된 `parsed_report`와 `portfolio_snapshot`을 메모리 컨텍스트로 유지하여 교차 분석의 일관성을 유지합니다. 매 분석이 끝나면 `scratch/` 내부의 파일들은 다음 날 분석 시 덮어쓰기 되도록 설계합니다.
- **데이터 누락 처리 (Default Rule):** 
  - 특정 리포트에서 Direction_Score를 명확히 도출할 수 없는 모호한 내용일 경우, 강제로 '0.0 (중립)'을 적용하여 과대 해석(Hallucination)을 방지합니다.
  - JSON 생성 시 마크다운 이스케이프 문자가 깨져 스크립트가 파싱하지 못하는 오류를 방지하기 위해, 에이전트는 파일 작성 도구 사용 시 순수 JSON 포맷(Strict JSON)으로만 출력하도록 제약합니다.