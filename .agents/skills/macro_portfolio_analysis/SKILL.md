---
name: macro-portfolio-analysis
description: "Macro-Portfolio Cross-Quantification Engine: 일일 매크로 리포트와 포트폴리오를 대조하여 4차원 스코어링, 퀀트 엔진 연산, DB 적재 및 Notion 업로드 수행"
---

# Macro-Portfolio Cross-Quantification Engine 워크플로우

당신은 글로벌 매크로 경제 분석가이자 TAA(Tactical Asset Allocation) 퀀트 포트폴리오 관리자입니다.
당신의 임무는 `input_staging/`에 수집된 거시경제 리포트와 Supabase의 실제 포트폴리오 스냅샷을 대조하여, **1) LLM 직교 파라미터 추출**, **2) 결정론적 퀀트 연산 엔진 구동**, **3) 정성적 TAA 리밸런싱 액션 플랜 합성**, **4) Supabase 시계열 테이블 UPSERT 적재**, 그리고 **5) Notion 자동 업로드**를 일자별로 완결하는 것입니다.

세부 스코어링 공식 및 페르소나 원칙은 [AGENTS.md](file:///c:/Users/maeng-gun/Desktop/python/macro_analyzer/macro_analyzer/AGENTS.md)를 준수하세요.

---

## 1. 분석 대상 일자 식별 원칙

* **분석의 기본 단위는 '일자(Date, YYYY-MM-DD)'입니다.**
* **사용자 지시어 해석**:
  * "오늘자 매크로 분석 시작해" -> 오늘 시스템 날짜 1일 처리
  * "2026-09-18 분석해줘" -> 특정 날짜 1일 처리
  * "8월 31일부터 9월 11일까지 분석해줘" -> 해당 기간 내 `input_staging/`에 존재하는 날짜들을 시간순(오름차순)으로 정렬하여 1일씩 순차 반복
  * 날짜 미지정 시 -> `input_staging/` 내 파일명(`YYYY-MM-DD_*.md`)에서 고유한 모든 날짜를 추출하여 과거부터 최신순으로 일자별 순차 반복

---

## 2. 일자별 5단계 파이프라인 (Step 1 ~ 5)

각 대상 일자(`target_date`: `YYYY-MM-DD`, 컴팩트: `YYYYMMDD`)에 대해 다음 단계를 엄격히 순서대로 완결합니다.

### Step 1: 데이터 Ingestion 및 스냅샷 확보
1. **PDF 변환 (필요 시)**:
   `input_staging/`에 해당 일자 PDF(`*{target_date}*.pdf`)가 존재할 경우 먼저 마크다운으로 변환합니다:
   ```bash
   .\.venv\Scripts\python.exe .agents/skills/macro_portfolio_analysis/scripts/convert_pdf_inputs.py --date <YYYY-MM-DD>
   ```
2. **포트폴리오 스냅샷 수집 및 만료 파일 정리**:
   ```bash
   .\.venv\Scripts\python.exe .agents/skills/macro_portfolio_analysis/scripts/fetch_portfolio.py --date <YYYYMMDD>
   ```
   * 이 스크립트는 분석 대상 일자(`target_date`)를 기준으로 Supabase `return` 테이블에서 대상 일자 이전(`<= target_date`) 중 가장 최신 기준일(`basis_date`)을 동적으로 탐색합니다.
   * `세부자산군`과 `세부자산군2`가 모두 존재하는 18개 리프 노드 행의 평가금액을 합산하여, 해당 과거 시점의 실제 8대 매크로 자산군 비중(%)을 정밀 산출합니다.
   * 15일이 경과한 `scratch/` 및 `archive/` 파일을 자동으로 정리하고, `basis_date` 메타데이터가 포함된 `scratch/portfolio_snapshot_{YYYYMMDD}.json`을 생성합니다.
3. **입력 텍스트 확보**:
   * 에이전트가 `input_staging/` 내 해당 일자의 모든 마크다운 파일(예: `{target_date}_wsj.md`, `{target_date}_insight.md` 등)을 직접 읽어 분석 컨텍스트로 결합합니다.

### Step 2: 거시경제 토픽 도출 및 직교 파라미터 매핑 (LLM 추론)
1. **경제학적/금융이론적 명제 중심 토픽 도출**:
   * 개별 기사나 리포트 단위가 아닌, **거시경제적 인과관계 및 금융이론적 명제** 단위로 토픽을 도출합니다.
   * 하나의 리포트/글 안에서도 독립된 경제적 메커니즘(예: 통화정책 피벗, 원자재 공급 충격)이 있으면 복수 토픽으로 분리합니다.
   * 반대로 여러 기사/리포트에서 동일한 현상을 다루고 있다면 하나의 통합 토픽으로 묶어냅니다.
   * 당일 핵심 매크로 토픽은 통상 **2~5개** 수준으로 엄선합니다.
2. **토픽 네이밍 컨벤션**:
   * `[경제학적 이론/명제 중심] 간결형`으로 명명합니다. (예: `기간프리미엄(Term Premium) 재평가와 글로벌 장기금리 상승`, `파생상품 만기 및 기관 리밸런싱에 따른 유동성 수급 충격`)
3. 각 토픽에 대해 [asset_universe.json](file:///c:/Users/maeng-gun/Desktop/python/macro_analyzer/macro_analyzer/.agents/skills/macro_portfolio_analysis/references/asset_universe.json)의 **8대 매크로 자산군**(`귀금속`, `원자재`, `인컴자산`, `국내주식`, `해외주식`, `국내채권`, `해외채권`, `만기보유채권 및 현금성`) 중 **직접적 관련이 있는 자산군**만 선별하여 매핑합니다.
4. 관련 자산군에 대해 실질적 파급력이 있는 **Horizon(1: 단기 0~3개월, 2: 중기 3개월~1년, 3: 장기 1년 이상)**을 선택하고 4차원 파라미터를 도출합니다:
   * **Direction**: `[-1, 0, 1]` (-1: 하락, 0: 중립/불확실, 1: 상승)
   * **Impact**: `[0.0 ~ 1.0]` (0.1 단위, 선반영된 기지의 뉴스는 감쇄)
   * **Signal**: `[0.0 ~ 1.0]` (0.1 단위, 하드 데이터 및 확실성)
   * **Rationale**: 판단 근거 1~2문장
5. **주의 (수학 연산 배제)**: Topic Shock, Weighted Impact, 평균값 등의 계산을 LLM이 직접 계산하지 말고, 순수 추출 JSON 데이터를 `scratch/extracted_shocks_{YYYYMMDD}.json`에 저장합니다:
   ```json
   {
     "date": "YYYY-MM-DD",
     "topics": [
       {
         "topic_id": "us_term_premium_and_rate_rise",
         "topic_title": "기간프리미엄(Term Premium) 재평가와 글로벌 장기금리 상승",
         "summary": "핵심 내용 5~10문장 심층 요약...",
         "shocks": [
           {
             "asset_class": "해외주식",
             "horizon": 1,
             "direction": 1,
             "impact": 0.7,
             "signal": 0.8,
             "rationale": "단기 유동성 공급 기대감으로 주식 시장 상승 모멘텀"
           }
         ]
       }
     ]
   }
   ```

### Step 3: 결정론적 퀀트 연산 엔진 실행 (Python Engine)
파이썬 퀀트 엔진을 구동하여 부동소수점 오차 없는 신뢰도 가중평균과 Total WI를 계산합니다:
```bash
.\.venv\Scripts\python.exe .agents/skills/macro_portfolio_analysis/scripts/calculate_metrics.py --shocks scratch/extracted_shocks_{YYYYMMDD}.json --portfolio scratch/portfolio_snapshot_{YYYYMMDD}.json --output scratch/calculated_metrics_{YYYYMMDD}.json
```
* **결측치(NULL) 분리 연산**: 당일 리포트에 직접 매핑된 충격이 없는 자산군(`shock_count == 0`)은 `asset_macro_score = None (NULL)`로 설정되고, `total_wi = 0.0`으로 처리되어 포트폴리오 스코어 왜곡 없이 자산별 결측치(Unobserved)가 명확히 분리됩니다.
* 연산 완료 후 `scratch/calculated_metrics_{YYYYMMDD}.json` 파일 내용을 읽어 확정 수치 테이블을 확보합니다.

### Step 4: 정성적 액션 플랜 합성 및 리포트 작성 (LLM 합성)
`calculated_metrics`의 확정 수치와 `portfolio_snapshot`의 `holdings` 목록을 결합하여 완성도 높은 마크다운 리포트를 작성합니다.
*(세부 작성 표준 및 모범 예시는 [gold_standard_report_example.md](file:///c:/Users/maeng-gun/Desktop/python/macro_analyzer/macro_analyzer/.agents/skills/macro_portfolio_analysis/examples/gold_standard_report_example.md)를 준수하세요.)*

* **본문 헤더 규칙**: 노션 페이지 제목과 중복되는 최상단 `# Daily Macro-Portfolio Analysis...` 같은 헤더는 생략하고, 바로 `## Part A: 당일 핵심 거시경제 이슈 요약`부터 시작합니다.
* **Part A (당일 핵심 거시경제 이슈 요약)**:
  * **토픽 제목**: `### N. [경제학적 이론/명제 중심 간결형 제목] (topic_id)`
  * **핵심 내용**: 토픽당 **5~10문장** 분량의 심층 요약 (해당 요약만 읽어도 리포트의 핵심 논지와 구체적 데이터/근거를 완전히 이해할 수 있도록 구성).
  * **시간축 해석**: 시계별(`[단기 H=1]`, `[중기 H=2]`, `[장기 H=3]`) 하위 불릿으로 구분하여 영향이 있는 Horizon에 대해 **`[매크로 변수 변동 → 전이 경로 및 메커니즘 → 수혜/피해 자산군 영향]`** 인과관계를 구체적으로 명시.
* **Part B (Horizon별 스코어링 테이블 및 심층 해설)**:
  * **0점 자산 필터링**: 각 시계별 테이블에서 `Asset Score = 0`인 자산군 행을 완전히 제외하고 실제 충격/스코어가 있는 자산군만 표시.
  * **미충격 시계 처리**: 특정 시계(H=N)에 충격 자산이 전무(0건)한 경우, 빈 표 대신 `> 해당 시계(H=N)는 직접적인 매크로 충격이 식별되지 않아 중립(0.000)입니다.` 안내 문구로 대체.
  * **종합스코어 심층 콜아웃**: 각 테이블 직하단에 콜아웃 블록 배치:
    ```markdown
    > **단기 포트폴리오 종합 스코어 (H=1): [수치]**
    > [2~5문장 분량의 심층 해석: 주도 자산군 기여도, 포트폴리오 영향 강도 및 방향성 서술]
    ```
* **Part C (일별 종합 분석 및 자산군 순위)**:
  * **종합 진단**: **3~5문장**으로 시계별(H=1~3) 종합 스코어 궤적(Dynamic Trajectory), 충격의 본질(단기 유동성 노이즈 vs 중장기 펀더멘털 패러다임), 포트폴리오의 순 노출(Net Exposure) 및 방어력/공격력 구조를 유기적으로 심층 진단.
  * **핵심 영향 자산군 분석**: Total WI 절대값 상위 자산군별로 비중과 기여도, 시장 파급 효과를 불릿으로 상세 해설.
* **Part D (액션 플랜 - TAA 리밸런싱 가이드)**:
  * 영향도 상위 3~5개 자산군 비중 조절 방향(확대/축소/유지)
  * **보유 ETF 조절 가이드**: 실제 `holdings`의 수익률/비중과 매크로 부합도를 고려한 구체적 실행 액션(차익실현, 추가매수, 비중축소, 관망)
  * **신규 추천 상품**: 기존 보유 종목으로 커버되지 않는 매크로 기회를 위한 유망 ETF 제안
* **Part E (리스크 모니터링)**:
  * 핵심 거시 리스크 2~3개 도출
  * 가장 타격이 클 수 있는 실제 보유 ETF 명시
  * 방어/헤지 액션을 촉발할 정량적 시장 트리거 지표 명시
* **임시 아카이브 저장**:
  리포트를 `archive/{YYYY-MM}/{YYYYMMDD}_macro_analysis.md`에 저장합니다. (오류 복구용 15일 임시 보관, `.json`은 생성하지 않음)

### Step 5: Supabase 시계열 적재 및 Notion 자동 업로드
1. **Supabase 시계열 테이블 UPSERT 적재**:
   ```bash
   .\.venv\Scripts\python.exe .agents/skills/macro_portfolio_analysis/scripts/load_to_supabase.py --metrics scratch/calculated_metrics_{YYYYMMDD}.json --clean
   ```
   * `--clean` 플래그는 당일 재분석 시 기존 데이터를 깔끔하게 삭제 후 재적재하여 데이터 정합성을 유지합니다.
   * `macro_topic_shocks`, `macro_daily_asset_scores`, `macro_daily_portfolio_scores` 3개 테이블에 적재되며, 미언급 자산은 `asset_macro_score = NULL, shock_count = 0`으로 분리 적재됩니다.
2. **Notion 자동 업로드 및 기존 페이지 멱등 정리**:
   * 작성한 마크다운 리포트 본문을 `scratch/notion_upload_temp.md`로 저장합니다.
   * 메타데이터를 `scratch/notion_upload_meta.json`으로 저장합니다:
     * **제목 생성 규칙**: 날짜는 노션 DB의 `날짜` 속성에 매핑되므로 제목에는 날짜를 넣지 않고, **당일 핵심 키워드/이슈들을 나열**하여 작성합니다. (예: `"9월말 단기수급 변동성, 글로벌 장기금리 상방압력, 우주 AI 데이터센터 등"`)
     ```json
     {
       "title": "당일 핵심 이슈 키워드 나열 (예: 9월말 단기수급 변동성, 글로벌 장기금리 상방압력 등)",
       "icon": "📊",
       "status": "미처리",
       "category": "AI생성",
       "date": "YYYY-MM-DD",
       "topic_page_id": "3e1bad03-f76c-8089-b890-f93c69807e21"
     }
     ```
   * **기존 동일 날짜 리포트 정리 (중복 방지)**:
     재분석 등으로 같은 날짜의 리포트가 재생성된 경우 기존 Notion 페이지를 찾아 아카이브(휴지통 이동)합니다:
     ```bash
     .\.venv\Scripts\python.exe .agents/skills/macro_portfolio_analysis/scripts/delete_notion_page.py --date <YYYY-MM-DD>
     ```
   * **신규 리포트 본문 업로드**:
     ```bash
     .\.venv\Scripts\python.exe C:/Users/maeng-gun/.gemini/config/skills/notion-uploader/scripts/upload_to_notion.py
     ```
   * 생성된 Notion 페이지 URL을 확인합니다.

---

## 3. 결과 보고 (Handoff)

모든 일자의 파이프라인 처리가 완료되면 사용자에게 다음 사항을 깔끔하게 요약 보고합니다:
1. 처리 완료된 일자 목록
2. 일자별 핵심 포트폴리오 종합 스코어 및 주요 리밸런싱 권고 방향
3. Supabase 적재 완료 현황
4. 생성된 Notion 페이지 링크
